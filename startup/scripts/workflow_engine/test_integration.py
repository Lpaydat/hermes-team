#!/usr/bin/env python3
"""
Real integration tests for the workflow engine — against REAL kanban boards.

Unlike test_engine.py (which uses FakeWorld with monkey-patched CLI calls),
these tests create REAL kanban boards via the hermes CLI, dispatch REAL cards
through the engine's create_card → hermes kanban create path, and verify
behavior against the real SQLite schema.

For speed, most tests SIMULATE card completions via direct SQLite writes
(mimicking what kanban_complete does) rather than waiting 30-60s for real
agents. Only 1-2 tests use real agent dispatch.

Each test:
  1. Creates a temporary board: hermes kanban boards create wf-int-test-<unique>
  2. Starts a workflow instance on that board
  3. Runs engine ticks (real card creation via hermes CLI)
  4. Verifies cards appear on the board
  5. Simulates completions (direct SQLite) or waits for real agent
  6. Cleans up the board (hermes kanban boards rm --delete)

Run: cd ~/.hermes-teams/startup/profiles/product-owner/scripts && python3 workflow_engine/test_integration.py

NOTE: These tests require:
  - The `hermes` CLI on PATH
  - Write access to ~/.hermes-teams/startup/kanban/boards/
  - The workflow_engine package importable (sys.path hack below)
"""
from __future__ import annotations
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Add scripts dir to path so workflow_engine resolves as package
SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow, Node
from workflow_engine.store import TemplateStore
from workflow_engine.kanban_adapter import (
    create_card,
    get_card,
    get_card_metadata,
    find_cards_by_idempotency_key,
    find_recent_completions,
    board_db_path,
    run_kanban,
    KANBAN_HOME,
)
from workflow_engine.runtime import (
    Engine,
    StateDB,
    NodeStatus,
    WorkflowInstance,
    NodeState,
    STATE_DB,
)


# ═══════════════════════════════════════════════════════════════════════════
# Test result tracking
# ═══════════════════════════════════════════════════════════════════════════
_PASSED = 0
_FAILED = 0
_ERRORS: list[str] = []


def _unique_board_name(prefix: str = "wf-int-test") -> str:
    """Generate a unique board slug with timestamp + uuid suffix."""
    ts = int(time.time())
    short = uuid.uuid4().hex[:6]
    return f"{prefix}-{ts}-{short}"


def _hermes_kanban(args: list[str], timeout: int = 30) -> tuple[int, str]:
    """Run a hermes kanban command, return (returncode, combined_output)."""
    cmd = ["hermes", "kanban"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        combined = result.stdout
        if result.stderr:
            combined += "\n" + result.stderr
        return result.returncode, combined
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except FileNotFoundError:
        return -2, "hermes CLI not found"


def _create_board(slug: str) -> bool:
    """Create a real kanban board. Returns True on success."""
    rc, _ = _hermes_kanban(["boards", "create", slug, "--name", "Integration Test"])
    return rc == 0


def _delete_board(slug: str) -> bool:
    """Hard-delete a board (removes the directory). Returns True on success."""
    rc, _ = _hermes_kanban(["boards", "rm", slug, "--delete"])
    return rc == 0


def _get_real_db_path(board: str) -> Path:
    """Get the real kanban.db path for a board (no monkey-patching)."""
    return KANBAN_HOME / board / "kanban.db"


def _simulate_completion(
    board: str,
    card_id: str,
    metadata: dict | None = None,
    summary: str = "",
    outcome: str = "completed",
):
    """Mark a card as done with a completed run, mimicking kanban_complete.

    Writes directly to the real board's SQLite DB. This simulates what happens
    when a real agent completes a card:
      1. UPDATE tasks SET status='done', completed_at=<now>
      2. INSERT INTO task_runs (...) VALUES ('completed', metadata, summary)

    This is MUCH faster than waiting for a real agent (seconds vs 30-60s).
    """
    db = _get_real_db_path(board)
    conn = sqlite3.connect(str(db))
    now = int(time.time())
    try:
        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = ?, started_at = COALESCE(started_at, ?) WHERE id = ?",
            (now, now, card_id),
        )
        conn.execute(
            """INSERT INTO task_runs (task_id, profile, status, outcome, summary, metadata, started_at, ended_at)
               VALUES (?, NULL, 'done', ?, ?, ?, ?, ?)""",
            (card_id, outcome, summary, json.dumps(metadata) if metadata else None, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _count_cards(board: str) -> int:
    """Count cards on a real board."""
    db = _get_real_db_path(board)
    if not db.exists():
        return 0
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def _get_card_status(board: str, card_id: str) -> str | None:
    """Read a card's status from the real board."""
    db = _get_real_db_path(board)
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (card_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _list_card_ids(board: str) -> list[str]:
    """Get all card IDs from a real board."""
    db = _get_real_db_path(board)
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT id FROM tasks").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _run_real_engine_tick(templates_dir: Path) -> list[str]:
    """Run the real engine tick (uses real STATE_DB, real hermes CLI).

    Creates an Engine instance with the given templates_dir and real state DB.
    """
    engine = Engine(templates_dir)
    return engine.tick()


# ═══════════════════════════════════════════════════════════════════════════
# Test fixture: real board + temp templates + temp state DB
# ═══════════════════════════════════════════════════════════════════════════

class RealBoardFixture:
    """Sets up a real kanban board + temp templates dir + temp state DB.

    The engine uses the REAL hermes CLI (no monkey-patching), so cards are
    created through the same path as production. State DB is isolated per test
    to avoid cross-test contamination.
    """

    def __init__(self, template_data: dict | None = None):
        self.board = _unique_board_name()
        self.boards_created: list[str] = [self.board]
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-int-"))
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)

        # Create the real board
        assert _create_board(self.board), f"Failed to create board {self.board}"

        # Isolate state DB per test to avoid cross-contamination
        self.state_db_path = self.tmpdir / "state.db"

        # Create engine with isolated state
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)

        # Add template if provided
        if template_data:
            self.add_template(template_data)

    def add_template(self, template: dict):
        """Write a workflow template to temp templates dir."""
        path = self.templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2))

    def tick(self) -> list[str]:
        """Run one engine tick against the real board."""
        return self.engine.tick()

    def start(self, workflow_id: str, context: dict | None = None) -> str:
        """Start a workflow instance on the real board."""
        return self.engine.start_manual(
            workflow_id=workflow_id,
            board=self.board,
            project_dir="",
            context=context or {},
        )

    def complete_card(self, card_id: str, metadata: dict | None = None,
                      summary: str = ""):
        """Simulate a card completion via direct SQLite write."""
        _simulate_completion(self.board, card_id, metadata, summary)

    def cleanup(self):
        """Delete all boards created during this test."""
        for board in self.boards_created:
            _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# Test runner — simple assert + pass/fail tracking
# ═══════════════════════════════════════════════════════════════════════════

def _simple_template(workflow_id: str, nodes: list[dict]) -> dict:
    """Build a minimal workflow template dict."""
    return {
        "id": workflow_id,
        "name": workflow_id,
        "nodes": nodes,
    }


def run_test(name: str, test_fn):
    """Run a test function that manages its own cleanup (via try/finally)."""
    global _PASSED, _FAILED
    print(f"\n{'='*70}")
    print(f"RUN: {name}")
    print(f"{'='*70}")
    try:
        test_fn()
        _PASSED += 1
        print(f"PASS: {name}")
    except AssertionError as e:
        _FAILED += 1
        _ERRORS.append(f"{name}: {e}")
        print(f"FAIL: {name}: {e}")
    except Exception as e:
        _FAILED += 1
        _ERRORS.append(f"{name}: {e}")
        import traceback
        print(f"ERROR: {name}: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Real card creation
# ═══════════════════════════════════════════════════════════════════════════

def test_real_card_creation():
    """Verify create_card works against a real kanban board schema."""
    board = _unique_board_name("wf-int-card")
    try:
        assert _create_board(board), "Board creation failed"

        ok, output = create_card(
            board=board,
            title="[test-node] live-testing",
            assignee="product-owner",
            body="Test body for card creation",
            idempotency_key="wf-test-1:test-node",
            priority=10,
        )
        assert ok, f"create_card failed: {output}"

        data = json.loads(output)
        card_id = data.get("id", "")
        assert card_id, f"No card id in output: {output}"

        # Verify via the adapter's get_card
        card = get_card(board, card_id)
        assert card is not None, f"Card {card_id} not found in DB"
        assert card.title == "[test-node] live-testing", f"Wrong title: {card.title}"
        assert card.assignee == "product-owner", f"Wrong assignee: {card.assignee}"
        assert card.idempotency_key == "wf-test-1:test-node", \
            f"Wrong idempotency_key: {card.idempotency_key}"
        assert card.status in ("todo", "ready"), f"Unexpected status: {card.status}"

        # Verify via raw SQL (catches adapter bugs)
        db = _get_real_db_path(board)
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT title, body, assignee, priority, idempotency_key FROM tasks WHERE id = ?",
            (card_id,),
        ).fetchone()
        conn.close()
        assert row is not None, "Card not in DB"
        assert row[0] == "[test-node] live-testing"
        assert row[1] == "Test body for card creation"
        assert row[2] == "product-owner"
        assert row[3] == 10
        assert row[4] == "wf-test-1:test-node"

        print(f"  Card created and verified: {card_id}, status={card.status}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Real idempotency key — find_cards_by_idempotency_key
# ═══════════════════════════════════════════════════════════════════════════

def test_real_idempotency_lookup():
    """Verify find_cards_by_idempotency_key works against real board schema."""
    board = _unique_board_name("wf-int-idem")
    try:
        assert _create_board(board), "Board creation failed"

        idem_key = f"wf-idem-test:{uuid.uuid4().hex[:8]}"

        # Create two cards with same idempotency key — hermes should dedup
        ok1, out1 = create_card(
            board=board, title="Card A", assignee="product-owner",
            idempotency_key=idem_key,
        )
        assert ok1, f"First create failed: {out1}"
        id1 = json.loads(out1)["id"]

        ok2, out2 = create_card(
            board=board, title="Card A (dup)", assignee="product-owner",
            idempotency_key=idem_key,
        )
        assert ok2, f"Second create failed: {out2}"
        id2 = json.loads(out2)["id"]

        # Idempotency should return the same card
        assert id1 == id2, f"Idempotency failed: {id1} != {id2}"

        # Now verify the adapter finds it
        cards = find_cards_by_idempotency_key(board, idem_key)
        assert len(cards) == 1, f"Expected 1 card, got {len(cards)}"
        assert cards[0].id == id1
        assert cards[0].idempotency_key == idem_key

        print(f"  Idempotency verified: card {id1} returned for key {idem_key}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Real metadata reading — get_card_metadata
# ═══════════════════════════════════════════════════════════════════════════

def test_real_metadata_reading():
    """Verify get_card_metadata reads from the real task_runs table."""
    board = _unique_board_name("wf-int-meta")
    try:
        assert _create_board(board), "Board creation failed"

        # Create a card
        ok, out = create_card(board=board, title="Meta test", assignee="product-owner")
        assert ok
        card_id = json.loads(out)["id"]

        # Before completion: metadata should be empty
        meta = get_card_metadata(board, card_id)
        assert meta == {} or meta.get("metadata", {}) == {}, \
            f"Expected empty metadata before completion, got: {meta}"

        # Simulate completion with metadata
        test_meta = {"spec_path": "/tmp/test.md", "verdict": "PASS", "count": 42}
        _simulate_completion(board, card_id, metadata=test_meta,
                             summary="Test completion summary")

        # Now metadata should be readable
        meta = get_card_metadata(board, card_id)
        assert "metadata" in meta, f"Missing 'metadata' key in: {meta}"
        assert meta["metadata"] == test_meta, \
            f"Metadata mismatch: expected {test_meta}, got {meta['metadata']}"
        assert meta["summary"] == "Test completion summary", \
            f"Summary mismatch: {meta.get('summary')}"

        print(f"  Metadata read: {meta['metadata']}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Real trigger detection — find_recent_completions
# ═══════════════════════════════════════════════════════════════════════════

def test_real_trigger_detection():
    """Verify find_recent_completions works against the real board schema.

    Creates a card, simulates completion, then checks that
    find_recent_completions picks it up.
    """
    board = _unique_board_name("wf-int-trig")
    try:
        assert _create_board(board), "Board creation failed"

        # Create a trigger card
        ok, out = create_card(
            board=board, title="[qa] regression check", assignee="qa",
        )
        assert ok
        trigger_card_id = json.loads(out)["id"]

        # Before completion: no recent completions
        since = int(time.time()) - 3600
        completions = find_recent_completions(board, since)
        assert len(completions) == 0, \
            f"Expected 0 completions, got {len(completions)}"

        # Simulate completion with trigger-matching metadata
        _simulate_completion(
            board, trigger_card_id,
            metadata={"verdict": "PASS", "feature": "auth"},
            summary="Regression test passed",
        )

        # Now find_recent_completions should find it
        completions = find_recent_completions(board, since)
        assert len(completions) >= 1, \
            f"Expected >=1 completion, got {len(completions)}"

        # Verify the trigger card is among them
        found = [c for c in completions if c.id == trigger_card_id]
        assert len(found) == 1, f"Trigger card not found in completions: {completions}"
        card = found[0]
        assert card.status == "done"
        assert card.assignee == "qa"
        assert card.metadata.get("verdict") == "PASS"
        assert card.summary == "Regression test passed"

        print(f"  Trigger card detected: {trigger_card_id}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Real project dir mapping — _board_to_project_dir
# ═══════════════════════════════════════════════════════════════════════════

def test_real_project_dir_mapping():
    """Verify _board_to_project_dir works with real active-projects.json."""
    # Create a real engine instance (uses real templates dir, but we only
    # need the _board_to_project_dir method)
    templates_dir = Path.home() / ".hermes-teams/startup/scripts/workflow_engine/templates"
    engine = Engine(templates_dir)

    # Test with a board that IS in active-projects.json (crr-pos → crr-pos-v2)
    project_dir = engine._board_to_project_dir("crr-pos")
    assert project_dir == "/home/lpaydat/projects/crr-pos-v2", \
        f"Expected /home/lpaydat/projects/crr-pos-v2, got: {project_dir}"

    # Test with a board NOT in active-projects.json → fallback to ~/projects/<board>
    # (won't exist, but should return the path or empty string)
    project_dir_unknown = engine._board_to_project_dir("nonexistent-board-xyz")
    assert project_dir_unknown == "", \
        f"Expected empty for unknown board, got: {project_dir_unknown}"

    print(f"  crr-pos → {project_dir}")
    print(f"  unknown board → '{project_dir_unknown}'")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Board cleanup — create and delete
# ═══════════════════════════════════════════════════════════════════════════

def test_board_cleanup():
    """Verify we can create a board, add cards, and delete it cleanly."""
    board = _unique_board_name("wf-int-cleanup")
    db_path = _get_real_db_path(board)

    # Initially doesn't exist
    assert not db_path.exists(), "Board DB should not exist before creation"

    try:
        # Create it
        assert _create_board(board), "Board creation failed"
        assert db_path.exists(), "Board DB should exist after creation"

        # Add a card
        ok, out = create_card(board=board, title="Cleanup test", assignee="product-owner")
        assert ok
        assert _count_cards(board) == 1

        # Delete it
        assert _delete_board(board), "Board deletion failed"
        assert not db_path.exists(), "Board DB should not exist after deletion"
        assert not db_path.parent.exists(), "Board dir should not exist after deletion"
    finally:
        # Ensure cleanup even if test fails partway
        if db_path.exists():
            _delete_board(board)

    print("  Board created, populated, and deleted successfully")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Multiple boards — engine handles multiple boards simultaneously
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_boards():
    """Verify the engine can run workflows on multiple boards at once."""
    board1 = _unique_board_name("wf-int-multi1")
    board2 = _unique_board_name("wf-int-multi2")
    tmpdir = Path(tempfile.mkdtemp(prefix="wf-multi-"))
    templates_dir = tmpdir / "templates"
    templates_dir.mkdir(parents=True)

    try:
        assert _create_board(board1), "Board1 creation failed"
        assert _create_board(board2), "Board2 creation failed"

        # Same simple template for both
        tmpl = _simple_template("simple-wf", [
            {"id": "step1", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Do step1"},
        ])
        (templates_dir / "simple-wf.json").write_text(json.dumps(tmpl))

        # Create engine with isolated state
        state_db = tmpdir / "state.db"
        engine = Engine(templates_dir)
        engine.state = StateDB(state_db)

        # Start workflow on both boards
        inst1 = engine.start_manual("simple-wf", board1, "", {})
        inst2 = engine.start_manual("simple-wf", board2, "", {})
        assert inst1 != inst2, "Instance IDs should differ"

        # Tick should dispatch on both boards
        actions = engine.tick()
        assert len(actions) >= 2, f"Expected >=2 actions, got {len(actions)}: {actions}"

        dispatched_boards = [a for a in actions if "DISPATCHED" in a]
        assert len(dispatched_boards) >= 2, \
            f"Expected >=2 DISPATCHED actions, got: {actions}"

        # Verify cards exist on both boards
        assert _count_cards(board1) == 1, f"Board1 should have 1 card, has {_count_cards(board1)}"
        assert _count_cards(board2) == 1, f"Board2 should have 1 card, has {_count_cards(board2)}"

        print(f"  Board1: {_count_cards(board1)} card, Board2: {_count_cards(board2)} card")
        print(f"  Actions: {actions}")
    finally:
        _delete_board(board1)
        _delete_board(board2)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Real card status transitions — todo → ready → running → done
# ═══════════════════════════════════════════════════════════════════════════

def test_card_status_transitions():
    """Verify card status transitions work on real boards.

    Creates a card (→ ready), simulates running, then completion (→ done).
    The engine should correctly detect the 'done' state.
    """
    board = _unique_board_name("wf-int-status")
    try:
        assert _create_board(board), "Board creation failed"

        ok, out = create_card(board=board, title="Status test", assignee="product-owner")
        assert ok
        card_id = json.loads(out)["id"]

        # Card starts as 'ready' (the hermes default for created cards)
        status = _get_card_status(board, card_id)
        assert status == "ready", f"Expected 'ready', got '{status}'"

        # Engine's get_card should see it
        card = get_card(board, card_id)
        assert card.status == "ready"

        # Simulate transition to running
        db = _get_real_db_path(board)
        conn = sqlite3.connect(str(db))
        conn.execute("UPDATE tasks SET status = 'running', started_at = ? WHERE id = ?",
                     (int(time.time()), card_id))
        conn.commit()
        conn.close()

        card = get_card(board, card_id)
        assert card.status == "running", f"Expected 'running', got '{card.status}'"

        # Simulate completion
        _simulate_completion(board, card_id, metadata={"result": "success"})

        card = get_card(board, card_id)
        assert card.status == "done", f"Expected 'done', got '{card.status}'"
        assert card.completed_at is not None, "completed_at should be set"

        print(f"  Transitions: ready → running → done verified for {card_id}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: Real card with empty metadata
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_metadata():
    """Verify engine handles cards completed with empty/no metadata."""
    board = _unique_board_name("wf-int-empty")
    try:
        assert _create_board(board), "Board creation failed"

        ok, out = create_card(board=board, title="Empty meta test", assignee="product-owner")
        assert ok
        card_id = json.loads(out)["id"]

        # Complete with no metadata (None)
        _simulate_completion(board, card_id, metadata=None, summary="Done with no meta")

        meta = get_card_metadata(board, card_id)
        # Should return empty metadata, not crash
        assert "metadata" in meta, f"Missing metadata key: {meta}"
        assert meta["metadata"] == {}, f"Expected empty dict, got: {meta['metadata']}"

        print(f"  Empty metadata handled: {meta}")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: Real card with large metadata (1000+ chars JSON)
# ═══════════════════════════════════════════════════════════════════════════

def test_large_metadata():
    """Verify engine handles cards with large metadata (1000+ chars)."""
    board = _unique_board_name("wf-int-large")
    try:
        assert _create_board(board), "Board creation failed"

        ok, out = create_card(board=board, title="Large meta test", assignee="product-owner")
        assert ok
        card_id = json.loads(out)["id"]

        # Create large metadata
        large_meta = {
            "findings": [{"id": i, "desc": f"Finding number {i} " * 20} for i in range(50)],
            "report": "X" * 2000,
            "verdict": "FAIL",
        }
        large_json = json.dumps(large_meta)
        assert len(large_json) > 1000, f"Metadata too small: {len(large_json)} chars"

        _simulate_completion(board, card_id, metadata=large_meta,
                             summary="Large metadata test")

        meta = get_card_metadata(board, card_id)
        assert meta["metadata"] == large_meta, "Large metadata mismatch"
        assert meta["metadata"]["report"] == "X" * 2000

        print(f"  Large metadata ({len(large_json)} chars) read successfully")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 11: Full engine lifecycle on real board (simulated completions)
# ═══════════════════════════════════════════════════════════════════════════

def test_engine_full_lifecycle_simulated():
    """Full workflow lifecycle on a real board with simulated completions.

    3-node pipeline: plan → build → test
    All completions are simulated via direct SQLite writes.
    """
    fixture = RealBoardFixture(_simple_template("lifecycle", [
        {"id": "plan", "profile": "product-owner", "skill": "dev-planning",
         "body_template": "Plan ${trigger.task}"},
        {"id": "build", "profile": "developer", "skill": "developer-loop",
         "body_template": "Build from ${nodes.plan.output.spec_path}",
         "depends_on": ["plan"]},
        {"id": "test", "profile": "qa", "skill": "live-testing",
         "body_template": "Test build from ${nodes.build.output.branch}",
         "depends_on": ["build"]},
    ]))
    try:
        # Start the workflow
        instance_id = fixture.start("lifecycle", context={"task": "real-integration-test"})
        print(f"  Started: {instance_id}")

        # Tick 1: dispatch 'plan'
        actions = fixture.tick()
        assert any("DISPATCHED" in a and "plan" in a for a in actions), \
            f"Expected plan DISPATCHED, got: {actions}"

        # Verify real card was created on the board
        assert _count_cards(fixture.board) == 1, \
            f"Expected 1 card on board, got {_count_cards(fixture.board)}"

        # Find the plan card and simulate completion
        plan_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:plan"
        )
        assert len(plan_cards) == 1, f"Expected 1 plan card, got {len(plan_cards)}"
        plan_card_id = plan_cards[0].id
        fixture.complete_card(plan_card_id, metadata={"spec_path": "/tmp/real-spec.md"})
        print(f"  Simulated plan completion: {plan_card_id}")

        # Tick 2: plan done → dispatch build
        actions = fixture.tick()
        assert any("DONE" in a and "plan" in a for a in actions), \
            f"Expected plan DONE, got: {actions}"
        assert any("DISPATCHED" in a and "build" in a for a in actions), \
            f"Expected build DISPATCHED, got: {actions}"

        build_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:build"
        )
        assert len(build_cards) == 1
        build_card_id = build_cards[0].id
        fixture.complete_card(build_card_id, metadata={"branch": "feat/real-test"})
        print(f"  Simulated build completion: {build_card_id}")

        # Tick 3: build done → dispatch test
        actions = fixture.tick()
        assert any("DONE" in a and "build" in a for a in actions), \
            f"Expected build DONE, got: {actions}"
        assert any("DISPATCHED" in a and "test" in a for a in actions), \
            f"Expected test DISPATCHED, got: {actions}"

        test_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:test"
        )
        assert len(test_cards) == 1
        test_card_id = test_cards[0].id
        fixture.complete_card(test_card_id, metadata={"verdict": "PASS"})
        print(f"  Simulated test completion: {test_card_id}")

        # Tick 4: test done → workflow complete
        actions = fixture.tick()
        assert any("DONE" in a and "test" in a for a in actions), \
            f"Expected test DONE, got: {actions}"
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Expected WORKFLOW COMPLETE, got: {actions}"

        # Verify no active instances remain
        active = fixture.engine.state.load_active_instances()
        assert len(active) == 0, f"Expected 0 active instances, got {len(active)}"

        print(f"  Full lifecycle completed on real board!")
    finally:
        fixture.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 12: Real trigger fires workflow on real board (simulated completion)
# ═══════════════════════════════════════════════════════════════════════════

def test_real_trigger_fires_workflow():
    """Verify a card_completed trigger starts a workflow on a real board.

    Creates a card on the board, simulates its completion with matching
    metadata, then ticks the engine and verifies a new workflow instance starts.
    """
    tmpl = {
        "id": "triggered-wf",
        "name": "Triggered workflow",
        "trigger": {
            "source": "card_completed",
            "condition": {"assignee": "qa", "metadata.verdict": "PASS"},
        },
        "nodes": [
            {"id": "notify", "profile": "product-owner", "skill": "dev-planning",
             "body_template": "Notify about ${trigger.card_id}"},
        ],
    }

    fixture = RealBoardFixture(tmpl)
    try:
        # Create a trigger card on the real board
        ok, out = create_card(
            board=fixture.board, title="[qa] trigger test", assignee="qa",
        )
        assert ok
        trigger_card_id = json.loads(out)["id"]

        # Simulate its completion with matching metadata
        _simulate_completion(
            fixture.board, trigger_card_id,
            metadata={"verdict": "PASS", "feature": "real-trigger"},
            summary="Trigger test passed",
        )
        print(f"  Trigger card completed: {trigger_card_id}")

        # Tick the engine — should detect the completion and start the workflow
        actions = fixture.tick()

        assert any("STARTED workflow" in a for a in actions), \
            f"Expected STARTED workflow, got: {actions}"

        # Verify a new instance was created (may be other active instances from other tests)
        active = fixture.engine.state.load_active_instances()
        # Filter to instances triggered by THIS test's card
        triggered = [i for i in active if i.trigger_context.get("card_id") == trigger_card_id]
        assert len(triggered) >= 1, f"Expected triggered-wf instance for card {trigger_card_id}, got {len(triggered)}"

        inst = triggered[0]
        assert inst.workflow_id == "triggered-wf"
        assert inst.trigger_context.get("card_id") == trigger_card_id
        assert inst.trigger_context.get("verdict") == "PASS"

        print(f"  Trigger fired: instance {inst.instance_id} started")
        print(f"  Trigger context: {inst.trigger_context}")

        # Tick again — should dispatch the notify node
        actions = fixture.tick()
        assert any("DISPATCHED" in a for a in actions), \
            f"Expected notify DISPATCHED, got: {actions}"
    finally:
        fixture.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 13: Idempotency on real board — engine doesn't create duplicate cards
# ═══════════════════════════════════════════════════════════════════════════

def test_real_idempotency_no_duplicates():
    """Verify engine doesn't create duplicate cards on re-tick."""
    fixture = RealBoardFixture(_simple_template("idem-real", [
        {"id": "only", "profile": "product-owner", "skill": "dev-planning",
         "body_template": "Only node"},
    ]))
    try:
        instance_id = fixture.start("idem-real")
        print(f"  Started: {instance_id}")

        # Tick 1: creates card
        actions1 = fixture.tick()
        assert _count_cards(fixture.board) == 1

        # Tick 2: should NOT create a duplicate
        actions2 = fixture.tick()
        assert _count_cards(fixture.board) == 1, \
            f"Expected 1 card after 2 ticks, got {_count_cards(fixture.board)}"

        print(f"  Idempotency verified: 1 card after 2 ticks")
    finally:
        fixture.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 14: Variable resolution on real board
# ═══════════════════════════════════════════════════════════════════════════

def test_real_variable_resolution():
    """Verify output from node A resolves in node B's body on a real board."""
    fixture = RealBoardFixture(_simple_template("var-real", [
        {"id": "producer", "profile": "product-owner", "skill": "dev-planning",
         "body_template": "Produce output"},
        {"id": "consumer", "profile": "product-owner", "skill": "dev-planning",
         "body_template": "Consume ${nodes.producer.output.result_path} and ${nodes.producer.output.version}",
         "depends_on": ["producer"]},
    ]))
    try:
        instance_id = fixture.start("var-real")
        fixture.tick()  # dispatch producer

        # Complete producer with outputs
        producer_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:producer"
        )
        assert len(producer_cards) == 1
        fixture.complete_card(
            producer_cards[0].id,
            metadata={"result_path": "/real/output.md", "version": "v2.0"},
        )

        # Tick: producer done → dispatch consumer
        actions = fixture.tick()

        # Verify the consumer card was created with resolved variables
        consumer_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:consumer"
        )
        assert len(consumer_cards) == 1

        # Read the actual body from the real DB to verify variable resolution
        db = _get_real_db_path(fixture.board)
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT body FROM tasks WHERE id = ?", (consumer_cards[0].id,)
        ).fetchone()
        conn.close()

        body = row[0] if row else ""
        assert "/real/output.md" in body, \
            f"Variable not resolved in body: {body}"
        assert "v2.0" in body, f"Variable not resolved in body: {body}"
        assert "${" not in body, f"Unresolved variable in body: {body}"

        print(f"  Consumer card body: {body}")
        print(f"  Variable resolution verified on real board!")
    finally:
        fixture.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 15: Deleted board detection — engine handles missing board gracefully
# ═══════════════════════════════════════════════════════════════════════════

def test_deleted_board_detection():
    """Verify engine detects a deleted board and marks instance complete."""
    fixture = RealBoardFixture(_simple_template("del-board", [
        {"id": "step1", "profile": "product-owner", "skill": "dev-planning",
         "body_template": "Step 1"},
    ]))
    try:
        instance_id = fixture.start("del-board")
        fixture.tick()  # dispatches card

        # Now DELETE the board out from under the engine
        _delete_board(fixture.board)
        fixture.boards_created = []  # prevent double-delete in cleanup
        print(f"  Board deleted while instance {instance_id} is active")

        # Tick should detect missing board and mark instance complete
        actions = fixture.tick()
        assert any("not found" in a.lower() or "missing" in a.lower() for a in actions), \
            f"Expected missing-board warning, got: {actions}"
        assert any("complete" in a.lower() or "zombie" in a.lower() for a in actions), \
            f"Expected instance marked complete, got: {actions}"

        # Instance should no longer be active
        active = fixture.engine.state.load_active_instances()
        active_for_instance = [i for i in active if i.instance_id == instance_id]
        assert len(active_for_instance) == 0, \
            f"Instance should be marked complete, still active: {active_for_instance}"

        print(f"  Deleted board detected, instance marked complete")
    finally:
        fixture.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 16: get_card returns None for nonexistent card (real board)
# ═══════════════════════════════════════════════════════════════════════════

def test_get_card_nonexistent():
    """Verify get_card returns None for a card that doesn't exist."""
    board = _unique_board_name("wf-int-nonexist")
    try:
        assert _create_board(board), "Board creation failed"

        card = get_card(board, "t_nonexistent_12345")
        assert card is None, f"Expected None, got: {card}"

        meta = get_card_metadata(board, "t_nonexistent_12345")
        assert meta == {}, f"Expected empty dict, got: {meta}"

        print("  get_card correctly returns None for nonexistent card")
    finally:
        _delete_board(board)


# ═══════════════════════════════════════════════════════════════════════════
# REAL AGENT DISPATCH TESTS (only run with --real flag to keep normal runs fast)
# ═══════════════════════════════════════════════════════════════════════════

def test_real_agent_echo_test():
    """Real agent dispatch test — single node workflow.

    This test dispatches a REAL card and waits for a real agent to complete it.
    It's slow (30-60s+) so only runs when --real is passed.

    Uses the echo-test template pattern: write a file, verify with metadata.
    """
    # Create a unique output file so this doesn't collide with other runs
    output_file = f"/tmp/wf-int-real-{uuid.uuid4().hex[:8]}.txt"
    expected_content = f"hello from integration test {int(time.time())}"

    tmpl = {
        "id": "real-echo",
        "name": "Real echo test",
        "nodes": [
            {
                "id": "write",
                "profile": "developer",
                "skill": "developer-loop",
                "body_template": (
                    f"Write exactly this string to {output_file}:\n\n"
                    f"'{expected_content}'\n\n"
                    f"Then complete this card with metadata: "
                    f"{{file_written: true, content: '{expected_content}'}}"
                ),
                "output": {
                    "schema": {
                        "type": "object",
                        "required": ["file_written"],
                        "properties": {
                            "file_written": {"type": "boolean"}
                        }
                    }
                }
            }
        ],
    }

    fixture = RealBoardFixture(tmpl)
    try:
        instance_id = fixture.start("real-echo")
        print(f"  Started: {instance_id}")
        print(f"  Output file: {output_file}")
        print(f"  Waiting for real agent (may take 30-60s)...")

        # Dispatch via engine tick
        actions = fixture.tick()
        assert any("DISPATCHED" in a for a in actions), \
            f"Expected DISPATCHED, got: {actions}"

        write_cards = find_cards_by_idempotency_key(
            fixture.board, f"wf:{instance_id}:write"
        )
        assert len(write_cards) == 1
        card_id = write_cards[0].id
        print(f"  Card dispatched: {card_id}")

        # Poll for completion (max 120s)
        deadline = time.time() + 120
        completed = False
        while time.time() < deadline:
            card = get_card(fixture.board, card_id)
            if card and card.status == "done":
                completed = True
                break
            time.sleep(5)

        assert completed, f"Card {card_id} did not complete within 120s"

        # Verify the file was actually written
        assert Path(output_file).exists(), f"Output file {output_file} not created"
        actual_content = Path(output_file).read_text()
        assert expected_content in actual_content, \
            f"Expected '{expected_content}' in file, got: {actual_content}"

        # Verify metadata
        meta = get_card_metadata(fixture.board, card_id)
        assert meta.get("metadata", {}).get("file_written") is True, \
            f"Expected file_written=True, got: {meta}"

        # Tick engine to detect completion
        actions = fixture.tick()
        assert any("DONE" in a for a in actions), f"Expected DONE, got: {actions}"
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Expected WORKFLOW COMPLETE, got: {actions}"

        print(f"  Real agent completed! File written, workflow advanced.")

        # Cleanup output file
        Path(output_file).unlink(missing_ok=True)
    finally:
        fixture.cleanup()
        Path(output_file).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# Main — run all tests
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Workflow engine integration tests")
    parser.add_argument("--real", action="store_true",
                        help="Include real agent dispatch tests (slow)")
    parser.add_argument("--only", type=str, default="",
                        help="Run only tests matching this substring")
    args = parser.parse_args()

    global _PASSED, _FAILED, _ERRORS
    _PASSED = 0
    _FAILED = 0
    _ERRORS = []

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  WORKFLOW ENGINE — REAL INTEGRATION TESTS                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"Timestamp: {int(time.time())}")
    print(f"Real agent tests: {'ENABLED' if args.real else 'DISABLED (use --real to enable)'}")
    print()

    # Define all tests
    all_tests = [
        # Real board/adapter tests (simulated completions)
        ("test_real_card_creation", test_real_card_creation),
        ("test_real_idempotency_lookup", test_real_idempotency_lookup),
        ("test_real_metadata_reading", test_real_metadata_reading),
        ("test_real_trigger_detection", test_real_trigger_detection),
        ("test_real_project_dir_mapping", test_real_project_dir_mapping),
        ("test_board_cleanup", test_board_cleanup),
        ("test_multiple_boards", test_multiple_boards),
        ("test_card_status_transitions", test_card_status_transitions),
        ("test_empty_metadata", test_empty_metadata),
        ("test_large_metadata", test_large_metadata),

        # Real engine lifecycle tests (simulated completions)
        ("test_engine_full_lifecycle_simulated", test_engine_full_lifecycle_simulated),
        ("test_real_trigger_fires_workflow", test_real_trigger_fires_workflow),
        ("test_real_idempotency_no_duplicates", test_real_idempotency_no_duplicates),
        ("test_real_variable_resolution", test_real_variable_resolution),
        ("test_deleted_board_detection", test_deleted_board_detection),
        ("test_get_card_nonexistent", test_get_card_nonexistent),
    ]

    # Add real agent tests if --real
    if args.real:
        all_tests.append(("test_real_agent_echo_test", test_real_agent_echo_test))

    # Filter
    if args.only:
        all_tests = [(n, fn) for n, fn in all_tests if args.only.lower() in n.lower()]

    # Run
    for name, fn in all_tests:
        run_test(name, fn)

    # Summary
    print(f"\n{'═'*70}")
    print(f"RESULTS: {_PASSED} passed, {_FAILED} failed, {_PASSED + _FAILED} total")
    if _ERRORS:
        print(f"\nFAILURES:")
        for e in _ERRORS:
            print(f"  ✗ {e}")
    print(f"{'═'*70}")

    sys.exit(0 if _FAILED == 0 else 1)


if __name__ == "__main__":
    main()
