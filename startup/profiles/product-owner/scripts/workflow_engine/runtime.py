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
import json
import time
import sqlite3
import logging

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
    trigger_context: dict = field(default_factory=dict)  # data from the trigger
    node_states: dict[str, NodeState] = field(default_factory=dict)
    parent_instance_id: str | None = None  # for subworkflows
    created_at: int = 0

    def context(self) -> dict:
        """Build the variable context for template resolution.

        Variables are namespaced:
          trigger.<key>  — from the trigger context
          nodes.<id>.output.<key>  — from completed node outputs
        """
        ctx = {}
        for k, v in self.trigger_context.items():
            ctx[f"trigger.{k}"] = v
        for node_id, state in self.node_states.items():
            for k, v in state.output.items():
                ctx[f"nodes.{node_id}.output.{k}"] = v
        return ctx


class StateDB:
    """SQLite-backed workflow state (cache — kanban DB is ground truth)."""

    def __init__(self, db_path: Path = STATE_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_instances (
                instance_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                board TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                trigger_context TEXT NOT NULL DEFAULT '{}',
                parent_instance_id TEXT,
                created_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
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
        """)
        conn.commit()
        conn.close()

    def create_instance(self, instance: WorkflowInstance):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT OR IGNORE INTO workflow_instances
               (instance_id, workflow_id, board, project_dir, trigger_context,
                parent_instance_id, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
            (
                instance.instance_id,
                instance.workflow_id,
                instance.board,
                instance.project_dir,
                json.dumps(instance.trigger_context),
                instance.parent_instance_id,
                instance.created_at,
            ),
        )
        for node_id, ns in instance.node_states.items():
            conn.execute(
                """INSERT OR IGNORE INTO node_states
                   (instance_id, node_id, status, card_id, output)
                   VALUES (?, ?, ?, ?, ?)""",
                (instance.instance_id, node_id, ns.status.value, ns.card_id, json.dumps(ns.output)),
            )
        conn.commit()
        conn.close()

    def load_active_instances(self) -> list[WorkflowInstance]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM workflow_instances WHERE status = 'active'"
        ).fetchall()

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
            )
            # Load node states
            ns_rows = conn.execute(
                "SELECT * FROM node_states WHERE instance_id = ?", (inst.instance_id,)
            ).fetchall()
            for ns_row in ns_rows:
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
        conn = sqlite3.connect(str(self.db_path))
        cur_card = card_id
        cur_output = output
        if cur_card is None or cur_output is None:
            existing = conn.execute(
                "SELECT card_id, output FROM node_states WHERE instance_id = ? AND node_id = ?",
                (instance_id, node_id),
            ).fetchone()
            cur_card = cur_card or (existing[0] if existing else None)
            cur_output = cur_output or (json.loads(existing[1]) if existing else {})
        conn.execute(
            """UPDATE node_states SET status = ?, card_id = ?, output = ?
               WHERE instance_id = ? AND node_id = ?""",
            (status.value, cur_card, json.dumps(cur_output), instance_id, node_id),
        )
        conn.commit()
        conn.close()

    def complete_instance(self, instance_id: str):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "UPDATE workflow_instances SET status = 'completed' WHERE instance_id = ?",
            (instance_id,),
        )
        conn.commit()
        conn.close()

    def get_watermark(self, board: str) -> int:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT last_ts FROM trigger_watermark WHERE board = ?", (board,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def set_watermark(self, board: str, ts: int):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT INTO trigger_watermark (board, last_ts) VALUES (?, ?)
               ON CONFLICT(board) DO UPDATE SET last_ts = ?""",
            (board, ts, ts),
        )
        conn.commit()
        conn.close()


class Engine:
    """The workflow engine — tick loop that advances workflows."""

    def __init__(self, templates_dir: str | Path):
        self.store = TemplateStore(templates_dir)
        self.state = StateDB()

    def tick(self):
        """Run one engine tick across all boards with active workflows."""
        actions = []

        # 1. Check completions on active instances
        for inst in self.state.load_active_instances():
            actions += self._check_instance(inst)

        # 2. Check triggers on all boards
        actions += self._check_triggers()

        return actions

    def _check_instance(self, inst: WorkflowInstance) -> list[str]:
        """Check a single workflow instance: advance nodes, handle completions."""
        actions = []
        wf = self.store.load(inst.workflow_id)
        if not wf:
            actions.append(f"SKIP instance {inst.instance_id}: template {inst.workflow_id} not found")
            return actions

        ctx = inst.context()

        # Check each pending node
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.PENDING:
                continue

            # Check dependencies
            deps_done = all(
                inst.node_states.get(dep, NodeState(instance_id="", node_id="")).status == NodeStatus.DONE
                for dep in node.depends_on
            )
            if not deps_done:
                continue

            # Check condition
            if node.condition and not evaluate_condition(node.condition, ctx):
                continue

            # All clear — dispatch the node
            ok, msg = self._dispatch_node(inst, node, ctx)
            if ok:
                actions.append(f"DISPATCHED node {node.id} on {inst.board} → card {msg}")
            else:
                actions.append(f"FAILED to dispatch node {node.id} on {inst.board}: {msg}")

        # Check dispatched nodes for completion
        for node in wf.nodes:
            ns = inst.node_states.get(node.id)
            if not ns or ns.status != NodeStatus.DISPATCHED or not ns.card_id:
                continue

            card = get_card(inst.board, ns.card_id)
            if not card:
                continue

            if card.status == "done":
                # Node completed — read output
                meta = get_card_metadata(inst.board, ns.card_id)
                output = meta.get("metadata", {})
                self.state.update_node_state(
                    inst.instance_id, node.id, NodeStatus.DONE, ns.card_id, output
                )
                actions.append(f"DONE node {node.id} (card {ns.card_id}) on {inst.board}")
            elif card.status == "blocked":
                actions.append(f"BLOCKED node {node.id} (card {ns.card_id}) — waiting for dynamic children")

        # Check if all nodes done → complete instance
        all_done = all(
            inst.node_states.get(node.id, NodeState(instance_id="", node_id="")).status == NodeStatus.DONE
            for node in wf.nodes
        )
        if all_done and wf.nodes:
            self.state.complete_instance(inst.instance_id)
            actions.append(f"WORKFLOW COMPLETE: {inst.workflow_id} ({inst.instance_id})")

        return actions

    def _dispatch_node(self, inst: WorkflowInstance, node: Node, ctx: dict) -> tuple[bool, str]:
        """Create a kanban card for a node."""
        # Resolve body template
        body = resolve_template(node.body_template, ctx)

        # Idempotency key
        idem_key = f"wf:{inst.instance_id}:{node.id}"

        # Check if already created
        existing = find_cards_by_idempotency_key(inst.board, idem_key)
        if existing:
            # Already created — just update state
            self.state.update_node_state(
                inst.instance_id, node.id, NodeStatus.DISPATCHED, existing[0].id
            )
            return True, existing[0].id

        # Create the card
        workspace = f"dir:{inst.project_dir}" if inst.project_dir else None
        ok, output = create_card(
            board=inst.board,
            title=f"[{node.id}] {node.skill}",
            assignee=node.profile,
            body=body,
            idempotency_key=idem_key,
            priority=10,
            workspace=workspace,
        )

        if not ok:
            return False, output

        # Extract card ID from JSON output
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

    def _check_triggers(self) -> list[str]:
        """Check all boards for new card completions that match workflow triggers."""
        actions = []

        for wf in self.store.all():
            if not wf.trigger:
                continue

            # For card_completed triggers, check recent completions
            if wf.trigger.source == "card_completed":
                # We need a board to check — get from trigger condition
                boards = self._boards_to_check()
                for board in boards:
                    last_ts = self.state.get_watermark(f"{board}:{wf.id}")
                    now = int(time.time())
                    # Look back 5 minutes (or since last check)
                    since = max(last_ts, now - 300)

                    completions = find_recent_completions(board, since)
                    for card in completions:
                        if self._matches_trigger(card, wf.trigger.condition):
                            # Start a workflow instance for this trigger
                            actions += self._start_from_trigger(wf, board, card)
                            self.state.set_watermark(f"{board}:{wf.id}", card.completed_at or now)
                    # Update watermark to now even if no matches
                    self.state.set_watermark(f"{board}:{wf.id}", now)

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
                meta = card.metadata or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                if meta.get("verdict") != expected:
                    return False
            elif key.startswith("metadata."):
                meta = card.metadata or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                field = key.split(".", 1)[1]
                if meta.get(field) != expected:
                    return False
            elif key == "title_prefix":
                if not (card.title or "").startswith(expected):
                    return False
            elif key == "title_not_prefix":
                if (card.title or "").startswith(expected):
                    return False
        return True

    def _start_from_trigger(self, wf: Workflow, board: str, trigger_card) -> list[str]:
        """Start a new workflow instance from a trigger card."""
        meta = trigger_card.metadata or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        instance_id = f"wf_{int(time.time())}_{wf.id}"
        now = int(time.time())

        # Trigger context: data from the triggering card
        trigger_context = {
            "card_id": trigger_card.id,
            "board": board,
            "assignee": trigger_card.assignee,
            **meta,  # Flatten metadata into trigger context
        }

        # Try to find project dir from board
        project_dir = self._board_to_project_dir(board)

        inst = WorkflowInstance(
            instance_id=instance_id,
            workflow_id=wf.id,
            board=board,
            project_dir=project_dir,
            trigger_context=trigger_context,
            created_at=now,
        )

        # Initialize node states
        for node in wf.nodes:
            inst.node_states[node.id] = NodeState(
                instance_id=instance_id, node_id=node.id
            )

        self.state.create_instance(inst)
        return [f"STARTED workflow {wf.id} ({instance_id}) on {board} — triggered by card {trigger_card.id}"]

    def _boards_to_check(self) -> list[str]:
        """Get list of boards to check for triggers."""
        boards_dir = Path.home() / ".hermes-teams/startup/kanban/boards"
        if not boards_dir.exists():
            return []
        return [p.name for p in boards_dir.iterdir() if p.is_dir() and (p / "kanban.db").exists()]

    def _board_to_project_dir(self, board: str) -> str:
        """Try to map a board name to a project directory."""
        # Check active-projects.json
        projects_file = Path.home() / ".hermes-teams/startup/kanban/active-projects.json"
        if projects_file.exists():
            try:
                projects = json.loads(projects_file.read_text())
                if board in projects:
                    return projects[board]
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

        instance_id = f"wf_{int(time.time())}_{workflow_id}"
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
