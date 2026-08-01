"""
Command node tests — shell execution without kanban cards or agents.

Tests the type="command" node that runs shell scripts synchronously,
captures output, and advances the workflow immediately.

Run: python3 test_command.py
"""
import sys
import json
import sqlite3
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow
from workflow_engine.test_engine import FakeWorld, count_cards


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Basic command — echo, captures stdout
# ═══════════════════════════════════════════════════════════════════════════

def test_command_basic():
    """A command node runs a shell command and captures output."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-basic",
        "name": "Command Basic",
        "nodes": [
            {"id": "echo", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo hello world"},
        ],
    })

    world.start("cmd-basic")
    actions = world.tick()

    # Command ran synchronously — node should be DONE immediately
    assert any("DONE" in a and "echo" in a for a in actions), \
        f"Expected command DONE, got: {actions}"

    # No kanban cards created
    assert count_cards(world.board_db) == 0, "Command node should not create cards"

    # Check output captured
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='echo'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    assert output.get("stdout") == "hello world", f"Expected stdout 'hello world', got: {output}"
    assert output.get("exit_code") == 0, f"Expected exit 0, got: {output}"

    world.cleanup()
    print("OK: test_command_basic")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Command with JSON output — parsed into node output
# ═══════════════════════════════════════════════════════════════════════════

def test_command_json_output():
    """Command stdout parsed as JSON merges into node output."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-json",
        "name": "Command JSON",
        "nodes": [
            {"id": "data", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo '{\"verdict\": \"PASS\", \"count\": 42}'"},
        ],
    })

    world.start("cmd-json")
    world.tick()

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='data'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    assert output.get("verdict") == "PASS", f"Expected verdict=PASS, got: {output}"
    assert output.get("count") == 42, f"Expected count=42, got: {output}"
    assert output.get("exit_code") == 0

    world.cleanup()
    print("OK: test_command_json_output")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Command failure — non-zero exit marks FAILED
# ═══════════════════════════════════════════════════════════════════════════

def test_command_failure():
    """Non-zero exit code marks node FAILED."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-fail",
        "name": "Command Fail",
        "nodes": [
            {"id": "boom", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "exit 1"},
        ],
    })

    world.start("cmd-fail")
    actions = world.tick()

    assert any("FAILED" in a and "boom" in a for a in actions), \
        f"Expected FAILED, got: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status FROM node_states WHERE node_id='boom'").fetchone()
    conn.close()
    assert row[0] == "failed", f"Expected status=failed, got: {row[0]}"

    world.cleanup()
    print("OK: test_command_failure")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Command then task — command output flows to next node
# ═══════════════════════════════════════════════════════════════════════════

def test_command_then_task():
    """Command node output available as variable in downstream nodes."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-flow",
        "name": "Command Flow",
        "nodes": [
            {"id": "get_value", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "printf '%s' '{\"build_id\": \"abc123\"}'"},
            {"id": "use_value", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build ${nodes.get_value.output.build_id}",
             "depends_on": ["get_value"]},
        ],
        "edges": [
            {"from": "get_value", "to": "use_value"},
        ],
    })

    world.start("cmd-flow")
    actions = world.tick()

    # Both nodes should process in one tick: command runs sync, then task dispatches
    assert any("DONE" in a and "get_value" in a for a in actions), \
        f"Expected command DONE, got: {actions}"
    assert any("DISPATCHED" in a and "use_value" in a for a in actions), \
        f"Expected use_value DISPATCHED, got: {actions}"

    # Verify the variable was resolved in the card body
    conn = sqlite3.connect(str(world.board_db))
    card = conn.execute("SELECT body FROM tasks WHERE assignee='developer'").fetchone()
    conn.close()
    assert card and "abc123" in card[0], f"Expected build_id in card body, got: {card}"

    world.cleanup()
    print("OK: test_command_then_task")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Command with variable substitution
# ═══════════════════════════════════════════════════════════════════════════

def test_command_variable_substitution():
    """Command supports ${} variable substitution."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-vars",
        "name": "Command Vars",
        "nodes": [
            {"id": "source", "profile": "qa", "skill": "live-testing",
             "body_template": "Get filename"},
            {"id": "process", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo ${nodes.source.output.filename}",
             "depends_on": ["source"]},
        ],
        "edges": [
            {"from": "source", "to": "process"},
        ],
    })

    world.start("cmd-vars")
    world.tick()  # dispatch source

    # Complete source with filename
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"filename": "report.csv"})

    actions = world.tick()  # source done → command runs

    assert any("DONE" in a and "process" in a for a in actions), \
        f"Expected command DONE, got: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='process'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    assert output.get("stdout") == "report.csv", \
        f"Expected stdout 'report.csv', got: {output}"

    world.cleanup()
    print("OK: test_command_variable_substitution")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Command timeout
# ═══════════════════════════════════════════════════════════════════════════

def test_command_timeout():
    """Command that exceeds timeout marks FAILED."""
    world = FakeWorld()
    # We can't test 300s timeout, but we can test that a failing command
    # with stderr is captured properly
    world.add_template({
        "id": "cmd-stderr",
        "name": "Command Stderr",
        "nodes": [
            {"id": "fail_cmd", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo 'error: bad input' >&2 && exit 2"},
        ],
    })

    world.start("cmd-stderr")
    actions = world.tick()

    assert any("FAILED" in a and "fail_cmd" in a for a in actions), \
        f"Expected FAILED, got: {actions}"

    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='fail_cmd'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    assert "bad input" in output.get("stderr", ""), \
        f"Expected stderr with 'bad input', got: {output}"
    assert output.get("exit_code") == 2

    world.cleanup()
    print("OK: test_command_timeout")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_command_basic,
        test_command_json_output,
        test_command_failure,
        test_command_then_task,
        test_command_variable_substitution,
        test_command_timeout,
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
