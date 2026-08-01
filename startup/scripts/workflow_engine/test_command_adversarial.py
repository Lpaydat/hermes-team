#!/usr/bin/env python3
"""Adversarial command node tests — try to break it."""
import sys
import json
import sqlite3
import os
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.test_engine import FakeWorld, count_cards


def test_command_injection():
    """Variable resolution that injects shell commands."""
    world = FakeWorld()
    world.add_template({
        "id": "inject",
        "name": "Injection",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "cmd", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo ${nodes.src.output.filename}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "cmd"}],
    })
    world.start("inject")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    # Inject a command
    world.complete_card(src_card, metadata={"filename": "test.txt; rm -rf /tmp/wf-inject-test"})
    os.makedirs("/tmp/wf-inject-test", exist_ok=True)
    actions = world.tick()
    # The rm -rf would have run because shell=True
    print(f"  actions: {actions}")
    if os.path.exists("/tmp/wf-inject-test"):
        print("  WARNING: injection didn't execute (safe)")
    else:
        print("  WARNING: INJECTION EXECUTED — rm -rf ran via variable substitution")
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='cmd'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    print(f"  stdout: {output.get('stdout', '')[:100]}")
    world.cleanup()


def test_command_huge_output():
    """Command that produces 100KB of output."""
    world = FakeWorld()
    world.add_template({
        "id": "huge",
        "name": "Huge",
        "nodes": [
            {"id": "big", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "python3 -c \"print('x' * 100000)\""},
        ],
    })
    world.start("huge")
    actions = world.tick()
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='big'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    stdout = output.get("stdout", "")
    print(f"  exit: {output.get('exit_code')}")
    print(f"  stdout length: {len(stdout)}")
    print(f"  node status: {row[2] if len(row) > 2 else 'N/A'}")
    world.cleanup()


def test_command_empty_string():
    """Empty command string."""
    world = FakeWorld()
    world.add_template({
        "id": "empty",
        "name": "Empty",
        "nodes": [
            {"id": "nothing", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": ""},
        ],
    })
    world.start("empty")
    actions = world.tick()
    print(f"  actions: {actions}")
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status, output FROM node_states WHERE node_id='nothing'").fetchone()
    conn.close()
    print(f"  status: {row[0]}")
    print(f"  output: {row[1][:100] if row[1] else 'NULL'}")
    world.cleanup()


def test_command_binary_output():
    """Command that outputs binary garbage."""
    world = FakeWorld()
    world.add_template({
        "id": "binary",
        "name": "Binary",
        "nodes": [
            {"id": "bin", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "head -c 100 /dev/urandom | base64"},
        ],
    })
    world.start("binary")
    actions = world.tick()
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status, output FROM node_states WHERE node_id='bin'").fetchone()
    conn.close()
    output = json.loads(row[1]) if row and row[1] else {}
    print(f"  status: {row[0] if row else 'N/A'}")
    print(f"  exit: {output.get('exit_code')}")
    print(f"  stdout length: {len(output.get('stdout', ''))}")
    world.cleanup()


def test_command_chained_3():
    """Three command nodes in sequence — all run in one tick."""
    world = FakeWorld()
    world.add_template({
        "id": "chained",
        "name": "Chained",
        "nodes": [
            {"id": "a", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo '{\"step\": 1}'"},
            {"id": "b", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo '{\"step\": 2}'"},
            {"id": "c", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo '{\"step\": 3, \"prev\": ${nodes.b.output.step}}'"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
        ],
    })
    world.start("chained")
    actions = world.tick()
    print(f"  actions ({len(actions)}):")
    for a in actions:
        print(f"    {a}")
    conn = sqlite3.connect(str(world.state_db_path))
    for r in conn.execute("SELECT node_id, status, output FROM node_states ORDER BY node_id").fetchall():
        print(f"  {r[0]}: {r[1]} = {r[2][:80] if r[2] else 'NULL'}")
    conn.close()
    world.cleanup()


def test_command_with_foreach():
    """Command node inside foreach — runs command per item."""
    world = FakeWorld()
    world.add_template({
        "id": "foreach-cmd",
        "name": "Foreach Command",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "process", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo processing ${item}",
             "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "process"}],
    })
    world.start("foreach-cmd")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"items": ["file1.txt", "file2.txt", "file3.txt"]})
    actions = world.tick()
    print(f"  actions ({len(actions)}):")
    for a in actions:
        print(f"    {a}")
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status, output FROM node_states WHERE node_id='process'").fetchone()
    conn.close()
    print(f"  process status: {row[0]}")
    if row[1]:
        output = json.loads(row[1])
        print(f"  foreach_cards: {output.get('_foreach_cards', 'N/A')}")
        print(f"  results: {output.get('results', 'N/A')}")
    world.cleanup()


def test_command_that_hangs():
    """Command that would hang forever — timeout kills it."""
    world = FakeWorld()
    world.add_template({
        "id": "hang",
        "name": "Hang",
        "nodes": [
            {"id": "sleep", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "sleep 999"},
        ],
    })
    world.start("hang")
    # This will block the tick for 300s — test with a note
    print("  SKIPPING actual hang test (would block 300s)")
    print("  NOTE: sleep 999 would timeout after 300s and mark FAILED")
    world.cleanup()


def test_command_missing_profile():
    """Command node with empty profile — should still work."""
    world = FakeWorld()
    world.add_template({
        "id": "noprofile",
        "name": "No Profile",
        "nodes": [
            {"id": "run", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo works"},
        ],
    })
    world.start("noprofile")
    actions = world.tick()
    print(f"  actions: {actions}")
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status FROM node_states WHERE node_id='run'").fetchone()
    conn.close()
    print(f"  status: {row[0] if row else 'N/A'}")
    world.cleanup()


def test_command_writes_file():
    """Command that creates a file as side effect."""
    world = FakeWorld()
    world.add_template({
        "id": "writefile",
        "name": "Write File",
        "nodes": [
            {"id": "write", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo 'content' > /tmp/wf-cmd-test.txt"},
            {"id": "read", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "cat /tmp/wf-cmd-test.txt"},
        ],
        "edges": [{"from": "write", "to": "read"}],
    })
    world.start("writefile")
    actions = world.tick()
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT output FROM node_states WHERE node_id='read'").fetchone()
    conn.close()
    output = json.loads(row[0]) if row else {}
    print(f"  read stdout: [{output.get('stdout', '').strip()}]")
    assert output.get("stdout", "").strip() == "content", f"Expected 'content', got '{output.get('stdout')}'"
    print("  PASS: file written and read correctly")
    os.unlink("/tmp/wf-cmd-test.txt")
    world.cleanup()


def test_command_undefined_variable():
    """Command referencing a non-existent variable."""
    world = FakeWorld()
    world.add_template({
        "id": "undef",
        "name": "Undefined",
        "nodes": [
            {"id": "bad", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "echo ${nodes.ghost.output.value}"},
        ],
    })
    world.start("undef")
    actions = world.tick()
    conn = sqlite3.connect(str(world.state_db_path))
    row = conn.execute("SELECT status, output FROM node_states WHERE node_id='bad'").fetchone()
    conn.close()
    output = json.loads(row[1]) if row and row[1] else {}
    print(f"  status: {row[0] if row else 'N/A'}")
    print(f"  stdout: [{output.get('stdout', '')}]")
    print(f"  (undefined var resolves to empty string — command still runs)")
    world.cleanup()


if __name__ == "__main__":
    tests = [
        ("Shell injection via variable", test_command_injection),
        ("100KB output", test_command_huge_output),
        ("Empty command string", test_command_empty_string),
        ("Binary output (base64)", test_command_binary_output),
        ("3 chained commands in one tick", test_command_chained_3),
        ("Command inside foreach", test_command_with_foreach),
        ("Hang (skip)", test_command_that_hangs),
        ("Empty profile field", test_command_missing_profile),
        ("Write + read file", test_command_writes_file),
        ("Undefined variable", test_command_undefined_variable),
    ]

    for name, test in tests:
        print(f"\n--- {name} ---")
        try:
            test()
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
