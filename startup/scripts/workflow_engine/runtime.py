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
import subprocess
import threading
import uuid

from .model import Workflow, Node, Edge, resolve_template, evaluate_condition, strip_template_var
from .store import TemplateStore
from .kanban_adapter import (
    create_card,
    get_card,
    get_card_metadata,
    find_cards_by_idempotency_key,
    find_recent_completions,
    validate_output,
    validate_against_schema,
    board_db_path,
)

log = logging.getLogger(__name__)

STATE_DB = Path.home() / ".hermes-teams/startup/kanban/workflow-state.db"
LOCK_FILE = Path.home() / ".hermes-teams/startup/kanban/workflow-engine.lock"
TRIGGER_LOOKBACK_SECS = 3600  # 1 hour


def _extract_parent_workflow(idempotency_key: str) -> str | None:
    """Deterministically parse the parent workflow ID from an engine card's
    idempotency key.

    Engine-created cards carry an idempotency key of the shape:

        wf:<instance_id>[:<suffix>...]

    where ``<instance_id>`` is ``wf_<timestamp>_<workflow.id>_<uuid8>`` and
    ``<workflow.id>`` may itself contain hyphens (but never underscores —
    enforced by ``Workflow.from_dict``). The optional ``:<suffix>...`` tail
    encodes foreach/chain/sw iteration indices and is ignored here.

    Returns the parent workflow ID, or ``None`` when the key is not an engine
    card (does not start with ``wf:wf_``) or is malformed.

    This replaces the prior heuristic that guessed the workflow ID chunk via
    "first chunk longer than 3 chars, non-digit" — which misclassified short
    workflow IDs (≤3 chars) and crashed on degenerate shapes.
    """
    if not idempotency_key or not idempotency_key.startswith("wf:"):
        return None
    parts = idempotency_key.split(":")
    if len(parts) < 2:
        return None
    instance_part = parts[1]
    # Engine instance IDs always start with "wf_"; anything else is not an
    # engine card we recognise.
    if not instance_part.startswith("wf_"):
        return None
    inst_chunks = instance_part.split("_")
    # Shape: ["wf", <timestamp>, <wf.id chunks...>, <uuid8>]
    # Need at least: wf + timestamp + 1 id chunk + uuid  →  >= 4 chunks.
    if len(inst_chunks) < 4:
        return None
    # Rejoin everything between the timestamp (index 1) and the uuid (last),
    # preserving hyphenated workflow IDs intact.
    return "_".join(inst_chunks[2:-1])


# DEPRECATED — T4 state-blob migration (bead hermes-teams-qxb5).
# NodeStatus is being replaced by a derived node_phase() value computed from the
# card's actual status on the board (the ground truth) rather than a monotonic
# local flag. This class is retained as a backwards-compat shim for one release
# cycle so existing test modules and call sites keep importing it without
# modification. Do NOT add new usages; new code should read phase from the
# board. Scheduled for removal in T5's contract phase.
class NodeStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # condition evaluated false, or a dependency FAILED/SKIPPED


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


# ─────────────────────────────────────────────────────────────────────────────
# T5: Stateless tick — derived node phase + activation rule (pure functions).
# These replace the monotonic NodeStatus with a value DERIVED from the state
# blob every tick. See DESIGN-stateless-graph.md §Derived Node Phase, §Activation
# Rule. Kept module-level so they are unit-testable with no Engine instance.
# ─────────────────────────────────────────────────────────────────────────────

# Node phases (the derived replacement for NodeStatus).
PHASE_PENDING = "pending"
PHASE_RUNNING = "running"
PHASE_DONE = "done"
PHASE_FAILED = "failed"
PHASE_SKIPPED = "skipped"
_TERMINAL_PHASES = frozenset({PHASE_DONE, PHASE_FAILED, PHASE_SKIPPED})


def node_phase(node: Node, node_state: dict) -> str:
    """Derive a node's phase purely from its state-blob entry. Never persisted.

    Returns one of: ``'pending' | 'running' | 'done' | 'failed' | 'skipped'``.

    Terminal flags (``skipped`` / ``failed``) written by pass 3 are checked
    FIRST — they override any card/child state. Handles all node types:
    task, command, wait, subworkflow, and the foreach variants.

    This is the core of the stateless model: a task card flipping done→todo on
    the board naturally transitions the node from ``done`` back to ``running``
    / ``pending`` as the graph walk re-evaluates. No frozen states.
    """
    # Terminal flags written by pass 3 (skip propagation, validation failure).
    # MUST be checked first — they override card/child state.
    if node_state.get("skipped"):
        return PHASE_SKIPPED
    if node_state.get("failed"):
        return PHASE_FAILED

    # command/wait: check the explicit ``done`` flag set when they complete.
    if node_state.get("done"):
        return PHASE_DONE
    if node.type in ("command", "wait"):
        return PHASE_PENDING

    # subworkflow (single child or foreach-subworkflow): check child completion.
    if node.type == "subworkflow" or (node.foreach and node.type == "subworkflow"):
        if node_state.get("done"):
            return PHASE_DONE
        if node_state.get("child_instance_id") or node_state.get("child_instance_ids"):
            return PHASE_RUNNING
        return PHASE_PENDING

    # foreach task (N cards): check ALL card statuses.
    if node.foreach and node.type == "task":
        statuses = node_state.get("card_statuses", [])
        if statuses and all(s in ("done", "archived") for s in statuses):
            return PHASE_DONE
        if node_state.get("cards"):
            return PHASE_RUNNING
        return PHASE_PENDING

    # task (single card): phase follows the card's actual board status.
    card_status = node_state.get("card_status", "")
    if card_status in ("done", "archived"):
        return PHASE_DONE
    if card_status == "blocked":
        return PHASE_RUNNING  # blocked is a form of in-flight
    if card_status in ("todo", "ready", "running"):
        return PHASE_RUNNING
    if node_state.get("card_id"):
        return PHASE_RUNNING

    # No card yet — not yet dispatched.
    return PHASE_PENDING


def _incoming_edges(wf: Workflow, node_id: str) -> list[Edge]:
    """All edges pointing TO node_id. Falls back to implicit depends_on edges
    when the template has no explicit edges."""
    if wf.edges:
        return [e for e in wf.edges if e.to_node == node_id]
    # Implicit edges from depends_on (unconditional) + node.condition (conditional).
    target = wf.get_node(node_id)
    cond = target.condition if target else None
    implicit: list[Edge] = []
    if target:
        for dep in target.depends_on:
            implicit.append(Edge(from_node=dep, to_node=node_id,
                                 condition=cond))  # condition attaches to the edge
    return implicit


def _phase_of(wf: Workflow, node_id: str, state_nodes: dict[str, dict],
              ctx: dict | None = None) -> str:
    """node_phase() wrapper that tolerates an unknown/removed source node.

    A source that no longer exists in the template (stale state, template edit)
    derives to ``skipped`` — it can never fire, so it counts as terminal-but-
    not-firing for the activation + dead-branch rules.
    """
    node = wf.get_node(node_id)
    if node is None:
        return PHASE_SKIPPED
    return node_phase(node, state_nodes.get(node_id, {}))


def activation_rule_satisfied(
    wf: Workflow, node_id: str, state_nodes: dict[str, dict], ctx: dict
) -> bool:
    """Port of runtime.py:796-863 (AND/OR edge semantics) for the stateless model.

    A node N is dispatchable when, over its set of incoming edges:
      Let U = unconditional incoming edges (no condition)
      Let C = conditional incoming edges (has condition)

      U_sat = every e in U has source phase == 'done'   (AND semantics)
      C_sat = some e in C has source phase == 'done'
              AND evaluate(e.condition, ctx) is True    (OR semantics)

      Dispatchable iff U_sat AND (C_sat OR C is empty)

    If both U and C are empty → entry node, always dispatchable.
    Sources that are skipped/failed are treated as terminal-but-not-firing.
    """
    incoming = _incoming_edges(wf, node_id)
    if not incoming:
        # Entry node. In the implicit-edge model, an entry node may still carry
        # a self-gating ``condition`` (e.g. only run when a trigger flag is set).
        # The legacy engine evaluated node.condition for dep-less nodes too, so
        # we preserve that: a false condition → not dispatchable (and the dead-
        # branch rule will skip it once no source can ever satisfy it).
        node = wf.get_node(node_id)
        if node and node.condition and not evaluate_condition(node.condition, ctx):
            return False
        return True  # entry node, no condition or condition passes

    unconditional = [e for e in incoming if not e.condition]
    conditional = [e for e in incoming if e.condition]

    # U_sat: every unconditional source must be done. Skipped/failed sources
    # don't satisfy the dependency (they didn't produce output).
    u_sat = True
    for edge in unconditional:
        if _phase_of(wf, edge.from_node, state_nodes, ctx) != PHASE_DONE:
            u_sat = False
            break

    # C_sat: at least one conditional source done AND its condition passes.
    c_sat = False
    for edge in conditional:
        if _phase_of(wf, edge.from_node, state_nodes, ctx) == PHASE_DONE:
            if edge.condition and evaluate_condition(edge.condition, ctx):
                c_sat = True
                break

    return u_sat and (c_sat or not conditional)


def all_incoming_terminal_and_none_fired(
    wf: Workflow, node_id: str, state_nodes: dict[str, dict], ctx: dict
) -> bool:
    """Dead-branch detection: every incoming source is terminal (done/failed/
    skipped) but none activated this node. Returns True → the node should be
    SKIPPED so skip propagation continues downstream."""
    incoming = _incoming_edges(wf, node_id)
    if not incoming:
        return False  # entry node — never skipped
    for edge in incoming:
        if _phase_of(wf, edge.from_node, state_nodes, ctx) not in _TERMINAL_PHASES:
            return False  # something still pending/running
    # All sources terminal but none fired → dead branch.
    return True


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
                node_ids TEXT NOT NULL DEFAULT '[]',
                -- T4 state-blob migration (expand phase): denormalized JSON
                -- snapshot of node states. Old code path still uses the
                -- node_states table; new code path (T5) reads this blob.
                state TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 0
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

            CREATE TABLE IF NOT EXISTS engine_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                instance_id TEXT,
                workflow_id TEXT,
                node_id TEXT,
                board TEXT,
                card_id TEXT,
                message TEXT NOT NULL,
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON engine_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_instance ON engine_events(instance_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON engine_events(event_type);
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
            # T4 state-blob migration (expand phase). Existing instances are
            # backfilled to '{}' by the default; active instances get real
            # blobs via backfill_state_blob() / migrate_to_state_blob.py.
            ("state", "ALTER TABLE workflow_instances ADD COLUMN state TEXT NOT NULL DEFAULT '{}'"),
            ("version", "ALTER TABLE workflow_instances ADD COLUMN version INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
                if col not in cols:
                    conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

    def log_event(
        self, level: str, event_type: str, message: str,
        instance_id: str = "", workflow_id: str = "", node_id: str = "",
        board: str = "", card_id: str = "", metadata: dict | None = None,
    ):
        """Log an engine event to the engine_events table.

        Levels: DEBUG, INFO, WARN, ERROR
        Event types: tick, node_dispatched, node_done, node_failed, node_skipped,
                     trigger_fired, workflow_started, workflow_completed, command_run,
                     card_created, card_completed, error, gc
        """
        import json as _json, time as _time
        conn = _db_connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO engine_events
                   (timestamp, level, event_type, instance_id, workflow_id,
                    node_id, board, card_id, message, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(_time.time()), level, event_type, instance_id, workflow_id,
                 node_id, board, card_id, message,
                 _json.dumps(metadata) if metadata else None),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

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
            conn.execute("SELECT 1 FROM engine_events LIMIT 1")
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
        self._ensure_schema()
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

    # ─── T4 state-blob helpers (scaffolding for T5) ───────────────────────
    # These are NOT called by the tick loop yet. The old node_states code path
    # remains the source of truth until T5's contract phase swaps over. These
    # helpers exist now so the migration can backfill the blob and so T5 can
    # adopt them without touching StateDB's schema again.

    def load_state(self, instance_id: str) -> dict:
        """Read the state-blob and its version for an instance.

        Returns a dict with two keys:
          - ``state``: the parsed JSON blob (``{}`` if the instance has no blob
            yet, e.g. before backfill).
          - ``version``: the optimistic-concurrency version counter.
        Returns ``{"state": {}, "version": 0}`` if the instance does not exist.
        """
        self._ensure_schema()
        conn = _db_connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT state, version FROM workflow_instances WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
        except sqlite3.OperationalError as e:
            log.warning("load_state failed: %s", e)
            conn.close()
            return {"state": {}, "version": 0}
        conn.close()
        if row is None:
            return {"state": {}, "version": 0}
        raw_state = row["state"] if "state" in row.keys() else "{}"
        version = row["version"] if "version" in row.keys() else 0
        try:
            state = json.loads(raw_state) if raw_state else {}
        except (json.JSONDecodeError, TypeError):
            log.warning("load_state: corrupt state blob for %s, returning {}", instance_id)
            state = {}
        return {"state": state, "version": version or 0}

    def save_state(self, instance_id: str, state_dict: dict, expected_version: int) -> bool:
        """Optimistically write the state blob, bumping the version counter.

        Uses ``expected_version`` for optimistic concurrency: the UPDATE only
        succeeds if the row's current ``version`` equals ``expected_version``.
        Returns ``True`` on success (exactly one row updated), ``False`` on a
        version conflict or if the instance does not exist. Callers that get
        ``False`` should re-``load_state``, merge, and retry.
        """
        self._ensure_schema()
        blob = json.dumps(state_dict)
        conn = _db_connect(self.db_path)
        try:
            cur = conn.execute(
                """UPDATE workflow_instances
                   SET state = ?, version = version + 1
                   WHERE instance_id = ? AND version = ?""",
                (blob, instance_id, expected_version),
            )
            conn.commit()
            # rowcount == 1 means version matched and the row was updated;
            # rowcount == 0 means either the version conflicted or the
            # instance does not exist — either way the caller must retry.
            return cur.rowcount == 1
        except sqlite3.OperationalError as e:
            log.warning("save_state failed: %s", e)
            return False
        finally:
            conn.close()

    def backfill_state_blob(self) -> dict:
        """One-time migration: populate ``state`` blobs from ``node_states``.

        For each active workflow instance, read its ``node_states`` rows and
        construct a JSON blob of the form::

            {
              node_id: {
                "card_id": <str|null>,
                "card_status": <status looked up from the board, or None>,
                "output": <parsed output dict>,
                "iteration": 0,
                "_legacy_status": <the old node_states.status value>,
              },
              ...
            }

        then UPDATE the instance row with the blob (version stays at 0). The
        ``node_states`` table is left intact so old code keeps working.

        This is idempotent: running it twice rewrites the same blobs. Returns a
        stats dict ``{"migrated": N, "skipped": N, "errors": N}``.
        """
        self._ensure_schema()
        # Local import to avoid a hard dependency cycle at module load — the
        # board lookup is only needed during migration, not on the hot path.
        from .kanban_adapter import get_card

        migrated = 0
        skipped = 0
        errors = 0

        conn = _db_connect(self.db_path)
        try:
            instances = conn.execute(
                "SELECT instance_id, board FROM workflow_instances WHERE status = 'active'"
            ).fetchall()
            for inst in instances:
                instance_id = inst["instance_id"]
                board = inst["board"]
                try:
                    ns_rows = conn.execute(
                        "SELECT node_id, status, card_id, output "
                        "FROM node_states WHERE instance_id = ?",
                        (instance_id,),
                    ).fetchall()
                except sqlite3.OperationalError as e:
                    log.warning("backfill: cannot read node_states for %s: %s", instance_id, e)
                    errors += 1
                    continue

                if not ns_rows:
                    skipped += 1
                    continue

                blob: dict[str, dict] = {}
                for ns_row in ns_rows:
                    node_id = ns_row["node_id"]
                    card_id = ns_row["card_id"]
                    # Parse the stored output defensively — a corrupt row must
                    # not abort the whole migration.
                    try:
                        output = json.loads(ns_row["output"]) if ns_row["output"] else {}
                    except (json.JSONDecodeError, TypeError):
                        log.warning(
                            "backfill: corrupt output for %s/%s, using {}",
                            instance_id, node_id,
                        )
                        output = {}

                    # card_status is looked up from the board (ground truth).
                    card_status = None
                    if card_id:
                        try:
                            card = get_card(board, card_id)
                            card_status = card.status if card else None
                        except Exception as e:
                            log.warning(
                                "backfill: card lookup failed for %s/%s: %s",
                                instance_id, node_id, e,
                            )

                    blob[node_id] = {
                        "card_id": card_id,
                        "card_status": card_status,
                        "output": output,
                        "iteration": 0,
                        "_legacy_status": ns_row["status"],
                    }

                conn.execute(
                    "UPDATE workflow_instances SET state = ? WHERE instance_id = ?",
                    (json.dumps(blob), instance_id),
                )
                migrated += 1
            conn.commit()
        except sqlite3.OperationalError as e:
            log.error("backfill_state_blob failed: %s", e)
            errors += 1
        finally:
            conn.close()

        log.info(
            "backfill_state_blob: migrated %d instance(s), skipped %d, errors %d",
            migrated, skipped, errors,
        )
        return {"migrated": migrated, "skipped": skipped, "errors": errors}

    def update_node_state(self, instance_id: str, node_id: str, status: NodeStatus,
                          card_id: str | None = None, output: dict | None = None):
        self._ensure_schema()
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
        self._ensure_schema()
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
        self._ensure_schema()
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

            # 1. Advance active instances via the stateless 3-pass tick.
            #    Instances created by the legacy path (pre-T5) are migrated on
            #    first contact: their node_states rows are folded into the blob.
            for inst in self.state.load_active_instances():
                actions += self._tick_instance(inst)

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

    def _tick_instance(self, inst: WorkflowInstance) -> list[str]:
        """T5 stateless tick: SYNC → RESET → ACTIVATE+DISPATCH (3 passes).

        Replaces the monotonic node-status model (_check_instance). Reads the
        instance's state blob via load_state, walks the graph template against
        it, and persists incrementally via save_state (optimistic versioning).

        The 8 dispatch shapes are reused from the legacy methods — they now
        record their results (card_id / outputs / done flags) into the blob
        instead of the node_states table.
        """
        actions: list[str] = []

        # ZOMBIE GUARD — preserved (reads completed_at DB column).
        if inst.completed_at is not None:
            actions.append(
                f"SKIP zombie instance {inst.instance_id}: previously completed "
                f"at {inst.completed_at}, will not re-dispatch (reactivate detected)"
            )
            self.state.complete_instance(inst.instance_id)
            return actions

        # DELETED BOARD GUARD — preserved.
        if inst.board and not board_db_path(inst.board).exists():
            actions.append(
                f"WARNING instance {inst.instance_id}: board '{inst.board}' not "
                f"found (missing) — marking instance complete to stop zombie cycling"
            )
            self.state.complete_instance(inst.instance_id)
            return actions

        wf = self.store.load(inst.workflow_id)
        if not wf:
            actions.append(f"SKIP instance {inst.instance_id}: template {inst.workflow_id} not found")
            return actions

        # Load the state blob (with optimistic version). Legacy instances
        # (created pre-T5) have an empty blob — fold their node_states in.
        blob_holder = self.state.load_state(inst.instance_id)
        state_nodes: dict[str, dict] = blob_holder["state"]
        version = blob_holder["version"]
        if not state_nodes:
            state_nodes = self._migrate_legacy_node_states(inst, wf)
            # Persist the migrated blob so subsequent ticks skip this step.
            if self.state.save_state(inst.instance_id, state_nodes, version):
                version += 1

        # Ensure every template node has a state entry (lazily created).
        for node in wf.nodes:
            state_nodes.setdefault(node.id, {})

        # ─── PASS 1: SYNC (read board truth into state) ──────────────────
        actions += self._sync_pass(inst, wf, state_nodes)
        # Persist any sync mutations (card_status / output reads).
        version, ok = self._persist(inst.instance_id, state_nodes, version)
        if not ok:
            return actions  # version conflict — abort tick

        # ─── PASS 2: RESET (handle back-edges) ───────────────────────────
        ctx = self._build_ctx(inst, state_nodes)
        self._reset_pass(inst, wf, state_nodes, ctx)
        version, ok = self._persist(inst.instance_id, state_nodes, version)
        if not ok:
            return actions  # version conflict — abort tick

        # ─── PASS 3: ACTIVATE + DISPATCH ─────────────────────────────────
        # Rebuild ctx after resets so dispatch sees the post-reset state.
        ctx = self._build_ctx(inst, state_nodes)
        actions += self._activate_dispatch_pass(inst, wf, state_nodes, ctx, version)

        # ─── Completion check (after pass 3) ─────────────────────────────
        if self._check_completion(inst, wf, state_nodes):
            self.state.complete_instance(inst.instance_id)
            actions.append(f"WORKFLOW COMPLETE: {inst.workflow_id} ({inst.instance_id})")
            self.state.log_event("INFO", "workflow_completed",
                f"Workflow {inst.workflow_id} completed",
                instance_id=inst.instance_id, workflow_id=inst.workflow_id, board=inst.board)

        # Log all actions from this tick.
        self._log_actions(actions, inst)
        return actions

    # ── helpers for the stateless tick ───────────────────────────────────

    def _migrate_legacy_node_states(self, inst: WorkflowInstance, wf: Workflow) -> dict[str, dict]:
        """Fold a legacy instance's node_states rows into a state blob.

        One-time migration when a pre-T5 instance is first seen by the new
        tick. Maps (card_id, status, output) → blob shape. ``card_status`` is
        read from the board when possible (the ground truth).
        """
        blob: dict[str, dict] = {}
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if ns is None:
                blob[node.id] = {}
                continue
            card_status = ""
            if ns.card_id:
                try:
                    card = get_card(inst.board, ns.card_id) if inst.board else None
                    card_status = card.status if card else ""
                except Exception:
                    card_status = ""
            entry: dict = {
                "card_id": ns.card_id,
                "card_status": card_status,
                "output": dict(ns.output or {}),
                "iteration": 0,
            }
            # Translate the legacy monotonic status into the derived model.
            if ns.status == NodeStatus.DONE:
                entry["card_status"] = entry["card_status"] or "done"
            elif ns.status == NodeStatus.FAILED:
                entry["failed"] = True
            elif ns.status == NodeStatus.SKIPPED:
                entry["skipped"] = True
            blob[node.id] = entry
        return blob

    def _build_ctx(self, inst: WorkflowInstance, state_nodes: dict[str, dict]) -> dict:
        """Build the variable context from trigger_context + node outputs in the blob."""
        ctx: dict = {}
        for k, v in inst.trigger_context.items():
            ctx[f"trigger.{k}"] = v
        for node_id, ns in state_nodes.items():
            output = ns.get("output") or {}
            if isinstance(output, dict):
                for k, v in output.items():
                    ctx[f"nodes.{node_id}.output.{k}"] = v
            # Expose the node's iteration counter so back-edge conditions can
            # gate on it (e.g. "${nodes.build.iteration} < 3"). Iteration 0 is
            # the first run; it resets/bumps on each back-edge reset.
            ctx[f"nodes.{node_id}.iteration"] = ns.get("iteration", 0)
        return ctx

    @staticmethod
    def _iter_suffix(iteration: int) -> str:
        """The idempotency-key fragment for a node's iteration.

        Iteration 0 (the first run) emits an EMPTY suffix so the key stays
        backwards-compatible with existing in-flight DAG instances
        (``wf:<inst>:<node>`` unchanged). Iteration 1+ emits ``:iter<N>``
        which must precede any item-specific suffix (foreach index, chain
        child, subworkflow child) per DESIGN §Idempotency.
        """
        return f":iter{iteration}" if iteration and iteration > 0 else ""

    def _persist(self, instance_id: str, state_nodes: dict[str, dict],
                 version: int) -> tuple[int, bool]:
        """Incremental optimistic save. Returns (new_version, success).
        On conflict returns (same_version, False) — caller should abort."""
        if self.state.save_state(instance_id, state_nodes, version):
            return version + 1, True
        return version, False

    def _sync_pass(self, inst: WorkflowInstance, wf: Workflow,
                   state_nodes: dict[str, dict]) -> list[str]:
        """PASS 1 SYNC: read board truth into state. No decisions, no dispatch.

        For each task node with a card_id, read the card from the board and
        update card_status. When a card is done/archived AND its output hasn't
        been read yet, read + validate the metadata. Foreach/subworkflow nodes
        sync their child statuses here too.
        """
        actions: list[str] = []
        valid_ids = {n.id for n in wf.nodes}

        # Prune stale nodes (template edited to remove a node).
        for nid in list(state_nodes.keys()):
            if nid not in valid_ids:
                log.warning("Pruning stale node '%s' from instance %s state", nid, inst.instance_id)
                del state_nodes[nid]

        for node in wf.nodes:
            ns = state_nodes.get(node.id, {})
            if ns.get("skipped") or ns.get("failed"):
                continue  # terminal flag set by pass 3 — don't re-sync

            # foreach task: sync ALL card statuses, aggregate when all done.
            if node.foreach and node.type == "task":
                self._sync_foreach_task(inst, node, ns)
                continue

            # foreach subworkflow: sync child statuses.
            if node.foreach and node.type == "subworkflow":
                self._sync_foreach_subworkflow(inst, node, ns)
                continue

            # single subworkflow: sync child completion + output mapping.
            if node.type == "subworkflow":
                self._sync_subworkflow(inst, node, ns)
                continue

            # command/wait: synchronous, no board race — skip sync.
            if node.type in ("command", "wait"):
                continue

            # task (single card): read card status from board.
            card_id = ns.get("card_id")
            if not card_id or not inst.board:
                continue
            card = get_card(inst.board, card_id)
            if not card:
                actions.append(f"WARNING node {node.id}: card {card_id} not found on board (dangling)")
                continue
            prev_status = ns.get("card_status")
            ns["card_status"] = card.status

            # When the card reaches done/archived, read + validate output once.
            if card.status in ("done", "archived") and not ns.get("output"):
                meta = get_card_metadata(inst.board, card_id)
                output = meta.get("metadata", {})
                if node.output and node.output.schema:
                    valid, err = validate_output(inst.board, card_id, node.output.schema)
                    if not valid:
                        log.warning("VALIDATION FAILED node %s (card %s): %s", node.id, card_id, err)
                        ns["failed"] = True
                        ns["output"] = {"_validation_error": err}
                        actions.append(f"VALIDATION FAILED node {node.id} (card {card_id}) on {inst.board}: {err}")
                        continue
                ns["output"] = output
                # Preserve the legacy "DONE node X" action string so external
                # observers (tests, event-log consumers) see identical output.
                actions.append(f"DONE node {node.id} (card {card_id}) on {inst.board}")
            elif prev_status != card.status:
                actions.append(f"SYNC node {node.id} card {card_id}: {prev_status}→{card.status}")
        return actions

    def _sync_foreach_task(self, inst: WorkflowInstance, node: Node, ns: dict):
        """Sync all foreach card statuses from the board; aggregate when all done."""
        card_ids = ns.get("cards", []) or []
        if not card_ids:
            return
        statuses: list[str] = []
        results: list[dict] = []
        for cid in card_ids:
            card = get_card(inst.board, cid) if inst.board else None
            statuses.append(card.status if card else "")
            if card and card.status in ("done", "archived"):
                meta = get_card_metadata(inst.board, cid) if inst.board else {}
                results.append(meta.get("metadata", {}))
        ns["card_statuses"] = statuses
        if statuses and all(s in ("done", "archived") for s in statuses):
            # All done — store the aggregate output once.
            if not ns.get("output") or ns.get("output", {}).get("results") != results:
                ns["output"] = {"cards": card_ids, "results": results}

    def _sync_subworkflow(self, inst: WorkflowInstance, node: Node, ns: dict):
        """Sync a single subworkflow child's completion into the node state.

        Reads the child instance's status + mapped outputs from the child's
        state blob (cross-instance read, DESIGN §Cross-Instance Reads).
        """
        child_id = ns.get("child_instance_id")
        if not child_id or ns.get("done"):
            return
        child_status = self._read_instance_status(child_id)
        if child_status != "completed":
            return
        mapped = self._map_child_outputs(inst, node, child_id)
        # Hard output validation against the parent node's output schema.
        if node.output and node.output.schema:
            valid, err = validate_against_schema(mapped, node.output.schema)
            if not valid:
                log.warning("VALIDATION FAILED subworkflow node %s: %s", node.id, err)
                ns["failed"] = True
                ns["output"] = mapped
                ns["done"] = False
                return
        ns["done"] = True
        ns["outputs"] = mapped
        ns["output"] = mapped

    def _sync_foreach_subworkflow(self, inst: WorkflowInstance, node: Node, ns: dict):
        """Sync all foreach-subworkflow child statuses; aggregate when all done."""
        child_ids = ns.get("child_instance_ids", []) or []
        if not child_ids:
            return
        results: list[dict] = []
        all_done = True
        for cid in child_ids:
            child_status = self._read_instance_status(cid)
            if child_status != "completed":
                all_done = False
                break
            child_outputs = self._read_child_outputs(cid)
            results.append({"instance_id": cid, "outputs": child_outputs})
        if all_done:
            ns["done"] = True
            ns["results"] = results
            ns["output"] = {"child_instance_ids": child_ids, "results": results}

    def _reset_pass(self, inst: WorkflowInstance, wf: Workflow,
                    state_nodes: dict[str, dict], ctx: dict):
        """PASS 2 RESET: compute back-edge resets from a SNAPSHOT, then apply.

        A back-edge (from, to) triggers a reset of `to` when:
          - node_phase(from) == 'done'
          - the back-edge condition evaluates true (or has no condition)
          - node_phase(to) is terminal (done/failed)
        Reset = archive current state to iterations[], bump iteration, clear
        card_id/card_status (keep last-known-good output).
        """
        if not wf.edges:
            return  # no explicit edges → no back-edges
        back_edges = [e for e in wf.edges if e.is_back_edge]
        if not back_edges:
            return

        # Compute the reset set from a SNAPSHOT (don't mutate during compute).
        reset_targets: set[str] = set()
        for edge in back_edges:
            from_phase = _phase_of(wf, edge.from_node, state_nodes, ctx)
            if from_phase != PHASE_DONE:
                continue
            if edge.condition and not evaluate_condition(edge.condition, ctx):
                continue
            to_phase = _phase_of(wf, edge.to_node, state_nodes, ctx)
            if to_phase in (PHASE_DONE, PHASE_FAILED):
                reset_targets.add(edge.to_node)

        # Apply resets.
        for node_id in reset_targets:
            ns = state_nodes.get(node_id, {})
            iteration = ns.get("iteration", 0)
            # Enforce an explicit max_iterations cap if the edge declares one.
            cap = self._back_edge_cap(wf, node_id)
            if cap is not None and iteration >= cap:
                continue  # cap reached — don't reset again
            # Archive current state to the iterations[] audit trail (cap 10).
            iterations = ns.get("iterations", [])
            iterations.append({
                "iteration": iteration,
                "card_id": ns.get("card_id"),
                "card_status": ns.get("card_status"),
                "output": ns.get("output"),
            })
            if len(iterations) > 10:
                iterations = iterations[-10:]
            ns["iterations"] = iterations
            ns["card_id"] = None
            ns["card_status"] = ""
            ns["iteration"] = iteration + 1
            # Clear terminal flags so the node becomes dispatchable again.
            ns.pop("done", None)
            ns.pop("failed", None)
            ns.pop("skipped", None)
            # Keep `output` pointing at last-known-good (don't wipe).

    @staticmethod
    def _back_edge_cap(wf: Workflow, to_node_id: str) -> int | None:
        """The max_iterations cap on the back-edge pointing at to_node_id, if any."""
        for e in wf.edges:
            if e.is_back_edge and e.to_node == to_node_id and e.max_iterations is not None:
                return e.max_iterations
        return None

    def _activate_dispatch_pass(self, inst: WorkflowInstance, wf: Workflow,
                                state_nodes: dict[str, dict], ctx: dict,
                                version: int) -> list[str]:
        """PASS 3: walk the graph, evaluate activation, dispatch pending nodes.

        For each node:
          phase = node_phase(...)
          terminal/running → skip
          pending → check activation rule; if not satisfied, maybe mark skipped
                    (dead branch); if satisfied, validate inputs then dispatch.
        State is persisted AFTER each dispatch (incremental).
        """
        actions: list[str] = []
        cur_version = version

        for node in wf.nodes:
            ns = state_nodes.setdefault(node.id, {})
            phase = node_phase(node, ns)

            if phase in _TERMINAL_PHASES or phase == PHASE_RUNNING:
                continue

            # phase == pending → check if it should dispatch.
            if not activation_rule_satisfied(wf, node.id, state_nodes, ctx):
                if all_incoming_terminal_and_none_fired(wf, node.id, state_nodes, ctx):
                    ns["skipped"] = True
                    actions.append(f"SKIPPED node {node.id} on {inst.board} (dead branch)")
                    cur_version, _ok = self._persist(inst.instance_id, state_nodes, cur_version)
                    ctx = self._build_ctx(inst, state_nodes)  # propagate skip
                    continue
                # Entry node with a false condition: leave pending (may dispatch
                # later when conditions change). Removed P7 self-skip scope creep.
                continue

            # Input schema validation (fail fast).
            missing = self._check_required_inputs(node, ctx)
            if missing:
                log.warning("INPUT VALIDATION FAILED node %s on %s: missing %s",
                            node.id, inst.board, missing)
                ns["failed"] = True
                ns["output"] = {"_validation_error": f"missing required inputs: {missing}"}
                actions.append(f"INPUT VALIDATION FAILED node {node.id} on {inst.board}: missing {missing}")
                cur_version, _ok = self._persist(inst.instance_id, state_nodes, cur_version)
                ctx = self._build_ctx(inst, state_nodes)
                continue

            # Dispatch by type (9 shapes) — records into the blob.
            ok, msg, action = self._dispatch_by_type(inst, node, ns, ctx)
            if action:
                actions.append(action)
            cur_version, _ok = self._persist(inst.instance_id, state_nodes, cur_version)
            if not _ok:
                log.warning("version conflict during dispatch — aborting tick for %s", inst.instance_id)
                break
            # Rebuild ctx so a synchronous command/wait output is visible to
            # the next node evaluated in the same pass.
            if ok and node.type in ("command", "wait"):
                ctx = self._build_ctx(inst, state_nodes)
        return actions

    @staticmethod
    def _check_required_inputs(node: Node, ctx: dict) -> list[str]:
        """Return the list of required input fields that can't be resolved from ctx."""
        if not node.input or not node.input.schema:
            return []
        missing: list[str] = []
        for req_var in node.input.schema.get("required", []):
            source_expr = node.input.sources.get(req_var, "")
            if source_expr:
                source_key = strip_template_var(source_expr)
                if source_key not in ctx:
                    missing.append(req_var)
            elif req_var not in ctx and f"trigger.{req_var}" not in ctx:
                missing.append(req_var)
        return missing

    def _dispatch_by_type(self, inst: WorkflowInstance, node: Node,
                          ns: dict, ctx: dict) -> tuple[bool, str, str]:
        """Dispatch a node by type, recording the result into the state blob.

        Reuses the legacy dispatch methods (which still write to node_states for
        back-compat) but mirrors their effects into the blob. Returns
        (ok, detail, action_message). The action_message is '' when there's
        nothing to report (e.g. dedup-adopted an existing card).
        """
        board = inst.board

        # foreach command: synchronous, inline.
        if node.foreach and node.type == "command":
            ok, msg = self._run_foreach_command(inst, node, ctx)
            self._mirror_legacy_to_blob(inst, node, ns)
            return ok, msg, (f"DONE node {node.id} (foreach command: {msg}) on {board}" if ok else f"FAILED foreach command node {node.id} on {board}: {msg}")

        # foreach subworkflow: N child instances.
        if node.foreach and node.type == "subworkflow":
            ok, msg = self._dispatch_foreach_subworkflow(inst, node, ctx, ns)
            self._mirror_legacy_to_blob(inst, node, ns)
            return ok, msg, (f"DISPATCHED node {node.id} (foreach subworkflow: {msg}) on {board}" if ok else f"FAILED foreach subworkflow node {node.id} on {board}: {msg}")

        # foreach task: N cards.
        if node.foreach:
            ok, msg = self._dispatch_foreach_node(inst, node, ctx)
            self._mirror_legacy_to_blob(inst, node, ns)
            return ok, msg, (f"DISPATCHED node {node.id} (foreach: {msg} cards) on {board}" if ok else f"FAILED to dispatch foreach node {node.id} on {board}: {msg}")

        # subworkflow (single child).
        if node.type == "subworkflow":
            ok, msg = self._dispatch_subworkflow_node(inst, node, ctx, ns)
            self._mirror_legacy_to_blob(inst, node, ns)
            return ok, msg, (f"DISPATCHED node {node.id} (subworkflow: {node.workflow_ref}) on {board} → child {msg}" if ok else f"FAILED to dispatch subworkflow node {node.id} on {board}: {msg}")

        # command: synchronous.
        if node.type == "command":
            ok, msg = self._run_command_node(inst, node, ctx)
            self._mirror_legacy_to_blob(inst, node, ns)
            return ok, msg, (f"DONE node {node.id} (command) on {board}: {msg[:80]}" if ok else f"FAILED node {node.id} (command) on {board}: {msg[:80]}")

        # wait: poll condition.
        if node.type == "wait":
            ok, msg = self._check_wait_node(inst, node, ctx)
            self._mirror_legacy_to_blob(inst, node, ns)
            if ok:
                return ok, msg, f"DONE node {node.id} (wait resolved: {msg[:60]}) on {board}"
            return ok, msg, ""  # silently waiting

        # task (template/delegate/chain): single card.
        ok, msg = self._dispatch_node(inst, node, ctx, ns)
        self._mirror_legacy_to_blob(inst, node, ns)
        return ok, msg, (f"DISPATCHED node {node.id} on {board} → card {msg}" if ok else f"FAILED to dispatch node {node.id} on {board}: {msg}")

    def _mirror_legacy_to_blob(self, inst: WorkflowInstance, node: Node, ns: dict):
        """Copy the just-written node_states row back into the blob entry.

        The legacy dispatch methods write to the ``node_states`` DB table (via
        ``update_node_state``) but do NOT update ``inst.node_states`` in memory.
        So we re-read the row from the DB — that's where the real post-dispatch
        state lives — and mirror it into the blob.
        """
        legacy = self._load_one_node_state(inst.instance_id, node.id)
        if legacy is None:
            return
        card_id, status, output = legacy
        iteration = ns.get("iteration", 0)
        ns["iteration"] = iteration

        if card_id and not ns.get("card_id"):
            ns["card_id"] = card_id

        # foreach task: card ids live in the output under _foreach_cards.
        if node.foreach and node.type == "task":
            cards = (output or {}).get("_foreach_cards") or []
            if cards:
                ns["cards"] = cards
                statuses = []
                for cid in cards:
                    card = get_card(inst.board, cid) if inst.board else None
                    statuses.append(card.status if card else "")
                ns["card_statuses"] = statuses
        # foreach subworkflow: child ids in output under _foreach_instances.
        if node.type == "subworkflow" and node.foreach:
            child_ids = (output or {}).get("_foreach_instances") or []
            if child_ids:
                ns["child_instance_ids"] = child_ids
        elif node.type == "subworkflow":
            child_id = (output or {}).get("_child_instance")
            if child_id:
                ns["child_instance_id"] = child_id
        # command/wait: mirror the done flag + output.
        if node.type in ("command", "wait"):
            if status == "done":
                ns["done"] = True
            if output:
                ns["output"] = dict(output)
        # task single card: mirror card_status from board.
        if (not node.foreach) and node.type == "task" and card_id:
            card = get_card(inst.board, card_id) if inst.board else None
            if card:
                ns["card_status"] = card.status
        # Propagate failed/skipped.
        if status == "failed":
            ns["failed"] = True
        if status == "skipped":
            ns["skipped"] = True
        # task single card output: adopt when done.
        if output and node.type == "task" and not node.foreach:
            if status == "done":
                ns["output"] = dict(output)

    def _load_one_node_state(self, instance_id: str, node_id: str) -> tuple[str | None, str, dict] | None:
        """Read a single node_states row from the DB. Returns (card_id, status, output)."""
        conn = _db_connect(self.state.db_path)
        try:
            row = conn.execute(
                "SELECT card_id, status, output FROM node_states WHERE instance_id = ? AND node_id = ?",
                (instance_id, node_id),
            ).fetchone()
            if row is None:
                return None
            try:
                output = json.loads(row["output"]) if row["output"] else {}
            except (json.JSONDecodeError, TypeError):
                output = {}
            return row["card_id"], row["status"], output
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

    def _check_completion(self, inst: WorkflowInstance, wf: Workflow,
                          state_nodes: dict[str, dict]) -> bool:
        """Completion fence: re-read board truth for exit nodes, then check
        that all reachable exit nodes are terminal. See DESIGN §Completion."""
        if not wf.nodes:
            return False

        ctx = self._build_ctx(inst, state_nodes)
        # Exit nodes = nodes that nothing else depends on (no outgoing edges).
        # For explicit edges: a node with no edge.from_node. For implicit edges:
        # a node that no other node lists in its depends_on.
        has_explicit = bool(wf.edges)
        if has_explicit:
            has_outgoing = {e.from_node for e in wf.edges}
            exit_nodes = [n for n in wf.nodes if n.id not in has_outgoing]
        else:
            depended_on = {dep for n in wf.nodes for dep in n.depends_on}
            exit_nodes = [n for n in wf.nodes if n.id not in depended_on]

        # If the graph has no exit nodes, it can't meaningfully complete.
        # (Self-deps, pure cycles, etc. — load-time validation catches most,
        # but implicit-edge templates can sneak through.)
        if not exit_nodes:
            return False

        # Completion fence: re-read board truth for each exit node.
        for exit_node in exit_nodes:
            ns = state_nodes.get(exit_node.id, {})
            if exit_node.foreach and exit_node.type == "task":
                for cid in ns.get("cards", []):
                    card = get_card(inst.board, cid) if inst.board else None
                    if not card or card.status not in ("done", "archived"):
                        return False
            elif exit_node.type == "subworkflow" or (exit_node.foreach and exit_node.type == "subworkflow"):
                child_ids = ns.get("child_instance_ids") or ([ns["child_instance_id"]] if ns.get("child_instance_id") else [])
                for cid in child_ids:
                    if self._read_instance_status(cid) != "completed":
                        return False
            elif ns.get("card_id") and exit_node.type == "task":
                card = get_card(inst.board, ns["card_id"]) if inst.board else None
                if not card or card.status not in ("done", "archived"):
                    return False

        # All exit nodes must be terminal.
        for exit_node in exit_nodes:
            phase = node_phase(exit_node, state_nodes.get(exit_node.id, {}))
            if phase not in _TERMINAL_PHASES:
                return False

        # If there are no exit nodes AND no terminal nodes yet, the graph is a
        # pure cycle (or all-pending) — it must not complete. This catches the
        # Reachability: ignore structurally disconnected components.
        # Load-time validation already rejects templates with no exit nodes
        # (unless explicit exit_condition), so the pure-cycle case is impossible.
        reachable = self._reachable_nodes(wf, state_nodes, ctx)
        for node in wf.nodes:
            if node.id not in reachable:
                continue  # orphan subgraph — doesn't block completion
            phase = node_phase(node, state_nodes.get(node.id, {}))
            if phase not in _TERMINAL_PHASES:
                return False
        return True

    def _reachable_nodes(self, wf: Workflow, state_nodes: dict[str, dict],
                         ctx: dict) -> set[str]:
        """BFS from all dispatched/done nodes following ALL edges (regardless
        of condition). Any node NOT visited is structurally unreachable."""
        # Seed: only nodes that are done or running (dispatched).
        # Per DESIGN §Reachability: "BFS from all dispatched/done nodes."
        seeds = {n.id for n in wf.nodes
                 if node_phase(n, state_nodes.get(n.id, {})) in (PHASE_DONE, PHASE_RUNNING)}
        visited: set[str] = set(seeds)
        queue = list(seeds)
        edges = wf.edges or [Edge(from_node=d, to_node=n.id)
                             for n in wf.nodes for d in n.depends_on]
        while queue:
            cur = queue.pop()
            for e in edges:
                if e.from_node == cur and e.to_node not in visited:
                    visited.add(e.to_node)
                    queue.append(e.to_node)
        return visited

    def _read_instance_status(self, instance_id: str) -> str:
        """Read a workflow instance's status column (fresh, not cached)."""
        conn = _db_connect(self.state.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM workflow_instances WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            return row["status"] if row else ""
        except sqlite3.OperationalError:
            return ""
        finally:
            conn.close()

    def _read_child_outputs(self, child_instance_id: str) -> dict:
        """Read a child instance's node outputs from its state blob.

        DESIGN §Cross-Instance Reads: couple through the instance row, not the
        node_states side table. Returns a flat ``nodes.<id>.output.<k>`` map.
        """
        holder = self.state.load_state(child_instance_id)
        child_nodes = holder["state"]
        outputs: dict = {}
        for node_id, node_state in child_nodes.items():
            output = node_state.get("output", {})
            if isinstance(output, dict):
                for k, v in output.items():
                    outputs[f"nodes.{node_id}.output.{k}"] = v
        return outputs

    def _map_child_outputs(self, inst: WorkflowInstance, node: Node,
                           child_instance_id: str) -> dict:
        """5-step child completion: read outputs → map via output_mapping.

        Preserved from the legacy _check_subworkflow_completion. Reads from the
        child's state blob instead of node_states.
        """
        child_outputs = self._read_child_outputs(child_instance_id)
        mapped: dict = {"_child_instance": child_instance_id}
        if node.output_mapping:
            for parent_key, child_expr in node.output_mapping.items():
                if (isinstance(child_expr, str) and child_expr.startswith("${")
                        and child_expr.endswith("}")):
                    child_var = strip_template_var(child_expr)
                    mapped[parent_key] = child_outputs.get(child_var, "")
                else:
                    mapped[parent_key] = child_expr
        else:
            # No mapping — flatten all child outputs (strip nodes.X.output.).
            for k, v in child_outputs.items():
                if ".output." in k:
                    mapped[k.split(".output.", 1)[1]] = v
        return mapped

    def _log_actions(self, actions: list[str], inst: WorkflowInstance):
        """Log each action string to the engine_events table."""
        for action in actions:
            level = "INFO"
            event_type = "action"
            if "COMPLETE" in action:
                event_type = "workflow_completed"
            elif "FAILED" in action:
                level = "ERROR"
                event_type = "node_failed"
            elif "DISPATCHED" in action:
                event_type = "node_dispatched"
            elif "DONE" in action:
                event_type = "node_done"
            elif "SKIPPED" in action:
                event_type = "node_skipped"
            elif "STARTED" in action:
                event_type = "trigger_fired"
            self.state.log_event(level, event_type, action,
                                 instance_id=inst.instance_id,
                                 workflow_id=inst.workflow_id, board=inst.board)

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
                any_blocked = False
                results = []
                for fcid in foreach_cards:
                    fcard = get_card(inst.board, fcid)
                    if not fcard:
                        actions.append(f"WARNING foreach node {node.id}: card {fcid} not found (dangling)")
                        all_done = False
                        break
                    if fcard.status == "done" or fcard.status == "archived":
                        fmeta = get_card_metadata(inst.board, fcid)
                        results.append(fmeta.get("metadata", {}))
                    elif fcard.status == "blocked":
                        all_done = False
                        any_blocked = True
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
                elif any_blocked:
                    actions.append(f"BLOCKED foreach node {node.id} — one or more cards blocked")
                continue

            # FOREACH SUBWORKFLOW completion: check all child instances
            foreach_instances = ns.output.get("_foreach_instances") if ns.output else None
            if foreach_instances is not None:
                all_done = True
                results = []
                for child_id in foreach_instances:
                    conn = _db_connect(self.state.db_path)
                    try:
                        row = conn.execute(
                            "SELECT status FROM workflow_instances WHERE instance_id = ?",
                            (child_id,),
                        ).fetchone()
                        if not row or row["status"] != "completed":
                            all_done = False
                        else:
                            # Collect child outputs
                            child_nodes = conn.execute(
                                "SELECT node_id, output FROM node_states WHERE instance_id = ?",
                                (child_id,),
                            ).fetchall()
                            child_output = {}
                            for cn in child_nodes:
                                try:
                                    child_output[cn["node_id"]] = json.loads(cn["output"]) if cn["output"] else {}
                                except (json.JSONDecodeError, TypeError):
                                    child_output[cn["node_id"]] = {}
                            results.append({"instance_id": child_id, "nodes": child_output})
                    except sqlite3.OperationalError:
                        all_done = False
                    finally:
                        conn.close()

                if all_done:
                    aggregated = {"_foreach_instances": foreach_instances, "results": results}
                    self.state.update_node_state(
                        inst.instance_id, node.id, NodeStatus.DONE, None, aggregated
                    )
                    ns.status = NodeStatus.DONE
                    ns.output = aggregated
                    actions.append(f"DONE foreach subworkflow node {node.id} ({len(foreach_instances)} instances) on {inst.board}")
                continue

            # Standard single-card completion check
            if not ns.card_id:
                continue

            card = get_card(inst.board, ns.card_id)
            if not card:
                # Dangling card_id — flag it but don't crash
                actions.append(f"WARNING node {node.id}: card {ns.card_id} not found on board (dangling)")
                continue

            if card.status == "done" or card.status == "archived":
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

        # If the workflow declares explicit edges, use them for dependency
        # resolution + conditions. Otherwise fall back to implicit depends_on.
        has_explicit_edges = bool(wf.edges)

        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.PENDING:
                continue

            if has_explicit_edges:
                # Find all edges pointing TO this node
                incoming = [e for e in wf.edges if e.to_node == node.id]
                if not incoming:
                    # No incoming edges — entry node, always dispatchable
                    pass
                else:
                    # Edge routing semantics:
                    # - Unconditional edges (no condition field): ALL sources
                    #   must be DONE (AND semantics — dependency convergence).
                    # - Conditional edges (has condition field): ANY source
                    #   DONE + condition passes activates the node (OR semantics
                    #   — conditional diamond routing like review→ship | review→fix).
                    # - Edges from SKIPPED/FAILED sources are ignored.
                    unconditional = [e for e in incoming if not e.condition]
                    conditional = [e for e in incoming if e.condition]

                    # Check unconditional edges: ALL must be DONE (or terminal)
                    unconditional_ok = True
                    all_sources_terminal = True
                    for edge in unconditional:
                        dep_ns = inst.node_states.get(edge.from_node)
                        if dep_ns is None:
                            unconditional_ok = False
                            all_sources_terminal = False
                            continue
                        if dep_ns.status == NodeStatus.DONE:
                            pass  # good — this dep is done
                        elif dep_ns.status in (NodeStatus.SKIPPED, NodeStatus.FAILED):
                            pass  # terminal but didn't run — ignore edge
                        else:
                            # Pending/dispatched — not done yet
                            unconditional_ok = False
                            all_sources_terminal = False

                    # Check conditional edges: ANY done + condition passes
                    conditional_ok = False
                    for edge in conditional:
                        dep_ns = inst.node_states.get(edge.from_node)
                        if dep_ns is None:
                            all_sources_terminal = False
                            continue
                        if dep_ns.status == NodeStatus.DONE:
                            if evaluate_condition(edge.condition, ctx):
                                conditional_ok = True
                                break
                        elif dep_ns.status in (NodeStatus.SKIPPED, NodeStatus.FAILED):
                            continue
                        else:
                            all_sources_terminal = False

                    # Activation: unconditional edges all done AND
                    # (conditional edges ok OR no conditional edges)
                    has_active_edge = unconditional_ok and (conditional_ok or not conditional)

                    if has_active_edge:
                        pass  # Fall through to dispatch
                    elif all_sources_terminal:
                        # All sources reached terminal state but none activated
                        self.state.update_node_state(
                            inst.instance_id, node.id, NodeStatus.SKIPPED, None, {},
                        )
                        ns.status = NodeStatus.SKIPPED
                        actions.append(f"SKIPPED node {node.id} on {inst.board} (no edge condition passed)")
                        continue
                    else:
                        # Some sources still pending — wait
                        continue
            else:
                # Implicit: use node.depends_on + node.condition
                deps = node.depends_on
                deps_done = all(
                    (dep_ns.status == NodeStatus.DONE)
                    for dep in deps
                    if (dep_ns := inst.node_states.get(dep)) is not None
                )
                all_deps_tracked = all(dep in inst.node_states for dep in deps)
                if not deps_done or not all_deps_tracked:
                    continue

                if node.condition and not evaluate_condition(node.condition, ctx):
                    # Mark as SKIPPED so the all_done check can complete the workflow
                    self.state.update_node_state(
                        inst.instance_id, node.id, NodeStatus.SKIPPED, None, {},
                    )
                    ns = inst.node_states.get(node.id)
                    if ns:
                        ns.status = NodeStatus.SKIPPED
                    actions.append(f"SKIPPED node {node.id} on {inst.board} (condition false)")
                    continue

            # INPUT SCHEMA VALIDATION: if the node declares an input schema,
            # verify all required inputs can be resolved from context.
            # Uses node.input.sources to know which context keys feed each input.
            if node.input and node.input.schema:
                required = node.input.schema.get("required", [])
                missing = []
                for req_var in required:
                    # Check if the variable is available in context.
                    # Look up via input.sources mapping, then direct context lookup.
                    source_expr = node.input.sources.get(req_var, "")
                    if source_expr:
                        # Resolve the source variable key
                        source_key = strip_template_var(source_expr)
                        if source_key not in ctx:
                            missing.append(req_var)
                    elif req_var not in ctx and f"trigger.{req_var}" not in ctx:
                        missing.append(req_var)
                if missing:
                    log.warning(
                        "INPUT VALIDATION FAILED node %s on %s: missing required inputs %s",
                        node.id, inst.board, missing,
                    )
                    self.state.update_node_state(
                        inst.instance_id, node.id, NodeStatus.FAILED, None,
                        {"_validation_error": f"missing required inputs: {missing}"},
                    )
                    ns = inst.node_states.get(node.id)
                    if ns:
                        ns.status = NodeStatus.FAILED
                    actions.append(
                        f"INPUT VALIDATION FAILED node {node.id} on {inst.board}: "
                        f"missing required inputs: {missing}"
                    )
                    continue

            if node.foreach and node.type == "command":
                # Foreach command: run command per item, no kanban cards.
                ok, msg = self._run_foreach_command(inst, node, ctx)
                if ok:
                    actions.append(f"DONE node {node.id} (foreach command: {msg}) on {inst.board}")
                else:
                    actions.append(f"FAILED foreach command node {node.id} on {inst.board}: {msg}")
            elif node.foreach and node.type == "subworkflow":
                # Foreach subworkflow: spawn one child workflow instance per item.
                # Each item runs independently through the child workflow — no barrier.
                ok, msg = self._dispatch_foreach_subworkflow(inst, node, ctx)  # legacy path, no ns
                if ok:
                    actions.append(f"DISPATCHED node {node.id} (foreach subworkflow: {msg}) on {inst.board}")
                else:
                    actions.append(f"FAILED foreach subworkflow node {node.id} on {inst.board}: {msg}")
            elif node.foreach:
                # Foreach node: resolve the list, create one card per item.
                ok, msg = self._dispatch_foreach_node(inst, node, ctx)
                if ok:
                    actions.append(f"DISPATCHED node {node.id} (foreach: {msg} cards) on {inst.board}")
                else:
                    actions.append(f"FAILED to dispatch foreach node {node.id} on {inst.board}: {msg}")
            elif node.type == "subworkflow":
                # Subworkflow node: start child workflow, block until it completes.
                ok, msg = self._dispatch_subworkflow_node(inst, node, ctx)  # legacy path, no ns
                if ok:
                    actions.append(f"DISPATCHED node {node.id} (subworkflow: {node.workflow_ref}) on {inst.board} → child {msg}")
                else:
                    actions.append(f"FAILED to dispatch subworkflow node {node.id} on {inst.board}: {msg}")
            elif node.type == "command":
                # Command node: run shell command synchronously, no kanban card.
                ok, msg = self._run_command_node(inst, node, ctx)
                if ok:
                    actions.append(f"DONE node {node.id} (command) on {inst.board}: {msg[:80]}")
                    # Rebuild context so downstream nodes in the same tick
                    # see this command's output.
                    ctx = inst.context()
                else:
                    actions.append(f"FAILED node {node.id} (command) on {inst.board}: {msg[:80]}")
            elif node.type == "wait":
                # Wait node: poll a condition each tick until it passes.
                ok, msg = self._check_wait_node(inst, node, ctx)
                if ok:
                    actions.append(f"DONE node {node.id} (wait resolved: {msg[:60]}) on {inst.board}")
                    ctx = inst.context()
                # else: silently wait
            else:
                ok, msg = self._dispatch_node(inst, node, ctx)
                if ok:
                    actions.append(f"DISPATCHED node {node.id} on {inst.board} → card {msg}")
                else:
                    actions.append(f"FAILED to dispatch node {node.id} on {inst.board}: {msg}")

        # Check if all nodes reached a terminal state → complete instance
        # Terminal states: DONE, FAILED, SKIPPED. PENDING/DISPATCHED are non-terminal.
        terminal_states = {NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.SKIPPED}
        if wf.nodes:
            all_done = all(
                ns is not None and ns.status in terminal_states
                for node in wf.nodes
                for ns in [inst.node_states.get(node.id)]
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
                    self.state.log_event("INFO", "workflow_completed",
                        f"Workflow {inst.workflow_id} completed",
                        instance_id=inst.instance_id, workflow_id=inst.workflow_id, board=inst.board)

        # Log all actions from this tick
        for action in actions:
            level = "INFO"
            event_type = "action"
            if "COMPLETE" in action:
                event_type = "workflow_completed"
            elif "FAILED" in action:
                level = "ERROR"
                event_type = "node_failed"
            elif "DISPATCHED" in action:
                event_type = "node_dispatched"
            elif "DONE" in action:
                event_type = "node_done"
            elif "SKIPPED" in action:
                event_type = "node_skipped"
            elif "STARTED" in action:
                event_type = "trigger_fired"

            self.state.log_event(level, event_type, action)

        return actions

    def _dispatch_node(self, inst: WorkflowInstance, node: Node, ctx: dict,
                       ns: dict | None = None) -> tuple[bool, str]:
        """Create a kanban card for a node. Idempotent via find_cards_by_idempotency_key.

        Branches on node.card_mode:
          - "template" (default): create a single card with the resolved body.
          - "delegate": create a meta-card assigned to the node's profile. The
            profile creates child cards itself (dev-dispatch pattern).
          - "chain": create a parent card + N child cards with parent-child links.
            The node body_template may contain a JSON list of child specs; each
            child card links to the parent via --parent.

        ``ns`` is the node's state-blob entry; its ``iteration`` field feeds the
        iteration-aware idempotency key (DESIGN §Idempotency). ``None`` (legacy
        call path) is treated as iteration 0 → backwards-compatible key.
        """
        body = resolve_template(node.body_template or "", ctx)
        iter_suf = self._iter_suffix((ns or {}).get("iteration", 0))
        idem_key = f"wf:{inst.instance_id}:{node.id}{iter_suf}"

        # Check if already created (prevents double dispatch)
        existing = find_cards_by_idempotency_key(inst.board, idem_key)
        if existing:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DISPATCHED, existing[0].id
            )
            return True, existing[0].id

        workspace = f"dir:{inst.project_dir}" if inst.project_dir else None

        if node.card_mode == "delegate":
            return self._dispatch_delegate_node(inst, node, body, idem_key, workspace)
        elif node.card_mode == "chain":
            return self._dispatch_chain_node(inst, node, body, idem_key, workspace)
        else:
            # Default: "template" mode — single card with resolved body
            # Use title_template if provided, else fallback to default
            if node.title_template:
                card_title = resolve_template(node.title_template, ctx)
            else:
                card_title = f"[{node.id}] {node.skill or 'task'}"
            ok, output = create_card(
                board=inst.board,
                title=card_title,
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

    def _run_foreach_command(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Run a command node once per item in a foreach list. No kanban cards.

        Each iteration gets ${item} and ${item_index} in context.
        Output aggregates all results: {"results": [{"stdout": "...", ...}, ...]}.
        """
        import shlex

        foreach_var = node.foreach or ""
        var_key = strip_template_var(foreach_var)
        items = ctx.get(var_key)

        if items is None:
            return False, f"foreach variable '{foreach_var}' resolved to None"
        if not isinstance(items, list):
            return False, f"foreach variable '{foreach_var}' is not a list"
        if not items:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None,
                {"_foreach_cards": [], "results": []},
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.DONE
                ns.output = {"_foreach_cards": [], "results": []}
            return True, "0"

        results = []
        all_ok = True
        for idx, item in enumerate(items):
            item_ctx = dict(ctx)
            item_ctx["item"] = item
            item_ctx["item_index"] = idx
            # shlex-quote values for safety
            safe_ctx = {}
            for k, v in item_ctx.items():
                safe_ctx[k] = shlex.quote(str(v)) if isinstance(v, str) else shlex.quote(str(v))
            cmd = resolve_template(node.command or "", safe_ctx)
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=300, cwd=inst.project_dir or None,
                )
                item_output = {
                    "exit_code": result.returncode,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "item": item,
                }
                try:
                    parsed = json.loads(result.stdout.strip())
                    if isinstance(parsed, dict):
                        item_output.update(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
                results.append(item_output)
                if result.returncode != 0:
                    all_ok = False
            except subprocess.TimeoutExpired:
                results.append({"exit_code": -1, "stdout": "", "stderr": "timeout", "item": item})
                all_ok = False
            except Exception as e:
                results.append({"exit_code": -1, "stdout": "", "stderr": str(e), "item": item})
                all_ok = False

        status = NodeStatus.DONE if all_ok else NodeStatus.FAILED
        output = {"_foreach_commands": True, "results": results}
        self.state.update_node_state(
            inst.instance_id, node.id, status, None, output,
        )
        ns = inst.node_states.get(node.id)
        if ns:
            ns.status = status
            ns.output = output
        return all_ok, f"{len(items)} items, {'all OK' if all_ok else 'some failed'}"

    def _run_command_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Run a shell command synchronously. No kanban card, no agent.

        The command supports ${} variable substitution from context.
        Variable values are shlex-quoted to prevent shell injection.
        Output is captured as the node's output dict:
          {"exit_code": N, "stdout": "...", "stderr": "..."}
        Exit code 0 = DONE. Non-zero = FAILED.

        The stdout is also parsed as JSON if possible, merging keys into output.
        """
        import shlex

        # Resolve variables but quote their values to prevent injection.
        # First, collect all variable values from ctx and shlex-quote them.
        safe_ctx = {}
        for k, v in ctx.items():
            if isinstance(v, str):
                safe_ctx[k] = shlex.quote(v)
            else:
                safe_ctx[k] = shlex.quote(str(v))
        cmd = resolve_template(node.command or "", safe_ctx)
        self.state.log_event("DEBUG", "command_run",
            f"Running command: {cmd[:200]}",
            instance_id=inst.instance_id, node_id=node.id, board=inst.board,
            metadata={"command": cmd[:500]})

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=300,  # 5 min max
                cwd=inst.project_dir or None,
            )
        except subprocess.TimeoutExpired:
            output = {"exit_code": -1, "stdout": "", "stderr": "command timed out after 300s"}
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.FAILED, None, output,
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.FAILED
                ns.output = output
            return False, "command timed out"
        except Exception as e:
            output = {"exit_code": -1, "stdout": "", "stderr": str(e)}
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.FAILED, None, output,
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.FAILED
                ns.output = output
            return False, str(e)

        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

        # Try to parse stdout as JSON and merge into output
        try:
            parsed = json.loads(result.stdout.strip())
            if isinstance(parsed, dict):
                output.update(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

        if result.returncode == 0:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None, output,
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.DONE
                ns.output = output
            return True, result.stdout.strip()[:200]
        else:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.FAILED, None, output,
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.FAILED
                ns.output = output
            return False, f"exit {result.returncode}: {result.stderr.strip()[:200]}"



    def _check_wait_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Poll a condition each tick until it evaluates true.

        The wait_condition is a standard condition string (same format as
        node.condition): "${nodes.X.output.Y} == 'value'" or "${trigger.Z} exists".

        Once the condition passes, the node marks DONE. The node output
        includes the condition result for downstream use.
        """
        cond = node.wait_condition or ""
        if not cond:
            # No condition — fire immediately
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None, {"resolved": True},
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.DONE
                ns.output = {"resolved": True}
            return True, "no condition — resolved immediately"

        if evaluate_condition(cond, ctx):
            output = {"resolved": True, "condition": cond}
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None, output,
            )
            ns = inst.node_states.get(node.id)
            if ns:
                ns.status = NodeStatus.DONE
                ns.output = output
            return True, f"condition passed: {cond[:60]}"
        else:
            return False, "condition not met yet"

    def _dispatch_delegate_node(self, inst: WorkflowInstance, node: Node, body: str,
                                idem_key: str, workspace: str | None) -> tuple[bool, str]:
        """Delegate mode: create a meta-card assigned to the node's profile.

        The profile is responsible for creating child cards itself. The
        meta-card's body instructs the profile what to do.
        """
        delegate_body = (
            body or ""
        )
        if not delegate_body.strip():
            delegate_body = (
                f"[DELEGATE] You are responsible for node '{node.id}'. "
                f"Create child kanban cards as needed to complete this work. "
                f"Skill: {node.skill or 'general'}."
            )

        ok, output = create_card(
            board=inst.board,
            title=f"[{node.id}] delegate: {node.skill or node.profile}",
            assignee=node.profile,
            body=delegate_body,
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

    def _dispatch_chain_node(self, inst: WorkflowInstance, node: Node, body: str,
                             idem_key: str, workspace: str | None) -> tuple[bool, str]:
        """Chain mode: create a parent card + N child cards with parent-child links.

        The node's body_template may contain a JSON list of child specs, e.g.:
          [{"id": "child1", "title": "...", "assignee": "..."}, ...]

        If the body is not a JSON list, we create a single parent card.
        Each child card links to the parent via --parent, forming a chain.
        """
        # Parse child specs from the body (if it's a JSON list)
        child_specs: list[dict] = []
        try:
            parsed = json.loads(body)
            if isinstance(parsed, list):
                child_specs = parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Create the parent card first
        parent_ok, parent_output = create_card(
            board=inst.board,
            title=f"[{node.id}] chain (parent)",
            assignee=node.profile,
            body=body if not child_specs else f"[CHAIN] Parent card for {node.id}. {len(child_specs)} children.",
            idempotency_key=idem_key,
            priority=10,
            workspace=workspace,
        )

        if not parent_ok:
            return False, parent_output

        try:
            parent_data = json.loads(parent_output)
            parent_card_id = parent_data.get("id", "")
        except (json.JSONDecodeError, TypeError):
            parent_card_id = ""

        if not parent_card_id:
            return False, "no parent card id in output"

        # Create child cards linked to the parent
        child_ids: list[str] = []
        for idx, spec in enumerate(child_specs):
            if not isinstance(spec, dict):
                continue
            child_idem = f"{idem_key}:chain:{idx}"
            child_title = spec.get("title", f"[{node.id}] child {idx}")
            child_assignee = spec.get("assignee", node.profile)
            child_body = spec.get("body", "")

            existing_child = find_cards_by_idempotency_key(inst.board, child_idem)
            if existing_child:
                child_ids.append(existing_child[0].id)
                continue

            cok, cout = create_card(
                board=inst.board,
                title=child_title,
                assignee=child_assignee,
                body=child_body,
                idempotency_key=child_idem,
                priority=10,
                workspace=workspace,
                parent=parent_card_id,
            )
            if cok:
                try:
                    cdata = json.loads(cout)
                    cid = cdata.get("id", "")
                    if cid:
                        child_ids.append(cid)
                except (json.JSONDecodeError, TypeError):
                    pass

        self.state.update_node_state(
            inst.instance_id, node.id, NodeStatus.DISPATCHED, parent_card_id
        )
        return True, parent_card_id

    def _dispatch_foreach_subworkflow(self, inst: WorkflowInstance, node: Node, ctx: dict,
                                      ns: dict | None = None) -> tuple[bool, str]:
        """Foreach subworkflow: spawn one child workflow instance per item.

        Each item gets its own independent workflow instance. When item A's
        grill completes, its build starts immediately — no barrier waiting
        for all items to complete grill before any build starts.

        The node completes when ALL child instances complete.
        """
        foreach_var = node.foreach
        var_key = strip_template_var(foreach_var)
        items = ctx.get(var_key)

        if items is None:
            return False, f"foreach variable '{foreach_var}' resolved to None"
        if not isinstance(items, list):
            return False, f"foreach variable '{foreach_var}' is not a list"
        if not items:
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DONE, None,
                {"_foreach_instances": [], "results": []},
            )
            legacy_ns = inst.node_states.get(node.id)
            if legacy_ns:
                legacy_ns.status = NodeStatus.DONE
                legacy_ns.output = {"_foreach_instances": [], "results": []}
            # Mirror to state blob so node_phase sees it as done
            if ns is not None:
                ns["done"] = True
                ns["output"] = {"_foreach_instances": [], "results": []}
            return True, "0"

        child_wf_id = node.workflow_ref
        if not child_wf_id:
            return False, "subworkflow node missing workflow_ref"
        child_wf = self.store.load(child_wf_id)
        if not child_wf:
            return False, f"child workflow template not found: {child_wf_id}"

        child_instance_ids: list[str] = []

        for idx, item in enumerate(items):
            # Build child context from input_mapping + item
            child_context = {}
            for key, expr in node.input_mapping.items():
                if isinstance(expr, str) and expr.startswith("${") and expr.endswith("}"):
                    ev = strip_template_var(expr)
                    child_context[key] = ctx.get(ev, "")
                else:
                    child_context[key] = expr
            # Inject item fields into child context (bare keys)
            if isinstance(item, dict):
                for ik, iv in item.items():
                    child_context[ik] = iv
            else:
                child_context["item"] = item
            child_context["item_index"] = idx
            child_context.setdefault("board", inst.board)
            child_context.setdefault("parent_instance", inst.instance_id)
            child_context.setdefault("parent_node", node.id)

            # Idempotency: check if child already started
            idem_key = f"wf:{inst.instance_id}:{node.id}{self._iter_suffix((ns or {}).get('iteration', 0))}:sw:{idx}"
            existing = find_cards_by_idempotency_key(inst.board, idem_key)
            if existing:
                # Child was tracked via idempotency key — find its instance
                # The instance ID is stored in the card metadata
                meta = get_card_metadata(inst.board, existing[0].id)
                if meta and meta.get("metadata", {}).get("_child_instance"):
                    child_instance_ids.append(meta["metadata"]["_child_instance"])
                    continue

            # Start child workflow
            child_id = self.start_manual(
                workflow_id=child_wf_id,
                board=inst.board,
                project_dir=inst.project_dir,
                context=child_context,
            )
            child_instance_ids.append(child_id)

            self.state.log_event("INFO", "subworkflow_spawned",
                f"Spawned child {child_wf_id} for item {idx}",
                instance_id=inst.instance_id, node_id=node.id,
                metadata={"child_instance": child_id, "item_index": idx})

        # Store child instance IDs, mark DISPATCHED
        output = {"_foreach_instances": child_instance_ids, "results": []}
        self.state.update_node_state(
            inst.instance_id, node.id, NodeStatus.DISPATCHED,
            None, output,
        )
        ns = inst.node_states.get(node.id)
        if ns:
            ns.status = NodeStatus.DISPATCHED
            ns.output = output
        return True, f"{len(child_instance_ids)} instances"

    def _dispatch_foreach_node(self, inst: WorkflowInstance, node: Node, ctx: dict,
                               ns: dict | None = None) -> tuple[bool, str]:
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
        var_key = strip_template_var(foreach_var)
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
        iter_suf = self._iter_suffix((ns or {}).get("iteration", 0)) if ns else ""
        card_ids: list[str] = []

        for idx, item in enumerate(items):
            # Build per-item context: the original ctx + ${item} = current item
            item_ctx = dict(ctx)
            item_ctx["item"] = item
            item_ctx["item_index"] = idx
            body = resolve_template(node.body_template or "", item_ctx)

            idem_key = f"wf:{inst.instance_id}:{node.id}{iter_suf}:{idx}"

            # Check if already created (idempotency across ticks)
            existing = find_cards_by_idempotency_key(inst.board, idem_key)
            if existing:
                card_ids.append(existing[0].id)
                continue

            # Use title_template if provided, else fallback to default
            if node.title_template:
                card_title = resolve_template(node.title_template, item_ctx)
            else:
                card_title = f"[{node.id}#{idx}] {node.skill or 'task'}"

            ok, output = create_card(
                board=inst.board,
                title=card_title,
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

    def _dispatch_subworkflow_node(self, inst: WorkflowInstance, node: Node, ctx: dict,
                                   ns: dict | None = None) -> tuple[bool, str]:
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
                var_key = strip_template_var(expr)
                child_context[key] = ctx.get(var_key, "")
            else:
                child_context[key] = expr
        # Always pass board + project_dir
        child_context.setdefault("board", inst.board)
        child_context.setdefault("parent_instance", inst.instance_id)
        child_context.setdefault("parent_node", node.id)

        # Idempotency: iteration-aware key for subworkflow dedup
        iter_suf = self._iter_suffix((ns or {}).get("iteration", 0))
        idem_key = f"wf:{inst.instance_id}:{node.id}{iter_suf}"
        existing = find_cards_by_idempotency_key(inst.board, idem_key)
        if existing:
            meta = get_card_metadata(inst.board, existing[0].id)
            if meta and meta.get("metadata", {}).get("_child_instance"):
                child_id = meta["metadata"]["_child_instance"]
                self.state.update_node_state(
                    inst.instance_id, node.id, NodeStatus.DISPATCHED, existing[0].id,
                    {"_child_instance": child_id},
                )
                return True, child_id

        # Check if child already started (legacy idempotency via node_states)
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
                child_var = strip_template_var(child_expr)
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
            valid, err = validate_against_schema(mapped_output, node.output.schema)
            if not valid:
                log.warning("VALIDATION FAILED subworkflow node %s: %s", node.id, err)
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
                        # Prevent engine-created cards from triggering other workflows.
                        # Cards created by the engine (idempotency_key starts with "wf:")
                        # are tracked by their parent workflow instance. If that instance
                        # has explicit edges, the routing is handled internally — no
                        # trigger-based workflow should also fire.
                        #
                        # Exception: if the card's workflow_id differs from the trigger's
                        # workflow_id AND the parent workflow has NO explicit edges, allow
                        # the trigger (backward compat for trigger-based composition).
                        # Self-trigger / cross-workflow suppression.
                        #
                        # Engine-created cards (idempotency_key starts with
                        # "wf:") are routed by the engine itself. We parse the
                        # parent workflow ID deterministically (see
                        # _extract_parent_workflow) and apply two rules:
                        #   1. Same-workflow self-trigger → always block
                        #      (prevents infinite trigger loops).
                        #   2. Cross-workflow → block only when the parent
                        #      workflow uses explicit edges (it handles the
                        #      routing internally); otherwise allow, for
                        #      backward-compat trigger-based composition.
                        if card.idempotency_key:
                            parent_wf_id = _extract_parent_workflow(card.idempotency_key)
                            if parent_wf_id is not None:
                                if parent_wf_id == wf.id:
                                    continue  # same-workflow self-trigger
                                parent_wf = self.store.load(parent_wf_id)
                                if parent_wf and parent_wf.edges:
                                    continue  # parent routes internally — skip
                        if self._matches_trigger(card, wf.trigger.condition):
                            trig_key = f"trig:{wf.id}:{card.id}"

                            # Record the trigger key to prevent re-triggering.
                            # NOTE: This is not fully atomic — the key is recorded
                            # in a separate connection from the instance creation.
                            # A crash between key-record and instance-create could
                            # orphan the trigger key (the workflow won't start but
                            # the key exists, preventing future re-trigger).
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

            elif wf.trigger.source == "bead_ready":
                actions += self._check_bead_trigger(wf)

        return actions



    def _check_bead_trigger(self, wf: Workflow) -> list[str]:
        """Check for ready beads matching this workflow's trigger condition.

        Runs `bd ready --json` in the project directory and starts a workflow
        instance for each matching bead. Bead ID flows into trigger context.
        """
        actions = []
        project_dir = self._first_active_project_dir()

        try:
            result = subprocess.run(
                ["bd", "ready", "--json"],
                capture_output=True, text=True, timeout=10,
                cwd=project_dir,
            )
            if result.returncode != 0:
                return actions
            beads = json.loads(result.stdout)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            return actions

        if not isinstance(beads, list):
            return actions

        condition = wf.trigger.condition if wf.trigger else {}
        bead_type = condition.get("type", "")
        bead_label = condition.get("label", "")

        for bead in beads:
            bead_id = bead.get("id", "")
            if not bead_id:
                continue
            if bead_type and bead.get("type") != bead_type:
                continue
            if bead_label and bead_label not in bead.get("labels", []):
                continue

            trig_key = f"trig:{wf.id}:bead:{bead_id}"
            conn = _db_connect(self.state.db_path)
            try:
                existing = conn.execute(
                    "SELECT 1 FROM trigger_keys WHERE key = ?", (trig_key,)
                ).fetchone()
                if existing:
                    conn.close()
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES (?, ?)",
                    (trig_key, int(time.time())),
                )
                conn.commit()
            except sqlite3.OperationalError as e:
                log.warning("bead trigger dedup failed: %s", e)
                conn.close()
                continue
            conn.close()

            trigger_ctx = {
                "bead_id": bead_id,
                "trigger_source": "bead_ready",
                "title": bead.get("title", ""),
                "description": bead.get("description", ""),
                "labels": bead.get("labels", []),
            }
            instance_id = self._create_instance(
                wf, board="", project_dir=project_dir,
                trigger_context=trigger_ctx,
            )
            actions.append(
                f"STARTED workflow {wf.id} from bead trigger: {bead_id} → {instance_id}"
            )

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
            elif key == "title_not_prefix" or key.startswith("title_not_prefix"):
                # Handle title_not_prefix, title_not_prefix2, etc.
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

    def _create_instance(self, wf: Workflow, board: str, project_dir: str,
                         trigger_context: dict, parent_instance_id: str | None = None) -> WorkflowInstance:
        """Build a WorkflowInstance, initialize node_states, persist it.

        Shared by _start_from_trigger (card_completed/bead_ready triggers) and
        start_manual (manual/subworkflow starts).
        """
        unique = uuid.uuid4().hex[:8]
        instance_id = f"wf_{int(time.time())}_{wf.id}_{unique}"
        now = int(time.time())

        inst = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=wf.id,
            board=board,
            project_dir=project_dir,
            trigger_context=trigger_context,
            parent_instance_id=parent_instance_id,
            created_at=now,
        )

        for node in wf.nodes:
            inst.node_states[node.id] = NodeState(
                instance_id=instance_id, node_id=node.id
            )

        self.state.create_instance(inst)
        return inst

    def _start_from_trigger(self, wf: Workflow, board: str, trigger_card) -> list[str]:
        """Start a new workflow instance from a trigger card."""
        meta = self._extract_metadata(trigger_card)

        trigger_context = {
            "card_id": trigger_card.id,
            "board": board,
            "assignee": trigger_card.assignee,
            **meta,
        }

        project_dir = self._board_to_project_dir(board)

        inst = self._create_instance(wf, board, project_dir, trigger_context)
        return [f"STARTED workflow {wf.id} ({inst.instance_id}) on {board} — triggered by card {trigger_card.id}"]

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

    def _first_active_project_dir(self) -> str:
        """Get the first active project directory (for bead_ready trigger).

        Beads are project-scoped, not board-scoped. When no specific board
        context is available, use the first active project.
        """
        projects_file = Path.home() / ".hermes-teams/startup/active-projects.json"
        if projects_file.exists():
            try:
                data = json.loads(projects_file.read_text())
                if "active_projects" in data:
                    for proj in data["active_projects"]:
                        path = proj.get("path", "")
                        if path:
                            return path
                elif isinstance(data, dict) and data:
                    return next(iter(data.values()), "")
            except (json.JSONDecodeError, TypeError):
                pass
        return "."

    def start_manual(self, workflow_id: str, board: str, project_dir: str = "",
                     context: dict | None = None) -> str:
        """Manually start a workflow instance. Returns instance_id."""
        wf = self.store.load(workflow_id)
        if not wf:
            raise ValueError(f"Workflow template not found: {workflow_id}")

        inst = self._create_instance(wf, board, project_dir, context or {})
        log.info("Started workflow %s (%s)", workflow_id, inst.instance_id)
        self.state.log_event("INFO", "workflow_started",
            f"Workflow {workflow_id} started manually on board {board}",
            instance_id=inst.instance_id, workflow_id=workflow_id, board=board)
        return inst.instance_id
