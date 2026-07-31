"""
Explicit edges tests — Edge dataclass with conditional routing.

Tests the type="edges" feature where edges are declared explicitly
in the JSON template instead of implicit depends_on + condition.

Run: python3 test_explicit_edges.py
"""
import sys
import sqlite3
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow, Edge
from workflow_engine.test_engine import FakeWorld, count_cards


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Basic explicit edges — A → B → C sequential
# ═══════════════════════════════════════════════════════════════════════════

def test_explicit_edges_basic():
    """Explicit edges: A→B→C sequential pipeline."""
    world = FakeWorld()
    world.add_template({
        "id": "explicit-basic",
        "name": "Explicit Basic",
        "nodes": [
            {"id": "a", "profile": "developer", "skill": "developer-loop",
             "body_template": "Node A"},
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Node B"},
            {"id": "c", "profile": "qa", "skill": "live-testing",
             "body_template": "Node C"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
        ],
    })

    world.start("explicit-basic")
    world.tick()
    assert count_cards(world.board_db) == 1, "Should dispatch node A only"

    # Complete A → B should dispatch
    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={"status": "done"})

    world.tick()
    assert count_cards(world.board_db) == 2, "Should dispatch B after A done"

    world.cleanup()
    print("OK: test_explicit_edges_basic")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Conditional edges — check → (PASS: ship | FAIL: fix)
# ═══════════════════════════════════════════════════════════════════════════

def test_explicit_edges_conditional():
    """Conditional edges route based on check node output."""
    world = FakeWorld()
    world.add_template({
        "id": "conditional-edges",
        "name": "Conditional Edges",
        "nodes": [
            {"id": "check", "profile": "qa", "skill": "live-testing",
             "body_template": "Check it"},
            {"id": "ship", "profile": "developer", "skill": "developer-loop",
             "body_template": "Ship it"},
            {"id": "fix", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Fix it"},
        ],
        "edges": [
            {"from": "check", "to": "ship", "condition": "${nodes.check.output.verdict} == 'PASS'"},
            {"from": "check", "to": "fix", "condition": "${nodes.check.output.verdict} == 'FAIL'"},
        ],
    })

    # PASS path
    world.start("conditional-edges")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    check_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(check_card, metadata={"verdict": "PASS"})

    actions = world.tick()
    assert any("DISPATCHED" in a and "ship" in a for a in actions), \
        f"PASS should dispatch ship, got: {actions}"
    assert any("SKIPPED" in a and "fix" in a for a in actions), \
        f"PASS should skip fix, got: {actions}"

    world.cleanup()

    # FAIL path
    world2 = FakeWorld()
    world2.add_template({
        "id": "conditional-edges",
        "name": "Conditional Edges",
        "nodes": [
            {"id": "check", "profile": "qa", "skill": "live-testing",
             "body_template": "Check it"},
            {"id": "ship", "profile": "developer", "skill": "developer-loop",
             "body_template": "Ship it"},
            {"id": "fix", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Fix it"},
        ],
        "edges": [
            {"from": "check", "to": "ship", "condition": "${nodes.check.output.verdict} == 'PASS'"},
            {"from": "check", "to": "fix", "condition": "${nodes.check.output.verdict} == 'FAIL'"},
        ],
    })

    world2.start("conditional-edges")
    world2.tick()
    conn = sqlite3.connect(str(world2.board_db))
    check_card2 = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world2.complete_card(check_card2, metadata={"verdict": "FAIL"})

    actions = world2.tick()
    assert any("DISPATCHED" in a and "fix" in a for a in actions), \
        f"FAIL should dispatch fix, got: {actions}"
    assert any("SKIPPED" in a and "ship" in a for a in actions), \
        f"FAIL should skip ship, got: {actions}"

    world2.cleanup()
    print("OK: test_explicit_edges_conditional")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Explicit edges with fan-out — one node → two parallel
# ═══════════════════════════════════════════════════════════════════════════

def test_explicit_edges_fanout():
    """Fan-out: one parent → two children via explicit edges (no condition)."""
    world = FakeWorld()
    world.add_template({
        "id": "fanout",
        "name": "Fan Out",
        "nodes": [
            {"id": "parent", "profile": "qa", "skill": "live-testing",
             "body_template": "Parent"},
            {"id": "child_a", "profile": "developer", "skill": "developer-loop",
             "body_template": "Child A"},
            {"id": "child_b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Child B"},
        ],
        "edges": [
            {"from": "parent", "to": "child_a"},
            {"from": "parent", "to": "child_b"},
        ],
    })

    world.start("fanout")
    world.tick()
    assert count_cards(world.board_db) == 1

    conn = sqlite3.connect(str(world.board_db))
    p_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(p_card, metadata={})

    actions = world.tick()
    assert count_cards(world.board_db) == 3, f"Expected 3 cards (1 parent + 2 children), got {count_cards(world.board_db)}"
    assert any("DISPATCHED" in a and "child_a" in a for a in actions), f"child_a should dispatch: {actions}"
    assert any("DISPATCHED" in a and "child_b" in a for a in actions), f"child_b should dispatch: {actions}"

    world.cleanup()
    print("OK: test_explicit_edges_fanout")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Backwards compatibility — implicit depends_on still works when no edges
# ═══════════════════════════════════════════════════════════════════════════

def test_implicit_still_works():
    """When no explicit edges, implicit depends_on should still work."""
    world = FakeWorld()
    world.add_template({
        "id": "implicit",
        "name": "Implicit",
        "nodes": [
            {"id": "a", "profile": "developer", "skill": "developer-loop",
             "body_template": "A"},
            {"id": "b", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "B", "depends_on": ["a"]},
        ],
    })

    world.start("implicit")
    world.tick()
    assert count_cards(world.board_db) == 1

    conn = sqlite3.connect(str(world.board_db))
    a_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    conn.close()
    world.complete_card(a_card, metadata={})

    world.tick()
    assert count_cards(world.board_db) == 2

    world.cleanup()
    print("OK: test_implicit_still_works")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Edge parsing in from_dict
# ═══════════════════════════════════════════════════════════════════════════

def test_edge_parsing():
    """Edges should be parsed from JSON template dict."""
    wf = Workflow.from_dict({
        "id": "test",
        "name": "Test",
        "nodes": [
            {"id": "a", "profile": "qa"},
            {"id": "b", "profile": "qa"},
        ],
        "edges": [
            {"from": "a", "to": "b", "condition": "${nodes.a.output.ok} == 'yes'"},
            {"from": "a", "to": "b"},  # no condition
        ],
    })
    assert len(wf.edges) == 2
    assert wf.edges[0].from_node == "a"
    assert wf.edges[0].to_node == "b"
    assert wf.edges[0].condition is not None
    assert wf.edges[1].condition is None
    print("OK: test_edge_parsing")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_explicit_edges_basic,
        test_explicit_edges_conditional,
        test_explicit_edges_fanout,
        test_implicit_still_works,
        test_edge_parsing,
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
