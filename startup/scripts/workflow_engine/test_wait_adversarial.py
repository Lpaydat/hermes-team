"""
Adversarial + edge case tests for the wait node.

Push every boundary: blocking, chaining, command output interaction,
undefined variables, numeric conditions, diamond convergence.

Run: python3 test_wait_adversarial.py
"""
import sys
import json
import sqlite3
import time
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.test_engine import FakeWorld, count_cards


# ═══════════════════════════════════════════════════════════════════════════
# WAIT — EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

def test_wait_blocks_workflow_completion():
    """Unresolved wait node prevents workflow from completing."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-block-complete",
        "name": "Wait Blocks Completion",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Source"},
            {"id": "gate", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.ready} == 'true'",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "gate"}],
    })
    world.start("wait-block-complete")
    world.tick()  # dispatch src

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"ready": "false"})  # NOT ready

    actions = world.tick()

    # Workflow should NOT complete — wait is still pending
    assert not any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Workflow should not complete with unresolved wait: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    gate_status = conn.execute("SELECT status FROM node_states WHERE node_id='gate'").fetchone()[0]
    conn.close()
    assert gate_status == "pending", f"gate should be pending, got {gate_status}"

    world.cleanup()
    print("OK: test_wait_blocks_workflow_completion")


def test_wait_with_command_output():
    """Wait resolves based on command node output."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-cmd",
        "name": "Wait Command",
        "nodes": [
            {"id": "check", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "printf '%s' '{\"status\": \"ready\"}'"},
            {"id": "gate", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.check.output.status} == 'ready'",
             "depends_on": ["check"]},
            {"id": "go", "profile": "developer", "skill": "",
             "body_template": "Go", "depends_on": ["gate"]},
        ],
        "edges": [
            {"from": "check", "to": "gate"},
            {"from": "gate", "to": "go"},
        ],
    })
    world.start("wait-cmd")
    actions = world.tick()

    # Command runs, output has status=ready, wait resolves, go dispatches — all in one tick
    assert any("DONE" in a and "check" in a for a in actions), f"command should run: {actions}"
    assert any("DONE" in a and "gate" in a for a in actions), f"wait should resolve: {actions}"
    assert any("DISPATCHED" in a and "go" in a for a in actions), f"go should dispatch: {actions}"

    world.cleanup()
    print("OK: test_wait_with_command_output")


def test_wait_with_command_output_blocking():
    """Wait blocks when command output doesn't match condition."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-cmd-block",
        "name": "Wait Command Block",
        "nodes": [
            {"id": "check", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "printf '%s' '{\"status\": \"not_ready\"}'"},
            {"id": "gate", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.check.output.status} == 'ready'",
             "depends_on": ["check"]},
        ],
        "edges": [{"from": "check", "to": "gate"}],
    })
    world.start("wait-cmd-block")
    actions = world.tick()

    assert any("DONE" in a and "check" in a for a in actions), f"command should run: {actions}"
    assert not any("DONE" in a and "gate" in a for a in actions), \
        f"wait should NOT resolve (status=not_ready): {actions}"
    assert not any("WORKFLOW COMPLETE" in a for a in actions)

    conn = sqlite3.connect(str(world.state_db_path))
    gate_status = conn.execute("SELECT status FROM node_states WHERE node_id='gate'").fetchone()[0]
    conn.close()
    assert gate_status == "pending"

    world.cleanup()
    print("OK: test_wait_with_command_output_blocking")


def test_chained_waits():
    """Two wait nodes in sequence — both must resolve."""
    world = FakeWorld()
    world.add_template({
        "id": "chained-wait",
        "name": "Chained Wait",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Source"},
            {"id": "w1", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.a} == '1'",
             "depends_on": ["src"]},
            {"id": "w2", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.b} == '2'",
             "depends_on": ["w1"]},
            {"id": "final", "profile": "developer", "skill": "",
             "body_template": "Final", "depends_on": ["w2"]},
        ],
        "edges": [
            {"from": "src", "to": "w1"},
            {"from": "w1", "to": "w2"},
            {"from": "w2", "to": "final"},
        ],
    })
    world.start("chained-wait")
    world.tick()  # dispatch src

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"a": "1", "b": "2"})

    actions = world.tick()

    # Both waits should resolve in the same tick (both conditions met)
    assert any("w1" in a and "DONE" in a for a in actions), f"w1 should resolve: {actions}"
    assert any("w2" in a and "DONE" in a for a in actions), f"w2 should resolve: {actions}"
    assert any("final" in a and "DISPATCHED" in a for a in actions), f"final should dispatch: {actions}"

    world.cleanup()
    print("OK: test_chained_waits")


def test_chained_waits_one_blocks():
    """Two waits in sequence — second blocks, preventing final dispatch."""
    world = FakeWorld()
    world.add_template({
        "id": "chained-block",
        "name": "Chained Block",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Source"},
            {"id": "w1", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.a} == '1'",
             "depends_on": ["src"]},
            {"id": "w2", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.b} == '999'",
             "depends_on": ["w1"]},
            {"id": "final", "profile": "developer", "skill": "",
             "body_template": "Final", "depends_on": ["w2"]},
        ],
        "edges": [
            {"from": "src", "to": "w1"},
            {"from": "w1", "to": "w2"},
            {"from": "w2", "to": "final"},
        ],
    })
    world.start("chained-block")
    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"a": "1", "b": "2"})

    actions = world.tick()

    assert any("w1" in a and "DONE" in a for a in actions), f"w1 should resolve: {actions}"
    assert not any("w2" in a and "DONE" in a for a in actions), \
        f"w2 should NOT resolve (b=2, not 999): {actions}"
    assert not any("final" in a and "DISPATCHED" in a for a in actions)

    world.cleanup()
    print("OK: test_chained_waits_one_blocks")


def test_wait_does_not_create_cards():
    """Wait node must not create kanban cards."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-nocards",
        "name": "Wait No Cards",
        "nodes": [
            {"id": "w", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": ""},
        ],
    })
    world.start("wait-nocards")
    world.tick()
    assert count_cards(world.board_db) == 0, "Wait should not create cards"
    world.cleanup()
    print("OK: test_wait_does_not_create_cards")


def test_wait_with_undefined_variable():
    """Wait condition references undefined variable — should not resolve."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-undef",
        "name": "Wait Undefined",
        "nodes": [
            {"id": "w", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.ghost.output.value} == '42'"},
        ],
    })
    world.start("wait-undef")
    actions = world.tick()

    # Undefined variable → condition false → wait stays pending
    assert not any("w" in a and "DONE" in a for a in actions), \
        f"Wait should not resolve with undefined var: {actions}"
    assert not any("WORKFLOW COMPLETE" in a for a in actions)

    conn = sqlite3.connect(str(world.state_db_path))
    status = conn.execute("SELECT status FROM node_states WHERE node_id='w'").fetchone()
    conn.close()
    assert status[0] == "pending"

    world.cleanup()
    print("OK: test_wait_with_undefined_variable")


def test_multiple_waits_converge():
    """Multiple wait nodes converging on a single task node."""
    world = FakeWorld()
    world.add_template({
        "id": "multi-wait",
        "name": "Multi Wait",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Set flags"},
            {"id": "w1", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.flag1} == 'true'",
             "depends_on": ["src"]},
            {"id": "w2", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.flag2} == 'true'",
             "depends_on": ["src"]},
            {"id": "go", "profile": "developer", "skill": "",
             "body_template": "Go after both", "depends_on": ["w1", "w2"]},
        ],
        "edges": [
            {"from": "src", "to": "w1"},
            {"from": "src", "to": "w2"},
            {"from": "w1", "to": "go"},
            {"from": "w2", "to": "go"},
        ],
    })
    world.start("multi-wait")
    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"flag1": "true", "flag2": "true"})

    actions = world.tick()

    assert any("w1" in a and "DONE" in a for a in actions), f"w1: {actions}"
    assert any("w2" in a and "DONE" in a for a in actions), f"w2: {actions}"
    assert any("go" in a and "DISPATCHED" in a for a in actions), f"go: {actions}"

    world.cleanup()
    print("OK: test_multiple_waits_converge")


def test_multiple_waits_one_blocks():
    """Multiple wait nodes converge — one blocks, preventing go."""
    world = FakeWorld()
    world.add_template({
        "id": "multi-block",
        "name": "Multi Block",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": "Set flags"},
            {"id": "w1", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.flag1} == 'true'",
             "depends_on": ["src"]},
            {"id": "w2", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.src.output.flag2} == 'true'",
             "depends_on": ["src"]},
            {"id": "go", "profile": "developer", "skill": "",
             "body_template": "Go", "depends_on": ["w1", "w2"]},
        ],
        "edges": [
            {"from": "src", "to": "w1"},
            {"from": "src", "to": "w2"},
            {"from": "w1", "to": "go"},
            {"from": "w2", "to": "go"},
        ],
    })
    world.start("multi-block")
    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"flag1": "true", "flag2": "false"})

    actions = world.tick()

    assert any("w1" in a and "DONE" in a for a in actions), f"w1 should resolve: {actions}"
    assert not any("w2" in a and "DONE" in a for a in actions), f"w2 should block: {actions}"
    assert not any("go" in a and "DISPATCHED" in a for a in actions), f"go should not dispatch: {actions}"

    world.cleanup()
    print("OK: test_multiple_waits_one_blocks")


def test_wait_condition_with_numbers():
    """Wait condition comparing numeric output (as string)."""
    world = FakeWorld()
    world.add_template({
        "id": "wait-num",
        "name": "Wait Numbers",
        "nodes": [
            {"id": "check", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "printf '%s' '{\"count\": 42}'"},
            {"id": "gate", "profile": "", "skill": "",
             "body_template": "", "type": "wait",
             "wait_condition": "${nodes.check.output.count} == '42'",
             "depends_on": ["check"]},
            {"id": "go", "profile": "developer", "skill": "",
             "body_template": "Go", "depends_on": ["gate"]},
        ],
        "edges": [
            {"from": "check", "to": "gate"},
            {"from": "gate", "to": "go"},
        ],
    })
    world.start("wait-num")
    actions = world.tick()

    assert any("check" in a and "DONE" in a for a in actions), f"command: {actions}"
    assert any("gate" in a and "DONE" in a for a in actions), f"wait should resolve: {actions}"
    assert any("go" in a and "DISPATCHED" in a for a in actions), f"go: {actions}"

    world.cleanup()
    print("OK: test_wait_condition_with_numbers")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Wait edge cases
        test_wait_blocks_workflow_completion,
        test_wait_with_command_output,
        test_wait_with_command_output_blocking,
        test_chained_waits,
        test_chained_waits_one_blocks,
        test_wait_does_not_create_cards,
        test_wait_with_undefined_variable,
        test_multiple_waits_converge,
        test_multiple_waits_one_blocks,
        test_wait_condition_with_numbers,
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
    if failed == 0:
        print("ALL ADVERSARIAL TESTS PASSED")
    else:
        print(f"{failed} TEST(S) FAILED")
    sys.exit(0 if failed == 0 else 1)
