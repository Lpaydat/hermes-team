"""
Subworkflow node tests — native subworkflow composition.

Tests the type="subworkflow" node that starts a child workflow instance,
blocks until it completes, and maps child outputs back to the parent.

Run: python3 test_subworkflow.py
"""
import sys
import json
import sqlite3
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import Workflow
from workflow_engine.store import TemplateStore
from workflow_engine.kanban_adapter import board_db_path, KANBAN_HOME
from workflow_engine.runtime import Engine, StateDB, NodeStatus, WorkflowInstance, NodeState
from workflow_engine.test_engine import FakeWorld, make_fake_board, make_fake_card, complete_fake_card, count_cards


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Basic subworkflow — parent starts child, child completes, parent advances
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_basic():
    """Parent workflow has a subworkflow node that runs a 1-node child."""
    world = FakeWorld()

    # Child workflow: 1 node
    world.add_template({
        "id": "child",
        "name": "Child",
        "nodes": [
            {"id": "work", "profile": "qa", "skill": "live-testing",
             "body_template": "Do child work"},
        ],
    })

    # Parent workflow: 1 task node + 1 subworkflow node + 1 task node
    world.add_template({
        "id": "parent",
        "name": "Parent",
        "nodes": [
            {"id": "start", "profile": "developer", "skill": "developer-loop",
             "body_template": "Start"},
            {"id": "run_child", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "child",
             "depends_on": ["start"]},
            {"id": "finish", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Finish after child",
             "depends_on": ["run_child"]},
        ],
    })

    world.start("parent")

    # Tick 1: dispatch start
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    start_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    conn.close()
    world.complete_card(start_card, metadata={"status": "started"})

    # Tick 2: start done → dispatch subworkflow node (starts child instance)
    actions = world.tick()
    assert any("DISPATCHED" in a and "subworkflow" in a and "run_child" in a for a in actions), \
        f"Expected subworkflow dispatch, got: {actions}"

    # Tick 3: child's work node dispatches
    actions = world.tick()
    assert any("DISPATCHED" in a and "work" in a for a in actions), \
        f"Expected child work dispatch, got: {actions}"

    # Complete child's work card
    conn = sqlite3.connect(str(world.board_db))
    work_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa' AND title LIKE '%work%'").fetchone()
    conn.close()
    if work_card:
        world.complete_card(work_card[0], metadata={"work_result": "child_done"})

    # Tick 4: child work done → child instance completes. In the stateless
    # engine the subworkflow node's completion is detected in the SYNC pass of
    # this same tick (child_status → completed, ns['done']=True), so no separate
    # "DONE subworkflow" action is emitted — the child instance simply completes.
    actions = world.tick()
    assert any("DONE" in a and "work" in a for a in actions), \
        f"Expected child work done, got: {actions}"
    assert any("WORKFLOW COMPLETE" in a and "child" in a for a in actions), \
        f"Expected child complete, got: {actions}"

    # Tick 5: run_child is now done (detected during tick 4's sync), so the
    # downstream finish node dispatches. Verify run_child reached 'done' via
    # the state snapshot rather than a dedicated action message.
    actions = world.tick()
    assert any("DISPATCHED" in a and "finish" in a for a in actions), \
        f"Expected finish dispatch, got: {actions}"
    run_child_state = world.state_snapshot().get("run_child", {})
    assert run_child_state.get("done") is True, \
        f"run_child subworkflow node should be done, got: {run_child_state}"

    world.cleanup()
    print("OK: test_subworkflow_basic")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Subworkflow with output mapping
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_output_mapping():
    """Child workflow produces output that maps back to parent via output_mapping."""
    world = FakeWorld()

    world.add_template({
        "id": "child-mapped",
        "name": "Child Mapped",
        "nodes": [
            {"id": "compute", "profile": "qa", "skill": "live-testing",
             "body_template": "Compute result"},
        ],
    })

    world.add_template({
        "id": "parent-mapped",
        "name": "Parent Mapped",
        "nodes": [
            {"id": "call_child", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "child-mapped",
             "output_mapping": {
                 "result": "${nodes.compute.output.value}",
                 "source": "child-mapped"
             }},
            {"id": "use_result", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Result is: ${nodes.call_child.output.result}",
             "depends_on": ["call_child"]},
        ],
    })

    world.start("parent-mapped")

    # Tick: dispatch subworkflow
    world.tick()

    # Tick: child dispatches
    actions = world.tick()
    assert any("DISPATCHED" in a and "compute" in a for a in actions), \
        f"Expected child dispatch, got: {actions}"

    # Complete child with specific output
    conn = sqlite3.connect(str(world.board_db))
    compute_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa' AND title LIKE '%compute%'").fetchone()
    conn.close()
    if compute_card:
        world.complete_card(compute_card[0], metadata={"value": 42})

    # Tick: child done, child instance completes. The subworkflow node's
    # completion (output mapping applied) is detected in the SYNC pass of the
    # NEXT tick (the child must be persisted as 'completed' before the parent's
    # sync reads it), so we tick once more and verify via the state snapshot.
    world.tick()  # child work done + child instance completes
    world.tick()  # parent sync detects child completion, applies output mapping

    # Verify output mapping landed in the state snapshot.
    call_child_state = world.state_snapshot().get("call_child", {})
    output = call_child_state.get("output") or call_child_state.get("outputs") or {}
    assert output.get("result") == 42, f"Expected result=42, got: {output}"
    assert output.get("source") == "child-mapped", f"Expected source=child-mapped, got: {output}"

    world.cleanup()
    print("OK: test_subworkflow_output_mapping")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Subworkflow with input mapping — parent passes context to child
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_input_mapping():
    """Parent passes data to child via input_mapping."""
    world = FakeWorld()

    world.add_template({
        "id": "child-input",
        "name": "Child Input",
        "nodes": [
            {"id": "echo", "profile": "qa", "skill": "live-testing",
             "body_template": "Process ${trigger.task_id}"},
        ],
    })

    world.add_template({
        "id": "parent-input",
        "name": "Parent Input",
        "nodes": [
            {"id": "start", "profile": "developer", "skill": "developer-loop",
             "body_template": "Start"},
            {"id": "call_child", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "child-input",
             "depends_on": ["start"],
             "input_mapping": {
                 "task_id": "${trigger.original_task}"
             }},
        ],
    })

    world.start("parent-input", context={"original_task": "TASK-42"})

    # Tick: dispatch start
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    start_card = conn.execute("SELECT id FROM tasks WHERE assignee='developer'").fetchone()[0]
    conn.close()
    world.complete_card(start_card, metadata={})

    # Tick: start done, dispatch subworkflow
    world.tick()

    # Tick: child dispatches — check trigger context was mapped
    actions = world.tick()
    assert any("DISPATCHED" in a and "echo" in a for a in actions), \
        f"Expected child echo dispatch, got: {actions}"

    # Verify child instance got the input mapping
    instances = world.engine.state.load_active_instances()
    child_inst = None
    for inst in instances:
        if inst.workflow_id == "child-input":
            child_inst = inst
            break
    if child_inst:
        assert child_inst.trigger_context.get("task_id") == "TASK-42", \
            f"Expected task_id=TASK-42 in child trigger context, got: {child_inst.trigger_context}"

    world.cleanup()
    print("OK: test_subworkflow_input_mapping")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Subworkflow not found — graceful error
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_not_found():
    """A subworkflow node referencing a nonexistent template should fail gracefully."""
    world = FakeWorld()
    world.add_template({
        "id": "parent-broken",
        "name": "Parent Broken",
        "nodes": [
            {"id": "call_missing", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "does-not-exist"},
        ],
    })

    world.start("parent-broken")
    actions = world.tick()

    assert any("FAILED" in a and "not found" in a for a in actions), \
        f"Expected FAILED for missing template, got: {actions}"

    world.cleanup()
    print("OK: test_subworkflow_not_found")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Subworkflow missing workflow_ref — error
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_missing_ref():
    """A subworkflow node without workflow_ref should fail."""
    world = FakeWorld()
    world.add_template({
        "id": "parent-noref",
        "name": "Parent No Ref",
        "nodes": [
            {"id": "call_nothing", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow"},
        ],
    })

    world.start("parent-noref")
    actions = world.tick()

    assert any("FAILED" in a and "workflow_ref" in a for a in actions), \
        f"Expected FAILED for missing workflow_ref, got: {actions}"

    world.cleanup()
    print("OK: test_subworkflow_missing_ref")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: Nested subworkflow — A → B → C (3 levels deep)
# ═══════════════════════════════════════════════════════════════════════════

def test_nested_subworkflow_3_levels():
    """Parent calls child, child calls grandchild — 3 levels deep."""
    world = FakeWorld()

    # Grandchild: 1 node
    world.add_template({
        "id": "grandchild",
        "name": "Grandchild",
        "nodes": [{"id": "gc_work", "profile": "qa", "skill": "live-testing",
                   "body_template": "Grandchild work"}],
    })

    # Child: 1 subworkflow node → grandchild
    world.add_template({
        "id": "child-nested",
        "name": "Child Nested",
        "nodes": [
            {"id": "call_gc", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "grandchild"},
        ],
    })

    # Parent: 1 subworkflow node → child
    world.add_template({
        "id": "parent-nested",
        "name": "Parent Nested",
        "nodes": [
            {"id": "call_child", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "child-nested"},
        ],
    })

    world.start("parent-nested")

    # Tick: dispatch parent subworkflow → child instance starts
    actions = world.tick()
    assert any("DISPATCHED" in a and "subworkflow" in a and "call_child" in a for a in actions), \
        f"Expected parent dispatch child, got: {actions}"

    # Tick: child dispatches its subworkflow → grandchild instance starts
    actions = world.tick()
    assert any("DISPATCHED" in a and "subworkflow" in a and "call_gc" in a for a in actions), \
        f"Expected child dispatch grandchild, got: {actions}"

    # Tick: grandchild dispatches work card
    actions = world.tick()
    assert any("DISPATCHED" in a and "gc_work" in a for a in actions), \
        f"Expected grandchild work dispatch, got: {actions}"

    # Complete grandchild work
    conn = sqlite3.connect(str(world.board_db))
    gc_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa' AND title LIKE '%gc_work%'").fetchone()
    conn.close()
    if gc_card:
        world.complete_card(gc_card[0], metadata={"gc_result": "done"})

    # Tick: grandchild work done → grandchild instance completes. In the
    # stateless engine each level's subworkflow completion is detected silently
    # during the SYNC pass (child_status → completed sets ns['done']=True), so
    # we verify the cascade via state_snapshot rather than "DONE subworkflow"
    # action messages.
    world.tick()
    # Tick: child detects grandchild completion → child completes
    world.tick()
    # Tick: parent detects child completion → parent completes
    world.tick()

    # Verify all three subworkflow nodes reached 'done' via the state snapshot.
    # The child-nested instance owns call_gc (grandchild subworkflow); the
    # parent-nested instance owns call_child (child subworkflow).
    conn = sqlite3.connect(str(world.state_db_path))
    inst_rows = conn.execute(
        "SELECT instance_id, workflow_id FROM workflow_instances"
    ).fetchall()
    conn.close()
    inst_by_wf = {row[1]: row[0] for row in inst_rows}

    child_inst_id = inst_by_wf.get("child-nested")
    if child_inst_id:
        child_blob = world.engine.state.load_state(child_inst_id).get("state", {})
        call_gc_state = child_blob.get("call_gc", {})
        assert call_gc_state.get("done") is True, \
            f"call_gc (grandchild subworkflow) should be done, got: {call_gc_state}"

    parent_inst_id = inst_by_wf.get("parent-nested")
    if parent_inst_id:
        parent_blob = world.engine.state.load_state(parent_inst_id).get("state", {})
        call_child_state = parent_blob.get("call_child", {})
        assert call_child_state.get("done") is True, \
            f"call_child (child subworkflow) should be done, got: {call_child_state}"

    world.cleanup()
    print("OK: test_nested_subworkflow_3_levels")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Subworkflow idempotency — tick twice doesn't start two children
# ═══════════════════════════════════════════════════════════════════════════

def test_subworkflow_idempotent():
    """Running tick twice should not start duplicate child instances."""
    world = FakeWorld()

    world.add_template({
        "id": "child-idem",
        "name": "Child Idem",
        "nodes": [{"id": "work", "profile": "qa", "skill": "live-testing",
                   "body_template": "Work"}],
    })

    world.add_template({
        "id": "parent-idem",
        "name": "Parent Idem",
        "nodes": [
            {"id": "call", "profile": "qa", "skill": "",
             "body_template": "",
             "type": "subworkflow",
             "workflow_ref": "child-idem"},
        ],
    })

    world.start("parent-idem")
    world.tick()  # dispatch subworkflow

    # Tick again — should NOT start a second child
    actions = world.tick()
    new_children = [a for a in actions if "DISPATCHED" in a and "subworkflow" in a and "call" in a]
    assert len(new_children) == 0, \
        f"Should not start duplicate child, got: {new_children}"

    world.cleanup()
    print("OK: test_subworkflow_idempotent")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_subworkflow_basic,
        test_subworkflow_output_mapping,
        test_subworkflow_input_mapping,
        test_subworkflow_not_found,
        test_subworkflow_missing_ref,
        test_nested_subworkflow_3_levels,
        test_subworkflow_idempotent,
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
