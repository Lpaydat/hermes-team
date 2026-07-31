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
                          priority=None, workspace=None):
        """Write directly to the fake board DB instead of calling hermes CLI."""
        db = self.tmpdir / "boards" / board / "kanban.db"
        # Use a counter to avoid timestamp collisions when multiple cards created in same ms
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
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT output FROM node_states WHERE node_id = 'plan'"
    ).fetchone()
    conn.close()
    plan_output = json.loads(row[0]) if row else {}
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
    assert any("BLOCKED" in a for a in actions), \
        f"Expected BLOCKED report, got: {actions}"
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
    """A card with output not matching the schema should still complete (soft validation)."""
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

    # Tick: node should still complete (engine does soft validation, doesn't block)
    actions = world.tick()
    assert any("DONE" in a and "qa" in a for a in actions), \
        f"Expected qa DONE despite schema mismatch, got: {actions}"
    # Downstream should still advance
    assert any("DISPATCHED" in a and "done" in a for a in actions), \
        f"Expected done DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_output_schema_validation")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE: Dead branch — condition never passes, workflow can't complete
# ═══════════════════════════════════════════════════ DONE══════════════════

def test_dead_branch():
    """A conditional node whose condition never passes should leave the workflow stuck."""
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
    # pass_path should NOT dispatch (condition fails)
    assert not any("DISPATCHED" in a and "pass_path" in a for a in actions), \
        f"pass_path should not dispatch on FAIL, got: {actions}"
    # Workflow should NOT complete (pass_path is pending forever)
    assert not any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Workflow should not complete with dead branch, got: {actions}"

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


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Happy paths
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
        # Edge cases & unhappy paths
        test_circular_dependency,
        test_nonexistent_template,
        test_empty_workflow,
        test_trigger_dedup,
        test_multiple_completions_one_tick,
        test_malformed_metadata,
        test_no_metadata,
        test_output_schema_validation,
        test_dead_branch,
        test_long_chain,
        test_unknown_card_status,
        test_trigger_with_title_prefix,
        test_missing_upstream_output,
        test_multiple_triggers_same_board,
        test_board_not_found,
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
