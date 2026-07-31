"""Runtime — the engine's tick loop.

Each tick:
1. Check triggers — did a card complete that should start a workflow?
2. Check nodes — are any nodes ready to dispatch (deps met, condition passes)?
3. Check completions — did a dispatched node's card complete? Validate output, resolve variables.
4. Advance — resolve downstream node inputs from completed outputs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from enum import Enum
import fcntl
import json
import time
import sqlite3
import logging
import threading
import uuid

from .model import Workflow, Node, resolve_template, evaluate_condition
from .store import TemplateStore
from .kanban_adapter import (
    create_card,
    get_card,
    get_card_metadata,
    find_cards_by_idempotency_key,
    find_recent_completions,
    validate_output,
    board_db_path,
)

log = logging.getLogger(__name__)

STATE_DB = Path.home() / ".hermes-teams/startup/kanban/workflow-state.db"
LOCK_FILE = Path.home() / ".hermes-teams/startup/kanban/workflow-engine.lock"
TRIGGER_LOOKBACK_SECS = 3600  # 1 hour


class NodeStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DONE = "done"
    FAILED = "failed"


@dataclass
class NodeState:
    """Runtime state of a node within a workflow instance."""
    instance_id: str
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    card_id: str | None = None
    output: dict = field(default_factory=dict)  # resolved output values


@dataclass
class WorkflowInstance:
    """A running instance of a workflow."""
    instance_id: str
    workflow_id: str
    board: str
    project_dir: str
    trigger_context: dict = field(default_factory=dict)
    node_states: dict[str, NodeState] = field(default_factory=dict)
    parent_instance_id: str | None = None
    created_at: int = 0
    completed_at: int | None = None  # set when instance first completed (zombie detection)
    node_ids: list[str] = field(default_factory=list)  # valid node IDs at creation time

    def context(self) -> dict:
        """Build the variable context for template resolution."""
        ctx = {}
        for k, v in self.trigger_context.items():
            ctx[f"trigger.{k}"] = v
        for node_id, state in self.node_states.items():
            for k, v in state.output.items():
                ctx[f"nodes.{node_id}.output.{k}"] = v
        return ctx


def _db_connect(db_path: Path) -> sqlite3.Connection:
    """Connect with WAL mode and busy timeout for concurrent access."""
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.OperationalError:
        pass  # Read-only or locked — best effort
    return conn


class StateDB:
    """SQLite-backed workflow state (cache — kanban DB is ground truth)."""

    def __init__(self, db_path: Path = STATE_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        conn = _db_connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_instances (
                instance_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                board TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                trigger_context TEXT NOT NULL DEFAULT '{}',
                parent_instance_id TEXT,
                created_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                completed_at INTEGER,
                node_ids TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS node_states (
                instance_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                card_id TEXT,
                output TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (instance_id, node_id),
                FOREIGN KEY (instance_id) REFERENCES workflow_instances(instance_id)
            );

            CREATE TABLE IF NOT EXISTS trigger_watermark (
                board TEXT PRIMARY KEY,
                last_ts INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS trigger_keys (
                key TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL
            );
        """)
        # Add columns to pre-existing DBs that predate them (migration)
        self._migrate_columns(conn)
        conn.commit()
        conn.close()

    def _migrate_columns(self, conn: sqlite3.Connection):
        """Add columns that may be missing in DBs created before the column existed."""
        for col, ddl in [
            ("completed_at", "ALTER TABLE workflow_instances ADD COLUMN completed_at INTEGER"),
            ("node_ids", "ALTER TABLE workflow_instances ADD COLUMN node_ids TEXT NOT NULL DEFAULT '[]'"),
        ]:
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
                if col not in cols:
                    conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

    def _ensure_schema(self):
        """Ensure tables exist (handles state DB deletion + recreation)."""
        db_path = Path(self.db_path)
        if not db_path.exists():
            self._init_schema()
            return
        conn = _db_connect(self.db_path)
        try:
            conn.execute("SELECT 1 FROM workflow_instances LIMIT 1")
            conn.execute("SELECT 1 FROM trigger_keys LIMIT 1")
            # Migrate any missing columns on an existing DB
            self._migrate_columns(conn)
            conn.commit()
        except sqlite3.OperationalError:
            conn.close()
            self._init_schema()
            return
        conn.close()

    def _trigger_key_exists(self, key: str) -> bool:
        """Check if a trigger key has been recorded (dedup)."""
        self._ensure_schema()
        conn = _db_connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM trigger_keys WHERE key = ?", (key,)
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False
        finally:
            conn.close()

    def _record_trigger_key_atomic(self, key: str, conn: sqlite3.Connection):
        """Record a trigger key using an existing connection (for atomicity)."""
        conn.execute(
            "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES (?, ?)",
            (key, int(time.time())),
        )

    def _record_trigger_key(self, key: str):
        """Record a trigger key to prevent re-triggering (standalone connection)."""
        self._ensure_schema()
        conn = _db_connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES (?, ?)",
                (key, int(time.time())),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("_record_trigger_key failed: %s", e)
        finally:
            conn.close()

    def create_instance(self, instance: WorkflowInstance):
        # Validate created_at — reject negative timestamps
        if instance.created_at is not None and instance.created_at < 0:
            raise ValueError(
                f"created_at must be non-negative, got {instance.created_at}"
            )
        conn = _db_connect(self.db_path)
        try:
            # UPSERT instead of INSERT OR IGNORE so board changes are not swallowed
            # Clamp created_at to a safe positive value
            safe_created_at = instance.created_at if instance.created_at and instance.created_at > 0 else int(time.time())
            # Snapshot the valid node IDs at creation time (stale-state detection)
            node_ids_json = json.dumps(list(instance.node_states.keys()))
            conn.execute(
                """INSERT INTO workflow_instances
                   (instance_id, workflow_id, board, project_dir, trigger_context,
                    parent_instance_id, created_at, status, completed_at, node_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', NULL, ?)
                   ON CONFLICT(instance_id) DO UPDATE SET
                     workflow_id=excluded.workflow_id,
                     board=excluded.board,
                     project_dir=excluded.project_dir,
                     trigger_context=excluded.trigger_context,
                     parent_instance_id=excluded.parent_instance_id,
                     created_at=excluded.created_at,
                     node_ids=excluded.node_ids,
                     status='active'""",
                (
                    instance.instance_id,
                    instance.workflow_id,
                    instance.board,
                    instance.project_dir,
                    json.dumps(instance.trigger_context),
                    instance.parent_instance_id,
                    safe_created_at,
                    node_ids_json,
                ),
            )
            for node_id, ns in instance.node_states.items():
                conn.execute(
                    """INSERT INTO node_states
                       (instance_id, node_id, status, card_id, output)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(instance_id, node_id) DO UPDATE SET
                         status=excluded.status,
                         card_id=excluded.card_id,
                         output=excluded.output""",
                    (instance.instance_id, node_id, ns.status.value, ns.card_id, json.dumps(ns.output)),
                )
            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("create_instance failed (read-only or locked): %s", e)
        finally:
            conn.close()

    def load_active_instances(self) -> list[WorkflowInstance]:
        self._ensure_schema()
        conn = _db_connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM workflow_instances WHERE status = 'active'"
            ).fetchall()
        except sqlite3.OperationalError:
            conn.close()
            return []

        instances = []
        for row in rows:
            inst = WorkflowInstance(
                instance_id=row["instance_id"],
                workflow_id=row["workflow_id"],
                board=row["board"],
                project_dir=row["project_dir"],
                trigger_context=json.loads(row["trigger_context"]),
                parent_instance_id=row["parent_instance_id"],
                created_at=row["created_at"],
                completed_at=row["completed_at"] if "completed_at" in row.keys() else None,
                node_ids=json.loads(row["node_ids"]) if "node_ids" in row.keys() and row["node_ids"] else [],
            )
            ns_rows = conn.execute(
                "SELECT * FROM node_states WHERE instance_id = ?", (inst.instance_id,)
            ).fetchall()
            for ns_row in ns_rows:
                # Filter out stale node states: a node state whose node_id is not
                # in the snapshot of valid node_ids recorded at creation time
                # (template was edited to remove the node after instance start).
                if inst.node_ids and ns_row["node_id"] not in inst.node_ids:
                    log.warning(
                        "Filtering stale node state '%s' from instance %s during load",
                        ns_row["node_id"], inst.instance_id,
                    )
                    continue
                ns = NodeState(
                    instance_id=inst.instance_id,
                    node_id=ns_row["node_id"],
                    status=NodeStatus(ns_row["status"]),
                    card_id=ns_row["card_id"],
                    output=json.loads(ns_row["output"]),
                )
                inst.node_states[ns.node_id] = ns
            instances.append(inst)
        conn.close()
        return instances

    def update_node_state(self, instance_id: str, node_id: str, status: NodeStatus,
                          card_id: str | None = None, output: dict | None = None):
        """Atomic UPSERT that merges with existing values via COALESCE.

        Avoids the read-then-write lost-update problem: when card_id or output
        is None (meaning "don't change"), we COALESCE with the existing value
        inside the single SQL statement, so concurrent callers can't clobber
        each other's field.
        """
        conn = _db_connect(self.db_path)
        try:
            # Build the UPSERT. When a caller omits card_id/output (None),
            # fall back to the existing row's value via COALESCE so concurrent
            # updates that set different fields don't lose data. The VALUES
            # must be non-NULL to satisfy the NOT NULL constraint on INSERT
            # (when the row doesn't exist yet); the ON CONFLICT clause then
            # applies COALESCE to keep the existing value for omitted fields.
            output_json = json.dumps(output) if output is not None else None
            conn.execute(
                """INSERT INTO node_states (instance_id, node_id, status, card_id, output)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(instance_id, node_id) DO UPDATE SET
                     status=excluded.status,
                     card_id=COALESCE(?, node_states.card_id),
                     output=CASE WHEN ? = 1 THEN ? ELSE node_states.output END""",
                (
                    instance_id, node_id, status.value,
                    card_id,  # for INSERT (NULL ok for nullable column)
                    output_json if output_json is not None else "{}",  # non-NULL default for INSERT
                    card_id,  # for COALESCE in UPDATE
                    1 if output is not None else 0,  # flag: should we update output?
                    output_json if output_json is not None else None,  # new output value
                ),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("update_node_state failed: %s", e)
        finally:
            conn.close()

    def complete_instance(self, instance_id: str):
        conn = _db_connect(self.db_path)
        try:
            conn.execute(
                """UPDATE workflow_instances
                   SET status = 'completed', completed_at = ?
                   WHERE instance_id = ?""",
                (int(time.time()), instance_id),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("complete_instance failed: %s", e)
        finally:
            conn.close()

    def get_watermark(self, board: str) -> int:
        self._ensure_schema()
        conn = _db_connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT last_ts FROM trigger_watermark WHERE board = ?", (board,)
            ).fetchone()
            conn.close()
            return row["last_ts"] if row else 0
        except sqlite3.OperationalError:
            conn.close()
            return 0

    def set_watermark(self, board: str, ts: int):
        conn = _db_connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO trigger_watermark (board, last_ts) VALUES (?, ?)
                   ON CONFLICT(board) DO UPDATE SET last_ts = ?""",
                (board, ts, ts),
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("set_watermark failed: %s", e)
        finally:
            conn.close()

    def cleanup(self, max_age_days: int = 7) -> dict[str, int]:
        """Garbage-collect old state rows. Call once per tick (cheap: a few DELETEs).

        Removes:
          - trigger_keys older than max_age_days
          - completed workflow_instances older than max_age_days (+ their node_states)
          - trigger_watermark entries whose last_ts is older than max_age_days

        Returns a dict with counts of rows deleted per table (for logging/tests).
        """
        self._ensure_schema()
        cutoff = int(time.time()) - (max_age_days * 86400)
        counts: dict[str, int] = {
            "trigger_keys": 0,
            "workflow_instances": 0,
            "node_states": 0,
            "trigger_watermark": 0,
        }
        conn = _db_connect(self.db_path)
        try:
            # 1. Delete old trigger_keys
            cur = conn.execute(
                "DELETE FROM trigger_keys WHERE created_at < ?", (cutoff,)
            )
            counts["trigger_keys"] = cur.rowcount

            # 2. Find old completed instances, delete their node_states, then them.
            old_instances = conn.execute(
                """SELECT instance_id FROM workflow_instances
                   WHERE status = 'completed' AND completed_at IS NOT NULL
                     AND completed_at < ?""",
                (cutoff,),
            ).fetchall()
            if old_instances:
                old_ids = [r["instance_id"] for r in old_instances]
                placeholders = ",".join("?" for _ in old_ids)
                cur = conn.execute(
                    f"DELETE FROM node_states WHERE instance_id IN ({placeholders})",
                    old_ids,
                )
                counts["node_states"] = cur.rowcount
                cur = conn.execute(
                    f"DELETE FROM workflow_instances WHERE instance_id IN ({placeholders})",
                    old_ids,
                )
                counts["workflow_instances"] = cur.rowcount

            # 3. Delete stale trigger_watermark entries (last_ts older than cutoff)
            cur = conn.execute(
                "DELETE FROM trigger_watermark WHERE last_ts < ?", (cutoff,)
            )
            counts["trigger_watermark"] = cur.rowcount

            conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("cleanup failed: %s", e)
        finally:
            conn.close()
        return counts


class Engine:
    """The workflow engine — tick loop that advances workflows."""

    def __init__(self, templates_dir: str | Path):
        self.store = TemplateStore(templates_dir)
        self.state = StateDB()
        self._tick_lock = threading.Lock()

    def tick(self) -> list[str]:
        """Run one engine tick. Thread-safe via internal lock.

        If another tick is already running, returns immediately (no-op).
        Wraps all DB operations in try/except so transient errors (locked DB,
        read-only) don't crash the engine.
        """
        if not self._tick_lock.acquire(blocking=False):
            return ["SKIP tick: another tick is already running"]

        lock_fd = None
        try:
            # File lock prevents two Engine processes from ticking simultaneously
            lock_fd = open(LOCK_FILE, "w")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError):
                return ["SKIP tick: another engine process holds the lock"]

            actions: list[str] = []

            # 0. Garbage-collect old state (trigger_keys, completed instances,
            #    stale watermarks). Cheap — a few DELETE queries once per tick.
            gc = self.state.cleanup()
            total_gc = sum(gc.values())
            if total_gc:
                actions.append(
                    f"GC: removed {total_gc} old state rows "
                    f"({gc['trigger_keys']} trigger_keys, "
                    f"{gc['workflow_instances']} instances, "
                    f"{gc['node_states']} node_states, "
                    f"{gc['trigger_watermark']} watermarks)"
                )

            # 1. Check completions on active instances
            for inst in self.state.load_active_instances():
                actions += self._check_instance(inst)

            # 2. Check triggers on all boards
            actions += self._check_triggers()

            return actions
        except Exception as e:
            log.error("tick failed: %s", e)
            return [f"ERROR tick: {e}"]
        finally:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
                lock_fd.close()
            self._tick_lock.release()

    def _check_instance(self, inst: WorkflowInstance) -> list[str]:
        """Check a single workflow instance: advance nodes, handle completions."""
        actions = []

        # ZOMBIE GUARD: if this instance was previously completed (completed_at
        # is set) but somehow reactivated, do not re-dispatch nodes — that would
        # create phantom work from an instance the user believed finished.
        if inst.completed_at is not None:
            actions.append(
                f"SKIP zombie instance {inst.instance_id}: previously completed at "
                f"{inst.completed_at}, will not re-dispatch (reactivate detected)"
            )
            # Re-mark as completed to prevent future processing
            self.state.complete_instance(inst.instance_id)
            return actions

        # DELETED BOARD GUARD: if the board DB no longer exists, the instance
        # can never progress — flag it and mark complete to stop zombie cycling.
        if not board_db_path(inst.board).exists():
            actions.append(
                f"WARNING instance {inst.instance_id}: board '{inst.board}' not found "
                f"(missing) — marking instance complete to stop zombie cycling"
            )
            self.state.complete_instance(inst.instance_id)
            return actions

        wf = self.store.load(inst.workflow_id)
        if not wf:
            actions.append(f"SKIP instance {inst.instance_id}: template {inst.workflow_id} not found")
            return actions

        # Build the set of valid node IDs from the template
        valid_node_ids = {n.id for n in wf.nodes}

        # Filter out stale node states that no longer exist in the template
        stale = [nid for nid in inst.node_states if nid not in valid_node_ids]
        for nid in stale:
            log.warning("Removing stale node state '%s' from instance %s", nid, inst.instance_id)
            del inst.node_states[nid]

        # PHASE 1: Check dispatched nodes for completion FIRST
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.DISPATCHED:
                continue

            # SUBWORKFLOW completion: check if child instance is done
            child_instance_id = ns.output.get("_child_instance") if ns.output else None
            if child_instance_id:
                child_output = self._check_subworkflow_completion(inst, node, ns, child_instance_id)
                if child_output is not None:
                    actions.append(f"DONE subworkflow node {node.id} (child {child_instance_id}) on {inst.board}")
                else:
                    # Check if child is still active
                    child_active = self._is_instance_active(child_instance_id)
                    if not child_active:
                        # Child completed but wasn't detected — check manually
                        actions.append(f"WARNING subworkflow node {node.id}: child {child_instance_id} no longer active")
                continue

            # FOREACH completion: check all child cards
            foreach_cards = ns.output.get("_foreach_cards") if ns.output else None
            if foreach_cards is not None:
                all_done = True
                results = []
                for fcid in foreach_cards:
                    fcard = get_card(inst.board, fcid)
                    if not fcard:
                        actions.append(f"WARNING foreach node {node.id}: card {fcid} not found (dangling)")
                        all_done = False
                        break
                    if fcard.status == "done":
                        fmeta = get_card_metadata(inst.board, fcid)
                        results.append(fmeta.get("metadata", {}))
                    elif fcard.status == "blocked":
                        all_done = False
                    else:
                        all_done = False

                if all_done:
                    aggregated = {"_foreach_cards": foreach_cards, "results": results}
                    self.state.update_node_state(
                        inst.instance_id, node.id, NodeStatus.DONE, ns.card_id, aggregated
                    )
                    ns.status = NodeStatus.DONE
                    ns.output = aggregated
                    actions.append(f"DONE foreach node {node.id} ({len(foreach_cards)} cards) on {inst.board}")
                elif any(get_card(inst.board, c) and get_card(inst.board, c).status == "blocked" for c in foreach_cards if get_card(inst.board, c)):
                    actions.append(f"BLOCKED foreach node {node.id} — one or more cards blocked")
                continue

            # Standard single-card completion check
            if not ns.card_id:
                continue

            card = get_card(inst.board, ns.card_id)
            if not card:
                # Dangling card_id — flag it but don't crash
                actions.append(f"WARNING node {node.id}: card {ns.card_id} not found on board (dangling)")
                continue

            if card.status == "done":
                meta = get_card_metadata(inst.board, ns.card_id)
                output = meta.get("metadata", {})

                # HARD OUTPUT VALIDATION (enterprise-grade):
                # Validate the card's metadata against the node's declared
                # output.schema (JSON Schema Draft 2020-12). If it fails, mark
                # the node FAILED (not DONE) so downstream nodes that depend on
                # it never advance. This prevents garbage output from poisoning
                # the rest of the workflow.
                if node.output and node.output.schema:
                    valid, err = validate_output(inst.board, ns.card_id, node.output.schema)
                    if not valid:
                        log.warning(
                            "VALIDATION FAILED node %s (card %s) on %s: %s",
                            node.id, ns.card_id, inst.board, err,
                        )
                        self.state.update_node_state(
                            inst.instance_id, node.id, NodeStatus.FAILED, ns.card_id, output
                        )
                        ns.status = NodeStatus.FAILED
                        ns.output = output
                        actions.append(
                            f"VALIDATION FAILED node {node.id} (card {ns.card_id}) "
                            f"on {inst.board}: {err}"
                        )
                        continue

                self.state.update_node_state(
                    inst.instance_id, node.id, NodeStatus.DONE, ns.card_id, output
                )
                ns.status = NodeStatus.DONE
                ns.output = output
                actions.append(f"DONE node {node.id} (card {ns.card_id}) on {inst.board}")
            elif card.status == "blocked":
                actions.append(f"BLOCKED node {node.id} (card {ns.card_id}) — waiting for dynamic children")
            elif card.status in ("todo", "ready", "running"):
                # Normal states for a dispatched card — no action needed
                pass

        # PHASE 1b: Check DONE nodes for card regression (card flipped back to
        # todo/ready/running after the node was already marked done).
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.DONE or not ns.card_id:
                continue

            card = get_card(inst.board, ns.card_id)
            if not card:
                # Card vanished entirely after being done — orphan/dangling
                actions.append(
                    f"WARNING node {node.id}: DONE card {ns.card_id} no longer exists on board "
                    f"(orphan/regression)"
                )
                continue

            if card.status in ("todo", "ready", "running"):
                actions.append(
                    f"WARNING node {node.id}: card {ns.card_id} regressed to '{card.status}' "
                    f"but node is DONE (orphan reuse)"
                )

        # PHASE 2: Check pending nodes for dispatch
        ctx = inst.context()
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.PENDING:
                continue

            deps_done = all(
                inst.node_states.get(dep, NodeState(instance_id="", node_id="")).status == NodeStatus.DONE
                for dep in node.depends_on
                if dep in inst.node_states  # only check deps that exist in the instance
            )
            # If any dep is not in inst.node_states, it might be a valid template dep
            # not yet tracked — treat as not-done
            all_deps_tracked = all(dep in inst.node_states for dep in node.depends_on)
            if not deps_done or not all_deps_tracked:
                continue

            if node.condition and not evaluate_condition(node.condition, ctx):
                continue

            if node.foreach:
                # Foreach node: resolve the list, create one card per item.
                ok, msg = self._dispatch_foreach_node(inst, node, ctx)
                if ok:
                    actions.append(f"DISPATCHED node {node.id} (foreach: {msg} cards) on {inst.board}")
                else:
                    actions.append(f"FAILED to dispatch foreach node {node.id} on {inst.board}: {msg}")
            elif node.type == "subworkflow":
                # Subworkflow node: start child workflow, block until it completes.
                ok, msg = self._dispatch_subworkflow_node(inst, node, ctx)
                if ok:
                    actions.append(f"DISPATCHED node {node.id} (subworkflow: {node.workflow_ref}) on {inst.board} → child {msg}")
                else:
                    actions.append(f"FAILED to dispatch subworkflow node {node.id} on {inst.board}: {msg}")
            else:
                ok, msg = self._dispatch_node(inst, node, ctx)
                if ok:
                    actions.append(f"DISPATCHED node {node.id} on {inst.board} → card {msg}")
                else:
                    actions.append(f"FAILED to dispatch node {node.id} on {inst.board}: {msg}")

        # Check if all nodes done → complete instance
        if wf.nodes:
            all_done = all(
                inst.node_states.get(node.id, NodeState(instance_id="", node_id="")).status == NodeStatus.DONE
                for node in wf.nodes
            )
            if all_done:
                # Verify all cards are actually done on the board (not just in state).
                # A missing card or a non-done card means we must NOT complete.
                cards_verified = True
                for node in wf.nodes:
                    ns = inst.node_states.get(node.id)
                    if ns and ns.card_id:
                        card = get_card(inst.board, ns.card_id)
                        if card is None:
                            # Card missing on board — cannot verify completion
                            cards_verified = False
                            actions.append(
                                f"WARNING: node {node.id} marked done but card {ns.card_id} "
                                f"is missing on board — cannot complete instance"
                            )
                            break
                        if card.status != "done":
                            cards_verified = False
                            actions.append(f"WARNING: node {node.id} marked done but card {ns.card_id} is '{card.status}' on board")
                            break
                if cards_verified:
                    self.state.complete_instance(inst.instance_id)
                    actions.append(f"WORKFLOW COMPLETE: {inst.workflow_id} ({inst.instance_id})")

        return actions

    def _dispatch_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Create a kanban card for a node. Idempotent via find_cards_by_idempotency_key."""
        body = resolve_template(node.body_template or "", ctx)
        idem_key = f"wf:{inst.instance_id}:{node.id}"

        # Check if already created (prevents double dispatch)
        existing = find_cards_by_idempotency_key(inst.board, idem_key)
        if existing:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DISPATCHED, existing[0].id
            )
            return True, existing[0].id

        workspace = f"dir:{inst.project_dir}" if inst.project_dir else None
        ok, output = create_card(
            board=inst.board,
            title=f"[{node.id}] {node.skill or 'task'}",
            assignee=node.profile,
            body=body,
            idempotency_key=idem_key,
            priority=10,
            workspace=workspace,
        )

        if not ok:
            return False, output

        try:
            data = json.loads(output)
            card_id = data.get("id", "")
        except (json.JSONDecodeError, TypeError):
            card_id = ""

        if card_id:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DISPATCHED, card_id
            )
            return True, card_id

        return False, "no card id in output"

    def _dispatch_foreach_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Dispatch a foreach node: resolve the list, create one card per item.

        The node's `foreach` field is a template variable like
        "${nodes.tickets.output.bead_ids}" that resolves to a list. We create
        one card per item, each card's body templated with the specific item
        (available as ${item} in the body template, plus the raw item appended).

        Card ids are stored in the node state's output under the `_foreach_cards`
        key. The node is marked DISPATCHED; PHASE 1 checks all cards for
        completion and aggregates outputs when done.
        """
        # Resolve the foreach variable to a list
        foreach_var = node.foreach
        # Strip ${...} wrapper to get the context key
        if foreach_var.startswith("${") and foreach_var.endswith("}"):
            var_key = foreach_var[2:-1]
        else:
            var_key = foreach_var
        items = ctx.get(var_key)

        if items is None:
            return False, f"foreach variable '{foreach_var}' resolved to None"
        if not isinstance(items, list):
            return False, f"foreach variable '{foreach_var}' is not a list (got {type(items).__name__})"

        if not items:
            # Empty list — nothing to do, mark DONE immediately with empty aggregate
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None,
                {"_foreach_cards": [], "results": []},
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.DONE
                ns.output = {"_foreach_cards": [], "results": []}
            return True, "0"

        workspace = f"dir:{inst.project_dir}" if inst.project_dir else None
        card_ids: list[str] = []

        for idx, item in enumerate(items):
            # Build per-item context: the original ctx + ${item} = current item
            item_ctx = dict(ctx)
            item_ctx["item"] = item
            item_ctx["item_index"] = idx
            body = resolve_template(node.body_template or "", item_ctx)

            idem_key = f"wf:{inst.instance_id}:{node.id}:{idx}"

            # Check if already created (idempotency across ticks)
            existing = find_cards_by_idempotency_key(inst.board, idem_key)
            if existing:
                card_ids.append(existing[0].id)
                continue

            ok, output = create_card(
                board=inst.board,
                title=f"[{node.id}#{idx}] {node.skill or 'task'}",
                assignee=node.profile,
                body=body,
                idempotency_key=idem_key,
                priority=10,
                workspace=workspace,
            )
            if not ok:
                return False, f"card creation failed for item {idx}: {output}"
            try:
                data = json.loads(output)
                cid = data.get("id", "")
            except (json.JSONDecodeError, TypeError):
                cid = ""
            if not cid:
                return False, f"no card id for item {idx}"
            card_ids.append(cid)

        # Store all card ids in the node state output, mark DISPATCHED.
        # Keep ns.card_id as the first card id for backward-compat with code
        # that checks a single card_id (e.g. regression guards).
        output = {"_foreach_cards": card_ids, "results": []}
        self.state.update_node_state(
            inst.instance_id, node.id, NodeStatus.DISPATCHED,
            card_ids[0] if card_ids else None, output,
        )
        ns = inst.node_states.get(node.id)
        if ns:
            ns.status = NodeStatus.DISPATCHED
            ns.card_id = card_ids[0] if card_ids else None
            ns.output = output
        return True, str(len(card_ids))

    def _dispatch_subworkflow_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Dispatch a subworkflow node: start a child workflow instance.

        The child runs independently (its own nodes dispatch on subsequent ticks).
        The parent node blocks in DISPATCHED state with _child_instance in output.
        On each tick, _check_subworkflow_completion checks if the child is done.
        """
        if not node.workflow_ref:
            return False, "subworkflow node missing workflow_ref"

        child_wf = self.store.load(node.workflow_ref)
        if not child_wf:
            return False, f"child workflow template not found: {node.workflow_ref}"

        # Resolve input mappings from parent context
        child_context = {}
        for key, expr in node.input_mapping.items():
            if isinstance(expr, str) and expr.startswith("${") and expr.endswith("}"):
                var_key = expr[2:-1]
                child_context[key] = ctx.get(var_key, "")
            else:
                child_context[key] = expr
        # Always pass board + project_dir
        child_context.setdefault("board", inst.board)
        child_context.setdefault("parent_instance", inst.instance_id)
        child_context.setdefault("parent_node", node.id)

        # Check if child already started (idempotency)
        existing_child = inst.node_states.get(node.id, NodeState("", "")).output.get("_child_instance")
        if existing_child and self._is_instance_active(existing_child):
            return True, existing_child

        # Start the child workflow
        child_id = self.start_manual(
            workflow_id=node.workflow_ref,
            board=inst.board,
            project_dir=inst.project_dir,
            context=child_context,
        )

        # Store child instance ID in node output
        output = {"_child_instance": child_id}
        self.state.update_node_state(
            inst.instance_id, node.id, NodeStatus.DISPATCHED, None, output
        )
        ns = inst.node_states.get(node.id)
        if ns:
            ns.status = NodeStatus.DISPATCHED
            ns.output = output

        return True, child_id

    def _check_subworkflow_completion(self, inst: WorkflowInstance, node: Node,
                                       ns: NodeState, child_instance_id: str) -> dict | None:
        """Check if a child workflow instance has completed.

        Returns the child's aggregated output if complete, None if still running.
        When complete, maps child outputs to parent via output_mapping.
        """
        conn = _db_connect(self.state.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM workflow_instances WHERE instance_id = ?",
                (child_instance_id,),
            ).fetchone()
            if not row:
                return None
            if row["status"] != "completed":
                return None
        except sqlite3.OperationalError:
            conn.close()
            return None
        conn.close()

        # Child is complete — read its final node outputs
        child_wf = self.store.load(node.workflow_ref)
        if not child_wf:
            return {}

        # Collect outputs from all child nodes
        conn2 = _db_connect(self.state.db_path)
        try:
            ns_rows = conn2.execute(
                "SELECT node_id, output FROM node_states WHERE instance_id = ? AND status = 'done'",
                (child_instance_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            conn2.close()
            return {}
        conn2.close()

        # Build child context (all node outputs)
        child_outputs = {}
        for ns_row in ns_rows:
            node_id = ns_row["node_id"]
            output = json.loads(ns_row["output"]) if ns_row["output"] else {}
            for k, v in output.items():
                child_outputs[f"nodes.{node_id}.output.{k}"] = v

        # Map child outputs to parent node output via output_mapping
        mapped_output = {"_child_instance": child_instance_id}
        for parent_key, child_expr in node.output_mapping.items():
            if isinstance(child_expr, str) and child_expr.startswith("${") and child_expr.endswith("}"):
                child_var = child_expr[2:-1]
                mapped_output[parent_key] = child_outputs.get(child_var, "")
            else:
                mapped_output[parent_key] = child_expr

        # If no output_mapping specified, flatten all child outputs
        if not node.output_mapping:
            for k, v in child_outputs.items():
                # Strip the "nodes.X.output." prefix for flat access
                if ".output." in k:
                    flat_key = k.split(".output.", 1)[1]
                    mapped_output[flat_key] = v

        # Apply hard output validation if the parent node declares an output schema
        if node.output and node.output.schema:
            from .kanban_adapter import validate_output as validate_metadata
            try:
                import jsonschema
                jsonschema.validate(instance=mapped_output, schema=node.output.schema)
            except ImportError:
                for req in node.output.schema.get("required", []):
                    if req not in mapped_output:
                        log.warning("VALIDATION FAILED subworkflow node %s: missing %s", node.id, req)
                        self.state.update_node_state(
                            inst.instance_id, node.id, NodeStatus.FAILED, None, mapped_output
                        )
                        ns.status = NodeStatus.FAILED
                        ns.output = mapped_output
                        return mapped_output
            except Exception as e:
                log.warning("VALIDATION FAILED subworkflow node %s: %s", node.id, e)
                self.state.update_node_state(
                    inst.instance_id, node.id, NodeStatus.FAILED, None, mapped_output
                )
                ns.status = NodeStatus.FAILED
                ns.output = mapped_output
                return mapped_output

        # Mark parent node done
        self.state.update_node_state(
            inst.instance_id, node.id, NodeStatus.DONE, None, mapped_output
        )
        ns.status = NodeStatus.DONE
        ns.output = mapped_output
        return mapped_output

    def _is_instance_active(self, instance_id: str) -> bool:
        """Check if a workflow instance is still active (not completed)."""
        conn = _db_connect(self.state.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM workflow_instances WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            conn.close()
            return row is not None and row["status"] == "active"
        except sqlite3.OperationalError:
            conn.close()
            return False

    def _check_triggers(self) -> list[str]:
        """Check all boards for new card completions that match workflow triggers."""
        actions = []

        for wf in self.store.all():
            if not wf.trigger:
                continue

            if wf.trigger.source == "card_completed":
                boards = self._boards_to_check()
                for board in boards:
                    now = int(time.time())
                    since = now - TRIGGER_LOOKBACK_SECS

                    # Paginate through ALL matching completions (no LIMIT 20 drop)
                    all_completions = find_recent_completions(board, since)
                    for card in all_completions:
                        if self._matches_trigger(card, wf.trigger.condition):
                            trig_key = f"trig:{wf.id}:{card.id}"

                            # Atomic: check + record + create instance in one transaction
                            conn = _db_connect(self.state.db_path)
                            try:
                                existing = conn.execute(
                                    "SELECT 1 FROM trigger_keys WHERE key = ?", (trig_key,)
                                ).fetchone()
                                if existing:
                                    conn.close()
                                    continue

                                # Record the key FIRST (before creating instance)
                                conn.execute(
                                    "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES (?, ?)",
                                    (trig_key, int(time.time())),
                                )
                                conn.commit()
                            except sqlite3.OperationalError as e:
                                log.warning("trigger dedup check failed: %s", e)
                                conn.close()
                                continue
                            conn.close()

                            actions += self._start_from_trigger(wf, board, card)

        return actions

    def _matches_trigger(self, card, condition: dict) -> bool:
        """Check if a completed card matches a trigger condition."""
        for key, expected in condition.items():
            if key == "assignee":
                if card.assignee != expected:
                    return False
            elif key == "status":
                if card.status != expected:
                    return False
            elif key == "metadata.verdict":
                meta = self._extract_metadata(card)
                if meta.get("verdict") != expected:
                    return False
            elif key.startswith("metadata."):
                meta = self._extract_metadata(card)
                field = key.split(".", 1)[1]
                if meta.get(field) != expected:
                    return False
            elif key == "title_prefix":
                if not (card.title or "").startswith(expected):
                    return False
            elif key == "title_not_prefix":
                if (card.title or "").startswith(expected):
                    return False
            elif key.startswith("title_not_prefix"):
                # Handle title_not_prefix2 etc.
                if (card.title or "").startswith(expected):
                    return False
        return True

    @staticmethod
    def _extract_metadata(card) -> dict:
        """Extract metadata dict from a card, handling str/None/invalid JSON."""
        meta = card.metadata or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        return meta

    def _start_from_trigger(self, wf: Workflow, board: str, trigger_card) -> list[str]:
        """Start a new workflow instance from a trigger card."""
        meta = self._extract_metadata(trigger_card)

        unique = uuid.uuid4().hex[:8]
        instance_id = f"wf_{int(time.time())}_{wf.id}_{unique}"
        now = int(time.time())

        trigger_context = {
            "card_id": trigger_card.id,
            "board": board,
            "assignee": trigger_card.assignee,
            **meta,
        }

        project_dir = self._board_to_project_dir(board)

        inst = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=wf.id,
            board=board,
            project_dir=project_dir,
            trigger_context=trigger_context,
            created_at=now,
        )

        for node in wf.nodes:
            inst.node_states[node.id] = NodeState(
                instance_id=instance_id, node_id=node.id
            )

        self.state.create_instance(inst)
        return [f"STARTED workflow {wf.id} ({instance_id}) on {board} — triggered by card {trigger_card.id}"]

    def _boards_to_check(self) -> list[str]:
        """Get list of boards to check for triggers."""
        from .kanban_adapter import KANBAN_HOME
        boards_dir = KANBAN_HOME
        if not boards_dir.exists():
            return []
        return [p.name for p in boards_dir.iterdir() if p.is_dir() and (p / "kanban.db").exists()]

    def _board_to_project_dir(self, board: str) -> str:
        """Try to map a board name to a project directory."""
        projects_file = Path.home() / ".hermes-teams/startup/active-projects.json"
        if projects_file.exists():
            try:
                data = json.loads(projects_file.read_text())
                # Handle both formats: {board: path} and {active_projects: [{board, path}]}
                if "active_projects" in data:
                    for proj in data["active_projects"]:
                        if proj.get("board") == board:
                            return proj.get("path", "")
                elif board in data:
                    return data[board]
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: ~/projects/<board>
        fallback = Path.home() / "projects" / board
        if fallback.exists():
            return str(fallback)
        return ""

    def start_manual(self, workflow_id: str, board: str, project_dir: str = "",
                     context: dict | None = None) -> str:
        """Manually start a workflow instance. Returns instance_id."""
        wf = self.store.load(workflow_id)
        if not wf:
            raise ValueError(f"Workflow template not found: {workflow_id}")

        unique = uuid.uuid4().hex[:8]
        instance_id = f"wf_{int(time.time())}_{workflow_id}_{unique}"
        now = int(time.time())

        inst = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=workflow_id,
            board=board,
            project_dir=project_dir,
            trigger_context=context or {},
            created_at=now,
        )

        for node in wf.nodes:
            inst.node_states[node.id] = NodeState(
                instance_id=instance_id, node_id=node.id
            )

        self.state.create_instance(inst)
        log.info("Started workflow %s (%s)", workflow_id, instance_id)
        return instance_id
