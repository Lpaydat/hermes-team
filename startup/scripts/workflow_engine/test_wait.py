"""
Wait node tests.

Tests the type="wait" node (polls condition until true).

Run: python3 test_wait.py
"""
import sys
import json
import sqlite3
import time
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.test_engine import FakeWorld


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Wait node — fires immediately when condition met
# ═══════════════════════════════════════════════════════════════════════════

def test_wait_immediate():
    """Wait node with condition already true resolves immediately."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-immediate",
        "name": "Wait Immediate",
        "nodes": [
            {"id": "source", "profile": "qa", "skill": "",
             "body_template": "Set flag"},
            {"id": "wait_ok", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.source.output.ready} == 'true'",
             "depends_on": ["source"]},
            {"id": "after", "profile": "developer", "skill": "",
             "body_template": "After wait", "depends_on": ["wait_ok"]},
        ],
        "edges": [
            {"from": "source", "to": "wait_ok"},
            {"from": "wait_ok", "to": "after"},
        ],
    })

    world.start("wait-immediate")
    world.tick()  # dispatch source

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"ready": "true"})

    actions = world.tick()
    assert any("DONE" in a and "wait_ok" in a for a in actions), \
        f"Expected wait resolved, got: {actions}"
    assert any("DISPATCHED" in a and "after" in a for a in actions), \
        f"Expected after DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_wait_immediate")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Wait node — blocks when condition not met
# ═══════════════════════════════════════════════════════════════════════════

def test_wait_blocks_then_resolves():
    """Wait node blocks when condition not met."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-block",
        "name": "Wait Block",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Source"},
            {"id": "gate", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.verdict} == 'PASS'",
             "depends_on": ["src"]},
            {"id": "proceed", "profile": "developer", "skill": "",
             "body_template": "Proceed", "depends_on": ["gate"]},
        ],
        "edges": [
            {"from": "src", "to": "gate"},
            {"from": "gate", "to": "proceed"},
        ],
    })

    world.start("wait-block")
    world.tick()  # dispatch src

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"verdict": "FAIL"})

    actions = world.tick()  # src done, but wait blocks
    assert not any("DONE" in a and "gate" in a for a in actions), \
        f"Wait should block on FAIL, got: {actions}"
    assert not any("DISPATCHED" in a and "proceed" in a for a in actions), \
        f"proceed should not dispatch, got: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    gate_status = conn.execute("SELECT status FROM node_states WHERE node_id='gate'").fetchone()
    conn.close()
    assert gate_status and gate_status[0] in ("pending", "dispatched"), \
        f"gate should be non-terminal (pending), got: {gate_status}"

    world.cleanup()
    print("OK: test_wait_blocks_then_resolves")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Wait node with empty condition fires immediately
# ═══════════════════════════════════════════════════════════════════════════

def test_wait_empty():
    """Wait node with no condition fires immediately."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-empty",
        "name": "Wait Empty",
        "nodes": [
            {"id": "pass_through", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": ""},
            {"id": "after", "profile": "developer", "skill": "",
             "body_template": "After", "depends_on": ["pass_through"]},
        ],
        "edges": [{"from": "pass_through", "to": "after"}],
    })

    world.start("wait-empty")
    actions = world.tick()

    assert any("DONE" in a and "pass_through" in a for a in actions), \
        f"Expected wait DONE, got: {actions}"
    assert any("DISPATCHED" in a and "after" in a for a in actions), \
        f"Expected after DISPATCHED, got: {actions}"

    world.cleanup()
    print("OK: test_wait_empty")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_wait_immediate,
        test_wait_blocks_then_resolves,
        test_wait_empty,
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
