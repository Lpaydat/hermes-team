"""End-to-end loop tests for the stateless workflow engine.

Tests the core feature the rewrite was built for: back-edge iteration.
A dev-verifier loop where FAIL resets the build node and creates a fresh card.
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from test_engine import FakeWorld, make_fake_board, make_fake_card, complete_fake_card, count_cards
from workflow_engine.runtime import Engine, StateDB, NodeStatus


def _make_loop_world():
    """Create a test world with a cyclic dev-verifier loop template.

    Graph:
      build → review
      review → ship  (condition: verdict == 'PASS')
      review → build (condition: verdict == 'FAIL', is_back_edge=True)

    The review→build edge is a back-edge (cycle). When review returns FAIL,
    build resets: iteration bumps, old card archived, fresh card dispatched.
    """
    world = FakeWorld()
    world.add_template({
        "id": "dev-loop",
        "name": "Dev-Verifier Loop",
        "nodes": [
            {"id": "build", "profile": "developer", "skill": "developer-loop",
             "body_template": "Build feature ${nodes.build.iteration}"},
            {"id": "review", "profile": "verifier", "skill": "adversarial-review",
             "body_template": "Review build iter ${nodes.build.iteration}",
             "depends_on": ["build"]},
            {"id": "ship", "profile": "qa", "skill": "live-testing",
             "body_template": "Ship it",
             "depends_on": ["review"],
             "condition": "${nodes.review.output.verdict} == 'PASS'"},
        ],
        "edges": [
            {"from": "build", "to": "review"},
            {"from": "review", "to": "ship",
             "condition": "${nodes.review.output.verdict} == 'PASS'"},
            {"from": "review", "to": "build",
             "condition": "${nodes.review.output.verdict} == 'FAIL'",
             "max_iterations": 5},
        ],
    })
    return world


def test_loop_fail_then_pass():
    """FAIL on iter 0 → build resets to iter 1 → review PASS → ship.

    The core loop scenario. Two iterations, then completion.
    """
    world = _make_loop_world()
    try:
        world.start("dev-loop")
        actions = world.tick()
        assert any("DISPATCHED" in a and "build" in a for a in actions), \
            f"Iter 0: build should dispatch, got: {actions}"

        # Complete build card (iter 0)
        conn = sqlite3.connect(str(world.board_db))
        build_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='developer' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(build_card, metadata={"commit": "abc123"})

        # Tick: build done, review dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "review" in a for a in actions), \
            f"Review should dispatch after build done, got: {actions}"

        # Complete review with FAIL
        conn = sqlite3.connect(str(world.board_db))
        review_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='verifier' AND status='todo'"
            " ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(review_card, metadata={"verdict": "FAIL"})

        # Tick: review done with FAIL → back-edge fires → build resets → build re-dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "build" in a for a in actions), \
            f"Iter 1: build should re-dispatch after FAIL reset, got: {actions}"

        # Verify iteration counter bumped
        nodes = world.state_snapshot()
        build_state = nodes.get("build", {})
        assert build_state.get("iteration", 0) >= 1, \
            f"Build iteration should be >= 1 after reset, got: {build_state}"

        # Verify the old card is archived in iterations[]
        iterations = build_state.get("iterations", [])
        assert len(iterations) >= 1, \
            f"Should have archived iter 0, got: {iterations}"
        assert iterations[0].get("card_id"), \
            f"Archived iter 0 should have card_id, got: {iterations[0]}"

        # Complete build card (iter 1) — fresh card, different from iter 0
        conn = sqlite3.connect(str(world.board_db))
        build_card_1 = conn.execute(
            "SELECT id FROM tasks WHERE assignee='developer' AND status='todo'"
            " ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        assert build_card_1 != build_card, \
            "Iter 1 build card should be different from iter 0"
        world.complete_card(build_card_1, metadata={"commit": "def456"})

        # Tick: build done, review dispatches
        actions = world.tick()
        assert any("DISPATCHED" in a and "review" in a for a in actions), \
            f"Iter 1: review should dispatch, got: {actions}"

        # Complete review with PASS
        conn = sqlite3.connect(str(world.board_db))
        review_card_1 = conn.execute(
            "SELECT id FROM tasks WHERE assignee='verifier' AND status='todo'"
            " ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(review_card_1, metadata={"verdict": "PASS"})

        # Tick: review PASS → ship dispatches → workflow completes
        actions = world.tick()
        assert any("DISPATCHED" in a and "ship" in a for a in actions), \
            f"Ship should dispatch on PASS, got: {actions}"

        # Complete ship
        conn = sqlite3.connect(str(world.board_db))
        ship_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='qa' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(ship_card, metadata={"result": "shipped"})

        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Workflow should complete after ship, got: {actions}"
    finally:
        world.cleanup()
    print("OK: test_loop_fail_then_pass")


def test_loop_iteration_cap():
    """After max_iterations FAILs, the back-edge stops firing.

    build iter 0 FAIL → iter 1 FAIL → iter 2 FAIL → cap reached (max=5)
    → build stays at last iteration, no more resets.
    """
    world = _make_loop_world()
    try:
        world.start("dev-loop")

        for expected_iter in range(3):
            # Dispatch build, complete it
            world.tick()
            conn = sqlite3.connect(str(world.board_db))
            build_card = conn.execute(
                "SELECT id FROM tasks WHERE assignee='developer' AND status='todo'"
                " ORDER BY created_at DESC LIMIT 1"
            ).fetchone()[0]
            conn.close()
            world.complete_card(build_card, metadata={"commit": f"iter{expected_iter}"})

            # Review dispatches
            world.tick()
            conn = sqlite3.connect(str(world.board_db))
            review_card = conn.execute(
                "SELECT id FROM tasks WHERE assignee='verifier' AND status='todo'"
                " ORDER BY created_at DESC LIMIT 1"
            ).fetchone()[0]
            conn.close()
            world.complete_card(review_card, metadata={"verdict": "FAIL"})

            # Tick: reset fires, build re-dispatches
            world.tick()

        # After 3 FAILs, iteration should be 3
        nodes = world.state_snapshot()
        build_state = nodes.get("build", {})
        assert build_state.get("iteration", 0) == 3, \
            f"After 3 FAIL resets, iteration should be 3, got: {build_state.get('iteration')}"

        # Iterations[] should have 3 archived entries
        iterations = build_state.get("iterations", [])
        assert len(iterations) == 3, \
            f"Should have 3 archived iterations, got: {len(iterations)}"
    finally:
        world.cleanup()
    print("OK: test_loop_iteration_cap")


def test_loop_output_preserved_during_reset_gap():
    """During the reset gap (between reset and re-dispatch), downstream nodes
    see the last-known-good output, not empty.

    This prevents crashes in templates that reference ${nodes.build.output.*}
    in the reset tick.
    """
    world = _make_loop_world()
    try:
        world.start("dev-loop")
        world.tick()

        # Complete build iter 0
        conn = sqlite3.connect(str(world.board_db))
        build_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='developer' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(build_card, metadata={"commit": "abc123"})

        # Complete review FAIL
        world.tick()
        conn = sqlite3.connect(str(world.board_db))
        review_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='verifier' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(review_card, metadata={"verdict": "FAIL"})

        # Tick: reset fires
        world.tick()

        # Check that build's output is preserved (not wiped)
        nodes = world.state_snapshot()
        build_output = nodes.get("build", {}).get("output", {})
        assert build_output.get("commit") == "abc123", \
            f"Output should be preserved during reset gap, got: {build_output}"
    finally:
        world.cleanup()
    print("OK: test_loop_output_preserved_during_reset_gap")


def test_loop_pass_on_first_try():
    """PASS on first try — no reset, no iteration, ship directly."""
    world = _make_loop_world()
    try:
        world.start("dev-loop")
        world.tick()

        # Complete build
        conn = sqlite3.connect(str(world.board_db))
        build_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='developer' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(build_card, metadata={"commit": "abc"})

        # Review dispatches
        world.tick()
        conn = sqlite3.connect(str(world.board_db))
        review_card = conn.execute(
            "SELECT id FROM tasks WHERE assignee='verifier' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(review_card, metadata={"verdict": "PASS"})

        # Tick: PASS → ship dispatches (no reset)
        actions = world.tick()
        assert any("DISPATCHED" in a and "ship" in a for a in actions), \
            f"Ship should dispatch on PASS, got: {actions}"
        assert not any("DISPATCHED" in a and "build" in a for a in actions), \
            f"Build should NOT re-dispatch on PASS, got: {actions}"

        # Iteration should still be 0
        nodes = world.state_snapshot()
        assert nodes.get("build", {}).get("iteration", 0) == 0, \
            f"Iteration should be 0 on first-try PASS, got: {nodes.get('build', {}).get('iteration')}"
    finally:
        world.cleanup()
    print("OK: test_loop_pass_on_first_try")


if __name__ == "__main__":
    tests = [
        test_loop_pass_on_first_try,
        test_loop_fail_then_pass,
        test_loop_iteration_cap,
        test_loop_output_preserved_during_reset_gap,
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
    sys.exit(0 if failed == 0 else 1)
