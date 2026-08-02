"""Tests for the T4 state-blob migration (expand phase, bead hermes-teams-qxb5).

Covers:
- ``state`` and ``version`` columns exist on ``workflow_instances`` after
  schema init and after migration of a pre-existing DB.
- ``load_state`` / ``save_state`` with optimistic versioning.
- ``backfill_state_blob`` round-trips ``node_states`` rows into the blob,
  including ``card_status`` lookup from the board.
- ``node_states`` table is NOT dropped (coexistence).
- ``NodeStatus`` deprecation shim still importable / usable.
- The standalone ``migrate_to_state_blob`` script (dry-run + --apply).

Run: python3 -m pytest test_state_blob.py -v
Or:  python3 test_state_blob.py
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add scripts dir to path (parent.parent = .../scripts, which contains the
# workflow_engine package).
SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine import kanban_adapter as ka
from workflow_engine.kanban_adapter import board_db_path, KANBAN_HOME
from workflow_engine.runtime import (
    StateDB, NodeStatus, NodeState, WorkflowInstance,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def make_fake_board(tmpdir: Path, board_name: str = "test-board") -> str:
    """Create a minimal kanban DB with the Hermes schema (tasks table)."""
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
    """)
    conn.commit()
    conn.close()
    return board_name


def make_fake_card(board_db: Path, card_id: str, status: str = "done"):
    """Insert a card row into a fake board."""
    conn = sqlite3.connect(str(board_db))
    conn.execute(
        """INSERT OR REPLACE INTO tasks
           (id, title, assignee, status, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (card_id, f"card {card_id}", "test-profile", status, int(time.time())),
    )
    conn.commit()
    conn.close()


def make_instance(
    instance_id: str = "inst-1",
    board: str = "test-board",
    nodes: dict | None = None,
) -> WorkflowInstance:
    """Build a WorkflowInstance with the given node_states."""
    nodes = nodes or {}
    inst = WorkflowInstance(
        instance_id=instance_id,
        workflow_id="wf-1",
        board=board,
        project_dir="/tmp",
        created_at=int(time.time()),
        node_states=nodes,
    )
    inst.node_ids = list(nodes.keys())
    return inst


# ═══════════════════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════════════════

def test_columns_present_on_fresh_db():
    """A freshly-created DB has state and version columns."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        conn = sqlite3.connect(str(db.db_path))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
        conn.close()
        assert "state" in cols, f"state column missing: {cols}"
        assert "version" in cols, f"version column missing: {cols}"


def test_columns_migrated_on_old_db():
    """A DB created WITHOUT the new columns gets them via _migrate_columns."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "state.db"
        # Create a pre-T4 schema manually.
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE workflow_instances (
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
            CREATE TABLE node_states (
                instance_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                card_id TEXT,
                output TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (instance_id, node_id)
            );
        """)
        conn.commit()
        conn.close()

        # Opening StateDB must add the missing columns.
        StateDB(db_path)
        conn = sqlite3.connect(str(db_path))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
        conn.close()
        assert "state" in cols and "version" in cols, f"migration failed: {cols}"


def test_node_states_table_still_exists():
    """T4 must NOT drop node_states — coexistence."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        conn = sqlite3.connect(str(db.db_path))
        tabs = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "node_states" in tabs, "node_states table was dropped — T4 must keep it"


# ═══════════════════════════════════════════════════════════════════════════
# load_state / save_state
# ═══════════════════════════════════════════════════════════════════════════

def test_load_state_default_for_new_instance():
    """load_state returns empty blob + version 0 for an instance with no blob."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={"n1": NodeState("inst-1", "n1", NodeStatus.PENDING)})
        db.create_instance(inst)
        result = db.load_state("inst-1")
        assert result == {"state": {}, "version": 0}, result


def test_load_state_nonexistent_instance():
    """load_state returns the default for an instance that doesn't exist."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        assert db.load_state("does-not-exist") == {"state": {}, "version": 0}


def test_save_state_basic_round_trip():
    """save_state writes and bumps version; load_state reads it back."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={"n1": NodeState("inst-1", "n1", NodeStatus.PENDING)})
        db.create_instance(inst)

        blob = {"nodes": {"n1": {"phase": "done", "output": {"r": 1}}}}
        ok = db.save_state("inst-1", blob, expected_version=0)
        assert ok is True, "first save should succeed"

        result = db.load_state("inst-1")
        assert result["state"] == blob, result
        assert result["version"] == 1, result


def test_save_state_version_conflict_returns_false():
    """A save with a stale expected_version must fail and not change the blob."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={"n1": NodeState("inst-1", "n1", NodeStatus.PENDING)})
        db.create_instance(inst)

        # Writer A: version 0 -> 1
        assert db.save_state("inst-1", {"a": 1}, expected_version=0) is True
        # Writer B: stale view of version 0 -> must conflict
        ok = db.save_state("inst-1", {"b": 2}, expected_version=0)
        assert ok is False, "stale-version save must return False"

        result = db.load_state("inst-1")
        assert result["version"] == 1, "version must not advance on conflict"
        assert result["state"] == {"a": 1}, "blob must be A's write, not B's"


def test_save_state_version_increments_monotonically():
    """Each successful save bumps version by exactly 1."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={"n1": NodeState("inst-1", "n1", NodeStatus.PENDING)})
        db.create_instance(inst)

        v = 0
        for i in range(5):
            assert db.save_state("inst-1", {"iter": i}, expected_version=v) is True
            v += 1
        result = db.load_state("inst-1")
        assert result["version"] == 5, result
        assert result["state"] == {"iter": 4}


def test_save_state_nonexistent_instance_returns_false():
    """save_state on an unknown instance returns False (no row to update)."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        assert db.save_state("ghost", {}, expected_version=0) is False


def test_save_state_correct_version_after_backfill():
    """After backfill (version stays 0), a save with expected_version=0 works."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(
            nodes={"n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"x": 1})}
        )
        db.create_instance(inst)
        db.backfill_state_blob()

        # backfill does not bump version; still 0.
        result = db.load_state("inst-1")
        assert result["version"] == 0
        ok = db.save_state("inst-1", {"new": "blob"}, expected_version=0)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# backfill_state_blob
# ═══════════════════════════════════════════════════════════════════════════

def test_backfill_populates_blob_from_node_states():
    """Backfill reads node_states and writes a per-node blob."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "card-1", {"result": 42}),
            "n2": NodeState("inst-1", "n2", NodeStatus.PENDING),
        })
        db.create_instance(inst)

        stats = db.backfill_state_blob()
        assert stats["migrated"] == 1, stats
        assert stats["errors"] == 0, stats

        result = db.load_state("inst-1")
        state = result["state"]
        assert "n1" in state and "n2" in state

        n1 = state["n1"]
        assert n1["card_id"] == "card-1"
        assert n1["output"] == {"result": 42}
        assert n1["iteration"] == 0
        assert n1["_legacy_status"] == "done"
        # card_status is None because the board doesn't exist in this test.
        assert n1["card_status"] is None

        n2 = state["n2"]
        assert n2["_legacy_status"] == "pending"
        assert n2["output"] == {}


def test_backfill_card_status_lookup_from_board():
    """When a real board exists, card_status is populated from the card row."""
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        board = make_fake_board(tmpdir, "test-board")
        board_db = tmpdir / "boards" / board / "kanban.db"
        make_fake_card(board_db, "card-1", status="done")

        db = StateDB(tmpdir / "state.db")
        inst = make_instance(
            board=board,
            nodes={"n1": NodeState("inst-1", "n1", NodeStatus.DONE, "card-1", {"r": 1})},
        )
        db.create_instance(inst)

        # Monkey-patch KANBAN_HOME so kanban_adapter finds the fake board.
        orig = ka.KANBAN_HOME
        ka.KANBAN_HOME = tmpdir / "boards"
        try:
            stats = db.backfill_state_blob()
        finally:
            ka.KANBAN_HOME = orig

        assert stats["migrated"] == 1 and stats["errors"] == 0, stats
        result = db.load_state("inst-1")
        assert result["state"]["n1"]["card_status"] == "done"


def test_backfill_skips_instance_with_no_node_states():
    """An active instance with zero node_states rows is skipped, not migrated."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={})  # no nodes
        db.create_instance(inst)

        stats = db.backfill_state_blob()
        assert stats["migrated"] == 0, stats
        assert stats["skipped"] == 1, stats

        result = db.load_state("inst-1")
        assert result["state"] == {}, "blob must remain empty when skipped"


def test_backfill_skips_completed_instances():
    """Only ACTIVE instances are migrated; completed ones are ignored."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"r": 1})
        })
        db.create_instance(inst)
        db.complete_instance("inst-1")  # mark completed

        stats = db.backfill_state_blob()
        assert stats["migrated"] == 0, stats


def test_backfill_is_idempotent():
    """Running backfill twice produces the same blob."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"r": 1})
        })
        db.create_instance(inst)

        s1 = db.backfill_state_blob()
        blob1 = db.load_state("inst-1")["state"]

        s2 = db.backfill_state_blob()
        blob2 = db.load_state("inst-1")["state"]

        assert s1["migrated"] == 1 and s2["migrated"] == 1
        assert blob1 == blob2, "idempotent backfill must not drift"


def test_backfill_does_not_touch_node_states_table():
    """Backfill leaves node_states rows intact (coexistence)."""
    with tempfile.TemporaryDirectory() as td:
        db = StateDB(Path(td) / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"r": 1})
        })
        db.create_instance(inst)

        db.backfill_state_blob()

        conn = sqlite3.connect(str(db.db_path))
        rows = conn.execute(
            "SELECT node_id, status, output FROM node_states WHERE instance_id = ?",
            ("inst-1",),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "n1"
        assert rows[0][1] == "done"
        assert json.loads(rows[0][2]) == {"r": 1}


def test_backfill_handles_corrupt_output_gracefully():
    """A node_states row with unparseable output falls back to {}."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "state.db"
        db = StateDB(db_path)
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"ok": True})
        })
        db.create_instance(inst)

        # Corrupt the output directly in the DB.
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE node_states SET output = ? WHERE instance_id = ? AND node_id = ?",
            ("not-valid-json{{{", "inst-1", "n1"),
        )
        conn.commit()
        conn.close()

        stats = db.backfill_state_blob()
        assert stats["errors"] == 0, "corrupt output should be recovered, not error"
        result = db.load_state("inst-1")
        assert result["state"]["n1"]["output"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# NodeStatus deprecation shim
# ═══════════════════════════════════════════════════════════════════════════

def test_node_status_still_importable_and_usable():
    """NodeStatus remains importable with all 5 values (deprecation shim)."""
    assert NodeStatus.PENDING == "pending"
    assert NodeStatus.DISPATCHED == "dispatched"
    assert NodeStatus.DONE == "done"
    assert NodeStatus.FAILED == "failed"
    assert NodeStatus.SKIPPED == "skipped"
    # str-Enum behaviour preserved: comparable to plain strings.
    assert NodeStatus.DONE == "done"


# ═══════════════════════════════════════════════════════════════════════════
# Standalone migration script
# ═══════════════════════════════════════════════════════════════════════════

def test_migration_script_dry_run_makes_no_changes():
    """The script without --apply must not modify the DB."""
    from workflow_engine.migrate_to_state_blob import main as migrate_main

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        db = StateDB(tmpdir / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"r": 1})
        })
        db.create_instance(inst)
        db_path = tmpdir / "state.db"

        rc = migrate_main(["--db", str(db_path), "-v"])
        assert rc == 0
        # Blob must still be empty after a dry-run.
        result = db.load_state("inst-1")
        assert result["state"] == {}, "dry-run must not backfill"


def test_migration_script_apply_backfills_and_backs_up():
    """--apply backfills the blob and writes a timestamped backup."""
    from workflow_engine.migrate_to_state_blob import main as migrate_main

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        db = StateDB(tmpdir / "state.db")
        inst = make_instance(nodes={
            "n1": NodeState("inst-1", "n1", NodeStatus.DONE, "c1", {"r": 1})
        })
        db.create_instance(inst)
        db_path = tmpdir / "state.db"

        rc = migrate_main(["--db", str(db_path), "--apply", "-v"])
        assert rc == 0

        # Blob is populated.
        result = db.load_state("inst-1")
        assert "n1" in result["state"]

        # Backup file exists.
        backups = list(tmpdir.glob("state.db.bak-*"))
        assert len(backups) == 1, f"expected 1 backup, got {backups}"

        # node_states table still present in the (post-migration) DB.
        conn = sqlite3.connect(str(db_path))
        tabs = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "node_states" in tabs


# ═══════════════════════════════════════════════════════════════════════════
# Test runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Minimal runner so the file works without pytest.
    import inspect
    funcs = [
        (name, fn) for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    passed, failed = 0, 0
    for name, fn in funcs:
        try:
            fn()
            print(f"PASS {name}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL {name}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(funcs)} total")
    sys.exit(1 if failed else 0)
