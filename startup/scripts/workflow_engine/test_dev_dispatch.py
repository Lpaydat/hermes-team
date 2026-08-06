"""E2E + edge-case tests for the dev-dispatch workflow template.

Tests against a REAL engine + real board (FakeWorld = real Engine/StateDB,
real SQLite board, real create_card monkey-patch). Covers every edge case:

1. All 5 routing types (bug/research/ops/architecture/default→tech-lead)
2. Trigger filtering (wrong assignee, wrong status, wrong title prefix)
3. Idempotency (trigger doesn't fire twice for same card)
4. No metadata.type → defaults to tech-lead
5. Empty metadata → defaults to tech-lead
6. Multiple spec cards complete simultaneously
7. Spec card that's archived (not done) → no trigger
8. Entry node is synchronous (command) — no card created for it
9. Dead-branch skip: non-matching routes are SKIPPED, not left pending
10. Workflow completes after the routed card completes
11. Output schema validation on route-bug and route-architect
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from test_engine import FakeWorld, count_cards
from workflow_engine.runtime import Engine, StateDB

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dev-dispatch.json"


def _load_template():
    return json.loads(TEMPLATE_PATH.read_text())


def _make_world():
    world = FakeWorld()
    world.add_template(_load_template())
    return world


def _add_spec_card(world, card_id, metadata=None, title="[spec] Test", assignee="product-owner"):
    world.add_card(card_id, assignee=assignee, status="done",
                   completed_at=int(time.time()),
                   metadata=metadata or {}, title=title)


def _get_routed_cards(world, include_po=False):
    """Return list of (assignee, title) for routed cards.

    By default excludes product-owner (the spec card holder). Set include_po=True
    to also see the [decompose] card (route-decompose, which is now a PO card).
    """
    conn = sqlite3.connect(str(world.board_db))
    if include_po:
        cards = conn.execute(
            "SELECT id, assignee, title, status FROM tasks "
            "WHERE id != 'spec1' AND id != 'spec-bug' AND id != 'spec-dev' "
            "ORDER BY created_at"
        ).fetchall()
    else:
        cards = conn.execute(
            "SELECT assignee, title, status FROM tasks "
            "WHERE assignee != 'product-owner' ORDER BY created_at"
        ).fetchall()
    conn.close()
    return cards


def _get_all_cards(world):
    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute(
        "SELECT id, assignee, title, status FROM tasks ORDER BY created_at"
    ).fetchall()
    conn.close()
    return cards


# ═══════════════════════════════════════════════════════════════════════════
# 1. BASIC ROUTING — all 5 types
# ═══════════════════════════════════════════════════════════════════════════

def test_route_bug():
    """metadata.type=bug → debugger card created."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()  # trigger + entry command
        world.tick()  # routing fires
        routed = _get_routed_cards(world)
        assert len(routed) == 1, f"Expected 1 routed card, got {len(routed)}: {routed}"
        assert routed[0][0] == "debugger", f"Expected debugger, got {routed[0][0]}"
    finally:
        world.cleanup()
    print("OK: test_route_bug")


def test_route_research():
    """metadata.type=research → scout card created."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "research"})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world)
        assert len(routed) == 1 and routed[0][0] == "scout", \
            f"Expected scout, got: {routed}"
    finally:
        world.cleanup()
    print("OK: test_route_research")


def test_route_ops():
    """metadata.type=ops → ops card created."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "ops"})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world)
        assert len(routed) == 1 and routed[0][0] == "ops", \
            f"Expected ops, got: {routed}"
    finally:
        world.cleanup()
    print("OK: test_route_ops")


def test_route_architecture():
    """metadata.type=architecture → architect card created."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "architecture"})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world)
        assert len(routed) == 1 and routed[0][0] == "architect", \
            f"Expected architect, got: {routed}"
    finally:
        world.cleanup()
    print("OK: test_route_architecture")


def test_route_tickets():
    """metadata.type=tickets → PO [dispatch] card (parse, don't decompose)."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "tickets"})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world, include_po=True)
        # route-tickets creates a product-owner [dispatch] card
        po_cards = [c for c in routed if c[1] == "product-owner"]
        assert len(po_cards) == 1, \
            f"Expected 1 PO dispatch card, got: {routed}"
        assert "[dispatch]" in po_cards[0][2], \
            f"Expected [dispatch] prefix, got: {po_cards}"
    finally:
        world.cleanup()
    print("OK: test_route_tickets")


def test_route_default_tech_lead():
    """metadata.type=feature (not bug/research/ops/architecture) → PO decompose card."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "feature"})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world, include_po=True)
        # route-decompose is now a product-owner [decompose] card
        po_cards = [c for c in routed if c[1] == "product-owner"]
        assert len(po_cards) == 1, \
            f"Expected 1 PO decompose card, got: {routed}"
        assert "[decompose]" in po_cards[0][2], \
            f"Expected [decompose] prefix, got: {po_cards}"
    finally:
        world.cleanup()
    print("OK: test_route_default_tech_lead")


# ═══════════════════════════════════════════════════════════════════════════
# 2. TRIGGER FILTERING — wrong cards don't trigger
# ═══════════════════════════════════════════════════════════════════════════

def test_wrong_assignee_no_trigger():
    """Card completed by developer (not product-owner) → no workflow starts."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"}, assignee="developer")
        world.tick()
        active = world.engine.state.load_active_instances()
        assert len(active) == 0, f"Should not start workflow for wrong assignee"
        # No engine-created cards (the spec card itself doesn't count)
        engine_cards = [c for c in _get_all_cards(world) if c[0] != "spec1"]
        assert len(engine_cards) == 0, f"No engine cards should be created, got: {engine_cards}"
    finally:
        world.cleanup()
    print("OK: test_wrong_assignee_no_trigger")


def test_wrong_status_no_trigger():
    """Card in 'todo' (not done) → no trigger."""
    world = _make_world()
    try:
        world.add_card("spec1", assignee="product-owner", status="todo",
                       metadata={"type": "bug"}, title="[spec] Test")
        world.tick()
        active = world.engine.state.load_active_instances()
        assert len(active) == 0, f"Should not trigger on non-done card"
    finally:
        world.cleanup()
    print("OK: test_wrong_status_no_trigger")


def test_wrong_title_prefix_no_trigger():
    """Card with title not starting with [spec] → no trigger."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"}, title="Fix bug")
        world.tick()
        active = world.engine.state.load_active_instances()
        assert len(active) == 0, f"Should not trigger without [spec] prefix"
    finally:
        world.cleanup()
    print("OK: test_wrong_title_prefix_no_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# 3. IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════════

def test_idempotent_trigger():
    """Same spec card doesn't trigger twice across multiple ticks."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()  # trigger fires
        world.tick()  # should NOT trigger again
        world.tick()  # should NOT trigger again
        instances = world.engine.state.load_active_instances()
        assert len(instances) == 1, \
            f"Should have 1 instance, got {len(instances)} (trigger fired multiple times)"
    finally:
        world.cleanup()
    print("OK: test_idempotent_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# 4. MISSING METADATA — defaults to tech-lead
# ═══════════════════════════════════════════════════════════════════════════

def test_no_metadata_type():
    """Spec card with no metadata.type → defaults to PO decompose card."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={})
        world.tick()
        world.tick()
        routed = _get_routed_cards(world, include_po=True)
        po_cards = [c for c in routed if c[1] == "product-owner"]
        assert len(po_cards) == 1 and "[decompose]" in po_cards[0][2], \
            f"No type → PO decompose, got: {routed}"
    finally:
        world.cleanup()
    print("OK: test_no_metadata_type")


def test_null_metadata():
    """Spec card with null metadata → defaults to PO decompose card."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata=None)
        world.tick()
        world.tick()
        routed = _get_routed_cards(world, include_po=True)
        po_cards = [c for c in routed if c[1] == "product-owner"]
        assert len(po_cards) == 1 and "[decompose]" in po_cards[0][2], \
            f"Null metadata → PO decompose, got: {routed}"
    finally:
        world.cleanup()
    print("OK: test_null_metadata")


# ═══════════════════════════════════════════════════════════════════════════
# 5. MULTIPLE SPECS
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_specs_same_tick():
    """Two spec cards complete → two workflows start, each routes correctly."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec-bug", metadata={"type": "bug"}, title="[spec] Bug")
        _add_spec_card(world, "spec-dev", metadata={"type": "feature"}, title="[spec] Dev")
        world.tick()
        instances = world.engine.state.load_active_instances()
        assert len(instances) == 2, \
            f"Two specs → two instances, got {len(instances)}"
        world.tick()  # routing fires for both
        routed = _get_routed_cards(world, include_po=True)
        # spec-bug → debugger; spec-dev → PO [decompose] card
        assignees = sorted(r[1] for r in routed)
        assert assignees == ["debugger", "product-owner"], \
            f"Expected debugger + product-owner, got: {assignees}"
    finally:
        world.cleanup()
    print("OK: test_multiple_specs_same_tick")


# ═══════════════════════════════════════════════════════════════════════════
# 6. ARCHIVED CARD
# ═══════════════════════════════════════════════════════════════════════════

def test_archived_card_no_trigger():
    """Spec card that's archived (not done) → no trigger."""
    world = _make_world()
    try:
        world.add_card("spec1", assignee="product-owner", status="archived",
                       completed_at=int(time.time()),
                       metadata={"type": "bug"}, title="[spec] Archived")
        world.tick()
        active = world.engine.state.load_active_instances()
        assert len(active) == 0, f"Archived card should not trigger"
    finally:
        world.cleanup()
    print("OK: test_archived_card_no_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# 7. ENTRY NODE — synchronous, no card
# ═══════════════════════════════════════════════════════════════════════════

def test_entry_no_card_created():
    """Entry node is command type — no kanban card should be created for it."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()  # trigger + entry command (synchronous)
        # Entry should complete in this tick. No card for entry.
        all_cards = _get_all_cards(world)
        # Only the spec card should exist (no entry card)
        entry_cards = [c for c in all_cards if c[1] == "product-owner" and c[0] != "spec1"]
        assert len(entry_cards) == 0, \
            f"Entry should not create a card, got: {entry_cards}"
    finally:
        world.cleanup()
    print("OK: test_entry_no_card_created")


# ═══════════════════════════════════════════════════════════════════════════
# 8. DEAD-BRANCH SKIP
# ═══════════════════════════════════════════════════════════════════════════

def test_non_matching_routes_skipped():
    """When type=bug, only route-bug dispatches. Other routes are SKIPPED."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()
        a2 = world.tick()  # routing fires
        # Should see DISPATCHED for route-bug, SKIPPED for the rest
        assert any("DISPATCHED" in a and "route-bug" in a for a in a2), \
            f"route-bug should dispatch"
        assert any("SKIPPED" in a and "route-scout" in a for a in a2), \
            f"route-scout should be skipped"
        assert any("SKIPPED" in a and "route-decompose" in a for a in a2), \
            f"route-decompose should be skipped"
        # Only 1 routed card
        routed = _get_routed_cards(world)
        assert len(routed) == 1, f"Only 1 card, got {len(routed)}"
    finally:
        world.cleanup()
    print("OK: test_non_matching_routes_skipped")


# ═══════════════════════════════════════════════════════════════════════════
# 9. WORKFLOW COMPLETION
# ═══════════════════════════════════════════════════════════════════════════

def test_workflow_completes_after_routed_card_done():
    """After the routed card completes, the workflow instance completes."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()  # trigger + entry
        world.tick()  # route-bug dispatches
        # Complete the debugger card
        routed = _get_routed_cards(world)
        assert len(routed) == 1
        conn = sqlite3.connect(str(world.board_db))
        card_id = conn.execute(
            "SELECT id FROM tasks WHERE assignee='debugger' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(card_id, metadata={"verdict": "root-caused"})
        # Tick: debugger done → workflow completes
        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Workflow should complete after routed card done, got: {actions}"
        active = world.engine.state.load_active_instances()
        assert len(active) == 0, f"Instance should be completed"
    finally:
        world.cleanup()
    print("OK: test_workflow_completes_after_routed_card_done")


# ═══════════════════════════════════════════════════════════════════════════
# 10. OUTPUT SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def test_schema_validation_bug():
    """route-bug has output schema requiring verdict. Invalid output → failed."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec1", metadata={"type": "bug"})
        world.tick()
        world.tick()
        # Complete debugger card with INVALID output (missing verdict)
        conn = sqlite3.connect(str(world.board_db))
        card_id = conn.execute(
            "SELECT id FROM tasks WHERE assignee='debugger' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        world.complete_card(card_id, metadata={"something_else": "no verdict"})
        actions = world.tick()
        # Should report VALIDATION FAILED
        assert any("VALIDATION FAILED" in a for a in actions), \
            f"Should fail validation, got: {actions}"
    finally:
        world.cleanup()
    print("OK: test_schema_validation_bug")


# ═══════════════════════════════════════════════════════════════════════════
# 11. BODY TEMPLATE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def test_body_contains_spec_card_id():
    """Routed card body should contain the spec card ID via template resolution."""
    world = _make_world()
    try:
        _add_spec_card(world, "spec-abc-123", metadata={"type": "bug"},
                       title="[spec] Important Bug")
        world.tick()
        world.tick()
        conn = sqlite3.connect(str(world.board_db))
        body = conn.execute(
            "SELECT body FROM tasks WHERE assignee='debugger' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        assert "spec-abc-123" in body, \
            f"Body should contain spec card ID, got: {body[:200]}"
        assert "Important Bug" in body, \
            f"Body should contain spec title, got: {body[:200]}"
    finally:
        world.cleanup()
    print("OK: test_body_contains_spec_card_id")


if __name__ == "__main__":
    tests = [
        # Basic routing
        test_route_bug,
        test_route_research,
        test_route_ops,
        test_route_architecture,
        test_route_tickets,
        test_route_default_tech_lead,
        # Trigger filtering
        test_wrong_assignee_no_trigger,
        test_wrong_status_no_trigger,
        test_wrong_title_prefix_no_trigger,
        # Idempotency
        test_idempotent_trigger,
        # Missing metadata
        test_no_metadata_type,
        test_null_metadata,
        # Multiple specs
        test_multiple_specs_same_tick,
        # Archived card
        test_archived_card_no_trigger,
        # Entry node
        test_entry_no_card_created,
        # Dead-branch skip
        test_non_matching_routes_skipped,
        # Workflow completion
        test_workflow_completes_after_routed_card_done,
        # Schema validation
        test_schema_validation_bug,
        # Body template resolution
        test_body_contains_spec_card_id,
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
    sys.exit(0 if failed == 0 else 1)
