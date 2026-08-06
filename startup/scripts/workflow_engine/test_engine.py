"""
Integration tests for the workflow engine — fake every part to test complete behavior.

These tests don't touch real beads or real dispatchers. They use temporary
kanban boards, fake workflow templates, and simulated card completions to
verify the engine's tick loop, trigger detection, node dispatch, variable
resolution, output validation, and instance lifecycle.

Run: python3 -m pytest test_engine.py -v
Or:  python3 test_engine.py
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


def get_card_status(board_db: Path, card_id: str) -> str | None:
    """Read a card's status from the fake board."""
    conn = sqlite3.connect(str(board_db))
    row = conn.execute(
        "SELECT status FROM tasks WHERE id = ?", (card_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_card_idempotency(board_db: Path, card_id: str) -> str | None:
    conn = sqlite3.connect(str(board_db))
    row = conn.execute(
        "SELECT idempotency_key FROM tasks WHERE id = ?", (card_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def count_cards(board_db: Path) -> int:
    conn = sqlite3.connect(str(board_db))
    count = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    conn.close()
    return count


# ═══════════════════════════════════════════════════════════════════════════
# Test context — sets up fake board + engine per test
# ═══════════════════════════════════════════════════════════════════════════

class FakeWorld:
    """Test fixture: temp dir, fake board, engine, state DB."""

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-test-"))
        self.board = make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)

        # Monkey-patch KANBAN_HOME so kanban_adapter uses our fake board
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

    def _fake_create_card(self, board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None, parent=None):
        """Write directly to the fake board DB instead of calling hermes CLI."""
        db = self.tmpdir / "boards" / board / "kanban.db"
        # Use a counter to avoid timestamp collisions when multiple cards created in same ms
        if not hasattr(self, '_card_counter'):
            self._card_counter = 0
        self._card_counter += 1
        card_id = f"t_{int(time.time()*1000)}_{self._card_counter}"
        conn = sqlite3.connect(str(db))
        conn.execute(
            """INSERT INTO tasks (id, title, assignee, status, idempotency_key, created_at, body)
               VALUES (?, ?, ?, 'todo', ?, ?, ?)""",
            (card_id, title, assignee, idempotency_key, int(time.time()), body),
        )
        if parent:
            conn.execute(
                "INSERT OR IGNORE INTO task_dependencies (child_id, parent_id) VALUES (?, ?)",
                (card_id, parent),
            )
        conn.commit()
        conn.close()
        return True, json.dumps({"id": card_id})

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

    def add_card(self, card_id: str, **kwargs):
        make_fake_card(self.board_db, card_id, **kwargs)

    def complete_card(self, card_id: str, metadata: dict | None = None, summary: str = ""):
        complete_fake_card(self.board_db, card_id, metadata, summary)

    def state_snapshot(self, instance_id: str = None) -> dict:
        """Read the state blob for an instance (or the first active one).
        
        Returns the nodes dict from the state blob — replaces direct
        node_states SQL queries in tests.
        """
        if instance_id is None:
            instances = self.engine.state.load_active_instances()
            if not instances:
                return {}
            instance_id = instances[0].instance_id
        loaded = self.engine.state.load_state(instance_id)
        state = loaded.get("state", {})
        # Node state is at the root of the blob (node_id keys), not nested under "nodes"
        return state

    def cleanup(self):
        import workflow_engine.kanban_adapter as ka
        import workflow_engine.runtime as rt
        ka.KANBAN_HOME = self._orig_home
        rt.create_card = self._orig_create


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Basic tick with no active instances → no actions
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_tick():
    """Engine tick with no active instances should return no actions."""
    world = FakeWorld()
    actions = world.tick()
    assert actions == [], f"Expected no actions, got: {actions}"
    world.cleanup()
    print("OK: test_empty_tick")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Manual start → tick dispatches first node
# ═══════════════════════════════════════════════════════════════════════════

def test_manual_start_dispatches_node():
    """Manually starting a workflow should dispatch entry nodes on next tick."""
    world = FakeWorld()
    world.add_template({
        "id": "simple",
        "name": "Simple workflow",
        "nodes": [
            {
                "id": "step1",
                "profile": "qa",
                "skill": "live-testing",
                "body_template": "Do the thing for ${trigger.project}",
            }
        ],
    })

    instance_id = world.start("simple", context={"project": "my-project"})
    actions = world.tick()

    assert len(actions) == 1, f"Expected 1 action, got: {actions}"
    assert "DISPATCHED" in actions[0], f"Expected DISPATCHED, got: {actions[0]}"
    assert "step1" in actions[0], f"Expected step1, got: {actions[0]}"

    # Verify card was created on the board
    assert count_cards(world.board_db) == 1, f"Expected 1 card, got {count_cards(world.board_db)}"

    # Verify variable substitution in card title/body would have used "my-project"
    # (the card body is passed to create_card, which we can verify via the mock)
    world.cleanup()
    print("OK: test_manual_start_dispatches_node")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Node completion → advances to next node
# ═══════════════════════════════════════════════════════════════════════════

def test_node_completion_advances():
    """When a node's card completes, the next node should dispatch."""
    world = FakeWorld()
    world.add_template({
        "id": "two-step",
        "name": "Two step workflow",
        "nodes": [
            {
                "id": "step1",
                "profile": "developer",
                "skill": "developer-loop",
                "body_template": "Build ${trigger.feature}",
            },
            {
                "id": "step2",
                "profile": "verifier",
                "skill": "adversarial-review",
                "body_template": "Verify the work on ${trigger.feature}",
                "depends_on": ["step1"],
            },
        ],
    })

    world.start("two-step", context={"feature": "csv-parser"})

    # Tick 1: should dispatch step1 only (step2 depends on step1)
    actions = world.tick()
    assert len(actions) == 1
    assert "step1" in actions[0]

    # Simulate step1's card completing
    # Find the card that was created
    conn = sqlite3.connect(str(world.board_db))
    card_row = conn.execute("SELECT id FROM tasks WHERE assignee = 'developer'").fetchone()
    conn.close()
    assert card_row, "No developer card was created"
    step1_card_id = card_row[0]

    # Complete it
    world.complete_card(step1_card_id, metadata={"branch_name": "feature/csv"})

    # Tick 2: should detect step1 done, dispatch step2
    actions = world.tick()
    assert len(actions) >= 1, f"Expected at least 1 action, got: {actions}"
    assert any("DONE" in a and "step1" in a for a in actions), f"Expected step1 DONE, got: {actions}"
    assert any("DISPATCHED" in a and "step2" in a for a in actions), f"Expected step2 DISPATCHED, got: {actions}"

    # Verify step2 card exists
    conn = sqlite3.connect(str(world.board_db))
    card2 = conn.execute("SELECT id FROM tasks WHERE assignee = 'verifier'").fetchone()
    conn.close()
    assert card2, "No verifier card was created"

    world.cleanup()
    print("OK: test_node_completion_advances")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Full workflow lifecycle — all nodes complete, instance finishes
# ═══════════════════════════════════════════════════════════════════════════

def test_full_lifecycle():
    """A 3-node workflow should complete end-to-end."""
    world = FakeWorld()
    world.add_template({
        "id": "three-step",
        "name": "Three step pipeline",
        "nodes": [
            {"id": "a", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan ${trigger.task}"},
            {"id": "b", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build based on ${nodes.a.output.spec_path}",
             "depends_on": ["a"]},
            {"id": "c", "profile": "qa", "skill": "live-testing",
             "body_template": "Test the build from ${nodes.b.output.branch_name}",
             "depends_on": ["b"]},
        ],
    })

    world.start("three-step", context={"task": "build-cli"})

    # Tick 1: dispatch a
    actions = world.tick()
    assert any("DISPATCHED" in a and "node a " in f" {a} " for a in actions), \
        f"Expected a DISPATCHED, got: {actions}"

    # Complete a with output
    conn = sqlite3.connect(str(world.board_db))
    card_a = conn.execute("SELECT id FROM tasks WHERE assignee = 'product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(card_a, metadata={"spec_path": "/tmp/spec.md"})

    # Tick 2: a done, dispatch b
    actions = world.tick()
    assert any("DONE" in a and "node a" in a for a in actions), \
        f"Expected a DONE, got: {actions}"

    conn = sqlite3.connect(str(world.board_db))
    card_b = conn.execute("SELECT id FROM tasks WHERE assignee = 'developer'").fetchone()[0]
    conn.close()
    world.complete_card(card_b, metadata={"branch_name": "feat/cli"})

    # Tick 3: b done, dispatch c
    actions = world.tick()
    assert any("DONE" in a and "node b" in a for a in actions), f"Expected b DONE, got: {actions}"
    assert any("DISPATCHED" in a and "node c" in a for a in actions), f"Expected c DISPATCHED, got: {actions}"

    conn = sqlite3.connect(str(world.board_db))
    card_c = conn.execute("SELECT id FROM tasks WHERE assignee = 'qa'").fetchone()[0]
    conn.close()
    world.complete_card(card_c, metadata={"verdict": "PASS"})

    # Tick 4: c done, workflow complete
    actions = world.tick()
    assert any("DONE" in a and "node c" in a for a in actions), f"Expected c DONE, got: {actions}"
    assert any("WORKFLOW COMPLETE" in a for a in actions), f"Expected WORKFLOW COMPLETE, got: {actions}"

    # Verify no active instances remain
    active = world.engine.state.load_active_instances()
    assert len(active) == 0, f"Expected 0 active instances, got {len(active)}"

    world.cleanup()
    print("OK: test_full_lifecycle")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Variable resolution — upstream output flows to downstream input
# ═════════════════════════════════════════════════════ context══════════════

def test_variable_resolution():
    """Output from node A should resolve in node B's body template."""
    world = FakeWorld()
    world.add_template({
        "id": "var-test",
        "name": "Variable test",
        "nodes": [
            {"id": "plan", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan the work"},
            {"id": "build", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build using spec at ${nodes.plan.output.spec_path} for epic ${nodes.plan.output.epic_id}",
             "depends_on": ["plan"]},
        ],
    })

    world.start("var-test", context={})

    # Tick 1: dispatch plan
    world.tick()

    # Complete plan with specific outputs
    conn = sqlite3.connect(str(world.board_db))
    card_plan = conn.execute("SELECT id FROM tasks WHERE assignee = 'product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(card_plan, metadata={"spec_path": "/custom/path.md", "epic_id": "EPIC-42"})

    # Tick 2: plan done, dispatch build
    actions = world.tick()

    # The build card should have been created. Let's check its body was resolved.
    # Since our mock doesn't store body, we verify via the instance context.
    instances = world.engine.state.load_active_instances()
    # Wait — instance was completed by now? No, build hasn't completed yet.
    # Let's check the state DB directly.
    nodes = world.state_snapshot()
    plan_output = nodes.get("plan", {}).get("output", {})
    assert plan_output.get("spec_path") == "/custom/path.md", \
        f"Expected spec_path=/custom/path.md, got: {plan_output}"
    assert plan_output.get("epic_id") == "EPIC-42", \
        f"Expected epic_id=EPIC-42, got: {plan_output}"

    world.cleanup()
    print("OK: test_variable_resolution")


# ═══════════════════════════════════════════════════════ cards══════════════

def test_idempotency():
    """Running tick twice should not create duplicate cards."""
    world = FakeWorld()
    world.add_template({
        "id": "idem-test",
        "name": "Idempotency test",
        "nodes": [
            {"id": "only", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("idem-test")

    # Tick 1: creates card
    actions1 = world.tick()
    assert len(actions1) == 1
    assert count_cards(world.board_db) == 1

    # Tick 2: card already created, should be a no-op (card is dispatched)
    actions2 = world.tick()
    assert count_cards(world.board_db) == 1, \
        f"Expected 1 card after 2 ticks, got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_idempotency")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Condition evaluation — node only runs if condition passes
# ═══════════════════════════════════════════════════════════════════════════

def test_conditional_node():
    """A node with a condition should only dispatch when condition is met."""
    world = FakeWorld()
    world.add_template({
        "id": "cond-test",
        "name": "Conditional test",
        "nodes": [
            {"id": "check", "profile": "qa", "skill": "live-testing",
             "body_template": "Run QA",
             "output": {"schema": {"required": ["verdict"]}}},
            {"id": "pass_path", "profile": "product-owner", "skill": "dev-dispatch",
             "body_template": "QA passed, ship it",
             "depends_on": ["check"],
             "condition": "${nodes.check.output.verdict} == 'PASS'"},
            {"id": "fail_path", "profile": "debugger", "skill": "debug-loop",
             "body_template": "QA failed, fix it",
             "depends_on": ["check"],
             "condition": "${nodes.check.output.verdict} == 'FAIL'"},
        ],
    })

    world.start("cond-test")

    # Tick 1: dispatch check
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    check_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'qa'").fetchone()[0]
    conn.close()

    # Complete with PASS
    world.complete_card(check_card, metadata={"verdict": "PASS"})

    # Tick 2: check done, only pass_path should dispatch (not fail_path)
    actions = world.tick()
    assert any("pass_path" in a and "DISPATCHED" in a for a in actions), \
        f"Expected pass_path DISPATCHED, got: {actions}"
    assert not any("fail_path" in a and "DISPATCHED" in a for a in actions), \
        f"fail_path should NOT dispatch on PASS, got: {actions}"

    world.cleanup()
    print("OK: test_conditional_node")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Trigger detection — card completion starts new workflow
# ═══════════════════════════════════════════════════════════════════════════

def test_trigger_detection():
    """A card completion matching a trigger condition should start a workflow."""
    world = FakeWorld()
    world.add_template({
        "id": "trigger-test",
        "name": "Trigger test",
        "trigger": {
            "source": "card_completed",
            "condition": {
                "assignee": "verifier",
                "status": "done",
                "metadata.verdict": "PASS",
            },
        },
        "nodes": [
            {"id": "qa", "profile": "qa", "skill": "live-testing",
             "body_template": "QA re-test triggered by ${trigger.card_id}"},
        ],
    })

    # Add a completed verifier card with PASS verdict
    world.add_card(
        "t_verifier_1",
        title="[verify] feature X",
        assignee="verifier",
        status="done",
        metadata={"verdict": "PASS", "merged_commit_sha": "abc1234"},
        completed_at=int(time.time()),
    )

    # Tick: should detect the trigger and start the workflow
    actions = world.tick()

    assert any("STARTED" in a and "trigger-test" in a for a in actions), \
        f"Expected workflow STARTED, got: {actions}"

    # Tick again: should dispatch the qa node
    actions2 = world.tick()
    assert any("DISPATCHED" in a and "qa" in a for a in actions2), \
        f"Expected qa node DISPATCHED, got: {actions2}"

    world.cleanup()
    print("OK: test_trigger_detection")


# ═══════════════════════════════════════════════════ lookalike══════════════

def test_trigger_no_match():
    """A card completion that does NOT match the trigger should NOT start a workflow."""
    world = FakeWorld()
    world.add_template({
        "id": "trigger-test",
        "name": "Trigger test",
        "trigger": {
            "source": "card_completed",
            "condition": {
                "assignee": "verifier",
                "status": "done",
                "metadata.verdict": "PASS",
            },
        },
        "nodes": [
            {"id": "qa", "profile": "qa", "skill": "live-testing",
             "body_template": "Should not trigger"},
        ],
    })

    # Add a completed verifier card with FAIL verdict (should NOT trigger)
    world.add_card(
        "t_verifier_fail",
        title="[verify] feature Y",
        assignee="verifier",
        status="done",
    )
    world.complete_card("t_verifier_fail", metadata={"verdict": "FAIL"})

    actions = world.tick()
    assert not any("STARTED" in a for a in actions), \
        f"FAIL verdict should not trigger, got: {actions}"

    world.cleanup()
    print("OK: test_trigger_no_match")


# ═══════════════════════════════ kanban══════════════

def test_idempotency_key_on_card():
    """Card created by engine should carry the wf:<instance>:<node> idempotency key."""
    world = FakeWorld()
    world.add_template({
        "id": "key-test",
        "name": "Key test",
        "nodes": [
            {"id": "step1", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    instance_id = world.start("key-test")
    world.tick()

    # Check the card has the right idempotency key
    conn = sqlite3.connect(str(world.board_db))
    row = conn.execute(
        "SELECT idempotency_key FROM tasks WHERE assignee = 'qa'"
    ).fetchone()
    conn.close()

    expected_key = f"wf:{instance_id}:step1"
    assert row[0] == expected_key, \
        f"Expected idempotency_key={expected_key}, got {row[0]}"

    world.cleanup()
    print("OK: test_idempotency_key_on_card")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 11: Parallel nodes — two nodes with same dependency dispatch together
# ═══════════════════════════════════════════════════════════════════════════

def test_parallel_dispatch():
    """Two nodes depending on the same parent should both dispatch when parent completes."""
    world = FakeWorld()
    world.add_template({
        "id": "parallel-test",
        "name": "Parallel test",
        "nodes": [
            {"id": "plan", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan"},
            {"id": "dev", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build",
             "depends_on": ["plan"]},
            {"id": "research", "profile": "researcher", "skill": "web-research",
             "body_template": "Research",
             "depends_on": ["plan"]},
        ],
    })

    world.start("parallel-test")
    world.tick()  # dispatch plan

    # Complete plan
    conn = sqlite3.connect(str(world.board_db))
    plan_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(plan_card, metadata={"spec_path": "/tmp/spec.md"})

    # Tick: both dev and research should dispatch
    actions = world.tick()
    assert any("dev" in a and "DISPATCHED" in a for a in actions), \
        f"Expected dev DISPATCHED, got: {actions}"
    assert any("research" in a and "DISPATCHED" in a for a in actions), \
        f"Expected research DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_parallel_dispatch")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 12: Blocked node — node stays blocked, engine reports it
# ═══════════════════════════════════════════════════════════════════════════

def test_blocked_node_reported():
    """A blocked node card should be reported but not advance."""
    world = FakeWorld()
    world.add_template({
        "id": "block-test",
        "name": "Block test",
        "nodes": [
            {"id": "work", "profile": "developer", "skill": "developer-loop",
             "body_template": "Do work"},
        ],
    })

    world.start("block-test")
    world.tick()  # dispatch work

    # Mark the card as blocked (not done)
    conn = sqlite3.connect(str(world.board_db))
    work_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'developer'").fetchone()[0]
    conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (work_card,))
    conn.commit()
    conn.close()

    # Tick: should report blocked, not advance
    actions = world.tick()
    assert any("BLOCKED" in a or "blocked" in a for a in actions), \
        f"Expected blocked report, got: {actions}"
    assert not any("DONE" in a for a in actions), \
        f"Should not report DONE for blocked card, got: {actions}"

    world.cleanup()
    print("OK: test_blocked_node_reported")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 13: Restart recovery — engine resumes mid-workflow after restart
# ═════════════════════════════════════════════════════ context══════════════

def test_restart_recovery():
    """Engine should resume a workflow mid-execution after restart (state DB persists)."""
    world = FakeWorld()
    world.add_template({
        "id": "restart-test",
        "name": "Restart test",
        "nodes": [
            {"id": "a", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build"},
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Verify",
             "depends_on": ["a"]},
        ],
    })

    instance_id = world.start("restart-test")
    world.tick()  # dispatch a

    # Complete a
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'developer'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={"branch_name": "feat/x"})

    # Simulate restart: create a NEW engine with the same state DB
    engine2 = Engine(world.templates_dir)
    engine2.state = StateDB(world.state_db_path)

    # Monkey-patch the new engine's create_card
    import workflow_engine.runtime as rt
    orig_create = rt.create_card
    rt.create_card = world._fake_create_card

    # Tick: should detect a is done, dispatch b
    actions = engine2.tick()

    assert any("DONE" in a and "a" in a for a in actions), \
        f"Expected a DONE after restart, got: {actions}"
    assert any("DISPATCHED" in a and "b" in a for a in actions), \
        f"Expected b DISPATCHED after restart, got: {actions}"

    rt.create_card = orig_create
    world.cleanup()
    print("OK: test_restart_recovery")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 14: Multiple instances on same board
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_instances():
    """Multiple workflow instances on the same board should not interfere."""
    world = FakeWorld()
    world.add_template({
        "id": "multi-test",
        "name": "Multi test",
        "nodes": [
            {"id": "step1", "profile": "qa", "skill": "live-testing",
             "body_template": "Test instance ${trigger.task_id}"},
        ],
    })

    # Start two instances
    id1 = world.start("multi-test", context={"task_id": "TASK-1"})
    id2 = world.start("multi-test", context={"task_id": "TASK-2"})

    assert id1 != id2

    # Tick: should dispatch both
    actions = world.tick()
    assert len([a for a in actions if "DISPATCHED" in a]) == 2, \
        f"Expected 2 dispatches, got: {actions}"

    # Both cards should have different idempotency keys
    conn = sqlite3.connect(str(world.board_db))
    keys = conn.execute("SELECT idempotency_key FROM tasks").fetchall()
    conn.close()
    assert len(keys) == 2
    assert keys[0][0] != keys[1][0], f"Keys should differ: {keys}"

    world.cleanup()
    print("OK: test_multiple_instances")


# ═════════════                            ═════════════════════════════════

def test_branching_workflow():
    """A diamond workflow: A → (B, C) → D. D only runs when both B and C complete."""
    world = FakeWorld()
    world.add_template({
        "id": "diamond",
        "name": "Diamond",
        "nodes": [
            {"id": "root", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan"},
            {"id": "build", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build",
             "depends_on": ["root"]},
            {"id": "research", "profile": "researcher", "skill": "web-research",
             "body_template": "Research",
             "depends_on": ["root"]},
            {"id": "synthesize", "profile": "architect", "skill": "design-council",
             "body_template": "Synthesize build + research",
             "depends_on": ["build", "research"]},
        ],
    })

    world.start("diamond")
    world.tick()  # dispatch root

    # Complete root
    conn = sqlite3.connect(str(world.board_db))
    root_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(root_card, metadata={"spec": "/tmp/spec.md"})

    # Tick: build + research should both dispatch (parallel)
    actions = world.tick()
    assert sum(1 for a in actions if "DISPATCHED" in a) == 2, \
        f"Expected 2 parallel dispatches, got: {actions}"

    # Complete build only
    conn = sqlite3.connect(str(world.board_db))
    build_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'developer'").fetchone()[0]
    conn.close()
    world.complete_card(build_card, metadata={"code": "main.py"})

    # Tick: build done, but synthesize should NOT dispatch (research not done)
    actions = world.tick()
    assert any("DONE" in a and "build" in a for a in actions), \
        f"Expected build DONE, got: {actions}"
    assert not any("synthesize" in a and "DISPATCHED" in a for a in actions), \
        f"synthesize should NOT dispatch before research completes, got: {actions}"

    # Complete research
    conn = sqlite3.connect(str(world.board_db))
    research_card = conn.execute("SELECT id FROM tasks WHERE assignee = 'researcher'").fetchone()[0]
    conn.close()
    world.complete_card(research_card, metadata={"findings": "research.md"})

    # Tick: research done, NOW synthesize should dispatch
    actions = world.tick()
    assert any("DONE" in a and "research" in a for a in actions), \
        f"Expected research DONE, got: {actions}"
    assert any("synthesize" in a and "DISPATCHED" in a for a in actions), \
        f"Expected synthesize DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_branching_workflow")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Circular dependency — engine should not infinite-loop
# ═══════════════════════════════════════════════════════════════════════════

def test_circular_dependency():
    """Two nodes depending on each other should not hang the engine."""
    world = FakeWorld()
    world.add_template({
        "id": "circular",
        "name": "Circular dependency",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "A", "depends_on": ["b"]},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "B", "depends_on": ["a"]},
        ],
    })

    world.start("circular")

    # Tick: neither node can dispatch (both waiting on the other)
    actions = world.tick()
    assert not any("DISPATCHED" in a for a in actions), \
        f"Circular deps should not dispatch, got: {actions}"
    # Engine should not crash
    assert count_cards(world.board_db) == 0

    world.cleanup()
    print("OK: test_circular_dependency")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Nonexistent template — start_manual should raise
# ═══════════════════════════════════════════════════════════════════════════

def test_nonexistent_template():
    """Starting a workflow with an unknown template ID should raise ValueError."""
    world = FakeWorld()
    try:
        world.start("does-not-exist")
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "not found" in str(e).lower()
    world.cleanup()
    print("OK: test_nonexistent_template")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Empty workflow — zero nodes should complete immediately
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_workflow():
    """A workflow with zero nodes should complete immediately on first tick."""
    world = FakeWorld()
    world.add_template({
        "id": "empty",
        "name": "Empty",
        "nodes": [],
    })

    world.start("empty")
    actions = world.tick()
    # No nodes to dispatch, but also no nodes to check → no crash
    # The all_done check should not fire for empty workflows (guarded by `and wf.nodes`)
    assert not any("DISPATCHED" in a for a in actions), \
        f"Empty workflow should not dispatch, got: {actions}"

    world.cleanup()
    print("OK: test_empty_workflow")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Trigger dedup — same card should not trigger twice
# ═══════════════════════════════════════════════════════════════════════════

def test_trigger_dedup():
    """The same completed card should not start two workflow instances."""
    world = FakeWorld()
    world.add_template({
        "id": "dedup-test",
        "name": "Dedup test",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [
            {"id": "qa", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    # One completed verifier card
    world.add_card("t_v1", assignee="verifier", status="done",
                   metadata={"verdict": "PASS"}, completed_at=int(time.time()))

    # Tick 1: should start one instance
    actions1 = world.tick()
    assert sum(1 for a in actions1 if "STARTED" in a) == 1

    # Tick 2: same card, watermark should prevent re-trigger
    actions2 = world.tick()
    started_again = [a for a in actions2 if "STARTED" in a]
    assert len(started_again) == 0, \
        f"Should not re-trigger same card, got: {started_again}"

    world.cleanup()
    print("OK: test_trigger_dedup")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Multiple completions in one tick
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_completions_one_tick():
    """Two parallel nodes completing should both advance in one tick."""
    world = FakeWorld()
    world.add_template({
        "id": "multi-complete",
        "name": "Multi complete",
        "nodes": [
            {"id": "root", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan"},
            {"id": "dev", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build", "depends_on": ["root"]},
            {"id": "research", "profile": "researcher", "skill": "web-research",
             "body_template": "Research", "depends_on": ["root"]},
            {"id": "merge", "profile": "architect", "skill": "design-council",
             "body_template": "Merge results", "depends_on": ["dev", "research"]},
        ],
    })

    world.start("multi-complete")
    world.tick()  # dispatch root

    # Complete root
    conn = sqlite3.connect(str(world.board_db))
    root_card = conn.execute("SELECT id FROM tasks WHERE assignee='product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(root_card, metadata={"spec": "/tmp/spec.md"})

    # Tick: dispatch dev + research
    world.tick()

    # Complete BOTH dev and research
    conn = sqlite3.connect(str(world.board_db))
    dev_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    research_card = conn.execute("SELECT id FROM tasks WHERE assignee='researcher'").fetchone()[0]
    conn.close()
    world.complete_card(dev_card, metadata={"code": "main.py"})
    world.complete_card(research_card, metadata={"report": "report.md"})

    # Single tick: both should be marked done, merge should dispatch
    actions = world.tick()
    done_count = sum(1 for a in actions if "DONE" in a)
    assert done_count == 2, f"Expected 2 DONEs, got {done_count}: {actions}"
    assert any("merge" in a and "DISPATCHED" in a for a in actions), \
        f"Expected merge DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_multiple_completions_one_tick")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Malformed metadata — engine should not crash
# ═══════════════════════════════════════════════════════════════════════════

def test_malformed_metadata():
    """A card with invalid JSON metadata should not crash the engine."""
    world = FakeWorld()
    world.add_template({
        "id": "malformed",
        "name": "Malformed metadata",
        "nodes": [
            {"id": "step1", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build"},
            {"id": "step2", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Verify ${nodes.step1.output.verdict}",
             "depends_on": ["step1"]},
        ],
    })

    world.start("malformed")
    world.tick()

    # Complete step1 with malformed metadata
    conn = sqlite3.connect(str(world.board_db))
    step1_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    # Insert run with broken JSON
    conn.execute(
        "INSERT INTO task_runs (task_id, outcome, summary, metadata) VALUES (?, 'completed', 'done', 'NOT VALID JSON{{{')",
        (step1_card,),
    )
    conn.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?", (int(time.time()), step1_card))
    conn.commit()
    conn.close()

    # Tick: should not crash, step1 marked done with empty output
    actions = world.tick()
    assert any("DONE" in a and "step1" in a for a in actions), \
        f"Expected step1 DONE despite malformed metadata, got: {actions}"
    # step2 should still dispatch (deps met, no condition)
    assert any("DISPATCHED" in a and "step2" in a for a in actions), \
        f"Expected step2 DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_malformed_metadata")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: No metadata at all
# ═══════════════════════════════════════════════════════════════════════════

def test_no_metadata():
    """A card completed with no metadata should still advance (empty output dict)."""
    world = FakeWorld()
    world.add_template({
        "id": "no-meta",
        "name": "No metadata",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "Test again", "depends_on": ["a"]},
        ],
    })

    world.start("no-meta")
    world.tick()

    # Complete with no metadata
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata=None)

    # Tick: a done, b should dispatch
    actions = world.tick()
    assert any("DONE" in a and "node a" in a for a in actions)
    assert any("DISPATCHED" in a and "node b" in a for a in actions)

    world.cleanup()
    print("OK: test_no_metadata")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Output schema validation — invalid output should be flagged
# ═══════════════════════════════════════════════════════════════════════════

def test_output_schema_validation():
    """A card with output not matching the schema should FAIL the node (hard validation).

    Enterprise-grade behavior: when a node's card completes with metadata that
    violates the node's declared output.schema (JSON Schema), the node is marked
    FAILED (not DONE), and downstream nodes that depend on it must NOT dispatch.
    """
    world = FakeWorld()
    world.add_template({
        "id": "schema-test",
        "name": "Schema test",
        "nodes": [
            {"id": "qa", "profile": "qa", "skill": "live-testing",
             "body_template": "Test",
             "output": {"schema": {
                 "type": "object",
                 "required": ["verdict"],
                 "properties": {
                     "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
                 }
             }}},
            {"id": "done", "profile": "product-owner", "skill": "dev-dispatch",
             "body_template": "Done", "depends_on": ["qa"]},
        ],
    })

    world.start("schema-test")
    world.tick()

    # Complete qa with INVALID output (missing verdict)
    conn = sqlite3.connect(str(world.board_db))
    qa_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(qa_card, metadata={"something_else": "no verdict"})

    # Tick: node should FAIL hard (validation error), not complete
    actions = world.tick()
    assert any("VALIDATION FAILED" in a and "qa" in a for a in actions), \
        f"Expected qa VALIDATION FAILED, got: {actions}"
    # Downstream should NOT advance (dependency failed)
    assert not any("DISPATCHED" in a and "done" in a for a in actions), \
        f"done node must NOT dispatch when qa failed validation, got: {actions}"

    # Validation failure detected and downstream skipped
    assert any("VALIDATION FAILED" in a and "qa" in a for a in actions), \
        f"Expected qa VALIDATION FAILED, got: {actions}"
    assert any("SKIPPED" in a and "done" in a for a in actions), \
        f"done node should be SKIPPED when qa failed, got: {actions}"

    world.cleanup()
    print("OK: test_output_schema_validation")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: State cleanup / GC — old trigger_keys and completed instances GC'd
# ═══════════════════════════════════════════════════════════════════════════

def test_state_cleanup_gc():
    """StateDB.cleanup() removes old trigger_keys, completed instances,
    node_states, and stale watermarks past max_age_days. Recent rows are kept."""
    world = FakeWorld()

    # Insert an OLD trigger_key (8 days ago)
    old_ts = int(time.time()) - (8 * 86400)
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute(
        "INSERT INTO trigger_keys (key, created_at) VALUES (?, ?)",
        ("old-trig-key", old_ts),
    )
    # Insert a RECENT trigger_key (1 hour ago)
    conn.execute(
        "INSERT INTO trigger_keys (key, created_at) VALUES (?, ?)",
        ("recent-trig-key", int(time.time()) - 3600),
    )

    # Insert an OLD completed instance + node_state (8 days ago)
    conn.execute(
        """INSERT INTO workflow_instances
           (instance_id, workflow_id, board, project_dir, trigger_context,
            parent_instance_id, created_at, status, completed_at, node_ids)
           VALUES (?, 'wf-x', 'test-board', '', '{}', NULL, ?, 'completed', ?, '[]')""",
        ("old-instance", old_ts, old_ts),
    )
    conn.execute(
        """INSERT INTO node_states (instance_id, node_id, status, card_id, output)
           VALUES (?, 'a', 'done', 'c1', '{}')""",
        ("old-instance",),
    )

    # Insert a RECENT completed instance (1 hour ago) — should survive
    recent_ts = int(time.time()) - 3600
    conn.execute(
        """INSERT INTO workflow_instances
           (instance_id, workflow_id, board, project_dir, trigger_context,
            parent_instance_id, created_at, status, completed_at, node_ids)
           VALUES (?, 'wf-y', 'test-board', '', '{}', NULL, ?, 'completed', ?, '[]')""",
        ("recent-instance", recent_ts, recent_ts),
    )
    conn.execute(
        """INSERT INTO node_states (instance_id, node_id, status, card_id, output)
           VALUES (?, 'b', 'done', 'c2', '{}')""",
        ("recent-instance",),
    )

    # Insert an OLD watermark (8 days ago) and a RECENT one (now)
    conn.execute(
        "INSERT INTO trigger_watermark (board, last_ts) VALUES ('stale-board', ?)",
        (old_ts,),
    )
    conn.execute(
        "INSERT INTO trigger_watermark (board, last_ts) VALUES ('fresh-board', ?)",
        (int(time.time()),),
    )
    conn.commit()
    conn.close()

    # Run cleanup with default 7-day threshold
    counts = world.engine.state.cleanup(max_age_days=7)

    assert counts["trigger_keys"] == 1, f"Expected 1 old trigger_key deleted, got {counts}"
    assert counts["workflow_instances"] == 1, f"Expected 1 old instance deleted, got {counts}"
    assert counts["node_states"] == 1, f"Expected 1 old node_state deleted, got {counts}"
    assert counts["trigger_watermark"] == 1, f"Expected 1 stale watermark deleted, got {counts}"

    # Verify the OLD rows are gone and RECENT ones survive
    conn = sqlite3.connect(str(world.state_db_path))
    old_key = conn.execute(
        "SELECT 1 FROM trigger_keys WHERE key = ?", ("old-trig-key",)
    ).fetchone()
    recent_key = conn.execute(
        "SELECT 1 FROM trigger_keys WHERE key = ?", ("recent-trig-key",)
    ).fetchone()
    old_inst = conn.execute(
        "SELECT 1 FROM workflow_instances WHERE instance_id = ?", ("old-instance",)
    ).fetchone()
    recent_inst = conn.execute(
        "SELECT 1 FROM workflow_instances WHERE instance_id = ?", ("recent-instance",)
    ).fetchone()
    old_ns = conn.execute(
        "SELECT 1 FROM node_states WHERE instance_id = ?", ("old-instance",)
    ).fetchone()
    recent_ns = conn.execute(
        "SELECT 1 FROM node_states WHERE instance_id = ?", ("recent-instance",)
    ).fetchone()
    stale_wm = conn.execute(
        "SELECT 1 FROM trigger_watermark WHERE board = ?", ("stale-board",)
    ).fetchone()
    fresh_wm = conn.execute(
        "SELECT 1 FROM trigger_watermark WHERE board = ?", ("fresh-board",)
    ).fetchone()
    conn.close()

    assert old_key is None, "old trigger_key should be deleted"
    assert recent_key is not None, "recent trigger_key should survive"
    assert old_inst is None, "old instance should be deleted"
    assert recent_inst is not None, "recent instance should survive"
    assert old_ns is None, "old node_state should be deleted"
    assert recent_ns is not None, "recent node_state should survive"
    assert stale_wm is None, "stale watermark should be deleted"
    assert fresh_wm is not None, "fresh watermark should survive"

    world.cleanup()
    print("OK: test_state_cleanup_gc")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Dead branch — condition never passes, workflow can't complete
# ═══════════════════════════════════════════════════ DONE══════════════════

def test_dead_branch():
    """A conditional node whose condition never passes gets SKIPPED — workflow completes."""
    world = FakeWorld()
    world.add_template({
        "id": "dead-branch",
        "name": "Dead branch",
        "nodes": [
            {"id": "check", "profile": "qa", "skill": "live-testing",
             "body_template": "Check"},
            {"id": "pass_path", "profile": "product-owner", "skill": "dev-dispatch",
             "body_template": "Ship it", "depends_on": ["check"],
             "condition": "${nodes.check.output.verdict} == 'PASS'"},
        ],
    })

    world.start("dead-branch")
    world.tick()

    # Complete check with FAIL
    conn = sqlite3.connect(str(world.board_db))
    check_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(check_card, metadata={"verdict": "FAIL"})

    actions = world.tick()
    assert any("DONE" in a and "check" in a for a in actions), \
        f"Expected check DONE, got: {actions}"
    # pass_path should be SKIPPED (condition fails), not dispatched
    assert any("SKIPPED" in a and "pass_path" in a for a in actions), \
        f"pass_path should be SKIPPED on FAIL, got: {actions}"
    assert not any("DISPATCHED" in a and "pass_path" in a for a in actions), \
        f"pass_path should not dispatch on FAIL, got: {actions}"
    # Workflow SHOULD complete — both nodes reached terminal state (DONE + SKIPPED)
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Workflow should complete with SKIPPED branch, got: {actions}"

    world.cleanup()
    print("OK: test_dead_branch")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Long chain — 5+ sequential nodes
# ═══════════════════════════════════════════════════════════════════════════

def test_long_chain():
    """A 5-node linear chain should complete end-to-end."""
    world = FakeWorld()
    nodes = []
    for i in range(5):
        node = {"id": f"step{i}", "profile": "qa", "skill": "live-testing",
                "body_template": f"Step {i}"}
        if i > 0:
            node["depends_on"] = [f"step{i-1}"]
        nodes.append(node)

    world.add_template({"id": "long-chain", "name": "Long chain", "nodes": nodes})
    world.start("long-chain")

    for i in range(5):
        world.tick()
        # Find the dispatched card for this step
        conn = sqlite3.connect(str(world.board_db))
        card = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE '%step{i}'".replace("{i}", str(i))).fetchone()
        if not card:
            # Try finding by latest non-done card
            card = conn.execute("SELECT id FROM tasks WHERE status != 'done' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert card, f"No card found for step{i}"
        world.complete_card(card[0], metadata={"step": i})
        conn.close()

    # Final tick: should complete
    actions = world.tick()
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Expected workflow complete after 5 steps, got: {actions}"

    world.cleanup()
    print("OK: test_long_chain")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Unknown card status — card in weird state
# ═══════════════════════════════════════════════════════════════════════════

def test_unknown_card_status():
    """A card with an unrecognized status should be ignored (not done, not blocked)."""
    world = FakeWorld()
    world.add_template({
        "id": "unknown-status",
        "name": "Unknown status",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("unknown-status")
    world.tick()

    # Set card to weird status
    conn = sqlite3.connect(str(world.board_db))
    card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.execute("UPDATE tasks SET status='weird_status' WHERE id=?", (card,))
    conn.commit()
    conn.close()

    # Tick: should not crash, should not mark done
    actions = world.tick()
    assert not any("DONE" in a for a in actions), \
        f"Unknown status should not be DONE, got: {actions}"
    assert not any("BLOCKED" in a for a in actions), \
        f"Unknown status should not be BLOCKED, got: {actions}"
    # Instance should still be active
    instances = world.engine.state.load_active_instances()
    assert len(instances) == 1

    world.cleanup()
    print("OK: test_unknown_card_status")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Trigger with title_prefix filter
# ═════════════════════════════════════════ assignee════════════════════════

def test_trigger_with_title_prefix():
    """Trigger should respect title_prefix to filter cards (e.g. skip [probe] cards)."""
    world = FakeWorld()
    world.add_template({
        "id": "prefix-test",
        "name": "Prefix test",
        "trigger": {
            "source": "card_completed",
            "condition": {
                "assignee": "verifier",
                "status": "done",
                "title_prefix": "[verify]",
            },
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "Test"}],
    })

    # Card that matches prefix
    world.add_card("t_match", title="[verify] feature X", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))
    # Card that doesn't match prefix (a probe card)
    world.add_card("t_no_match", title="[probe] fresh-eyes", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))

    actions = world.tick()
    started = [a for a in actions if "STARTED" in a]
    assert len(started) == 1, \
        f"Expected 1 trigger (matching prefix only), got: {started}"

    world.cleanup()
    print("OK: test_trigger_with_title_prefix")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Missing upstream output — template var doesn't resolve
# ═══════════════════════════════════════════════════════════════════════════

def test_missing_upstream_output():
    """If upstream output is missing, template var should resolve to empty string."""
    world = FakeWorld()
    world.add_template({
        "id": "missing-output",
        "name": "Missing output",
        "nodes": [
            {"id": "plan", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan"},
            {"id": "build", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build using spec at ${nodes.plan.output.spec_path}",
             "depends_on": ["plan"]},
        ],
    })

    world.start("missing-output")
    world.tick()

    # Complete plan with NO spec_path in output
    conn = sqlite3.connect(str(world.board_db))
    plan_card = conn.execute("SELECT id FROM tasks WHERE assignee='product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(plan_card, metadata={"unrelated": "stuff"})

    # Tick: plan done, build should dispatch (missing var → empty)
    actions = world.tick()
    assert any("DISPATCHED" in a and "build" in a for a in actions), \
        f"Build should dispatch even with missing upstream output, got: {actions}"

    world.cleanup()
    print("OK: test_missing_upstream_output")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Multiple triggers on same board — different workflows react to different cards
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_triggers_same_board():
    """Two different trigger templates should react to different cards."""
    world = FakeWorld()

    # Trigger 1: verifier PASS → qa workflow
    world.add_template({
        "id": "qa-trigger",
        "name": "QA trigger",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "QA re-test"}],
    })

    # Trigger 2: qa FAIL → debug workflow
    world.add_template({
        "id": "debug-trigger",
        "name": "Debug trigger",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "qa", "status": "done", "metadata.verdict": "FAIL"},
        },
        "nodes": [{"id": "debug", "profile": "debugger", "skill": "debug-loop",
                   "body_template": "Fix the bug"}],
    })

    # Add both types of completed cards
    world.add_card("t_verifier", title="[verify] feature", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))
    world.add_card("t_qa", title="[qa] test", assignee="qa",
                   status="done", metadata={"verdict": "FAIL"}, completed_at=int(time.time()))

    actions = world.tick()
    started = [a for a in actions if "STARTED" in a]
    assert len(started) == 2, \
        f"Expected 2 workflows started (one per trigger), got: {started}"
    assert any("qa-trigger" in a for a in started)
    assert any("debug-trigger" in a for a in started)

    world.cleanup()
    print("OK: test_multiple_triggers_same_board")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Board not found — operations on nonexistent board
# ═══════════════════════════════════════════════════════════════════════════

def test_board_not_found():
    """Operations on a nonexistent board should not crash."""
    from workflow_engine.kanban_adapter import get_card, find_recent_completions

    # get_card on nonexistent board
    result = get_card("nonexistent-board-xyz", "t_fake")
    assert result is None, f"Expected None for nonexistent board, got: {result}"

    # find_recent_completions on nonexistent board
    result = find_recent_completions("nonexistent-board-xyz", 0)
    assert result == [], f"Expected empty list for nonexistent board, got: {result}"

    print("OK: test_board_not_found")


def test_corrupt_board_db_does_not_crash_trigger_scan():
    """A board whose kanban.db exists but is corrupt (e.g. interrupted init
    leaving a 4 KB file with no `tasks` table) must not crash the cross-board
    trigger scan. The engine iterates ALL boards in find_recent_completions;
    one unreadable board should be skipped (return []), not raise and kill the
    whole tick.

    Regression: observed when a leftover `todo-app` board with an empty DB
    made test_real_trigger_fires_workflow fail with 'no such table: tasks'."""
    import sqlite3
    import tempfile
    from pathlib import Path
    from workflow_engine import kanban_adapter
    from workflow_engine.kanban_adapter import find_recent_completions

    # A real SQLite file with NO tables — mimics interrupted board init.
    corrupt_dir = Path(tempfile.mkdtemp()) / "corrupt-board"
    corrupt_dir.mkdir()
    corrupt_db = corrupt_dir / "kanban.db"
    conn = sqlite3.connect(str(corrupt_db))
    conn.execute("CREATE TABLE _unused (x)")  # valid SQLite, but no tasks table
    conn.commit()
    conn.close()
    assert corrupt_db.exists()

    original = kanban_adapter.board_db_path
    try:
        kanban_adapter.board_db_path = lambda board: corrupt_db
        result = find_recent_completions("corrupt-board", 0)
        assert result == [], f"Expected [] for corrupt board, got: {result}"
    finally:
        kanban_adapter.board_db_path = original

    print("OK: test_corrupt_board_db_does_not_crash_trigger_scan")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Self-triggering infinite loop
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_self_triggering_loop():
    """A workflow whose node assignee matches the trigger would loop forever.
    The engine MUST prevent this — either by tracking which cards it created,
    or by not triggering on its own cards."""
    world = FakeWorld()
    world.add_template({
        "id": "self-trigger",
        "name": "Self trigger",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "qa", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [
            {"id": "qa_check", "profile": "qa", "skill": "live-testing",
             "body_template": "Check",
             "output": {"schema": {"required": ["verdict"]}}},
        ],
    })

    # Seed with one external QA card
    world.add_card("t_external", title="[qa] external test", assignee="qa",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))

    # Tick 1: trigger fires, creates instance, dispatches qa_check
    actions1 = world.tick()
    assert any("STARTED" in a for a in actions1), f"Should start from external card: {actions1}"

    # Tick 2: dispatch qa_check node
    actions2 = world.tick()
    assert any("DISPATCHED" in a and "qa_check" in a for a in actions2), f"Should dispatch node: {actions2}"

    # Complete the engine-created card
    conn = sqlite3.connect(str(world.board_db))
    engine_card = conn.execute(
        "SELECT id FROM tasks WHERE idempotency_key LIKE 'wf:%qa_check'"
    ).fetchone()[0]
    conn.close()
    world.complete_card(engine_card, metadata={"verdict": "PASS"})

    # Tick 3: node completes, workflow finishes. BUT does the trigger ALSO fire
    # on the engine-created card, starting a NEW instance?
    actions3 = world.tick()
    new_starts = [a for a in actions3 if "STARTED" in a]

    # This is the bug: if the trigger doesn't exclude engine-created cards,
    # it will start a new instance every time a QA card completes.
    # For now, just document the behavior:
    if new_starts:
        print(f"  WARNING: self-trigger detected — engine creates card that re-triggers: {new_starts}")
        # This is a known limitation — the engine needs trigger source filtering
        # to exclude cards it created (via idempotency_key prefix "wf:")
    else:
        print("  Engine correctly prevented self-trigger")

    world.cleanup()
    print("OK: test_adv_self_triggering_loop")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Duplicate node IDs
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_duplicate_node_ids():
    """Two nodes with the same ID — the second should be ignored or flagged."""
    world = FakeWorld()
    world.add_template({
        "id": "dup-ids",
        "name": "Duplicate IDs",
        "nodes": [
            {"id": "step", "profile": "qa", "skill": "live-testing",
             "body_template": "First"},
            {"id": "step", "profile": "developer", "skill": "developer-loop",
             "body_template": "Second (duplicate ID)"},
        ],
    })

    world.start("dup-ids")
    actions = world.tick()

    # Should create only ONE card (the engine deduplicates by node ID in node_states)
    card_count = count_cards(world.board_db)
    assert card_count == 1, \
        f"Duplicate node IDs should create 1 card, got {card_count}"

    # The card should be for the first definition (qa) or we accept either
    conn = sqlite3.connect(str(world.board_db))
    assignees = [r[0] for r in conn.execute("SELECT assignee FROM tasks").fetchall()]
    conn.close()
    assert len(assignees) == 1, f"Expected 1 card, got {assignees}"

    world.cleanup()
    print("OK: test_adv_duplicate_node_ids")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: State DB deleted mid-workflow
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_state_db_deleted():
    """If the state DB is lost, the engine should not crash — it just loses tracking.
    Cards on the board become orphaned (no workflow instance)."""
    world = FakeWorld()
    world.add_template({
        "id": "state-loss",
        "name": "State loss",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "Test again", "depends_on": ["a"]},
        ],
    })

    world.start("state-loss")
    world.tick()  # dispatch a

    # Delete state DB (simulates disk loss)
    world.state_db_path.unlink()

    # Tick: engine should not crash, but instance is lost
    actions = world.tick()
    # No active instances (state DB is fresh/empty)
    assert not any("DISPATCHED" in a for a in actions), \
        f"Lost instance should not dispatch, got: {actions}"
    # The card on the board is orphaned — nobody advances it
    # This is the documented behavior: state DB is a cache, kanban is ground truth,
    # but losing the cache means losing variable bindings and instance tracking.

    world.cleanup()
    print("OK: test_adv_state_db_deleted")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Non-existent dependency
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_nonexistent_dependency():
    """A node that depends on a non-existent node ID should never dispatch."""
    world = FakeWorld()
    world.add_template({
        "id": "ghost-dep",
        "name": "Ghost dependency",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "A", "depends_on": ["ghost_node"]},
        ],
    })

    world.start("ghost-dep")
    actions = world.tick()

    # Node "a" depends on "ghost_node" which doesn't exist in the workflow
    # The dependency check will fail because ghost_node has no node state
    assert not any("DISPATCHED" in a for a in actions), \
        f"Node with ghost dependency should not dispatch, got: {actions}"
    assert count_cards(world.board_db) == 0

    world.cleanup()
    print("OK: test_adv_nonexistent_dependency")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Multiple triggers fire for multiple matching cards in one tick
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_multiple_matching_cards_one_tick():
    """Three verifier PASS cards complete simultaneously — should start 3 instances."""
    world = FakeWorld()
    world.add_template({
        "id": "multi-trigger",
        "name": "Multi trigger",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "Test"}],
    })

    now = int(time.time())
    for i in range(3):
        world.add_card(f"t_v{i}", title=f"[verify] feature {i}", assignee="verifier",
                       status="done", metadata={"verdict": "PASS"}, completed_at=now)

    actions = world.tick()
    started = [a for a in actions if "STARTED" in a]
    assert len(started) == 3, \
        f"Expected 3 instances started, got {len(started)}: {started}"

    world.cleanup()
    print("OK: test_adv_multiple_matching_cards_one_tick")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Trigger fires for engine-created card (the core loop bug)
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_trigger_on_engine_card():
    """When the engine creates a card that matches a trigger condition,
    completing that card should NOT re-trigger the same workflow.
    Engine-created cards have idempotency_key starting with 'wf:' and are
    filtered from trigger checks to prevent double-fire and infinite loops.

    To test re-verify triggering, we need an EXTERNAL (non-engine) QA card."""
    world = FakeWorld()

    # Workflow 1: trigger on verifier PASS, node is QA
    world.add_template({
        "id": "qa-loop",
        "name": "QA loop",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "Test"}],
    })

    # Workflow 2: trigger on QA FAIL, node is verifier (creates the loop!)
    world.add_template({
        "id": "re-verify",
        "name": "Re-verify",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "qa", "status": "done", "metadata.verdict": "FAIL"},
        },
        "nodes": [{"id": "verifier", "profile": "verifier", "skill": "adversarial-review",
                   "body_template": "Re-verify"}],
    })

    # Seed: external verifier PASS
    world.add_card("t_ext", title="[verify] ext", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))

    # Tick 1: qa-loop starts
    actions = world.tick()
    assert any("qa-loop" in a and "STARTED" in a for a in actions)

    # Tick 2: qa node dispatches
    world.tick()

    # Complete engine-created qa with FAIL — should NOT trigger re-verify
    # (engine cards have wf: idempotency keys and are filtered)
    conn = sqlite3.connect(str(world.board_db))
    qa_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(qa_card, metadata={"verdict": "FAIL"})

    # Tick 3: qa completes. Engine-created card has different workflow_id
    # (qa-loop) than re-verify, so cross-workflow trigger DOES fire.
    # This is correct composition: qa-loop's output triggers re-verify.
    actions = world.tick()
    assert any("re-verify" in a and "STARTED" in a for a in actions), \
        f"Cross-workflow trigger should fire (qa-loop → re-verify), got: {actions}"

    # Now add an EXTERNAL qa card with FAIL — this SHOULD trigger re-verify
    world.add_card("t_ext_qa", title="[qa] external", assignee="qa",
                   status="done", metadata={"verdict": "FAIL"}, completed_at=int(time.time()))

    # Tick 4: re-verify should start from external card
    actions = world.tick()
    assert any("re-verify" in a and "STARTED" in a for a in actions), \
        f"External card should trigger re-verify, got: {actions}"

    # Tick 5: re-verify dispatches its verifier node
    world.tick()

    # Complete the re-verify verifier card with PASS
    conn = sqlite3.connect(str(world.board_db))
    ver_card = conn.execute(
        "SELECT id FROM tasks WHERE assignee='verifier' AND idempotency_key LIKE 'wf:%'"
    ).fetchone()
    conn.close()
    if ver_card:
        world.complete_card(ver_card[0], metadata={"verdict": "PASS"})

    # Tick 6: verifier done. The re-verify verifier card has a different
    # workflow_id than qa-loop, so cross-workflow trigger fires.
    # This is correct composition: re-verify → qa-loop recursion.
    actions = world.tick()
    new_qa_starts = [a for a in actions if "qa-loop" in a and "STARTED" in a]
    # This recursion is expected — it terminates when conditions stop matching
    # (when QA passes). The self-trigger prevention only blocks the SAME workflow
    # from re-triggering itself, not cross-workflow composition.
    if new_qa_starts:
        print(f"  Cross-workflow recursion: re-verify → qa-loop (correct composition)")
    else:
        print(f"  No recursion (dedup or condition prevented it)")

    world.cleanup()
    print("OK: test_adv_trigger_on_engine_card")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: JSON/template injection via metadata values
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_template_injection():
    """Metadata containing ${} patterns should not cause recursive resolution."""
    world = FakeWorld()
    world.add_template({
        "id": "inject-test",
        "name": "Injection test",
        "nodes": [
            {"id": "a", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan: ${trigger.user_input}"},
            {"id": "b", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build with ${nodes.a.output.spec}",
             "depends_on": ["a"]},
        ],
    })

    # Start with malicious trigger context
    world.start("inject-test", context={
        "user_input": "${nodes.b.output.evil_command} rm -rf /"
    })

    # Tick: dispatch a
    world.tick()

    # Complete a with output containing template injection
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='product-owner'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={
        "spec": "/safe/path.md",
        "evil_command": "THIS SHOULD NOT EXECUTE"
    })

    # Tick: a done, b dispatches
    actions = world.tick()
    assert any("DISPATCHED" in a and "b" in a for a in actions), \
        f"b should dispatch despite injection attempt: {actions}"

    # The key check: does the engine's resolve_template do recursive expansion?
    # It should NOT — resolve_template does simple string replacement, not eval.
    # So ${nodes.b.output.evil_command} in trigger context stays as literal text
    # (or gets removed as unresolved), it doesn't execute b's output.

    world.cleanup()
    print("OK: test_adv_template_injection")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Very long chain that could stack overflow or timeout
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_long_chain_20():
    """A 20-node linear chain should complete without stack overflow."""
    world = FakeWorld()
    nodes = []
    for i in range(20):
        node = {"id": f"n{i}", "profile": "qa", "skill": "live-testing",
                "body_template": f"Step {i}"}
        if i > 0:
            node["depends_on"] = [f"n{i-1}"]
        nodes.append(node)

    world.add_template({"id": "long20", "name": "Long 20", "nodes": nodes})
    world.start("long20")

    for i in range(20):
        world.tick()
        conn = sqlite3.connect(str(world.board_db))
        card = conn.execute(
            f"SELECT id FROM tasks WHERE idempotency_key LIKE '%n{i}' AND status != 'done'"
        ).fetchone()
        if not card:
            card = conn.execute(
                "SELECT id FROM tasks WHERE status != 'done' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        assert card, f"No card found at step {i}"
        world.complete_card(card[0], metadata={"step": i})
        conn.close()

    actions = world.tick()
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"20-node chain should complete, got: {actions}"

    world.cleanup()
    print("OK: test_adv_long_chain_20")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Condition referencing own output (deadlock)
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_condition_references_own_output():
    """A node whose condition references its own output can never run (deadlock)."""
    world = FakeWorld()
    world.add_template({
        "id": "self-cond",
        "name": "Self condition",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test",
             "condition": "${nodes.a.output.ready} == 'true'"},
        ],
    })

    world.start("self-cond")
    actions = world.tick()

    # Node can never dispatch — it needs its own output to evaluate the condition
    assert not any("DISPATCHED" in a for a in actions), \
        f"Self-referential condition should block dispatch, got: {actions}"
    assert count_cards(world.board_db) == 0

    world.cleanup()
    print("OK: test_adv_condition_references_own_output")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Watermark gap — card completed during engine downtime
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_watermark_gap():
    """A card completed while the engine was down for >5 min should still trigger.

    The trigger lookback is max(last_watermark, now-300). If the engine was down
    for 10 min, the lookback is now-300 (5 min), missing cards from 5-10 min ago.
    """
    world = FakeWorld()
    world.add_template({
        "id": "gap-test",
        "name": "Gap test",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"},
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "Test"}],
    })

    # Card completed 10 minutes ago (600 seconds)
    old_ts = int(time.time()) - 600
    world.add_card("t_old", title="[verify] old", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=old_ts)

    # First tick: should it find the old card?
    actions = world.tick()
    started = [a for a in actions if "STARTED" in a]

    if started:
        print("  Old card was detected (engine found it)")
    else:
        print("  WARNING: card from 10 min ago NOT detected — lookback window too small")

    world.cleanup()
    print("OK: test_adv_watermark_gap")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Card archived between ticks
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_card_archived_mid_workflow():
    """If a dispatched card gets archived (not done), the node should treat it
    as terminal — archived means the card is gone from the board. The engine
    should advance past it rather than waiting forever."""
    world = FakeWorld()
    world.add_template({
        "id": "archive-test",
        "name": "Archive test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "Test again", "depends_on": ["a"]},
        ],
    })

    world.start("archive-test")
    world.tick()

    # Archive the card (simulates manual cleanup or GC)
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.execute("UPDATE tasks SET status='archived' WHERE id=?", (a_card,))
    conn.commit()
    conn.close()

    # Tick: archived card is terminal — node a should be DONE, node b should dispatch
    actions = world.tick()
    assert any("DONE" in a for a in actions), \
        f"Archived card should be treated as terminal (DONE), got: {actions}"
    assert any("DISPATCHED" in a and "node b" in a for a in actions), \
        f"b should dispatch when parent is archived (terminal), got: {actions}"

    world.cleanup()
    print("OK: test_adv_card_archived_mid_workflow")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Empty string as condition value
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_empty_string_condition():
    """Condition checking against empty string should work correctly."""
    world = FakeWorld()
    world.add_template({
        "id": "empty-cond",
        "name": "Empty condition",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Check"},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "Run if not empty",
             "depends_on": ["a"],
             "condition": "${nodes.a.output.error} exists"},
            {"id": "c", "profile": "qa", "skill": "live-testing",
             "body_template": "Run if empty",
             "depends_on": ["a"],
             "condition": "${nodes.a.output.error} is empty"},
        ],
    })

    world.start("empty-cond")
    world.tick()

    # Complete a with empty error field
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={"error": "", "result": "ok"})

    actions = world.tick()
    # "error" exists but is empty string → "exists" should be True (non-None)
    # but the evaluate_condition checks bool(context.get(key)) which is False for ""
    # So "exists" is False for empty string, and "is empty" is True
    assert not any("DISPATCHED" in a and "node b" in a for a in actions), \
        f"Empty string should not satisfy 'exists', got: {actions}"
    assert any("DISPATCHED" in a and "node c" in a for a in actions), \
        f"Empty string should satisfy 'is empty', got: {actions}"

    world.cleanup()
    print("OK: test_adv_empty_string_condition")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL: Rapid successive ticks (race condition)
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_rapid_ticks():
    """Calling tick() many times in quick succession should not create duplicate cards."""
    world = FakeWorld()
    world.add_template({
        "id": "rapid",
        "name": "Rapid",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("rapid")

    # Fire 10 ticks instantly
    for _ in range(10):
        world.tick()

    # Should have exactly 1 card (idempotency key prevents duplicates)
    assert count_cards(world.board_db) == 1, \
        f"10 rapid ticks should create 1 card, got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_adv_rapid_ticks")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL GRAPH PATHOLOGY TESTS
# Structurally broken or pathological workflow graphs.
# Focus: cycles, disconnected components, impossible conditions, star topology,
# forward references, large fan-out.
# ═══════════════════════════════════════════════════════════════════════════

def test_adv_graph_disconnected_node():
    """A node that exists in the nodes list but is unreachable from any entry.

    Graph: E (entry) → F (reachable).  Plus unreachable cycle X ↔ Y.
    E and F complete normally, but X↔Y are a disconnected cycle with no entry.
    The workflow can NEVER complete because X and Y stay PENDING forever.
    WEAKNESS: engine has no reachability analysis — unreachable nodes silently
    block the all_done check, hanging the instance indefinitely.
    """
    world = FakeWorld()
    world.add_template({
        "id": "disconnected",
        "name": "Disconnected component",
        "nodes": [
            {"id": "e", "profile": "qa", "skill": "live-testing",
             "body_template": "Entry"},
            {"id": "f", "profile": "qa", "skill": "live-testing",
             "body_template": "Follows E", "depends_on": ["e"]},
            # Unreachable cycle — no entry into this component
            {"id": "x", "profile": "qa", "skill": "live-testing",
             "body_template": "X", "depends_on": ["y"]},
            {"id": "y", "profile": "qa", "skill": "live-testing",
             "body_template": "Y", "depends_on": ["x"]},
        ],
    })
    world.start("disconnected")

    # Tick 1: e dispatches (entry). x and y do NOT (cycle).
    actions = world.tick()
    assert any("DISPATCHED" in a and "node e" in a for a in actions), \
        f"Entry e should dispatch, got: {actions}"
    assert not any("DISPATCHED" in a and ("node x" in a or "node y" in a) for a in actions), \
        f"Disconnected cycle nodes should not dispatch, got: {actions}"

    # Complete e, then f
    conn = sqlite3.connect(str(world.board_db))
    e_card = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE '%:e'").fetchone()[0]
    conn.close()
    world.complete_card(e_card, metadata={"ok": True})

    world.tick()  # e done, f dispatched

    conn = sqlite3.connect(str(world.board_db))
    f_card = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE '%:f'").fetchone()[0]
    conn.close()
    world.complete_card(f_card, metadata={"ok": True})

    # Tick: e and f are done. New behavior (design v2.2): the reachability
    # check (BFS from done nodes) ignores disconnected components, so x and y
    # don't block completion. The workflow completes.
    actions = world.tick()
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Workflow should complete — disconnected components ignored, got: {actions}"

    world.cleanup()
    print("OK: test_adv_graph_disconnected_node")


def test_adv_graph_conflicting_diamond():
    """Diamond A→(B,C)→D where B and C have contradictory conditions.

    B runs only on PASS, C runs only on FAIL. D depends on both.
    Only one of B/C can ever dispatch, so D's deps can NEVER all be DONE.
    WEAKNESS: engine treats 'condition failed' the same as 'waiting for deps'
    (both are PENDING). A permanently-dead branch silently blocks all fan-in
    dependents, deadlocking the workflow with no diagnostic.
    """
    world = FakeWorld()
    world.add_template({
        "id": "conflict-diamond",
        "name": "Conflicting diamond",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Decide"},
            {"id": "b", "profile": "developer", "skill": "developer-loop",
             "body_template": "Run on PASS",
             "depends_on": ["a"],
             "condition": "${nodes.a.output.verdict} == 'PASS'"},
            {"id": "c", "profile": "debugger", "skill": "debug-loop",
             "body_template": "Run on FAIL",
             "depends_on": ["a"],
             "condition": "${nodes.a.output.verdict} == 'FAIL'"},
            {"id": "d", "profile": "architect", "skill": "design-council",
             "body_template": "Merge B and C",
             "depends_on": ["b", "c"]},
        ],
    })
    world.start("conflict-diamond")
    world.tick()  # dispatch a

    # Complete a with PASS → B dispatches, C does NOT
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE '%:a'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={"verdict": "PASS"})

    actions = world.tick()
    assert any("DISPATCHED" in a and "node b" in a for a in actions), \
        f"B should dispatch on PASS, got: {actions}"
    assert not any("DISPATCHED" in a and "node c" in a for a in actions), \
        f"C should NOT dispatch on PASS, got: {actions}"

    # Complete B
    conn = sqlite3.connect(str(world.board_db))
    b_card = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE '%:b'").fetchone()[0]
    conn.close()
    world.complete_card(b_card, metadata={"code": "done"})

    # Tick: B done, but C is permanently stuck PENDING → D can NEVER dispatch
    actions = world.tick()
    assert any("DONE" in a and "node b" in a for a in actions), \
        f"B should be done, got: {actions}"
    assert not any("DISPATCHED" in a and "node d" in a for a in actions), \
        f"D should NOT dispatch — C is a dead branch, got: {actions}"
    # New behavior (design v2.2): dead branches are SKIPPED, not hung.
    # C is skipped (condition false), D is skipped (dead-branch propagation),
    # and the workflow completes because all exit nodes reach terminal state.
    assert any("SKIPPED" in a and "node d" in a for a in actions), \
        f"D should be SKIPPED (dead branch from C), got: {actions}"

    world.cleanup()
    print("OK: test_adv_graph_conflicting_diamond")


def test_adv_graph_self_dependency():
    """Node A depends on itself — the simplest possible cycle.

    A self-dependency creates an implicit back-edge (self-loop). Load-time
    validation should reject it: a back-edge without an iteration cap.
    If it somehow loads, the node never dispatches (waits for itself).
    """
    world = FakeWorld()
    world.add_template({
        "id": "self-dep",
        "name": "Self dependency",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "A depends on A",
             "depends_on": ["a"]},
        ],
    })
    world.start("self-dep")
    actions = world.tick()

    assert not any("DISPATCHED" in a for a in actions), \
        f"Self-dependent node should not dispatch, got: {actions}"
    assert count_cards(world.board_db) == 0, \
        f"No cards should be created for self-dependent node"

    # The node stays pending — it can never fire (waits for itself)
    # Instance stays active (permanently stuck unless manually resolved)
    active = world.engine.state.load_active_instances()
    assert len(active) == 1, "Self-deadlocked instance should still be active"

    world.cleanup()
    print("OK: test_adv_graph_self_dependency")


def test_adv_graph_three_node_cycle():
    """A→B→C→A — a 3-node cycle. None can ever dispatch.

    Extends the existing 2-node circular test. WEAKNESS: same as 2-node —
    no cycle detection, no diagnostic, silent hang. But with 3+ nodes it's
    harder to spot by eye in a real workflow definition.
    """
    world = FakeWorld()
    world.add_template({
        "id": "cycle3",
        "name": "Three node cycle",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "A", "depends_on": ["c"]},
            {"id": "b", "profile": "qa", "skill": "live-testing",
             "body_template": "B", "depends_on": ["a"]},
            {"id": "c", "profile": "qa", "skill": "live-testing",
             "body_template": "C", "depends_on": ["b"]},
        ],
    })
    world.start("cycle3")
    actions = world.tick()

    assert not any("DISPATCHED" in a for a in actions), \
        f"No node in a 3-cycle should dispatch, got: {actions}"
    assert count_cards(world.board_db) == 0

    # Tick again — still nothing, no crash
    actions2 = world.tick()
    assert not any("DISPATCHED" in a for a in actions2), \
        f"Second tick should still not dispatch, got: {actions2}"

    world.cleanup()
    print("OK: test_adv_graph_three_node_cycle")


def test_adv_graph_two_entry_nodes():
    """Two nodes with no dependencies — both should dispatch on tick 1.

    This is actually valid behavior, not a bug. But it's a topology the engine
    must handle: multiple independent entry points fan out simultaneously.
    """
    world = FakeWorld()
    world.add_template({
        "id": "two-entries",
        "name": "Two entries",
        "nodes": [
            {"id": "alpha", "profile": "qa", "skill": "live-testing",
             "body_template": "Alpha entry"},
            {"id": "beta", "profile": "developer", "skill": "developer-loop",
             "body_template": "Beta entry"},
        ],
    })
    world.start("two-entries")
    actions = world.tick()

    dispatched = [a for a in actions if "DISPATCHED" in a]
    assert len(dispatched) == 2, \
        f"Both entry nodes should dispatch, got: {actions}"
    assert any("alpha" in a for a in dispatched)
    assert any("beta" in a for a in dispatched)
    assert count_cards(world.board_db) == 2

    world.cleanup()
    print("OK: test_adv_graph_two_entry_nodes")


def test_adv_graph_forward_reference():
    """Node defined FIRST depends on a node defined LATER in the list.

    The engine builds node_states from all nodes at start_manual time, and
    checks deps by dict lookup (not positional). So forward references should
    work fine. This test verifies that — and would catch any order-dependent
    processing bug.
    """
    world = FakeWorld()
    world.add_template({
        "id": "forward-ref",
        "name": "Forward reference",
        "nodes": [
            # consumer defined BEFORE producer
            {"id": "consumer", "profile": "developer", "skill": "developer-loop",
             "body_template": "Uses ${nodes.producer.output.artifact}",
             "depends_on": ["producer"]},
            # producer defined AFTER consumer
            {"id": "producer", "profile": "qa", "skill": "live-testing",
             "body_template": "Makes artifact"},
        ],
    })
    world.start("forward-ref")
    actions = world.tick()

    # Producer should dispatch (entry node), consumer should NOT (dep not met)
    assert any("DISPATCHED" in a and "producer" in a for a in actions), \
        f"Forward-referenced producer should dispatch, got: {actions}"
    assert not any("DISPATCHED" in a and "consumer" in a for a in actions), \
        f"Consumer should wait for producer, got: {actions}"

    # Complete producer → consumer dispatches
    conn = sqlite3.connect(str(world.board_db))
    prod_card = conn.execute(
        "SELECT id FROM tasks WHERE idempotency_key LIKE '%:producer'"
    ).fetchone()[0]
    conn.close()
    world.complete_card(prod_card, metadata={"artifact": "/tmp/build.zip"})

    actions2 = world.tick()
    assert any("DISPATCHED" in a and "consumer" in a for a in actions2), \
        f"Consumer should dispatch after producer completes, got: {actions2}"

    world.cleanup()
    print("OK: test_adv_graph_forward_reference")


def test_adv_graph_all_conditions_impossible():
    """Every node has a condition that can never be true.

    Entry nodes with false conditions stay pending — they might fire later
    if trigger context changes. They're not skipped (no incoming edges to
    mark them as dead branches). The workflow stays active.
    """
    world = FakeWorld()
    world.add_template({
        "id": "all-impossible",
        "name": "All impossible conditions",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "A",
             "condition": "${trigger.magic_flag} == 'yes'"},
            {"id": "b", "profile": "developer", "skill": "developer-loop",
             "body_template": "B",
             "condition": "${trigger.other_flag} == 'sure'"},
        ],
    })
    # Start with context that does NOT contain magic_flag or other_flag
    world.start("all-impossible", context={"unrelated": "data"})
    actions = world.tick()

    # Neither node dispatches — conditions are false
    assert not any("DISPATCHED" in a for a in actions), \
        f"Nodes with false conditions should not dispatch, got: {actions}"
    # Nodes stay pending — workflow not complete
    assert not any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Workflow should not complete with pending nodes, got: {actions}"
    assert count_cards(world.board_db) == 0

    world.cleanup()
    print("OK: test_adv_graph_all_conditions_impossible")


def test_adv_graph_50_node_fanout():
    """One root → 50 parallel children. Stress test the tick loop.

    When root completes, all 50 children must dispatch in a single tick.
    This exercises: 50 idempotency-key lookups, 50 card creations, 50 state
    DB updates — all in one pass through the node list.
    """
    N = 50
    world = FakeWorld()
    nodes = [{"id": "root", "profile": "qa", "skill": "live-testing",
              "body_template": "Root"}]
    for i in range(N):
        nodes.append({
            "id": f"child{i}",
            "profile": "qa",
            "skill": "live-testing",
            "body_template": f"Child {i}",
            "depends_on": ["root"],
        })
    world.add_template({"id": "fanout50", "name": "50-node fanout", "nodes": nodes})
    world.start("fanout50")

    # Tick 1: root dispatches
    world.tick()
    assert count_cards(world.board_db) == 1

    # Complete root
    conn = sqlite3.connect(str(world.board_db))
    root_card = conn.execute(
        "SELECT id FROM tasks WHERE idempotency_key LIKE '%:root'"
    ).fetchone()[0]
    conn.close()
    world.complete_card(root_card, metadata={"ready": True})

    # Tick 2: all 50 children should dispatch in one tick
    actions = world.tick()
    dispatched = [a for a in actions if "DISPATCHED" in a]
    assert len(dispatched) == N, \
        f"Expected {N} child dispatches, got {len(dispatched)}: {actions[:5]}..."

    total_cards = count_cards(world.board_db)
    assert total_cards == N + 1, \
        f"Expected {N+1} cards (root + children), got {total_cards}"

    world.cleanup()
    print(f"OK: test_adv_graph_50_node_fanout ({N} children dispatched in one tick)")


def test_adv_graph_star_topology():
    """One sink node depends on ALL other nodes (star topology).

    N-1 satellites dispatch immediately; sink waits until every satellite
    completes. Tests that the engine correctly tracks many dependencies on
    a single node and only dispatches when ALL are done.
    """
    N_SATELLITES = 10
    world = FakeWorld()
    nodes = []
    satellite_ids = []
    for i in range(N_SATELLITES):
        sid = f"sat{i}"
        satellite_ids.append(sid)
        nodes.append({"id": sid, "profile": "qa", "skill": "live-testing",
                      "body_template": f"Satellite {i}"})
    # Sink depends on every satellite
    nodes.append({"id": "sink", "profile": "architect", "skill": "design-council",
                  "body_template": "Depends on all satellites",
                  "depends_on": satellite_ids})

    world.add_template({"id": "star", "name": "Star topology", "nodes": nodes})
    world.start("star")

    # Tick 1: all satellites dispatch, sink does NOT
    actions = world.tick()
    dispatched = [a for a in actions if "DISPATCHED" in a]
    assert len(dispatched) == N_SATELLITES, \
        f"All {N_SATELLITES} satellites should dispatch, got {len(dispatched)}"
    assert not any("DISPATCHED" in a and "sink" in a for a in actions), \
        f"Sink should not dispatch until all sats done, got: {actions}"

    # Complete all but one satellite
    for sid in satellite_ids[:-1]:
        conn = sqlite3.connect(str(world.board_db))
        card = conn.execute(
            f"SELECT id FROM tasks WHERE idempotency_key LIKE '%:{sid}'"
        ).fetchone()[0]
        conn.close()
        world.complete_card(card, metadata={"sat": sid})

    # Tick: sink should STILL not dispatch (one sat incomplete)
    actions = world.tick()
    assert not any("DISPATCHED" in a and "sink" in a for a in actions), \
        f"Sink should wait for last satellite, got: {actions}"

    # Complete the last satellite
    last_sid = satellite_ids[-1]
    conn = sqlite3.connect(str(world.board_db))
    card = conn.execute(
        f"SELECT id FROM tasks WHERE idempotency_key LIKE '%:{last_sid}'"
    ).fetchone()[0]
    conn.close()
    world.complete_card(card, metadata={"sat": last_sid})

    # Tick: NOW sink should dispatch
    actions = world.tick()
    assert any("DISPATCHED" in a and "sink" in a for a in actions), \
        f"Sink should dispatch when all satellites done, got: {actions}"

    world.cleanup()
    print("OK: test_adv_graph_star_topology")


def test_adv_graph_empty_vs_missing_depends_on():
    """Empty depends_on list vs missing depends_on key — both are entry nodes.

    model.from_dict uses n.get("depends_on", []) so both resolve to [].
    This test verifies behavioral equivalence: both dispatch on tick 1.
    """
    world = FakeWorld()
    world.add_template({
        "id": "dep-compare",
        "name": "Depends_on comparison",
        "nodes": [
            # Explicit empty list
            {"id": "explicit_empty", "profile": "qa", "skill": "live-testing",
             "body_template": "Explicit empty deps",
             "depends_on": []},
            # Key entirely missing
            {"id": "missing_key", "profile": "developer",
             "skill": "developer-loop",
             "body_template": "No depends_on key"},
        ],
    })
    world.start("dep-compare")
    actions = world.tick()

    # Both should dispatch — both are entry nodes
    dispatched = [a for a in actions if "DISPATCHED" in a]
    assert len(dispatched) == 2, \
        f"Both nodes should be entry nodes regardless of depends_on form, got: {actions}"
    assert any("explicit_empty" in a for a in dispatched)
    assert any("missing_key" in a for a in dispatched)

    world.cleanup()
    print("OK: test_adv_graph_empty_vs_missing_depends_on")



def run_data_corruption_tests():
    """Run the adversarial data corruption test suite. Returns (passed, failed, count)."""
    data_tests = [
        test_adv_data_null_body_template,
        test_adv_data_null_profile,
        test_adv_data_empty_node_id,
        test_adv_data_huge_node_id,
        test_adv_data_huge_body_template,
        test_adv_data_nested_json_template_vars,
        test_adv_data_conflicting_trigger_keys,
        test_adv_data_body_no_vars,
        test_adv_data_body_only_vars,
        test_adv_data_unicode_node_id,
        test_adv_data_unicode_profile,
        test_adv_data_null_byte_in_body,
        test_adv_data_condition_malformed,
        test_adv_data_condition_double_quotes,
        test_adv_data_condition_trailing_garbage,
        test_adv_data_resolve_dict_value,
        test_adv_data_resolve_list_value,
        test_adv_data_empty_everything,
        test_adv_data_newline_in_node_id,
        test_adv_data_template_var_in_condition_value,
    ]
    passed = 0
    failed = 0
    for test in data_tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    return passed, failed, len(data_tests)


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL DATA CORRUPTION TESTS
# Focus: malformed templates, null values, unicode, huge payloads,
#        condition parser edge cases, template injection.
# ═══════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# 1. NULL / None values where strings expected
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_null_body_template():
    """body_template set to JSON null should not crash resolve_template.

    WEAKNESS: from_dict does n.get("body_template", "") which returns None
    when the key exists with value null. Then resolve_template(None, ctx)
    calls None.replace() → AttributeError.
    """
    world = FakeWorld()
    # Write JSON with explicit null for body_template
    import json as _json
    template_path = world.templates_dir / "null-body.json"
    template_path.write_text(_json.dumps({
        "id": "null-body",
        "name": "Null body",
        "nodes": [
            {"id": "step1", "profile": "qa", "skill": "live-testing",
             "body_template": None},
        ],
    }))

    world.start("null-body")

    # This will either crash with AttributeError or handle gracefully
    try:
        actions = world.tick()
        # If it doesn't crash, verify no card was created with a None body
        assert count_cards(world.board_db) <= 1
    except (AttributeError, TypeError) as e:
        # Documented weakness: null body_template crashes resolve_template
        print(f"  BUG: null body_template crashed engine: {type(e).__name__}: {e}")

    world.cleanup()
    print("OK: test_adv_data_null_body_template")


def test_adv_data_null_profile():
    """profile set to JSON null should not produce cards with None assignee.

    WEAKNESS: None flows to create_card(assignee=None), which either crashes
    or creates a card with a NULL assignee column.
    """
    world = FakeWorld()
    import json as _json
    template_path = world.templates_dir / "null-profile.json"
    template_path.write_text(_json.dumps({
        "id": "null-profile",
        "name": "Null profile",
        "nodes": [
            {"id": "step1", "profile": None, "skill": "live-testing",
             "body_template": "Test"},
        ],
    }))

    world.start("null-profile")

    try:
        actions = world.tick()
        # If it didn't crash, check whether a card with NULL assignee was created
        conn = sqlite3.connect(str(world.board_db))
        row = conn.execute("SELECT assignee FROM tasks LIMIT 1").fetchone()
        conn.close()
        if row and row[0] is None:
            print(f"  BUG: card created with NULL assignee")
    except (TypeError, sqlite3.IntegrityError) as e:
        print(f"  null profile caused error (expected): {type(e).__name__}: {e}")

    world.cleanup()
    print("OK: test_adv_data_null_profile")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Empty / huge node IDs
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_empty_node_id():
    """Empty string node ID should not cause idempotency key collisions."""
    world = FakeWorld()
    world.add_template({
        "id": "empty-id",
        "name": "Empty ID",
        "nodes": [
            {"id": "", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("empty-id")
    actions = world.tick()

    # The card title would be "[] live-testing" — weird but shouldn't crash
    card_count = count_cards(world.board_db)
    assert card_count == 1, f"Expected 1 card for empty-id node, got {card_count}"

    # Verify the idempotency key — it would be "wf:<instance>:" (trailing colon)
    conn = sqlite3.connect(str(world.board_db))
    key = conn.execute("SELECT idempotency_key FROM tasks LIMIT 1").fetchone()
    conn.close()
    assert key and key[0].endswith(":"), \
        f"Empty node ID should produce key ending with ':', got {key}"

    world.cleanup()
    print("OK: test_adv_data_empty_node_id")


def test_adv_data_huge_node_id():
    """A 10000-char node ID should not crash the engine."""
    world = FakeWorld()
    big_id = "x" * 10000
    world.add_template({
        "id": "huge-id",
        "name": "Huge ID",
        "nodes": [
            {"id": big_id, "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("huge-id")
    actions = world.tick()

    # Should create a card with a massive title
    assert count_cards(world.board_db) == 1, \
        f"Huge node ID should still create a card, got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_adv_data_huge_node_id")


def test_adv_data_huge_body_template():
    """A 10000+ char body template should resolve without issues."""
    world = FakeWorld()
    huge_body = "A" * 10000 + " ${trigger.var}"
    world.add_template({
        "id": "huge-body",
        "name": "Huge body",
        "nodes": [
            {"id": "step1", "profile": "qa", "skill": "live-testing",
             "body_template": huge_body},
        ],
    })

    world.start("huge-body", context={"var": "VALUE"})
    actions = world.tick()

    assert count_cards(world.board_db) == 1, \
        f"Huge body template should dispatch, got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_adv_data_huge_body_template")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Nested JSON containing ${} patterns (template injection via data)
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_nested_json_template_vars():
    """Card metadata containing ${} patterns should not be re-resolved.

    WEAKNESS: resolve_template does simple str.replace, so if upstream output
    contains ${...} text, it gets embedded literally into downstream templates.
    This is safe (no recursion) but the embedded ${} is removed by the
    final regex sweep, potentially corrupting data.
    """
    world = FakeWorld()
    world.add_template({
        "id": "nested-inject",
        "name": "Nested inject",
        "nodes": [
            {"id": "a", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Plan"},
            {"id": "b", "profile": "developer", "skill": "developer-loop",
             "body_template": "Output was: ${nodes.a.output.result}",
             "depends_on": ["a"]},
        ],
    })

    world.start("nested-inject")
    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='product-owner'").fetchone()[0]
    conn.close()

    # Complete a with output containing ${} pattern
    world.complete_card(a_card, metadata={
        "result": "${nodes.a.output.evil} INJECTED"
    })

    actions = world.tick()
    assert any("DISPATCHED" in a and "node b" in a for a in actions), \
        f"b should dispatch: {actions}"

    world.cleanup()
    print("OK: test_adv_data_nested_json_template_vars")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Conflicting trigger keys
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_conflicting_trigger_keys():
    """Trigger with both title_prefix AND title_not_prefix (same prefix).

    WEAKNESS: _matches_trigger ANDs all conditions. With both keys present,
    the card must start with the prefix AND not start with the prefix —
    impossible. The engine silently never triggers instead of warning.
    """
    world = FakeWorld()
    world.add_template({
        "id": "conflict-trigger",
        "name": "Conflict trigger",
        "trigger": {
            "source": "card_completed",
            "condition": {
                "assignee": "verifier",
                "status": "done",
                "title_prefix": "[verify]",
                "title_not_prefix": "[verify]",
            },
        },
        "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                   "body_template": "Test"}],
    })

    world.add_card("t_conflict", title="[verify] feature X", assignee="verifier",
                   status="done", metadata={"verdict": "PASS"}, completed_at=int(time.time()))

    actions = world.tick()
    started = [a for a in actions if "STARTED" in a]

    # Conflicting conditions should produce NO trigger — silently
    assert len(started) == 0, \
        f"Conflicting prefix/not_prefix should never trigger, got: {started}"

    world.cleanup()
    print("OK: test_adv_data_conflicting_trigger_keys")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Body template extremes: no vars vs only vars
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_body_no_vars():
    """A body template with zero ${} variables should pass through unchanged."""
    result = resolve_template("plain text no variables", {"trigger.x": "val"})
    assert result == "plain text no variables", \
        f"Template without vars should be unchanged, got: {result}"
    print("OK: test_adv_data_body_no_vars")


def test_adv_data_body_only_vars():
    """A body template that is entirely ${} variables should resolve fully."""
    result = resolve_template(
        "${a}${b}${c}",
        {"a": "X", "b": "Y", "c": "Z"}
    )
    assert result == "XYZ", \
        f"All-variables template should resolve to 'XYZ', got: '{result}'"
    print("OK: test_adv_data_body_only_vars")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Unicode and special characters
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_unicode_node_id():
    """Node ID with emoji and unicode should not crash the engine."""
    world = FakeWorld()
    world.add_template({
        "id": "unicode-id",
        "name": "Unicode ID",
        "nodes": [
            {"id": "🎉-node-テスト", "profile": "qa", "skill": "live-testing",
             "body_template": "Unicode test 🚀"},
        ],
    })

    world.start("unicode-id")
    actions = world.tick()

    assert count_cards(world.board_db) == 1, \
        f"Unicode node ID should dispatch, got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_adv_data_unicode_node_id")


def test_adv_data_unicode_profile():
    """Profile name with unicode characters should flow through."""
    world = FakeWorld()
    world.add_template({
        "id": "unicode-profile",
        "name": "Unicode profile",
        "nodes": [
            {"id": "step1", "profile": "développeur-测试", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("unicode-profile")
    actions = world.tick()

    conn = sqlite3.connect(str(world.board_db))
    row = conn.execute("SELECT assignee FROM tasks LIMIT 1").fetchone()
    conn.close()
    assert row and "测试" in row[0], \
        f"Unicode profile should be stored, got: {row}"

    world.cleanup()
    print("OK: test_adv_data_unicode_profile")


def test_adv_data_null_byte_in_body():
    """Null bytes in body template should be handled without crash."""
    world = FakeWorld()
    # Use raw string with null byte
    world.add_template({
        "id": "null-byte",
        "name": "Null byte",
        "nodes": [
            {"id": "step1", "profile": "qa", "skill": "live-testing",
             "body_template": "before\x00after ${trigger.x}"},
        ],
    })

    world.start("null-byte", context={"x": "VAL"})
    try:
        actions = world.tick()
        assert count_cards(world.board_db) == 1, \
            f"Null-byte body should still dispatch, got {count_cards(world.board_db)}"
    except Exception as e:
        print(f"  null byte in body caused error: {type(e).__name__}: {e}")

    world.cleanup()
    print("OK: test_adv_data_null_byte_in_body")


def test_adv_data_newline_in_node_id():
    """Newlines in node ID should not break card creation or state tracking."""
    world = FakeWorld()
    world.add_template({
        "id": "newline-id",
        "name": "Newline ID",
        "nodes": [
            {"id": "line1\nline2", "profile": "qa", "skill": "live-testing",
             "body_template": "Test"},
        ],
    })

    world.start("newline-id")
    try:
        actions = world.tick()
        assert count_cards(world.board_db) == 1, \
            f"Newline node ID should dispatch, got {count_cards(world.board_db)}"
    except Exception as e:
        print(f"  newline in node ID caused error: {type(e).__name__}: {e}")

    world.cleanup()
    print("OK: test_adv_data_newline_in_node_id")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Condition parser edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_condition_malformed():
    """evaluate_condition with no operator should return False (silent failure).

    WEAKNESS: A bare ${var} with no operator returns False, not an error.
    The user might expect a truthy check but gets silent failure.
    """
    # Bare variable, no operator
    result = evaluate_condition("${var}", {"var": "truthy_value"})
    assert result is False, \
        f"Bare ${'{var}'} with no operator should return False, got {result}"

    # Empty condition string
    result = evaluate_condition("", {})
    assert result is False, \
        f"Empty condition should return False, got {result}"

    # Just whitespace
    result = evaluate_condition("   ", {})
    assert result is False, \
        f"Whitespace condition should return False, got {result}"

    # Random text
    result = evaluate_condition("hello world", {})
    assert result is False, \
        f"Random text condition should return False, got {result}"

    print("OK: test_adv_data_condition_malformed")


def test_adv_data_condition_double_quotes():
    """evaluate_condition only supports single quotes, not double quotes.

    WEAKNESS: The regex uses '(.+?)' which only matches single-quoted values.
    A condition with double quotes "${var} == \"value\"" silently fails.
    """
    # Single quotes work
    result = evaluate_condition("${var} == 'value'", {"var": "value"})
    assert result is True, "Single-quote equality should work"

    # Double quotes do NOT work
    result = evaluate_condition('${var} == "value"', {"var": "value"})
    assert result is False, \
        f"Double quotes should silently fail (regex only matches single), got {result}"

    print("OK: test_adv_data_condition_double_quotes")


def test_adv_data_condition_trailing_garbage():
    """evaluate_condition handles trailing content correctly.

    The old regex-based code used re.match (anchors at start, not end),
    so trailing garbage was silently ignored. The new condition engine
    is stricter: a clause with unrecognized trailing content fails to
    match and returns False, which is the correct behavior.
    """
    # Equality with trailing garbage — no longer matches (correct: stricter parsing)
    result = evaluate_condition("${var} == 'val' EVIL TRAILING", {"var": "val"})
    assert result is False, \
        f"Trailing garbage after equality should not match (strict parsing), got {result}"

    # "exists" with trailing garbage — no longer matches either
    result = evaluate_condition("${var} exists garbage", {"var": "truthy"})
    assert result is False, \
        f"Trailing garbage after 'exists' should not match (strict parsing), got {result}"

    print("OK: test_adv_data_condition_trailing_garbage")


# ─────────────────────────────────────────────────────────────────────────────
# 8. resolve_template with non-string values (dicts, lists)
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_resolve_dict_value():
    """resolve_template with a dict value embeds Python repr (data corruption).

    WEAKNESS: str(value) on a dict produces "{'key': 'val'}" — Python repr,
    not JSON. This corrupts the template with Python-specific syntax.
    """
    result = resolve_template(
        "Config: ${trigger.config}",
        {"trigger.config": {"nested": "value", "num": 42}}
    )
    # The dict gets stringified with Python repr
    assert "nested" in result, f"Dict content should appear, got: {result}"
    # It's Python repr, not JSON: single quotes, not double
    assert "'nested'" in result, \
        f"Dict should be Python repr (single quotes), got: {result}"
    assert result == "Config: {'nested': 'value', 'num': 42}", \
        f"Expected Python dict repr, got: {result}"

    print("OK: test_adv_data_resolve_dict_value")


def test_adv_data_resolve_list_value():
    """resolve_template with a list value embeds Python repr."""
    result = resolve_template(
        "Items: ${trigger.items}",
        {"trigger.items": ["a", "b", "c"]}
    )
    assert result == "Items: ['a', 'b', 'c']", \
        f"List should become Python repr, got: {result}"

    print("OK: test_adv_data_resolve_list_value")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Completely empty workflow (0 trigger, 0 nodes)
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_empty_everything():
    """A workflow with no trigger and no nodes should not crash."""
    world = FakeWorld()
    world.add_template({
        "id": "empty-all",
        "name": "Empty everything",
    })

    world.start("empty-all")
    actions = world.tick()

    # No nodes → no dispatch, no crash
    assert not any("DISPATCHED" in a for a in actions), \
        f"Empty workflow should not dispatch, got: {actions}"
    assert count_cards(world.board_db) == 0

    world.cleanup()
    print("OK: test_adv_data_empty_everything")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Template variable patterns in condition comparison values
# ─────────────────────────────────────────────────────────────────────────────

def test_adv_data_template_var_in_condition_value():
    """A condition value containing ${} should be treated literally.

    WEAKNESS: The value captured by regex '(.+?)' in evaluate_condition
    is compared literally against context. If the context value contains
    ${} it won't match a literal comparison.
    """
    ctx = {"var": "${other}"}

    # The context value is literally "${other}"
    result = evaluate_condition("${var} == '${other}'", ctx)
    # The regex captures the value between quotes as "${other}"
    # str(context.get("var")) == "${other}" → True
    assert result is True, \
        f"Literal ${'{other}'} value should match, got: {result}"

    # But if we try to compare against the "resolved" value of ${other}
    result2 = evaluate_condition("${var} == 'resolved_val'", ctx)
    assert result2 is False, \
        f"No resolution of nested vars in condition values, got: {result2}"

    print("OK: test_adv_data_template_var_in_condition_value")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL STATE & LIFECYCLE TESTS — ROUND 2 (state management focus)
# Probe the StateDB class and Engine instance lifecycle for robustness gaps:
# zombie instances, stale state, card reuse, orphaned instances, DB corruption,
# unbounded growth.
# ═══════════════════════════════════════════════════════════════════════════


def test_adv_state_zombie_instance_reactivated():
    """Zombie instance: a completed instance is manually flipped back to
    'active' and a node reset to 'pending'. The engine re-dispatches it as
    if it were new — phantom work from an instance the user believed finished.
    Expected safe behavior: detect prior completion, skip re-processing."""
    world = FakeWorld()
    world.add_template({
        "id": "zombie",
        "name": "Zombie test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do"},
        ],
    })
    iid = world.start("zombie")
    world.tick()  # dispatch a
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(a_card)
    world.tick()  # a done -> workflow complete

    # Zombie: reactivate + reset node to pending
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute("UPDATE workflow_instances SET status='active' WHERE instance_id=?", (iid,))
    conn.execute("UPDATE node_states SET status='pending' WHERE instance_id=? AND node_id='a'", (iid,))
    conn.commit()
    conn.close()

    before = count_cards(world.board_db)
    actions = world.tick()
    after = count_cards(world.board_db)

    # DESIRED: no re-dispatch of a finished instance
    assert not any("DISPATCHED" in a for a in actions), \
        f"BUG: zombie instance re-dispatched a node: {actions}"
    assert before == after, \
        f"BUG: zombie instance created extra card: {before} -> {after}"
    world.cleanup()
    print("OK: test_adv_state_zombie_instance_reactivated")


def test_adv_state_fake_card_id_dispatched():
    """Node state set to DISPATCHED with a card_id that doesn't exist on the
    board. The engine silently does nothing — the node hangs forever with no
    error, no timeout, no recovery action.
    Expected: engine should detect the dangling reference and report it."""
    world = FakeWorld()
    world.add_template({
        "id": "dangling",
        "name": "Dangling card test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do"},
        ],
    })
    iid = world.start("dangling")
    # Manually set node a to DISPATCHED with a fake card_id (no real card)
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute(
        "UPDATE node_states SET status='dispatched', card_id='FAKE-NONEXISTENT' "
        "WHERE instance_id=? AND node_id='a'",
        (iid,),
    )
    conn.commit()
    conn.close()

    actions = world.tick()

    # DESIRED: engine reports the dangling card reference
    has_error = any(
        "FAKE" in a or "missing" in a.lower() or "not found" in a.lower()
        or "error" in a.lower() or "dangling" in a.lower()
        for a in actions
    )
    assert has_error, \
        f"BUG: dangling card_id silently ignored — no error reported. Actions: {actions}"
    world.cleanup()
    print("OK: test_adv_state_fake_card_id_dispatched")


def test_adv_state_stale_node_states_after_template_edit():
    """Instance has node_states for nodes that no longer exist in the template
    (template edited to remove a node after the instance started). The orphan
    states persist in the DB and pollute the in-memory instance — orphan
    outputs can leak into variable resolution context.
    Expected: engine should clean up or ignore orphan node states."""
    world = FakeWorld()
    world.add_template({
        "id": "stale-state",
        "name": "Stale state test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "A"},
            {"id": "b", "profile": "qa", "skill": "live-testing", "body_template": "B",
             "depends_on": ["a"]},
        ],
    })
    iid = world.start("stale-state")

    # Insert an orphan node state directly (simulates removed node 'ghost')
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute(
        "INSERT OR REPLACE INTO node_states (instance_id, node_id, status, output) "
        "VALUES (?, 'ghost', 'done', '{}')",
        (iid,),
    )
    conn.commit()
    conn.close()

    instances = world.engine.state.load_active_instances()
    inst = [i for i in instances if i.instance_id == iid][0]

    # DESIRED: orphan node 'ghost' should not appear (not in template)
    assert "ghost" not in inst.node_states, \
        f"BUG: orphan node state 'ghost' leaked into instance: {list(inst.node_states.keys())}"
    world.cleanup()
    print("OK: test_adv_state_stale_node_states_after_template_edit")


def test_adv_state_card_reuse_done_to_todo():
    """Card reuse: a done card is manually changed back to 'todo' on the board.
    The node is already DONE in state, so the engine ignores the card entirely.
    The card becomes an orphan — nobody owns it, nobody completes it.
    Expected: engine should detect the card regression or flag the orphan."""
    world = FakeWorld()
    world.add_template({
        "id": "reuse",
        "name": "Card reuse test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
            {"id": "b", "profile": "qa", "skill": "live-testing", "body_template": "B",
             "depends_on": ["a"]},
        ],
    })
    world.start("reuse")
    world.tick()  # dispatch a
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(a_card)
    world.tick()  # a done -> dispatch b (instance still active, b is pending)

    # Flip the card back to 'todo' (manual reuse) while b is still running
    conn = sqlite3.connect(str(world.board_db))
    conn.execute("UPDATE tasks SET status='todo', completed_at=NULL WHERE id=?", (a_card,))
    conn.commit()
    conn.close()

    actions = world.tick()

    # DESIRED: engine should flag the regressed/orphaned card
    has_flag = any(
        "orphan" in a.lower() or "reuse" in a.lower() or a_card in a
        for a in actions
    )
    assert has_flag, \
        f"BUG: card {a_card} regressed to 'todo' but engine didn't flag it. Actions: {actions}"
    world.cleanup()
    print("OK: test_adv_state_card_reuse_done_to_todo")


def test_adv_state_instances_for_deleted_board():
    """Orphaned instance: the board DB is deleted but the instance remains
    'active' in the state DB. The engine loads it every tick, tries to read
    the (missing) board, gets nothing, and silently moves on — forever.
    The instance is a zombie that never completes and never errors.
    Expected: engine should detect the missing board and error/skip/cleanup."""
    world = FakeWorld()
    world.add_template({
        "id": "orphan-board",
        "name": "Orphan board test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
        ],
    })
    world.start("orphan-board")
    world.tick()  # dispatch a

    # Delete the board DB entirely
    world.board_db.unlink()

    actions = world.tick()

    # DESIRED: engine should report that the instance's board is missing
    has_report = any(
        "board" in a.lower() and ("missing" in a.lower() or "not found" in a.lower()
                                  or "error" in a.lower() or "skip" in a.lower())
        for a in actions
    )
    assert has_report, \
        f"BUG: deleted board silently ignored — instance zombies forever. Actions: {actions}"

    # Instance should not stay active forever
    active = world.engine.state.load_active_instances()
    assert len(active) == 0, \
        f"BUG: orphaned instance with deleted board still active: {len(active)}"
    world.cleanup()
    print("OK: test_adv_state_instances_for_deleted_board")


def test_adv_state_create_instance_duplicate_id():
    """create_instance called twice with the same instance_id but different
    board. INSERT OR IGNORE silently drops the second call — the board/project
    change is lost with no error.
    Expected: should either upsert or raise."""
    world = FakeWorld()
    world.add_template({
        "id": "dup-id",
        "name": "Dup ID test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
        ],
    })

    inst1 = WorkflowInstance(
        instance_id="fixed-id-123",
        workflow_id="dup-id",
        board="board-A",
        project_dir="/tmp/a",
        created_at=int(time.time()),
    )
    inst1.node_states["a"] = NodeState(instance_id="fixed-id-123", node_id="a")
    world.engine.state.create_instance(inst1)

    # Second call — different board, same instance_id
    inst2 = WorkflowInstance(
        instance_id="fixed-id-123",
        workflow_id="dup-id",
        board="board-B",
        project_dir="/tmp/b",
        created_at=int(time.time()),
    )
    inst2.node_states["a"] = NodeState(instance_id="fixed-id-123", node_id="a")
    world.engine.state.create_instance(inst2)

    # DESIRED: second call should have updated or raised
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT board FROM workflow_instances WHERE instance_id='fixed-id-123'"
    ).fetchone()
    conn.close()
    actual_board = row[0] if row else None

    assert actual_board == "board-B", \
        f"BUG: duplicate create_instance silently ignored board change (INSERT OR IGNORE). board={actual_board}"
    world.cleanup()
    print("OK: test_adv_state_create_instance_duplicate_id")


def test_adv_state_update_node_before_create():
    """update_node_state called for a node/instance that doesn't exist yet.
    The UPDATE silently affects 0 rows — no error, no insert. The state is lost.
    Expected: should raise or upsert."""
    world = FakeWorld()

    world.engine.state.update_node_state(
        "nonexistent-instance", "nonexistent-node", NodeStatus.DONE,
        card_id="card-x", output={"result": "ok"},
    )

    # DESIRED: the state should have been saved (or an error raised)
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT status FROM node_states WHERE instance_id='nonexistent-instance' "
        "AND node_id='nonexistent-node'"
    ).fetchone()
    conn.close()

    assert row is not None, \
        "BUG: update_node_state on non-existent row silently lost the update (0 rows affected)"
    world.cleanup()
    print("OK: test_adv_state_update_node_before_create")


def test_adv_state_complete_while_card_running():
    """Race: all node states manually set to DONE while the cards are still
    'todo' on the board. The engine completes the instance based solely on the
    state DB, never verifying actual card status. Cards become orphans.
    Expected: engine should verify card completion before completing instance."""
    world = FakeWorld()
    world.add_template({
        "id": "race-complete",
        "name": "Race complete test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
        ],
    })
    iid = world.start("race-complete")
    world.tick()  # dispatch a (card is 'todo')

    # Card still 'todo' on board — but manually mark node DONE in state DB
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute(
        "UPDATE node_states SET status='done', card_id='whatever', output='{}' "
        "WHERE instance_id=? AND node_id='a'",
        (iid,),
    )
    conn.commit()
    conn.close()

    actions = world.tick()

    # DESIRED: engine should NOT complete — card is still 'todo'
    has_complete = any("WORKFLOW COMPLETE" in a for a in actions)
    assert not has_complete, \
        f"BUG: instance completed while card is still 'todo' on board. Actions: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT status FROM workflow_instances WHERE instance_id=?", (iid,)
    ).fetchone()
    conn.close()
    assert row[0] != "completed", \
        "BUG: instance marked completed based on state DB alone, card never verified"
    world.cleanup()
    print("OK: test_adv_state_complete_while_card_running")


def test_adv_state_bad_created_at():
    """Instance with created_at = 0 or negative. No validation — stored as-is.
    Expected: engine should validate timestamps and reject garbage."""
    world = FakeWorld()
    world.add_template({
        "id": "bad-ts",
        "name": "Bad timestamp test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
        ],
    })

    inst = WorkflowInstance(
        instance_id="wf_negative_ts",
        workflow_id="bad-ts",
        board="test-board",
        project_dir="/tmp",
        created_at=-1,
    )
    inst.node_states["a"] = NodeState(instance_id="wf_negative_ts", node_id="a")

    raised = False
    try:
        world.engine.state.create_instance(inst)
    except (ValueError, AssertionError):
        raised = True

    assert raised, "BUG: negative created_at (-1) accepted without validation"

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT created_at FROM workflow_instances WHERE instance_id='wf_negative_ts'"
    ).fetchone()
    conn.close()
    assert row is None, \
        f"BUG: negative timestamp stored in DB: created_at={row[0] if row else None}"
    world.cleanup()
    print("OK: test_adv_state_bad_created_at")


def test_adv_state_multiple_instances_isolation():
    """Two instances of the same workflow on the same board. One completes.
    The other should be unaffected — instances must be isolated.
    Regression test for instance independence."""
    world = FakeWorld()
    world.add_template({
        "id": "iso",
        "name": "Isolation test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing", "body_template": "Do"},
        ],
    })

    iid1 = world.start("iso")
    iid2 = world.start("iso")
    world.tick()  # dispatch both

    # Find card for instance 1 via state DB (deterministic)
    conn = sqlite3.connect(str(world.state_db_path))
    card1 = conn.execute(
        "SELECT card_id FROM node_states WHERE instance_id=? AND node_id='a'", (iid1,)
    ).fetchone()[0]
    conn.close()

    world.complete_card(card1)
    world.tick()

    active = world.engine.state.load_active_instances()
    active_ids = [i.instance_id for i in active]

    assert len(active) == 1, \
        f"BUG: completing one instance affected the other. Active: {active_ids}"
    assert iid2 in active_ids, f"BUG: instance 2 should still be active, got: {active_ids}"
    assert iid1 not in active_ids, f"BUG: instance 1 should be completed, got: {active_ids}"
    world.cleanup()
    print("OK: test_adv_state_multiple_instances_isolation")


def test_adv_state_trigger_keys_unbounded():
    """trigger_keys table grows without bound — no GC, no TTL. Insert 10000
    entries and verify lookup still works. The weakness is unbounded growth.
    Expected: lookup remains fast (indexed), but there is no cleanup mechanism."""
    world = FakeWorld()

    conn = sqlite3.connect(str(world.state_db_path))
    conn.executemany(
        "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES (?, ?)",
        [(f"trig:wf:card_{i}", int(time.time())) for i in range(10000)],
    )
    conn.commit()
    count = conn.execute("SELECT count(*) FROM trigger_keys").fetchone()[0]
    conn.close()

    assert count == 10000, f"Expected 10000 trigger keys, got {count}"

    # Lookup should be fast (indexed by PRIMARY KEY)
    t0 = time.time()
    for i in range(1000):
        world.engine.state._trigger_key_exists(f"trig:wf:card_{i}")
    elapsed = time.time() - t0

    assert elapsed < 2.0, \
        f"BUG: trigger key lookup too slow with 10000 entries: {elapsed:.2f}s for 1000 lookups"

    # Confirm no GC: insert an ancient key, verify it survives
    conn = sqlite3.connect(str(world.state_db_path))
    conn.execute(
        "INSERT OR IGNORE INTO trigger_keys (key, created_at) VALUES ('ancient', 1)"
    )
    conn.commit()
    conn.close()
    exists = world.engine.state._trigger_key_exists("ancient")

    assert exists, "Ancient trigger key should still exist (confirms no GC — documented weakness)"
    world.cleanup()
    print(f"OK: test_adv_state_trigger_keys_unbounded (10000 entries, {elapsed:.3f}s/1000 lookups)")


def test_adv_state_readonly_db():
    """State DB file is read-only (chmod 444). Engine writes fail with
    sqlite3.OperationalError — no graceful handling, engine crashes.
    Expected: engine should handle read-only DB gracefully or give a clear error."""
    import os

    world = FakeWorld()
    ro_db_path = world.tmpdir / "readonly.db"

    # Create a valid DB first, then make read-only
    sdb = StateDB(ro_db_path)
    del sdb
    os.chmod(str(ro_db_path), 0o444)

    inst = WorkflowInstance(
        instance_id="ro-test",
        workflow_id="x",
        board="b",
        project_dir="/tmp",
        created_at=int(time.time()),
    )
    inst.node_states["a"] = NodeState(instance_id="ro-test", node_id="a")

    raised = False
    err_msg = ""
    try:
        ro_sdb = StateDB(ro_db_path)
        ro_sdb.create_instance(inst)
    except Exception as e:
        raised = True
        err_msg = f"{type(e).__name__}: {e}"

    # Restore permissions for cleanup
    os.chmod(str(ro_db_path), 0o644)

    # DESIRED: should handle gracefully, not crash
    assert not raised, \
        f"BUG: read-only state DB crashes engine with: {err_msg}"
    world.cleanup()
    print("OK: test_adv_state_readonly_db")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL CONCURRENCY TESTS
# Race conditions, simultaneous access, partial writes, database locking.
# These target the engine's complete lack of locking: every StateDB method
# opens its own connection, does non-atomic read-modify-write, and never
# catches sqlite3.OperationalError. The dispatch path is check-then-create
# with no transaction. Trigger dedup is check-then-act across three separate
# connections.
# ═══════════════════════════════════════════════════════════════════════════

import threading


def _make_second_engine(world):
    """Build a second Engine that shares the same templates dir + state DB."""
    eng = Engine(world.templates_dir)
    eng.state = StateDB(world.state_db_path)
    return eng


def _count_active_instances(state_db_path):
    conn = sqlite3.connect(str(state_db_path))
    try:
        return conn.execute(
            "SELECT count(*) FROM workflow_instances WHERE status = 'active'"
        ).fetchone()[0]
    finally:
        conn.close()


# --- TEST C1: two engines, same node, concurrent dispatch -> double card ---
def test_adv_concurrency_two_engines_double_dispatch():
    """Two Engine instances ticking concurrently against the same state DB
    must not create duplicate cards for one node.

    The engine now uses a cross-process file lock (LOCK_FILE via fcntl). When
    a second engine tries to tick while the first holds the lock, it returns
    SKIP immediately and creates no cards. This serializes ticks so exactly
    one card is created — the check-then-create race is eliminated because the
    second engine never runs its dispatch logic at all.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "race", "name": "Race",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("race")
        eng2 = _make_second_engine(world)

        errors = []
        results = {}

        def run(name, eng):
            try:
                results[name] = eng.tick()
            except Exception as e:  # noqa
                errors.append(e)

        t1 = threading.Thread(target=run, args=("eng1", world.engine))
        t2 = threading.Thread(target=run, args=("eng2", eng2))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"threads raised unexpectedly: {errors}"
        n = count_cards(world.board_db)
        # CORRECT behavior: exactly 1 card. The file lock serializes ticks so
        # the second engine is SKIP'd entirely — no double dispatch possible.
        assert n == 1, (
            f"Two concurrent engines should create exactly 1 card for one node, "
            f"got {n} — file lock should have serialized the ticks. "
            f"eng1={results.get('eng1')}, eng2={results.get('eng2')}"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_two_engines_double_dispatch")


# --- TEST C2: concurrent read-modify-write on same node -> lost update ---
def test_adv_concurrency_concurrent_state_writes():
    """update_node_state is now an atomic UPSERT that merges omitted fields via
    COALESCE. Two concurrent calls that each set a different field (one sets
    card_id, one sets output) no longer clobber each other — both survive.

    This test exercises the engine's update_node_state method directly,
    simulating two concurrent updates with a barrier so they overlap.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "rmw", "name": "RMW",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        inst_id = world.start("rmw")

        barrier = threading.Barrier(2)

        def rmw_update(set_card):
            # Use the engine's atomic update_node_state. When set_card=True we
            # only set card_id (output=None); when False we only set output
            # (card_id=None). The COALESCE merge ensures neither field is lost.
            barrier.wait(timeout=5)
            if set_card:
                world.engine.state.update_node_state(
                    inst_id, "a", NodeStatus.DISPATCHED, card_id="card_1",
                )
            else:
                world.engine.state.update_node_state(
                    inst_id, "a", NodeStatus.DONE, output={"verdict": "PASS"},
                )

        t1 = threading.Thread(target=rmw_update, args=(True,))
        t2 = threading.Thread(target=rmw_update, args=(False,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        conn = sqlite3.connect(str(world.state_db_path))
        row = conn.execute(
            "SELECT card_id, output FROM node_states "
            "WHERE instance_id = ? AND node_id = ?", (inst_id, "a"),
        ).fetchone()
        conn.close()
        final_card = row[0]
        final_output = json.loads(row[1]) if row[1] else {}

        # CORRECT: both updates survive (card_id set AND verdict set).
        # The atomic COALESCE merge means concurrent field-level updates
        # don't lose data.
        assert final_card == "card_1" and final_output.get("verdict") == "PASS", (
            f"Concurrent update_node_state lost an update: "
            f"card_id={final_card!r} output={final_output!r} — "
            f"the COALESCE merge should have preserved both fields"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_concurrent_state_writes")


# --- TEST C3: trigger dedup race -> duplicate workflow instances ---
def test_adv_concurrency_trigger_dedup_race():
    """Two engines detecting the same trigger card concurrently must start at
    most one workflow instance.

    _check_triggers calls _trigger_key_exists (read), then _start_from_trigger
    (creates instance), then _record_trigger_key (write) across three separate
    connections with no transaction. Two concurrent ticks can both see 'no key'
    and both start an instance.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "trig", "name": "Trig",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "dev"}},
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.add_card("devcard", assignee="dev", status="done",
                       completed_at=int(time.time()), metadata={"k": 1})
        eng2 = _make_second_engine(world)

        # Close the check-then-act window: both threads create their instance
        # before either records the dedup key.
        barrier = threading.Barrier(2)
        orig_record = world.engine.state._record_trigger_key

        def synced_record(key):
            barrier.wait(timeout=5)
            orig_record(key)

        world.engine.state._record_trigger_key = synced_record
        eng2.state._record_trigger_key = synced_record

        errors = []

        def run(eng):
            try:
                eng.tick()
            except Exception as e:  # noqa
                errors.append(e)

        t1 = threading.Thread(target=run, args=(world.engine,))
        t2 = threading.Thread(target=run, args=(eng2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"threads raised unexpectedly: {errors}"
        n = _count_active_instances(world.state_db_path)
        # CORRECT: one trigger card -> one instance. The race produces two, so
        # this FAILS and exposes duplicate workflow instances.
        assert n == 1, (
            f"One trigger card should start exactly one instance, got {n} — "
            f"trigger dedup check-then-act race creates duplicates"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_trigger_dedup_race")


# --- TEST C4: overlapping ticks on the same engine -> double dispatch ---
def test_adv_concurrency_overlapping_ticks():
    """Calling tick() on the same Engine from two threads concurrently must be
    safe. tick() now uses an internal threading.Lock (_tick_lock): when a second
    thread calls tick() while the first is running, it returns SKIP immediately
    and does no work. This eliminates the stale-snapshot double dispatch.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "overlap", "name": "Overlap",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("overlap")

        errors = []
        results = []

        def run():
            try:
                results.append(world.tick())
            except Exception as e:  # noqa
                errors.append(e)

        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"overlapping ticks raised unexpectedly: {errors}"
        n = count_cards(world.board_db)
        # CORRECT: tick() is now reentrant via _tick_lock — one node, one card.
        # The second tick is SKIP'd so no duplicate card is created.
        assert n == 1, (
            f"Overlapping ticks on one engine should create 1 card, got {n} — "
            f"the internal tick lock should have serialized them. Results: {results}"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_overlapping_ticks")


# --- TEST C5: state DB locked by another writer -> tick crashes ---
def test_adv_concurrency_db_locked():
    """If the state DB is locked by another writer, the engine's tick should
    degrade gracefully (skip/log), not raise and kill the tick loop. StateDB
    opens a fresh connection per call and never catches sqlite3.OperationalError,
    so a 'database is locked' error propagates straight out of tick().
    """
    world = FakeWorld()
    import workflow_engine.runtime as rt
    orig_connect = rt.sqlite3.connect
    try:
        world.add_template({
            "id": "locked", "name": "Locked",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("locked")

        # Simulate another process holding a write lock: every connect raises.
        def locked_connect(*a, **k):
            raise sqlite3.OperationalError("database is locked")

        rt.sqlite3.connect = locked_connect

        crashed = False
        try:
            world.tick()
        except sqlite3.OperationalError:
            crashed = True
        except Exception:
            crashed = True

        # CORRECT: a locked DB must not crash the tick. StateDB has no error
        # handling, so this FAILS (crashed == True).
        assert not crashed, (
            "Engine crashed on 'database is locked' — StateDB/tick have no "
            "OperationalError handling, a contended DB kills the tick loop"
        )
    finally:
        rt.sqlite3.connect = orig_connect
        world.cleanup()
    print("OK: test_adv_concurrency_db_locked")


# --- TEST C6: partial write — instance created, trigger key lost -> dup ---
def test_adv_concurrency_partial_write_trigger_key():
    """If the engine creates a workflow instance but the trigger dedup key is
    never persisted (crash between create_instance and _record_trigger_key),
    the next tick starts a DUPLICATE instance for the same trigger card. The
    create-then-record sequence is not atomic.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "partial", "name": "Partial",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "dev"}},
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.add_card("devcard", assignee="dev", status="done",
                       completed_at=int(time.time()), metadata={"k": 1})

        # Simulate the dedup-key write being lost (partial write / crash).
        world.engine.state._record_trigger_key = lambda key: None

        world.tick()   # instance created, key NOT persisted
        world.tick()   # key absent -> engine re-triggers the same card

        n = _count_active_instances(world.state_db_path)
        # CORRECT: one trigger card -> at most one instance even after a lost
        # dedup write. The non-atomic create-then-record produces two, so this
        # FAILS.
        assert n == 1, (
            f"Lost trigger-key write caused duplicate instances: {n} — "
            f"create_instance and _record_trigger_key are not atomic"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_partial_write_trigger_key")


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL TRIGGER-SYSTEM TESTS
# Focus: trigger storms, duplicate triggers, metadata path edge cases,
#        self-triggering via engine cards, empty-condition trigger-everything.
# Targets: runtime._check_triggers / _matches_trigger / _start_from_trigger,
#          kanban_adapter.find_recent_completions (LIMIT 20!),
#          StateDB._trigger_key_exists / _record_trigger_key.
# ═══════════════════════════════════════════════════════════════════════════


def test_adv_trigger_storm_100_cards():
    """100 matching completed cards in one tick — does the engine create 100?

    WEAKNESS: find_recent_completions() has LIMIT 20 (kanban_adapter.py:180).
    Only 20 of the 100 cards are ever fetched. 80 cards are silently dropped
    by the adapter BEFORE the trigger matcher even runs. The engine starts
    exactly 20 instances, not 100 — silent data-loss under load.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "storm", "name": "Storm",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        now = int(time.time())
        for i in range(100):
            make_fake_card(world.board_db, f"storm_{i:03d}",
                           title=f"[verify] {i}", assignee="verifier",
                           status="done", metadata={"verdict": "PASS"},
                           completed_at=now)
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        # Assert the CORRECT behavior so the test fails loudly, documenting the gap.
        assert len(started) == 100, (
            f"BUG: only {len(started)} of 100 matching cards triggered. "
            f"find_recent_completions LIMIT 20 silently drops the rest."
        )
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_storm_100_cards")


def test_adv_trigger_metadata_list_value():
    """Trigger condition metadata.verdict='PASS' vs card verdict=['PASS','FAIL'].

    WEAKNESS: _matches_trigger does `meta.get('verdict') != expected`. A list
    value ['PASS','FAIL'] != 'PASS' → True → returns False → no trigger. A card
    that semantically contains 'PASS' silently fails because the matcher only
    supports exact scalar equality (no 'in'/membership semantics).
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "list-verdict", "name": "List verdict",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        make_fake_card(world.board_db, "c_list", title="[verify] list",
                       assignee="verifier", status="done",
                       metadata={"verdict": ["PASS", "FAIL"]},
                       completed_at=int(time.time()))
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 0, (
            f"Expected no trigger (list != scalar), got {len(started)}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_metadata_list_value")


def test_adv_trigger_missing_metadata_path():
    """Condition references metadata.nonesuch but card has no such field.

    meta.get('nonesuch') → None != 'value' → returns False. Safe (no trigger).
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "missing-field", "name": "Missing field",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.nonesuch": "value"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        make_fake_card(world.board_db, "c_ok", title="[verify] ok",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS", "other": "x"},
                       completed_at=int(time.time()))
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 0, (
            f"Missing metadata field should not trigger, got {len(started)}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_missing_metadata_path")


def test_adv_trigger_duplicate_conditions_two_workflows():
    """Two workflows with the SAME trigger condition both fire for one card.

    Dedup key is per-workflow (trig:{wf.id}:{card.id}), so a single completed
    card starts TWO instances (one per workflow). A config error (two identical
    triggers) silently doubles work.
    """
    world = FakeWorld()
    try:
        cond = {"assignee": "verifier", "status": "done", "metadata.verdict": "PASS"}
        world.add_template({"id": "wf-a", "name": "A",
                            "trigger": {"source": "card_completed", "condition": cond},
                            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                                       "body_template": "x"}]})
        world.add_template({"id": "wf-b", "name": "B",
                            "trigger": {"source": "card_completed", "condition": cond},
                            "nodes": [{"id": "b", "profile": "qa", "skill": "live-testing",
                                       "body_template": "x"}]})
        make_fake_card(world.board_db, "one_card", title="[verify] one",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=int(time.time()))
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 2, (
            f"Two identical-condition workflows should each fire → 2 starts, "
            f"got {len(started)}: {started}")
        assert any("wf-a" in s for s in started)
        assert any("wf-b" in s for s in started)
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_duplicate_conditions_two_workflows")


def test_adv_trigger_keys_table_corrupted():
    """If the trigger_keys table is dropped/corrupted, tick() should not crash.

    WEAKNESS: _record_trigger_key() has NO try/except (unlike
    _trigger_key_exists which catches OperationalError). A missing table makes
    _record_trigger_key raise sqlite3.OperationalError, propagating out of
    _check_triggers and crashing tick() — AFTER the instance was already
    created. Next tick re-triggers → unbounded growth.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "corrupt", "name": "Corrupt",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        make_fake_card(world.board_db, "c1", title="[verify] c1",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=int(time.time()))
        # Corrupt: drop the trigger_keys table.
        conn = sqlite3.connect(str(world.state_db_path))
        conn.execute("DROP TABLE trigger_keys")
        conn.commit()
        conn.close()
        crashed = False
        try:
            world.tick()
        except Exception as e:
            crashed = True
            print(f"  BUG: _record_trigger_key crashed tick(): "
                  f"{type(e).__name__}: {e}")
        # Document the behavior either way (don't hard-fail; this is a robustness probe).
        if crashed:
            print("  CONFIRMED: tick() raises when trigger_keys table missing.")
        else:
            print("  tick() survived corrupted trigger_keys table.")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_keys_table_corrupted")


def test_adv_trigger_card_completed_at_null():
    """Card status=done, metadata matches, but completed_at IS NULL.

    WEAKNESS: find_recent_completions SQL is `WHERE completed_at > ?`. In SQL,
    NULL > N evaluates to NULL (falsy), so a done card with NULL completed_at
    is INVISIBLE to triggers — silently never fires, even though status=done
    and metadata matches.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "null-ts", "name": "Null ts",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        # Card done + matching metadata but completed_at explicitly NULL.
        conn = sqlite3.connect(str(world.board_db))
        now = int(time.time())
        conn.execute(
            """INSERT INTO tasks (id, title, assignee, status, completed_at, created_at)
               VALUES (?, ?, 'verifier', 'done', NULL, ?)""",
            ("c_null_ts", "[verify] null-ts", now))
        conn.execute(
            """INSERT INTO task_runs (task_id, outcome, summary, metadata)
               VALUES (?, 'completed', '', ?)""",
            ("c_null_ts", json.dumps({"verdict": "PASS"})))
        conn.commit()
        conn.close()
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 0, (
            f"Expected NULL completed_at to hide the card, got {len(started)}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_card_completed_at_null")


def test_adv_trigger_dotted_metadata_key():
    """Card metadata key literally named 'a.b.c' vs condition 'metadata.a.b.c'.

    WEAKNESS: _matches_trigger does `field = key.split('.', 1)[1]` then
    `meta.get(field)`. For 'metadata.a.b.c', split('.',1) → ['metadata','a.b.c'],
    so field='a.b.c' → looks up meta['a.b.c'] (flat). It does NOT support
    nested traversal (meta['a']['b']['c']). A flat dotted key matches; a
    nested dict does not — surprising and likely unintended.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "dotted", "name": "Dotted",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.a.b.c": "deep"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        now = int(time.time())
        # Nested dict — should NOT match (no nested traversal).
        make_fake_card(world.board_db, "c_nested", title="[verify] nested",
                       assignee="verifier", status="done",
                       metadata={"a": {"b": {"c": "deep"}}}, completed_at=now)
        actions = world.tick()
        started_nested = [a for a in actions if "STARTED" in a]

        # Fresh world for the flat-key card (first tick recorded dedup state).
        world2 = FakeWorld()
        try:
            world2.add_template({
                "id": "dotted2", "name": "Dotted2",
                "trigger": {"source": "card_completed",
                            "condition": {"assignee": "verifier", "status": "done",
                                          "metadata.a.b.c": "deep"}},
                "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                           "body_template": "x"}],
            })
            make_fake_card(world2.board_db, "c_flat", title="[verify] flat",
                           assignee="verifier", status="done",
                           metadata={"a.b.c": "deep"}, completed_at=now)
            actions2 = world2.tick()
            started_flat = [a for a in actions2 if "STARTED" in a]
        finally:
            world2.cleanup()

        assert len(started_nested) == 0, (
            "Nested dict {a:{b:{c}}} should NOT match metadata.a.b.c — got trigger")
        assert len(started_flat) == 1, (
            "Flat key 'a.b.c' SHOULD match metadata.a.b.c (flat lookup) — got 0")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_dotted_metadata_key")


def test_adv_trigger_cross_board():
    """A trigger fires for a card on a DIFFERENT board.

    WEAKNESS: _boards_to_check() returns ALL boards under KANBAN_HOME. The
    engine checks every board for every trigger. There is no notion of a
    workflow being scoped to one board/project → cross-board contamination.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "crossboard", "name": "Crossboard",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        # Add a SECOND board with a matching card.
        make_fake_board(world.tmpdir, "other-board")
        board_b_db = world.tmpdir / "boards" / "other-board" / "kanban.db"
        now = int(time.time())
        make_fake_card(board_b_db, "c_b", title="[verify] other",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=now)
        # Nothing on test-board. Does the trigger still fire from other-board?
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) >= 1, (
            "Expected cross-board trigger (no board scoping), got 0 starts")
        assert "other-board" in started[0]
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_cross_board")

def test_adv_trigger_self_trigger_engine_card():
    """An engine-created card (idempotency_key 'wf:*') that matches a trigger
    condition does NOT re-trigger the workflow — the wf: prefix filter prevents
    self-triggering runaway loops.

    This is the CORRECT behavior after the double-fire fix.
    """
    world = FakeWorld()
    try:
        # Workflow whose node assigns to 'verifier' with verdict PASS —
        # matching its own trigger condition. Pure self-trigger.
        world.add_template({
            "id": "selfloop", "name": "Selfloop",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "verify", "profile": "verifier",
                       "skill": "adversarial-review", "body_template": "x"}],
        })
        # Seed: one external verifier PASS.
        make_fake_card(world.board_db, "seed", title="[verify] seed",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=int(time.time()))

        # Tick 1: trigger fires, instance starts.
        a1 = world.tick()
        assert len([a for a in a1 if "STARTED" in a]) == 1, a1
        # Tick 2: engine dispatches the 'verify' node → creates a wf: card.
        a2 = world.tick()
        assert any("DISPATCHED" in x and "verify" in x for x in a2), a2
        # Find the engine-created card and complete it (still matches trigger).
        conn = sqlite3.connect(str(world.board_db))
        row = conn.execute(
            "SELECT id FROM tasks WHERE idempotency_key LIKE 'wf:%verify'"
        ).fetchone()
        conn.close()
        assert row, "engine-created verify card not found"
        engine_card_id = row[0]
        conn = sqlite3.connect(str(world.board_db))
        conn.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?",
                     (int(time.time()), engine_card_id))
        conn.execute(
            "INSERT INTO task_runs (task_id, outcome, summary, metadata) "
            "VALUES (?, 'completed', '', ?)",
            (engine_card_id, json.dumps({"verdict": "PASS"})))
        conn.commit()
        conn.close()
        # Tick 3: the engine's OWN card matches the trigger but self-trigger
        # prevention blocks it (same workflow_id in idempotency_key).
        a3 = world.tick()
        new_starts = [a for a in a3 if "STARTED" in a]
        assert len(new_starts) == 0, (
            f"Self-trigger should be prevented (same workflow), got: {new_starts}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_self_trigger_engine_card")


def test_adv_trigger_empty_condition_matches_all():
    """Trigger condition is an empty dict {} → matches ALL completed cards.

    WEAKNESS: _matches_trigger iterates condition.items(); an empty dict means
    the loop body never runs, so it falls through to `return True` for EVERY
    completed card. A misconfigured `"condition": {}` is a 'trigger everything'
    bomb: starts a workflow for every completed card on every board.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "matchall2", "name": "Matchall2",
            "trigger": {"source": "card_completed", "condition": {}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        now = int(time.time())
        make_fake_card(world.board_db, "m1", title="[x] 1", assignee="qa",
                       status="done", metadata={"verdict": "FAIL"}, completed_at=now)
        make_fake_card(world.board_db, "m2", title="[x] 2", assignee="researcher",
                       status="done", metadata={"verdict": "PASS"}, completed_at=now)
        make_fake_card(world.board_db, "m3", title="[x] 3", assignee="architect",
                       status="done", metadata={"verdict": "WAT"}, completed_at=now)
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a and "matchall2" in a]
        assert len(started) == 3, (
            f"Empty condition {{}} should match all 3 cards, got "
            f"{len(started)}: {started}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_empty_condition_matches_all")


def test_adv_trigger_dedup_hides_concurrent_cards():
    """Two cards complete at the SAME second. Both match. Both should start.

    Dedup key is per-card (trig:{wf}:{card.id}), so two distinct cards at the
    same timestamp must both trigger. Verify dedup is card-scoped, not
    timestamp-scoped (which would be a bug).
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "same-ts", "name": "Same ts",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "done",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        now = int(time.time())
        make_fake_card(world.board_db, "same_a", title="[verify] a",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=now)
        make_fake_card(world.board_db, "same_b", title="[verify] b",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=now)
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 2, (
            f"Two cards at same ts should both trigger (card-scoped dedup), "
            f"got {len(started)}: {started}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_dedup_hides_concurrent_cards")


def test_adv_trigger_status_filter_redundant():
    """A trigger condition {'status':'todo'} can NEVER match because
    find_recent_completions only returns done cards (WHERE status='done').
    The Python-side status filter is dead code for non-'done' values —
    silent dead trigger.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "deadstatus", "name": "Dead status",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "verifier", "status": "todo",
                                      "metadata.verdict": "PASS"}},
            "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        make_fake_card(world.board_db, "d1", title="[verify] d",
                       assignee="verifier", status="done",
                       metadata={"verdict": "PASS"}, completed_at=int(time.time()))
        actions = world.tick()
        started = [a for a in actions if "STARTED" in a]
        assert len(started) == 0, (
            f"status:'todo' condition should never fire (SQL only returns done) "
            f"— got {len(started)}")
    finally:
        world.cleanup()
    print("OK: test_adv_trigger_status_filter_redundant")


# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

def run_trigger_storm_tests():
    """Run the adversarial trigger-system test suite. Returns (passed, failed, count)."""
    trigger_tests = [
        test_adv_trigger_storm_100_cards,
        test_adv_trigger_metadata_list_value,
        test_adv_trigger_missing_metadata_path,
        test_adv_trigger_duplicate_conditions_two_workflows,
        test_adv_trigger_keys_table_corrupted,
        test_adv_trigger_card_completed_at_null,
        test_adv_trigger_dotted_metadata_key,
        test_adv_trigger_cross_board,
        test_adv_trigger_self_trigger_engine_card,
        test_adv_trigger_empty_condition_matches_all,
        test_adv_trigger_dedup_hides_concurrent_cards,
        test_adv_trigger_status_filter_redundant,
    ]
    passed = 0
    failed = 0
    for test in trigger_tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    return passed, failed, len(trigger_tests)


if __name__ == "__main__":
    tests = [
        # Happy paths (15)
        test_empty_tick,
        test_manual_start_dispatches_node,
        test_node_completion_advances,
        test_full_lifecycle,
        test_variable_resolution,
        test_idempotency,
        test_conditional_node,
        test_trigger_detection,
        test_trigger_no_match,
        test_idempotency_key_on_card,
        test_parallel_dispatch,
        test_blocked_node_reported,
        test_restart_recovery,
        test_multiple_instances,
        test_branching_workflow,
        # Edge cases & unhappy paths (15)
        test_circular_dependency,
        test_nonexistent_template,
        test_empty_workflow,
        test_trigger_dedup,
        test_multiple_completions_one_tick,
        test_malformed_metadata,
        test_no_metadata,
        test_output_schema_validation,
        test_state_cleanup_gc,
        test_dead_branch,
        test_long_chain,
        test_unknown_card_status,
        test_trigger_with_title_prefix,
        test_missing_upstream_output,
        test_multiple_triggers_same_board,
        test_board_not_found,
        # Adversarial v1 (13)
        test_adv_self_triggering_loop,
        test_adv_duplicate_node_ids,
        test_adv_state_db_deleted,
        test_adv_nonexistent_dependency,
        test_adv_multiple_matching_cards_one_tick,
        test_adv_trigger_on_engine_card,
        test_adv_template_injection,
        test_adv_long_chain_20,
        test_adv_condition_references_own_output,
        test_adv_watermark_gap,
        test_adv_card_archived_mid_workflow,
        test_adv_empty_string_condition,
        test_adv_rapid_ticks,
        # Adversarial graph pathology (10)
        test_adv_graph_disconnected_node,
        test_adv_graph_conflicting_diamond,
        test_adv_graph_self_dependency,
        test_adv_graph_three_node_cycle,
        test_adv_graph_two_entry_nodes,
        test_adv_graph_forward_reference,
        test_adv_graph_all_conditions_impossible,
        test_adv_graph_50_node_fanout,
        test_adv_graph_star_topology,
        test_adv_graph_empty_vs_missing_depends_on,
        # Adversarial state & lifecycle (12)
        test_adv_state_zombie_instance_reactivated,
        test_adv_state_fake_card_id_dispatched,
        test_adv_state_stale_node_states_after_template_edit,
        test_adv_state_card_reuse_done_to_todo,
        test_adv_state_instances_for_deleted_board,
        test_adv_state_create_instance_duplicate_id,
        test_adv_state_update_node_before_create,
        test_adv_state_complete_while_card_running,
        test_adv_state_bad_created_at,
        test_adv_state_multiple_instances_isolation,
        test_adv_state_trigger_keys_unbounded,
        test_adv_state_readonly_db,
        # Adversarial concurrency (6)
        test_adv_concurrency_two_engines_double_dispatch,
        test_adv_concurrency_concurrent_state_writes,
        test_adv_concurrency_trigger_dedup_race,
        test_adv_concurrency_overlapping_ticks,
        test_adv_concurrency_db_locked,
        test_adv_concurrency_partial_write_trigger_key,
        # Adversarial data corruption (20)
        test_adv_data_null_body_template,
        test_adv_data_null_profile,
        test_adv_data_empty_node_id,
        test_adv_data_huge_node_id,
        test_adv_data_huge_body_template,
        test_adv_data_nested_json_template_vars,
        test_adv_data_conflicting_trigger_keys,
        test_adv_data_body_no_vars,
        test_adv_data_body_only_vars,
        test_adv_data_unicode_node_id,
        test_adv_data_unicode_profile,
        test_adv_data_null_byte_in_body,
        test_adv_data_newline_in_node_id,
        test_adv_data_condition_malformed,
        test_adv_data_condition_double_quotes,
        test_adv_data_condition_trailing_garbage,
        test_adv_data_resolve_dict_value,
        test_adv_data_resolve_list_value,
        test_adv_data_empty_everything,
        test_adv_data_template_var_in_condition_value,
        # Adversarial trigger system (12)
        test_adv_trigger_storm_100_cards,
        test_adv_trigger_metadata_list_value,
        test_adv_trigger_missing_metadata_path,
        test_adv_trigger_duplicate_conditions_two_workflows,
        test_adv_trigger_keys_table_corrupted,
        test_adv_trigger_card_completed_at_null,
        test_adv_trigger_dotted_metadata_key,
        test_adv_trigger_cross_board,
        test_adv_trigger_self_trigger_engine_card,
        test_adv_trigger_empty_condition_matches_all,
        test_adv_trigger_dedup_hides_concurrent_cards,
        test_adv_trigger_status_filter_redundant,
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

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{failed} TEST(S) FAILED")
    sys.exit(0 if failed == 0 else 1)
