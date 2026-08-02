"""
Foreach subworkflow tests — parallel pipeline, no barriers.

Tests the foreach + subworkflow node type that spawns independent
workflow instances per item. Each item runs grill→build→handoff
independently — no barrier waiting for all items.

Run: python3 test_foreach_subworkflow.py
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
# TEST 1: Basic foreach subworkflow — spawns one instance per item
# ═══════════════════════════════════════════════════════════════════════════

def test_basic_foreach_subworkflow():
    """Foreach subworkflow spawns one child instance per item."""
    world = FakeWorld()
    # Parent template with foreach subworkflow
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "", "body_template": ""},
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "spawn"}],
    })
    # Child template
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "step1", "profile": "builder", "skill": "",
             "body_template": "Step 1 for ${trigger.slug}"},
        ],
    })

    world.start("parent")
    world.tick()  # dispatch src

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"items": [
        {"slug": "idea-a", "name": "Idea A", "score": 10},
        {"slug": "idea-b", "name": "Idea B", "score": 20},
    ]})

    actions = world.tick()  # src done, foreach subworkflow dispatches
    world.tick()  # child instances dispatch their cards

    # Should have spawned 2 child instances
    assert any("DISPATCHED" in a and "spawn" in a and "2 instances" in a for a in actions), \
        f"Expected 2 instances spawned: {actions}"

    # Each child should have dispatched its step1 card
    conn = sqlite3.connect(str(world.board_db))
    builder_cards = conn.execute("SELECT title FROM tasks WHERE assignee='builder'").fetchall()
    conn.close()
    assert len(builder_cards) == 2, f"Expected 2 builder cards, got {len(builder_cards)}"

    # Check instance count
    conn = sqlite3.connect(str(world.state_db_path))
    instance_count = conn.execute("SELECT COUNT(*) FROM workflow_instances").fetchone()[0]
    conn.close()
    assert instance_count == 3, f"Expected 3 instances (1 parent + 2 children), got {instance_count}"

    world.cleanup()
    print("OK: test_basic_foreach_subworkflow")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Independent progress — child A completes while child B still running
# ═══════════════════════════════════════════════════════════════════════════

def test_independent_progress():
    """Child A can complete independently while child B is still running."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "", "body_template": ""},
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "spawn"}],
    })
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "step1", "profile": "builder", "skill": "",
             "body_template": "Step 1 for ${trigger.slug}"},
            {"id": "step2", "profile": "verifier", "skill": "",
             "body_template": "Step 2 for ${trigger.slug}",
             "depends_on": ["step1"]},
        ],
        "edges": [{"from": "step1", "to": "step2"}],
    })

    world.start("parent")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"items": [
        {"slug": "a", "name": "A", "score": 10},
        {"slug": "b", "name": "B", "score": 20},
    ]})

    world.tick()  # spawn 2 children
    world.tick()  # child instances dispatch their step1 cards

    # Now we have 2 builder cards (step1 for each child)
    conn = sqlite3.connect(str(world.board_db))
    builder_cards = conn.execute("SELECT id, title FROM tasks WHERE assignee='builder' ORDER BY id").fetchall()
    conn.close()
    assert len(builder_cards) == 2

    # Complete ONLY child A's step1 — child A's step2 should dispatch
    # while child B's step1 is still running
    world.complete_card(builder_cards[0][0], metadata={"result": "done"})

    actions = world.tick()

    # Child A's step2 should have dispatched (verifier card)
    assert any("step2" in a and "DISPATCHED" in a for a in actions), \
        f"Child A's step2 should dispatch independently: {actions}"

    # Child B's step1 should still be running — no step2 for B yet
    conn = sqlite3.connect(str(world.board_db))
    verifier_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE assignee='verifier'").fetchone()[0]
    conn.close()
    assert verifier_count == 1, f"Only 1 verifier card (child A's step2), got {verifier_count}"

    world.cleanup()
    print("OK: test_independent_progress")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Parent completes when all children complete
# ═══════════════════════════════════════════════════════════════════════════

def test_parent_completes_when_all_children_done():
    """Parent's spawn node completes only when ALL children complete."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${trigger.items}"},
        ],
    })
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "work", "profile": "builder", "skill": "",
             "body_template": "Work for ${trigger.slug}"},
        ],
    })

    world.start("parent", context={"items": [
        {"slug": "a", "name": "A", "score": 10},
        {"slug": "b", "name": "B", "score": 20},
    ]})
    world.tick()  # spawn children
    world.tick()  # child instances dispatch their work cards

    # Complete child A only — parent should NOT complete yet
    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute("SELECT id FROM tasks WHERE assignee='builder' ORDER BY id").fetchall()
    conn.close()
    assert len(cards) == 2

    world.complete_card(cards[0][0])
    actions = world.tick()

    # Parent spawn node should still be DISPATCHED (child B not done)
    assert not any("DONE" in a and "spawn" in a for a in actions), \
        f"Parent should not complete while child B running: {actions}"

    # Now complete child B
    world.complete_card(cards[1][0])
    world.tick()  # child B's work completes
    actions = world.tick()  # parent detects all children done, completes

    # In the stateless engine the spawn node's completion is detected silently
    # in the SYNC pass (all child instances → completed sets ns['done']=True),
    # so verify spawn reached 'done' via the state snapshot rather than a
    # dedicated "DONE spawn" action. The parent instance may already be
    # completed by this tick, so read its blob directly by workflow_id.
    conn = sqlite3.connect(str(world.state_db_path))
    parent_row = conn.execute(
        "SELECT instance_id FROM workflow_instances WHERE workflow_id = 'parent' "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    parent_snapshot = {}
    if parent_row:
        parent_snapshot = world.engine.state.load_state(parent_row[0]).get("state", {})
    spawn_state = parent_snapshot.get("spawn", {})
    assert spawn_state.get("done") is True, \
        f"Parent spawn node should be done after all children complete, got: {spawn_state}"
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Parent workflow should complete: {actions}"

    world.cleanup()
    print("OK: test_parent_completes_when_all_children_done")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Child context gets item fields
# ═══════════════════════════════════════════════════════════════════════════

def test_child_context_has_item_fields():
    """Child workflow instances receive item dict fields as trigger context."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${trigger.items}"},
        ],
    })
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "work", "profile": "builder", "skill": "",
             "body_template": "Slug: ${trigger.slug} Score: ${trigger.score}"},
        ],
    })

    world.start("parent", context={"items": [
        {"slug": "test-idea", "name": "Test Idea", "score": 18},
    ]})
    world.tick()  # spawn child
    world.tick()  # child dispatches work card

    conn = sqlite3.connect(str(world.board_db))
    card = conn.execute("SELECT body FROM tasks WHERE assignee='builder'").fetchone()
    conn.close()
    assert card, "No builder card created"
    body = card[0]
    assert "test-idea" in body, f"Slug should be in body: {body}"
    assert "18" in body, f"Score should be in body: {body}"

    world.cleanup()
    print("OK: test_child_context_has_item_fields")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Empty list — parent completes immediately
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_list():
    """Foreach subworkflow with empty list completes immediately."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${trigger.items}"},
        ],
    })
    world.add_template({
        "id": "child", "name": "Child",
        "nodes": [{"id": "work", "profile": "builder", "skill": "", "body_template": "Work"}],
    })

    world.start("parent", context={"items": []})
    actions = world.tick()

    # Empty list — spawn node marks DONE and workflow completes
    assert any("WORKFLOW COMPLETE" in a for a in actions), \
        f"Empty foreach should let workflow complete: {actions}"

    world.cleanup()
    print("OK: test_empty_list")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: String items (not dicts)
# ═══════════════════════════════════════════════════════════════════════════

def test_string_items():
    """Foreach subworkflow works with string items (not dicts)."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "child", "foreach": "${trigger.items}"},
        ],
    })
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "work", "profile": "builder", "skill": "",
             "body_template": "Process: ${trigger.item}"},
        ],
    })

    world.start("parent", context={"items": ["alpha", "beta", "gamma"]})
    world.tick()  # spawn children
    world.tick()  # children dispatch cards

    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute("SELECT body FROM tasks WHERE assignee='builder' ORDER BY body").fetchall()
    conn.close()
    assert len(cards) == 3, f"Expected 3 cards, got {len(cards)}"
    bodies = [c[0] for c in cards]
    assert any("alpha" in b for b in bodies), f"Missing alpha: {bodies}"
    assert any("beta" in b for b in bodies)
    assert any("gamma" in b for b in bodies)

    world.cleanup()
    print("OK: test_string_items")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: 3-step child pipeline — independent flow
# ═══════════════════════════════════════════════════════════════════════════

def test_three_step_child_pipeline():
    """Child with grill→build→handoff runs independently per item."""
    world = FakeWorld()
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "spawn", "profile": "builder", "skill": "",
             "body_template": "", "type": "subworkflow",
             "workflow_ref": "pipeline", "foreach": "${trigger.items}"},
        ],
    })
    world.add_template({
        "id": "pipeline",
        "name": "Pipeline",
        "nodes": [
            {"id": "grill", "profile": "builder", "skill": "",
             "body_template": "Grill: ${trigger.slug}"},
            {"id": "build", "profile": "builder", "skill": "",
             "body_template": "Build: ${trigger.slug}",
             "depends_on": ["grill"]},
            {"id": "handoff", "profile": "builder", "skill": "",
             "body_template": "Handoff: ${trigger.slug}",
             "depends_on": ["build"]},
        ],
        "edges": [
            {"from": "grill", "to": "build"},
            {"from": "build", "to": "handoff"},
        ],
    })

    world.start("parent", context={"items": [
        {"slug": "a", "name": "A", "score": 10},
        {"slug": "b", "name": "B", "score": 20},
    ]})
    world.tick()  # spawn 2 children
    world.tick()  # children dispatch grill cards

    # Both children dispatch grill cards
    conn = sqlite3.connect(str(world.board_db))
    grill_cards = conn.execute("SELECT id FROM tasks WHERE assignee='builder' AND body LIKE '%Grill:%'").fetchall()
    conn.close()
    assert len(grill_cards) == 2

    # Complete grill A → build A should dispatch (not waiting for grill B)
    world.complete_card(grill_cards[0][0])
    actions = world.tick()

    assert any("build" in a and "DISPATCHED" in a for a in actions), \
        f"Build A should dispatch after grill A completes: {actions}"

    world.cleanup()
    print("OK: test_three_step_child_pipeline")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_basic_foreach_subworkflow,
        test_independent_progress,
        test_parent_completes_when_all_children_done,
        test_child_context_has_item_fields,
        test_empty_list,
        test_string_items,
        test_three_step_child_pipeline,
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
        print("ALL TESTS PASSED")
    else:
        print(f"{failed} TEST(S) FAILED")
    sys.exit(0 if failed == 0 else 1)
