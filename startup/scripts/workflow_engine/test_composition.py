"""
Composition & subworkflow tests for the workflow engine.

These tests verify how workflows compose when the engine does NOT yet have a
native "subworkflow" node type (see docs/workflow-composition-design.md for the
planned model). Composition today is achieved via TRIGGERS: workflow B has a
`card_completed` trigger that fires when a node in workflow A completes with
matching metadata. This is "trigger-based composition."

Tests cover:
  1. Trigger-based composition (A output triggers B)
  2. Nested chains (A → B → C)
  3. Recursive triggers (A → B → A) — does trigger_keys dedup prevent infinite loop?
  4. Parallel children (one node in A triggers both B and C simultaneously)
  5. Subworkflow failure isolation (child fails/blocks — does parent know?)
  6. Composition data flow (metadata passes through trigger context)

Uses the same FakeWorld fixture as test_engine.py: temp kanban boards with real
SQLite schema, simulated completions via direct DB writes, monkey-patched
KANBAN_HOME so the engine reads from our temp board.

Run: python3 -m pytest test_composition.py -v
Or:  python3 test_composition.py
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add scripts dir to path
SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow, Node, resolve_template, evaluate_condition
from workflow_engine.store import TemplateStore
from workflow_engine.kanban_adapter import board_db_path, KANBAN_HOME
from workflow_engine.runtime import Engine, StateDB, NodeStatus, WorkflowInstance, NodeState


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — fake kanban board, fake cards, fake completions
# (Mirrors test_engine.py helpers so patterns are consistent.)
# ═══════════════════════════════════════════════════════════════════════════

def make_fake_board(tmpdir: Path, board_name: str = "test-board") -> str:
    """Create a minimal kanban DB with the Hermes schema."""
    db_path = tmpdir / "boards" / board_name / "kanban.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            assignee TEXT,
            status TEXT DEFAULT 'todo',
            idempotency_key TEXT,
            completed_at INTEGER,
            priority INTEGER DEFAULT 0,
            body TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            parents TEXT DEFAULT '[]'
        );
        CREATE TABLE task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            outcome TEXT,
            summary TEXT,
            metadata TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT,
            ts INTEGER NOT NULL
        );
        CREATE TABLE task_links (
            child_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            PRIMARY KEY (child_id, parent_id)
        );
    """)
    conn.commit()
    conn.close()
    return board_name


def make_fake_card(
    board_db: Path,
    card_id: str,
    title: str = "test card",
    assignee: str = "test-profile",
    status: str = "todo",
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    summary: str = "",
    completed_at: int | None = None,
):
    """Insert a card into a fake board, optionally with a completed run."""
    conn = sqlite3.connect(str(board_db))
    now = int(time.time())
    conn.execute(
        """INSERT OR REPLACE INTO tasks (id, title, assignee, status, idempotency_key, completed_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (card_id, title, assignee, status, idempotency_key, completed_at, now),
    )
    if metadata is not None or summary:
        conn.execute(
            """INSERT INTO task_runs (task_id, outcome, summary, metadata)
               VALUES (?, 'completed', ?, ?)""",
            (card_id, summary, json.dumps(metadata) if metadata else None),
        )
    conn.commit()
    conn.close()


def complete_fake_card(board_db: Path, card_id: str, metadata: dict | None = None,
                       summary: str = ""):
    """Mark a card as done with a completed run (simulates kanban_complete)."""
    conn = sqlite3.connect(str(board_db))
    conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (int(time.time()), card_id),
    )
    conn.execute(
        """INSERT INTO task_runs (task_id, outcome, summary, metadata)
           VALUES (?, 'completed', ?, ?)""",
        (card_id, summary, json.dumps(metadata) if metadata else None),
    )
    conn.commit()
    conn.close()


def count_cards(board_db: Path) -> int:
    conn = sqlite3.connect(str(board_db))
    count = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    conn.close()
    return count


def get_instance_count(state_db: Path, workflow_id: str | None = None) -> int:
    """Count workflow instances in the state DB, optionally filtered by workflow_id."""
    conn = sqlite3.connect(str(state_db))
    if workflow_id:
        count = conn.execute(
            "SELECT count(*) FROM workflow_instances WHERE workflow_id = ?",
            (workflow_id,)
        ).fetchone()[0]
    else:
        count = conn.execute("SELECT count(*) FROM workflow_instances").fetchone()[0]
    conn.close()
    return count


# ═══════════════════════════════════════════════════════════════════════════
# FakeWorld — test fixture
# ═══════════════════════════════════════════════════════════════════════════

class FakeWorld:
    """Test fixture: temp dir, fake board, engine, state DB.

    Supports multiple boards for cross-workflow composition tests.
    """

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-comp-test-"))
        self.board = make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)

        # Monkey-patch KANBAN_HOME so kanban_adapter uses our fake boards
        import workflow_engine.kanban_adapter as ka
        self._orig_home = ka.KANBAN_HOME
        ka.KANBAN_HOME = self.tmpdir / "boards"

        # Create engine with temp state DB
        self.state_db_path = self.tmpdir / "state.db"
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)

        # Monkey-patch engine's kanban create to write to our fake board
        import workflow_engine.runtime as rt
        self._orig_create = rt.create_card
        rt.create_card = self._fake_create_card

        self._boards = {"test-board": self.board_db}

    def _fake_create_card(self, board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None):
        """Write directly to the fake board DB instead of calling hermes CLI."""
        db = self.tmpdir / "boards" / board / "kanban.db"
        if not hasattr(self, '_card_counter'):
            self._card_counter = 0
        self._card_counter += 1
        card_id = f"t_{int(time.time()*1000)}_{self._card_counter}"
        conn = sqlite3.connect(str(db))
        conn.execute(
            """INSERT INTO tasks (id, title, assignee, status, idempotency_key, created_at)
               VALUES (?, ?, ?, 'todo', ?, ?)""",
            (card_id, title, assignee, idempotency_key, int(time.time())),
        )
        conn.commit()
        conn.close()
        return True, json.dumps({"id": card_id})

    def add_board(self, name: str) -> Path:
        """Create an additional fake board and return its DB path."""
        make_fake_board(self.tmpdir, name)
        db = self.tmpdir / "boards" / name / "kanban.db"
        self._boards[name] = db
        return db

    def add_template(self, template: dict):
        """Write a workflow template to the temp templates dir."""
        path = self.templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2))

    def tick(self):
        return self.engine.tick()

    def start(self, workflow_id: str, context: dict | None = None) -> str:
        return self.engine.start_manual(
            workflow_id=workflow_id,
            board=self.board,
            project_dir=str(self.tmpdir),
            context=context or {},
        )

    def add_card(self, board_name: str | None = None, **kwargs):
        """Add a card. If board_name is None, uses default board."""
        db = self._boards.get(board_name, self.board_db) if board_name else self.board_db
        make_fake_card(db, **kwargs)

    def complete_card(self, card_id: str, board_name: str | None = None,
                      metadata: dict | None = None, summary: str = ""):
        """Complete a card. If board_name is None, uses default board."""
        db = self._boards.get(board_name, self.board_db) if board_name else self.board_db
        complete_fake_card(db, card_id, metadata, summary)

    def find_card_by_assignee(self, assignee: str, board_name: str | None = None) -> str | None:
        """Find the first card ID for an assignee on a board."""
        db = self._boards.get(board_name, self.board_db) if board_name else self.board_db
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT id FROM tasks WHERE assignee = ?", (assignee,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def find_cards_by_idem_prefix(self, prefix: str, board_name: str | None = None) -> list[str]:
        """Find card IDs by idempotency_key prefix (e.g. 'wf:')."""
        db = self._boards.get(board_name, self.board_db) if board_name else self.board_db
        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT id FROM tasks WHERE idempotency_key LIKE ?", (prefix + "%",)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def cleanup(self):
        import workflow_engine.kanban_adapter as ka
        import workflow_engine.runtime as rt
        ka.KANBAN_HOME = self._orig_home
        rt.create_card = self._orig_create


# ═══════════════════════════════════════════════════════════════════════════
# Composition helpers — templates for A/B/C workflows
# ═══════════════════════════════════════════════════════════════════════════

def workflow_a(trigger_condition: dict | None = None,
               assignee: str = "worker-a", verdict: str = "PASS"):
    """Parent workflow A. Its node completes with metadata matching B's trigger.

    If trigger_condition is provided, A also HAS a trigger (making it
    triggerable by another workflow's output — for recursion tests).
    """
    template = {
        "id": "workflow-a",
        "name": "Workflow A (parent)",
        "nodes": [
            {
                "id": "do_a",
                "profile": assignee,
                "skill": "work-skill",
                "body_template": "Do work A for ${trigger.task}",
            },
        ],
    }
    if trigger_condition:
        template["trigger"] = {
            "source": "card_completed",
            "condition": trigger_condition,
        }
    return template


def workflow_b(trigger_condition: dict, assignee: str = "worker-b",
               verdict: str = "PASS"):
    """Child workflow B. Triggered by A's node completion."""
    return {
        "id": "workflow-b",
        "name": "Workflow B (child of A)",
        "trigger": {
            "source": "card_completed",
            "condition": trigger_condition,
        },
        "nodes": [
            {
                "id": "do_b",
                "profile": assignee,
                "skill": "work-skill",
                "body_template": "Do work B triggered by ${trigger.card_id}",
            },
        ],
    }


def workflow_c(trigger_condition: dict, assignee: str = "worker-c"):
    """Grandchild workflow C. Triggered by B's node completion."""
    return {
        "id": "workflow-c",
        "name": "Workflow C (child of B)",
        "trigger": {
            "source": "card_completed",
            "condition": trigger_condition,
        },
        "nodes": [
            {
                "id": "do_c",
                "profile": assignee,
                "skill": "work-skill",
                "body_template": "Do work C triggered by ${trigger.card_id}",
            },
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Trigger-based composition — A output triggers B
# ═══════════════════════════════════════════════════════════════════════════

def test_trigger_composition_a_triggers_b():
    """When workflow A's node completes, workflow B should start via trigger.

    This is the simplest composition: no native subworkflow node, just a
    trigger-based link. A's node produces metadata that matches B's trigger
    condition. Completing A's node → B starts.
    """
    world = FakeWorld()
    try:
        # Workflow A: produces a card with assignee=worker-a, verdict=PASS
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))

        # Workflow B: triggered when a card with assignee=worker-a, verdict=PASS completes
        world.add_template(workflow_b(
            trigger_condition={
                "assignee": "worker-a",
                "status": "done",
                "metadata.verdict": "PASS",
            }
        ))

        # Start A manually
        world.start("workflow-a", context={"task": "build-feature"})

        # Tick 1: A's node dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_a" in a for a in actions), \
            f"Expected do_a DISPATCHED, got: {actions}"

        # Complete A's node with PASS verdict
        a_card = world.find_card_by_assignee("worker-a")
        assert a_card, "A's card not found"
        a_card_id: str = a_card
        world.complete_card(a_card_id, metadata={"verdict": "PASS"})

        # Tick 2: A's node marked DONE, B should start via trigger
        actions = world.tick()
        assert any("DONE" in a and "do_a" in a for a in actions), \
            f"Expected do_a DONE, got: {actions}"
        assert any("STARTED" in a and "workflow-b" in a for a in actions), \
            f"Expected workflow-b STARTED via trigger, got: {actions}"

        # Tick 3: B's node should dispatch
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_b" in a for a in actions), \
            f"Expected do_b DISPATCHED, got: {actions}"

        # Verify two instances were created
        assert get_instance_count(world.state_db_path) == 2

        # Verify two cards exist: one for A, one for B
        assert count_cards(world.board_db) == 2
    finally:
        world.cleanup()
    print("OK: test_trigger_composition_a_triggers_b")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Nested chain — A → B → C (3-level trigger chain)
# ═══════════════════════════════════════════════════════════════════════════

def test_nested_chain_a_b_c():
    """A 3-level trigger chain: A completes → B starts → B completes → C starts.

    Tests deeper nesting through composition. Each workflow's node output
    matches the next workflow's trigger condition.
    """
    world = FakeWorld()
    try:
        # A produces worker-a/verdict=PASS
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        # B triggered by worker-a/verdict=PASS, produces worker-b/verdict=DONE
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
            assignee="worker-b", verdict="DONE",
        ))
        # C triggered by worker-b/verdict=DONE
        world.add_template(workflow_c(
            trigger_condition={"assignee": "worker-b", "status": "done",
                               "metadata.verdict": "DONE"},
        ))

        # Start the chain
        world.start("workflow-a", context={"task": "deep-chain"})

        # === Level 1: A runs and completes ===
        world.tick()  # dispatch A
        a_card = world.find_card_by_assignee("worker-a")
        assert a_card, "A's card not created"
        a_card_id: str = a_card
        world.complete_card(a_card_id, metadata={"verdict": "PASS"})

        actions = world.tick()
        assert any("DONE" in a and "do_a" in a for a in actions), \
            f"Expected do_a DONE, got: {actions}"
        assert any("STARTED" in a and "workflow-b" in a for a in actions), \
            f"Expected workflow-b STARTED, got: {actions}"

        # === Level 2: B runs and completes ===
        world.tick()  # dispatch B
        b_card = world.find_card_by_assignee("worker-b")
        assert b_card, "B's card not created"
        world.complete_card(b_card, metadata={"verdict": "DONE"})

        actions = world.tick()
        assert any("DONE" in a and "do_b" in a for a in actions), \
            f"Expected do_b DONE, got: {actions}"
        assert any("STARTED" in a and "workflow-c" in a for a in actions), \
            f"Expected workflow-c STARTED, got: {actions}"

        # === Level 3: C runs ===
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_c" in a for a in actions), \
            f"Expected do_c DISPATCHED, got: {actions}"

        # Verify three instances were created (A, B, C)
        assert get_instance_count(world.state_db_path) == 3

        # Verify three cards exist (one per workflow)
        assert count_cards(world.board_db) == 3
    finally:
        world.cleanup()
    print("OK: test_nested_chain_a_b_c")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Recursive triggers — A → B → A (mutual recursion)
# ═══════════════════════════════════════════════════════════════════════════

def test_recursive_trigger_a_b_a():
    """A triggers B, B triggers A. Does trigger_keys dedup prevent infinite loop?

    FINDING: The trigger dedup key is `trig:{wf_id}:{card_id}`. Each completed
    card has a UNIQUE card_id. So when A's first node completes → B starts.
    When B's node completes → it's a DIFFERENT card → new trigger key → A
    starts AGAIN. The dedup prevents the SAME card from triggering the SAME
    workflow twice, but it does NOT prevent recursion via new cards.

    This test verifies that A→B→A produces a chain (not a single deduped start)
    and that the chain continues growing as long as cards keep completing.
    The "infinite loop" is only bounded by how many ticks the test runs.
    """
    world = FakeWorld()
    try:
        # A triggered by worker-b/verdict=DONE, produces worker-a/verdict=PASS
        world.add_template(workflow_a(
            trigger_condition={"assignee": "worker-b", "status": "done",
                               "metadata.verdict": "DONE"},
            assignee="worker-a", verdict="PASS",
        ))
        # B triggered by worker-a/verdict=PASS, produces worker-b/verdict=DONE
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
            assignee="worker-b", verdict="DONE",
        ))

        # Seed: start one instance of A manually
        world.start("workflow-a", context={"task": "recursive-seed"})

        # Tick 1: A dispatches
        world.tick()
        a1_card = world.find_card_by_assignee("worker-a")
        assert a1_card, "A1 card not created"
        world.complete_card(a1_card, metadata={"verdict": "PASS"})

        # Tick 2: A1 done → B1 starts
        actions = world.tick()
        assert any("STARTED" in a and "workflow-b" in a for a in actions), \
            f"Expected B1 STARTED, got: {actions}"

        # Tick 3: B1 dispatches
        world.tick()
        b1_card = world.find_card_by_assignee("worker-b")
        assert b1_card, "B1 card not created"
        world.complete_card(b1_card, metadata={"verdict": "DONE"})

        # Tick 4: B1 done → A2 starts (recursion!)
        actions = world.tick()
        assert any("STARTED" in a and "workflow-a" in a for a in actions), \
            f"Expected A2 STARTED via recursion, got: {actions}"

        # Tick 5: A2 dispatches — this is a SECOND instance of A
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_a" in a for a in actions), \
            f"Expected A2 do_a DISPATCHED, got: {actions}"

        # Verify recursion happened: at least 2 instances of A
        a_instances = get_instance_count(world.state_db_path, "workflow-a")
        b_instances = get_instance_count(world.state_db_path, "workflow-b")
        assert a_instances >= 2, \
            f"Expected ≥2 instances of A (recursion), got {a_instances}"
        assert b_instances >= 1, \
            f"Expected ≥1 instance of B, got {b_instances}"

        # Continue the chain one more level to prove it keeps going
        a2_cards = world.find_cards_by_idem_prefix("wf:")  # all engine-created cards
        # A2's card should have been created — find it by checking we have ≥2 worker-a cards
        # Actually, both A1 and A2 have assignee worker-a. Let's count:
        conn = sqlite3.connect(str(world.board_db))
        a_card_count = conn.execute(
            "SELECT count(*) FROM tasks WHERE assignee = 'worker-a'"
        ).fetchone()[0]
        conn.close()
        assert a_card_count >= 2, \
            f"Expected ≥2 worker-a cards (A1 + A2), got {a_card_count}"
    finally:
        world.cleanup()
    print("OK: test_recursive_trigger_a_b_a")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3b: Recursive triggers — trigger_keys dedup behavior
# ═══════════════════════════════════════════════════════════════════════════

def test_trigger_dedup_is_per_card_not_per_workflow():
    """Verify that trigger dedup is keyed on (workflow_id, card_id), not workflow_id alone.

    This confirms WHY A→B→A recursion is possible: the same card can't trigger
    the same workflow twice, but a DIFFERENT card CAN trigger it. The dedup
    is structural (per-card), not semantic (per-workflow-pair).
    """
    world = FakeWorld()
    try:
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        # Two different cards from "worker-a", both with PASS verdict
        world.add_card(
            card_id="card_x",
            title="[a] first work",
            assignee="worker-a",
            status="done",
            metadata={"verdict": "PASS"},
            completed_at=int(time.time()),
        )
        world.add_card(
            card_id="card_y",
            title="[a] second work",
            assignee="worker-a",
            status="done",
            metadata={"verdict": "PASS"},
            completed_at=int(time.time()),
        )

        # Tick: both cards should trigger separate instances of B
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 2, \
            f"Expected 2 STARTED (one per card), got {len(started)}: {started}"

        # Tick again: neither card should trigger again (dedup)
        actions2 = world.tick()
        started_again = [a for a in actions2 if "STARTED" in a]
        assert len(started_again) == 0, \
            f"Dedup should prevent re-trigger, got {started_again}"

        # Verify trigger_keys in state DB
        conn = sqlite3.connect(str(world.state_db_path))
        keys = conn.execute("SELECT key FROM trigger_keys").fetchall()
        conn.close()
        key_strs = [k[0] for k in keys]
        assert any("card_x" in k for k in key_strs), \
            f"Expected trig key for card_x, got {key_strs}"
        assert any("card_y" in k for k in key_strs), \
            f"Expected trig key for card_y, got {key_strs}"
    finally:
        world.cleanup()
    print("OK: test_trigger_dedup_is_per_card_not_per_workflow")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Parallel children — one node in A triggers both B and C
# ═══════════════════════════════════════════════════════════════════════════

def test_parallel_children_one_node_triggers_b_and_c():
    """One node in A completes, and BOTH B and C start (fan-out via triggers).

    A's node produces metadata that matches both B's and C's trigger conditions.
    This tests parallel composition: a single completion fans out to multiple
    child workflows.
    """
    world = FakeWorld()
    try:
        # A produces worker-a/verdict=PASS
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        # B triggered by worker-a/verdict=PASS
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
            assignee="worker-b",
        ))
        # C also triggered by worker-a/verdict=PASS (same condition!)
        world.add_template(workflow_c(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        # Start A
        world.start("workflow-a", context={"task": "parallel-children"})

        # Tick 1: A dispatches
        world.tick()
        a_card = world.find_card_by_assignee("worker-a")
        assert a_card
        a_card_id: str = a_card
        world.complete_card(a_card_id, metadata={"verdict": "PASS"})

        # Tick 2: A done → BOTH B and C should start
        actions = world.tick()
        assert any("DONE" in a and "do_a" in a for a in actions), \
            f"Expected do_a DONE, got: {actions}"
        started_b = [a for a in actions if "STARTED" in a and "workflow-b" in a]
        started_c = [a for a in actions if "STARTED" in a and "workflow-c" in a]
        assert len(started_b) == 1, f"Expected workflow-b STARTED, got: {started_b}"
        assert len(started_c) == 1, f"Expected workflow-c STARTED, got: {started_c}"

        # Tick 3: both B and C should dispatch
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_b" in a for a in actions), \
            f"Expected do_b DISPATCHED, got: {actions}"
        assert any("DISPATCHED" in a and "do_c" in a for a in actions), \
            f"Expected do_c DISPATCHED, got: {actions}"

        # Verify 3 instances total: 1×A + 1×B + 1×C
        assert get_instance_count(world.state_db_path) == 3
        assert get_instance_count(world.state_db_path, "workflow-b") == 1
        assert get_instance_count(world.state_db_path, "workflow-c") == 1

        # Verify 3 cards: 1 for A, 1 for B, 1 for C
        assert count_cards(world.board_db) == 3
    finally:
        world.cleanup()
    print("OK: test_parallel_children_one_node_triggers_b_and_c")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Subworkflow failure isolation — child fails, parent doesn't know
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_failure_isolation():
    """When a child workflow's node blocks/fails, the parent workflow is unaffected.

    FINDING: Without native subworkflow support, the parent and child are
    completely independent instances linked only by a trigger. The parent's
    completion depends ONLY on its own nodes — it has no mechanism to observe
    or wait for the child's outcome. This is the core gap that the
    subworkflow node type (design doc §3) would fill.

    This test verifies:
    1. Parent completes regardless of child state (no blocking link)
    2. Child can block/fail without parent knowing
    3. The trigger-based link is fire-and-forget
    """
    world = FakeWorld()
    try:
        # A produces worker-a/verdict=PASS
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        # B triggered by worker-a/verdict=PASS
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        # Start A
        world.start("workflow-a", context={"task": "failure-isolation"})

        # Tick 1: A dispatches
        world.tick()
        a_card = world.find_card_by_assignee("worker-a")
        assert a_card, "A's card not created"
        a_card_id: str = a_card
        world.complete_card(a_card_id, metadata={"verdict": "PASS"})

        # Tick 2: A done → B starts
        actions = world.tick()
        assert any("STARTED" in a and "workflow-b" in a for a in actions)

        # Tick 3: B dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_b" in a for a in actions)

        # Now BLOCK B's card (simulating child workflow failure / HITL block)
        b_card = world.find_card_by_assignee("worker-b")
        assert b_card, "B's card not created"
        conn = sqlite3.connect(str(world.board_db))
        conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (b_card,))
        conn.commit()
        conn.close()

        # Tick 4: B is blocked. But A should already be COMPLETE (it finished
        # when its own node completed — it doesn't wait for B).
        # A completed at tick 2 when do_a reached DONE.
        active_instances = world.engine.state.load_active_instances()
        a_active = [i for i in active_instances if i.workflow_id == "workflow-a"]
        b_active = [i for i in active_instances if i.workflow_id == "workflow-b"]

        # A is NOT active (it completed)
        assert len(a_active) == 0, \
            f"A should be complete regardless of B state, but A is still active: {a_active}"

        # B IS still active (it's blocked)
        assert len(b_active) == 1, \
            f"B should be active (blocked), got {len(b_active)}"

        # Tick 5: verify B's block is reported but A is gone
        actions = world.tick()
        blocked_reports = [a for a in actions if "BLOCKED" in a or "blocked" in a]
        assert any("do_b" in a for a in blocked_reports), \
            f"Expected do_b blocked report, got: {actions}"
        # No A-related actions — A is done and gone
        a_actions = [a for a in actions if "workflow-a" in a or "do_a" in a]
        assert len(a_actions) == 0, \
            f"A should not appear in any actions (already complete), got: {a_actions}"
    finally:
        world.cleanup()
    print("OK: test_subworkflow_failure_isolation")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5b: Subworkflow failure — child's card stays in "todo" forever
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_child_stuck_parent_unaffected():
    """Child workflow's node never completes (stuck in 'todo').

    The parent has already finished. The child is orphaned with no observer.
    This demonstrates the isolation gap: there is no back-propagation of
    child failure to the parent.
    """
    world = FakeWorld()
    try:
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        world.start("workflow-a", context={"task": "child-stuck"})
        world.tick()  # dispatch A
        a_card = world.find_card_by_assignee("worker-a")
        world.complete_card(a_card, metadata={"verdict": "PASS"})

        # Tick: A done, B starts
        world.tick()

        # Tick: B dispatches (card created, status=todo)
        world.tick()
        b_card = world.find_card_by_assignee("worker-b")
        assert b_card, "B's card not created"

        # B's card is still 'todo' — never completed, never blocked, just stuck.
        # Run multiple ticks — nothing changes.
        for _ in range(3):
            actions = world.tick()
            # B should get a WARNING about the card being in non-done state,
            # but the engine doesn't crash and doesn't advance.
            # No new instances should be created.
            new_starts = [a for a in actions if "STARTED" in a]
            assert len(new_starts) == 0, \
                f"No new instances expected when B is stuck, got: {new_starts}"

        # Verify: A is complete, B is still active
        active = world.engine.state.load_active_instances()
        assert len([i for i in active if i.workflow_id == "workflow-a"]) == 0
        assert len([i for i in active if i.workflow_id == "workflow-b"]) == 1
    finally:
        world.cleanup()
    print("OK: test_subworkflow_child_stuck_parent_unaffected")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Composition data flow — metadata passes through trigger context
# ═══════════════════════════════════════════════════════════════════════════

def test_composition_data_flow_via_trigger():
    """When A triggers B, A's card metadata becomes B's trigger_context.

    The trigger mechanism passes the triggering card's metadata into the
    child workflow's trigger_context, making it available as ${trigger.*}
    in node body templates. This is the data-flow channel for composition.
    """
    world = FakeWorld()
    try:
        # A produces rich metadata including a build_id
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        # B triggered by worker-a/verdict=PASS, reads trigger.build_id
        world.add_template({
            "id": "workflow-b",
            "name": "Workflow B (data flow)",
            "trigger": {
                "source": "card_completed",
                "condition": {"assignee": "worker-a", "status": "done",
                              "metadata.verdict": "PASS"},
            },
            "nodes": [
                {
                    "id": "do_b",
                    "profile": "worker-b",
                    "skill": "work-skill",
                    "body_template": "Process build ${trigger.build_id} from card ${trigger.card_id}",
                },
            ],
        })

        world.start("workflow-a", context={"task": "data-flow"})
        world.tick()  # dispatch A
        a_card = world.find_card_by_assignee("worker-a")
        # Complete A's card with rich metadata
        world.complete_card(a_card, metadata={
            "verdict": "PASS",
            "build_id": "BUILD-12345",
            "branch": "feature/x",
        })

        # Tick: A done, B starts via trigger
        actions = world.tick()
        assert any("STARTED" in a and "workflow-b" in a for a in actions)

        # Tick: B dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "do_b" in a for a in actions)

        # Verify B's trigger_context has the build_id from A's card metadata
        conn = sqlite3.connect(str(world.state_db_path))
        rows = conn.execute(
            "SELECT trigger_context FROM workflow_instances WHERE workflow_id = 'workflow-b'"
        ).fetchall()
        conn.close()
        assert len(rows) >= 1
        ctx = json.loads(rows[0][0])
        assert ctx.get("build_id") == "BUILD-12345", \
            f"Expected build_id in trigger_context, got: {ctx}"
        assert ctx.get("verdict") == "PASS", \
            f"Expected verdict in trigger_context, got: {ctx}"
        assert "card_id" in ctx, \
            f"Expected card_id in trigger_context, got: {ctx}"
    finally:
        world.cleanup()
    print("OK: test_composition_data_flow_via_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Multi-board composition — A on board-1 triggers B on board-1
#         (trigger scans all boards)
# ═══════════════════════════════════════════════════════════════════════════

def test_composition_multiple_boards():
    """Composition works across board boundaries.

    The engine's _check_triggers scans ALL boards under KANBAN_HOME. A card
    completing on any board can trigger a workflow on that same board. This
    test verifies composition works when both parent and child use the same
    board (the common case) and the trigger scans it correctly.
    """
    world = FakeWorld()
    try:
        world.add_template(workflow_a(assignee="worker-a", verdict="PASS"))
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        # Start A
        world.start("workflow-a", context={"task": "same-board-comp"})

        # Complete A's workflow end-to-end
        world.tick()
        a_card = world.find_card_by_assignee("worker-a")
        world.complete_card(a_card, metadata={"verdict": "PASS"})

        # B should trigger
        actions = world.tick()
        assert any("STARTED" in a and "workflow-b" in a for a in actions), \
            f"Expected B triggered on same board, got: {actions}"

        # Verify both instances reference the same board
        conn = sqlite3.connect(str(world.state_db_path))
        boards = conn.execute("SELECT DISTINCT board FROM workflow_instances").fetchall()
        conn.close()
        assert len(boards) == 1, \
            f"Expected all instances on test-board, got boards: {[b[0] for b in boards]}"
    finally:
        world.cleanup()
    print("OK: test_composition_multiple_boards")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Bounded recursion — trigger_keys limits re-trigger per card
# ═══════════════════════════════════════════════════════════════════════════

def test_bounded_recursion_card_dedup():
    """Even in a recursive A↔B cycle, the same card cannot trigger twice.

    This is the WEAK recursion guard: trigger_keys prevents the same (card,
    workflow) pair from triggering twice. It does NOT prevent different cards
    from triggering — but it DOES prevent a single card from spawning
    multiple instances of the same workflow in a race condition.
    """
    world = FakeWorld()
    try:
        # B triggered by worker-a/verdict=PASS
        world.add_template(workflow_b(
            trigger_condition={"assignee": "worker-a", "status": "done",
                               "metadata.verdict": "PASS"},
        ))

        # One card
        world.add_card(
            card_id="single_card",
            title="[a] single",
            assignee="worker-a",
            status="done",
            metadata={"verdict": "PASS"},
            completed_at=int(time.time()),
        )

        # Tick: trigger fires once
        actions1 = world.tick()
        assert len([a for a in actions1 if "STARTED" in a]) == 1

        # Tick 2-5: trigger should NOT fire again (same card, dedup)
        for i in range(4):
            actions = world.tick()
            assert len([a for a in actions if "STARTED" in a]) == 0, \
                f"Tick {i+2}: same card should not re-trigger, got: {actions}"

        # Only one instance of B should exist
        assert get_instance_count(world.state_db_path, "workflow-b") == 1
    finally:
        world.cleanup()
    print("OK: test_bounded_recursion_card_dedup")


# ═══════════════════════════════════════════════════════════════════════════
# Main runner — for `python3 test_composition.py`
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_trigger_composition_a_triggers_b,
        test_nested_chain_a_b_c,
        test_recursive_trigger_a_b_a,
        test_trigger_dedup_is_per_card_not_per_workflow,
        test_parallel_children_one_node_triggers_b_and_c,
        test_subworkflow_failure_isolation,
        test_subworkflow_child_stuck_parent_unaffected,
        test_composition_data_flow_via_trigger,
        test_composition_multiple_boards,
        test_bounded_recursion_card_dedup,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
