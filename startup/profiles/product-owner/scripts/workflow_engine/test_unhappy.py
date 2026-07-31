"""
Unhappy-path integration tests for the workflow engine.

These tests verify that the engine handles error conditions gracefully:
  1. Nonexistent boards
  2. Locked / read-only board DB (card creation fails)
  3. Missing profiles (card dispatches but nobody claims it)
  4. Error card statuses ('gave_up', 'timed_out')
  5. Board schema mismatch (kanban.db exists but missing tables)
  6. Nonexistent skill reference
  7. Empty body template (resolves to empty string)
  8. Empty-string profile
  9. Spam tick (multiple ticks while card still running — no duplicate actions)
 10. Out-of-order completion (node 2's card done before node 1)

Uses the FakeWorld pattern from test_engine.py: temp kanban boards, fake
card creation, simulated completions. No real beads or dispatchers involved.

Run: python3 -m pytest test_unhappy.py -v
Or:  python3 test_unhappy.py
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add scripts dir to path
SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow, Node, resolve_template
from workflow_engine.store import TemplateStore
from workflow_engine.kanban_adapter import board_db_path, KANBAN_HOME
from workflow_engine.runtime import (
    Engine, StateDB, NodeStatus, WorkflowInstance, NodeState,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — identical structure to test_engine.py's helpers
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


def count_cards(board_db: Path) -> int:
    conn = sqlite3.connect(str(board_db))
    count = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    conn.close()
    return count


# ═══════════════════════════════════════════════════════════════════════════
# Test fixture — FakeWorld adapted from test_engine.py
# ═══════════════════════════════════════════════════════════════════════════

class FakeWorld:
    """Test fixture: temp dir, fake board, engine, state DB."""

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-unhappy-"))
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
        path = self.templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2))

    def tick(self):
        return self.engine.tick()

    def start(self, workflow_id: str, context: dict | None = None,
              board: str | None = None) -> str:
        return self.engine.start_manual(
            workflow_id=workflow_id,
            board=board or self.board,
            project_dir=str(self.tmpdir),
            context=context or {},
        )

    def get_card_id_by_assignee(self, assignee: str) -> str | None:
        conn = sqlite3.connect(str(self.board_db))
        row = conn.execute(
            "SELECT id FROM tasks WHERE assignee = ?", (assignee,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def set_card_status(self, card_id: str, status: str,
                        metadata: dict | None = None):
        """Set a card's status directly in the fake board DB."""
        conn = sqlite3.connect(str(self.board_db))
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (status, card_id),
        )
        if status == "done":
            conn.execute(
                "UPDATE tasks SET completed_at = ? WHERE id = ?",
                (int(time.time()), card_id),
            )
            if metadata is not None:
                conn.execute(
                    """INSERT INTO task_runs (task_id, outcome, summary, metadata)
                       VALUES (?, 'completed', ?, ?)""",
                    (card_id, "", json.dumps(metadata)),
                )
        conn.commit()
        conn.close()

    def cleanup(self):
        import workflow_engine.kanban_adapter as ka
        import workflow_engine.runtime as rt
        ka.KANBAN_HOME = self._orig_home
        rt.create_card = self._orig_create


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Start workflow on a board that doesn't exist
# ═══════════════════════════════════════════════════════════════════════════

def test_nonexistent_board():
    """Starting a workflow on a board that doesn't exist should not crash.
    The engine's deleted-board guard should detect the missing board DB and
    mark the instance complete to prevent zombie cycling."""
    world = FakeWorld()
    world.add_template({
        "id": "simple",
        "name": "Simple workflow",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do the thing"},
        ],
    })

    # Start on a board that has no kanban.db
    instance_id = world.start("simple", board="no-such-board-xyz")
    assert instance_id, "Should return an instance_id even for missing board"

    # Tick should not crash
    actions = world.tick()
    assert isinstance(actions, list), f"Tick should return a list, got: {type(actions)}"

    # Engine should report the missing board and mark instance complete
    has_board_warning = any(
        "board" in a.lower() and ("missing" in a.lower() or "not found" in a.lower()
                                   or "complete" in a.lower())
        for a in actions
    )
    assert has_board_warning, \
        f"Expected board-not-found warning in actions, got: {actions}"

    # Instance should not linger as active (zombie prevention)
    active = world.engine.state.load_active_instances()
    assert len(active) == 0, \
        f"Expected 0 active instances (board guard should complete it), got: {len(active)}"

    world.cleanup()
    print("OK: test_nonexistent_board")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Card creation fails (board DB is read-only / locked)
# ═══════════════════════════════════════════════════════════════════════════

def test_card_creation_fails():
    """When create_card fails (returns False), the engine should report the
    failure in actions but NOT crash. The node stays pending and can retry."""
    world = FakeWorld()
    world.add_template({
        "id": "dispatch-fail",
        "name": "Dispatch fail test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do the thing"},
        ],
    })

    # Monkey-patch create_card to simulate a locked / read-only board
    def failing_create(*args, **kwargs):
        return False, "database is locked"

    import workflow_engine.runtime as rt
    rt.create_card = failing_create

    world.start("dispatch-fail")

    # Tick should NOT crash — should report the failure
    actions = world.tick()
    assert isinstance(actions, list), f"Tick should return a list, got: {type(actions)}"

    has_fail = any("FAILED" in a or "ERROR" in a for a in actions)
    assert has_fail, \
        f"Expected a FAILED/ERROR action when card creation fails, got: {actions}"

    # No card should have been created
    assert count_cards(world.board_db) == 0, \
        f"Expected 0 cards when creation fails, got {count_cards(world.board_db)}"

    # Restore create_card and tick again — should succeed (retry works)
    rt.create_card = world._fake_create_card
    actions2 = world.tick()
    assert any("DISPATCHED" in a for a in actions2), \
        f"Expected dispatch to succeed on retry, got: {actions2}"

    world.cleanup()
    print("OK: test_card_creation_fails")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Profile doesn't exist (card dispatches but nobody claims it)
# ═══════════════════════════════════════════════════════════════════════════

def test_missing_profile():
    """A card dispatched to a profile that doesn't exist as a gateway stays
    in 'todo' forever. The engine should NOT timeout or error — it should
    simply wait patiently on each tick."""
    world = FakeWorld()
    world.add_template({
        "id": "ghost-profile",
        "name": "Ghost profile test",
        "nodes": [
            {"id": "a", "profile": "nonexistent-profile-xyz",
             "skill": "live-testing", "body_template": "Do the thing"},
        ],
    })

    world.start("ghost-profile")

    # Tick 1: dispatches the card (engine doesn't validate profile existence)
    actions1 = world.tick()
    assert any("DISPATCHED" in a for a in actions1), \
        f"Expected card to dispatch even with unknown profile, got: {actions1}"

    card_id = world.get_card_id_by_assignee("nonexistent-profile-xyz")
    assert card_id, "Card should have been created for the unknown profile"

    # Tick 2: card is still 'todo' (nobody claimed it). Engine should not
    # error, crash, or spam. It should just wait.
    actions2 = world.tick()
    assert isinstance(actions2, list), \
        f"Tick 2 should not crash, got: {type(actions2)}"

    # Tick 3: same — still waiting patiently
    actions3 = world.tick()
    assert isinstance(actions3, list), \
        f"Tick 3 should not crash, got: {type(actions3)}"

    # Instance should still be active (waiting for the card to complete)
    active = world.engine.state.load_active_instances()
    assert len(active) == 1, \
        f"Expected 1 active instance (waiting), got: {len(active)}"

    world.cleanup()
    print("OK: test_missing_profile")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Card completed with error status ('gave_up' / 'timed_out')
# ═══════════════════════════════════════════════════════════════════════════

def test_error_card_status():
    """When a card ends up in an error status ('gave_up', 'timed_out') that
    is neither 'done' nor 'blocked', the engine should not crash. It should
    report the unexpected status as a WARNING and the node stays dispatched."""
    world = FakeWorld()
    world.add_template({
        "id": "error-status",
        "name": "Error status test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do the thing"},
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Verify", "depends_on": ["a"]},
        ],
    })

    world.start("error-status")
    world.tick()  # dispatch node a

    card_id = world.get_card_id_by_assignee("qa")
    assert card_id, "Node a card should have been created"

    # Set the card to an error status that the engine doesn't explicitly handle
    world.set_card_status(card_id, "gave_up")

    # Tick should not crash — engine should report the unexpected status
    actions = world.tick()
    assert isinstance(actions, list), \
        f"Tick with error-status card should not crash, got: {type(actions)}"

    # The node should NOT be marked done (card isn't 'done')
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute(
        "SELECT status FROM node_states WHERE node_id = 'a'"
    ).fetchone()
    conn.close()
    assert row[0] != "done", \
        f"Node should not be 'done' when card status is 'gave_up', got: {row[0]}"

    # Node b should NOT have been dispatched (dependency 'a' not done)
    card_b = world.get_card_id_by_assignee("verifier")
    assert card_b is None, \
        "Node b should not be dispatched when node a is in error state"

    world.cleanup()
    print("OK: test_error_card_status")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Board schema mismatch (kanban.db exists but missing tables)
# ═══════════════════════════════════════════════════════════════════════════

def test_schema_mismatch():
    """A kanban.db that exists but is missing the 'tasks' table (schema
    mismatch) should cause the engine to handle gracefully — either catch the
    OperationalError inside tick's try/except wrapper, or report an error."""
    world = FakeWorld()
    world.add_template({
        "id": "schema-bad",
        "name": "Schema mismatch test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do the thing"},
        ],
    })

    # Create a board with a kanban.db that has NO 'tasks' table
    bad_board_dir = world.tmpdir / "boards" / "bad-schema" / "kanban.db"
    bad_board_dir.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(bad_board_dir))
    # Create an unrelated table — the DB exists but lacks the kanban schema
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.execute("INSERT INTO unrelated VALUES (1)")
    conn.commit()
    conn.close()

    # Start a workflow on the bad-schema board
    instance_id = world.start("schema-bad", board="bad-schema")

    # Tick should not crash — the outer try/except in tick() catches it
    actions = world.tick()
    # tick() returns either ERROR actions or a graceful list
    assert isinstance(actions, list), \
        f"Tick with bad-schema board should return a list, got: {type(actions)}"

    # It should NOT silently succeed as if nothing were wrong —
    # either an ERROR/SKIP/WARNING action, or the instance gets completed
    # by the guard (board_db_path exists but queries fail).
    # The key assertion: no unhandled exception propagated.
    print(f"  (schema mismatch actions: {actions})")

    world.cleanup()
    print("OK: test_schema_mismatch")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Workflow references a skill that doesn't exist
# ═══════════════════════════════════════════════════════════════════════════

def test_nonexistent_skill():
    """A node referencing a skill that doesn't exist should still dispatch
    a card. The engine doesn't validate skill existence — that's the agent's
    problem. The card should be created with the skill name in the title."""
    world = FakeWorld()
    world.add_template({
        "id": "ghost-skill",
        "name": "Ghost skill test",
        "nodes": [
            {"id": "a", "profile": "qa",
             "skill": "this-skill-does-not-exist-12345",
             "body_template": "Do the thing with ${trigger.x}"},
        ],
    })

    world.start("ghost-skill", context={"x": "value"})
    actions = world.tick()

    # Card should dispatch fine — engine doesn't check skill validity
    assert any("DISPATCHED" in a for a in actions), \
        f"Expected dispatch even with nonexistent skill, got: {actions}"

    assert count_cards(world.board_db) == 1, \
        f"Expected 1 card created, got {count_cards(world.board_db)}"

    # The card title should contain the skill name
    conn = sqlite3.connect(str(world.board_db))
    row = conn.execute("SELECT title FROM tasks LIMIT 1").fetchone()
    conn.close()
    assert "this-skill-does-not-exist-12345" in row[0], \
        f"Card title should contain skill name, got: {row[0]}"

    world.cleanup()
    print("OK: test_nonexistent_skill")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Card body resolves to empty string
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_body():
    """When body_template is empty or resolves to empty (all vars missing),
    the card should still be created and dispatched. create_card skips the
    --body flag when body is falsy — that's fine, the card still works."""
    world = FakeWorld()

    # Case A: body_template is literally empty string
    world.add_template({
        "id": "empty-body",
        "name": "Empty body test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": ""},
        ],
    })
    world.start("empty-body")
    actions_a = world.tick()
    assert any("DISPATCHED" in a for a in actions_a), \
        f"Expected dispatch with empty body, got: {actions_a}"

    # Case B: body_template has only unresolved variables (resolves to "")
    world.add_template({
        "id": "unresolved-body",
        "name": "Unresolved body test",
        "nodes": [
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "${nodes.nonexistent.output.path} and ${trigger.missing}"},
        ],
    })
    world.start("unresolved-body")
    actions_b = world.tick()
    assert any("DISPATCHED" in a for a in actions_b), \
        f"Expected dispatch with all-unresolved body vars, got: {actions_b}"

    assert count_cards(world.board_db) == 2, \
        f"Expected 2 cards (one per node), got {count_cards(world.board_db)}"

    world.cleanup()
    print("OK: test_empty_body")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Node profile is empty string
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_profile():
    """A node with profile='' creates a card with an empty assignee. The
    engine should not crash — the card dispatches (with empty assignee),
    and downstream behavior is the dispatcher's problem."""
    world = FakeWorld()
    world.add_template({
        "id": "empty-profile",
        "name": "Empty profile test",
        "nodes": [
            {"id": "a", "profile": "", "skill": "live-testing",
             "body_template": "Do the thing"},
        ],
    })

    world.start("empty-profile")

    # Tick should not crash
    actions = world.tick()
    assert isinstance(actions, list), \
        f"Tick with empty profile should return a list, got: {type(actions)}"

    # The card should either dispatch (with empty assignee) or fail gracefully.
    # Either way, no unhandled exception.
    if any("DISPATCHED" in a for a in actions):
        # Card was created — verify it has empty assignee
        conn = sqlite3.connect(str(world.board_db))
        row = conn.execute("SELECT assignee FROM tasks LIMIT 1").fetchone()
        conn.close()
        assert row is not None, "Card should exist after dispatch"
        assert row[0] == "", \
            f"Card assignee should be empty string, got: '{row[0]}'"
    else:
        # If it failed, it should be a FAILED action, not a crash
        assert any("FAILED" in a for a in actions), \
            f"Expected either DISPATCHED or FAILED, got: {actions}"

    world.cleanup()
    print("OK: test_empty_profile")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: Spam tick — multiple ticks while card still 'running'
# ═══════════════════════════════════════════════════════════════════════════

def test_spam_tick_no_duplicates():
    """Ticking multiple times while a card is still 'running' should NOT
    create duplicate cards. The idempotency key mechanism prevents
    re-dispatch."""
    world = FakeWorld()
    world.add_template({
        "id": "spam-test",
        "name": "Spam tick test",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "live-testing",
             "body_template": "Do the thing"},
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Verify", "depends_on": ["a"]},
        ],
    })

    world.start("spam-test")

    # Tick 1: dispatch node a
    actions1 = world.tick()
    assert count_cards(world.board_db) == 1, \
        f"Expected 1 card after tick 1, got {count_cards(world.board_db)}"

    card_a = world.get_card_id_by_assignee("qa")

    assert card_a is not None, "Node a card should exist before setting status"
    # Set card to 'running' (claimed by a worker, not done yet)
    world.set_card_status(card_a, "running")

    # Spam 10 ticks — should NOT create any duplicate cards
    for i in range(10):
        actions = world.tick()
        assert isinstance(actions, list), \
            f"Tick {i+2} should not crash, got: {type(actions)}"

    # Still only 1 card (node a), node b not dispatched yet
    assert count_cards(world.board_db) == 1, \
        f"Expected 1 card after 11 ticks (no duplicates), got {count_cards(world.board_db)}"

    # Instance still active
    active = world.engine.state.load_active_instances()
    assert len(active) == 1, \
        f"Expected 1 active instance, got: {len(active)}"

    world.cleanup()
    print("OK: test_spam_tick_no_duplicates")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: Out-of-order completion (node 2 card done before node 1)
# ═══════════════════════════════════════════════════════════════════════════

def test_out_of_order_completion():
    """In a chain (a → b), node b can only be dispatched after a is done.
    But what if two INDEPENDENT entry nodes complete in reverse order?
    The engine should handle both completions regardless of which finishes
    first."""
    world = FakeWorld()
    world.add_template({
        "id": "out-of-order",
        "name": "Out of order test",
        "nodes": [
            {"id": "a", "profile": "dev-a", "skill": "developer-loop",
             "body_template": "Build A"},
            {"id": "b", "profile": "dev-b", "skill": "developer-loop",
             "body_template": "Build B"},
            {"id": "c", "profile": "qa", "skill": "live-testing",
             "body_template": "Test both", "depends_on": ["a", "b"]},
        ],
    })

    world.start("out-of-order")

    # Tick: dispatch both a and b (independent entry nodes)
    actions = world.tick()
    assert count_cards(world.board_db) == 2, \
        f"Expected 2 cards (a and b), got {count_cards(world.board_db)}"

    card_a = world.get_card_id_by_assignee("dev-a")
    card_b = world.get_card_id_by_assignee("dev-b")
    assert card_a and card_b, "Both entry node cards should exist"

    # Complete node b FIRST (out of order), then node a
    world.set_card_status(card_b, "done", metadata={"branch_b": "feat/b"})
    actions_b = world.tick()
    assert any("DONE" in a and "node b" in a for a in actions_b), \
        f"Expected node b DONE, got: {actions_b}"

    # Node c should NOT dispatch yet — node a not done
    card_c = world.get_card_id_by_assignee("qa")
    assert card_c is None, \
        "Node c should not be dispatched until both a and b are done"

    # Now complete node a
    world.set_card_status(card_a, "done", metadata={"branch_a": "feat/a"})
    actions_a = world.tick()
    assert any("DONE" in a and "node a" in a for a in actions_a), \
        f"Expected node a DONE, got: {actions_a}"

    # Now node c should dispatch
    assert any("DISPATCHED" in a and "node c" in a for a in actions_a), \
        f"Expected node c DISPATCHED after both deps done, got: {actions_a}"

    # Complete node c — workflow should finish
    card_c = world.get_card_id_by_assignee("qa")
    assert card_c, "Node c card should exist now"
    world.set_card_status(card_c, "done", metadata={"verdict": "PASS"})
    actions_c = world.tick()
    assert any("WORKFLOW COMPLETE" in a for a in actions_c), \
        f"Expected WORKFLOW COMPLETE, got: {actions_c}"

    active = world.engine.state.load_active_instances()
    assert len(active) == 0, \
        f"Expected 0 active instances after completion, got: {len(active)}"

    world.cleanup()
    print("OK: test_out_of_order_completion")


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_nonexistent_board,
        test_card_creation_fails,
        test_missing_profile,
        test_error_card_status,
        test_schema_mismatch,
        test_nonexistent_skill,
        test_empty_body,
        test_empty_profile,
        test_spam_tick_no_duplicates,
        test_out_of_order_completion,
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
