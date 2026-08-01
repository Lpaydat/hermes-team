"""
Foreach enhancement tests: title_template + dot-path variable resolution.

Tests the two new engine features:
1. Custom card titles for foreach nodes via title_template
2. Dot-path resolution (${item.slug}) when foreach iterates over dicts

Run: python3 test_foreach_enhancements.py
"""
import sys
import json
import sqlite3
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.test_engine import FakeWorld
from workflow_engine.model import resolve_template


# ═══════════════════════════════════════════════════════════════════════════
# DOT-PATH RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def test_resolve_dot_path_basic():
    """resolve_template resolves ${item.field} when item is a dict."""
    ctx = {"item": {"slug": "my-idea", "name": "My Idea", "score": 18}}
    result = resolve_template("Slug: ${item.slug} | Name: ${item.name} | Score: ${item.score}", ctx)
    assert result == "Slug: my-idea | Name: My Idea | Score: 18", f"Got: {result}"
    print("OK: test_resolve_dot_path_basic")


def test_resolve_dot_path_missing_field():
    """resolve_template handles missing sub-field gracefully."""
    ctx = {"item": {"slug": "x"}}
    result = resolve_template("${item.slug} and ${item.missing}", ctx)
    assert "x" in result, f"Should resolve slug: {result}"
    assert "missing" not in result, f"Missing field should be empty: {result}"
    print("OK: test_resolve_dot_path_missing_field")


def test_resolve_dot_path_nested_in_command():
    """resolve_template handles dot-paths alongside flat keys."""
    ctx = {
        "item": {"slug": "test-idea"},
        "nodes.parse.output.count": 5,
        "trigger.board": "my-board",
    }
    result = resolve_template(
        "Board: ${trigger.board} | Item: ${item.slug} | Count: ${nodes.parse.output.count}", ctx
    )
    assert "Board: my-board" in result
    assert "Item: test-idea" in result
    assert "Count: 5" in result
    print("OK: test_resolve_dot_path_nested_in_command")


def test_resolve_item_as_dict_string():
    """When ${item} is referenced without dot-path, gets dict string repr."""
    ctx = {"item": {"slug": "x", "name": "y"}}
    result = resolve_template("Item: ${item}", ctx)
    assert "slug" in result and "x" in result, f"Should contain dict repr: {result}"
    print("OK: test_resolve_item_as_dict_string")


# ═══════════════════════════════════════════════════════════════════════════
# TITLE_TEMPLATE IN FOREACH
# ═══════════════════════════════════════════════════════════════════════════

def test_foreach_custom_title():
    """Foreach node with title_template creates cards with custom titles."""
    world = FakeWorld()
    world.add_template({
        "id": "custom-title",
        "name": "Custom Title",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "cards", "profile": "builder", "skill": "self-grill",
             "body_template": "Slug: ${item}",
             "title_template": "Grill: ${item}",
             "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "cards"}],
    })

    world.start("custom-title")
    world.tick()  # dispatch src

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"items": ["idea-1", "idea-2", "idea-3"]})

    world.tick()  # foreach dispatches

    conn = sqlite3.connect(str(world.board_db))
    titles = [r[0] for r in conn.execute("SELECT title FROM tasks WHERE assignee='builder' ORDER BY title").fetchall()]
    conn.close()

    assert "Grill: idea-1" in titles, f"Expected 'Grill: idea-1' in {titles}"
    assert "Grill: idea-2" in titles, f"Expected 'Grill: idea-2' in {titles}"
    assert "Grill: idea-3" in titles, f"Expected 'Grill: idea-3' in {titles}"
    assert len(titles) == 3, f"Expected 3 cards, got {len(titles)}: {titles}"

    world.cleanup()
    print("OK: test_foreach_custom_title")


def test_foreach_custom_title_with_dicts():
    """Foreach with title_template + dot-path resolution for dict items."""
    world = FakeWorld()
    world.add_template({
        "id": "dict-title",
        "name": "Dict Title",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "cards", "profile": "builder", "skill": "",
             "body_template": "Score: ${item.score}/25 | Slug: ${item.slug}",
             "title_template": "Build: ${item.name}",
             "foreach": "${nodes.src.output.ideas}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "cards"}],
    })

    world.start("dict-title")
    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"ideas": [
        {"slug": "leadpilot", "name": "LeadPilot", "score": 21},
        {"slug": "osint-desk", "name": "OSINT Desk", "score": 20},
    ]})

    world.tick()  # foreach dispatches

    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute("SELECT title, body FROM tasks WHERE assignee='builder' ORDER BY title").fetchall()
    conn.close()

    assert len(cards) == 2, f"Expected 2 cards, got {len(cards)}"

    # Check titles use dot-path resolution
    titles = [c[0] for c in cards]
    assert "Build: LeadPilot" in titles, f"Expected 'Build: LeadPilot' in {titles}"
    assert "Build: OSINT Desk" in titles, f"Expected 'Build: OSINT Desk' in {titles}"

    # Check bodies use dot-path resolution
    for title, body in cards:
        if "LeadPilot" in title:
            assert "Score: 21/25" in body, f"Expected score 21 in body: {body}"
            assert "Slug: leadpilot" in body, f"Expected slug in body: {body}"
        elif "OSINT Desk" in title:
            assert "Score: 20/25" in body, f"Expected score 20 in body: {body}"
            assert "Slug: osint-desk" in body, f"Expected slug in body: {body}"

    world.cleanup()
    print("OK: test_foreach_custom_title_with_dicts")


def test_foreach_default_title_when_no_template():
    """Foreach without title_template falls back to default [node#idx] title."""
    world = FakeWorld()
    world.add_template({
        "id": "default-title",
        "name": "Default Title",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "cards", "profile": "builder", "skill": "self-grill",
             "body_template": "Build ${item}",
             "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "cards"}],
    })

    world.start("default-title")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"items": ["a", "b"]})

    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    titles = [r[0] for r in conn.execute("SELECT title FROM tasks WHERE assignee='builder'").fetchall()]
    conn.close()

    # Should have default titles
    assert len(titles) == 2
    for t in titles:
        assert "cards#" in t, f"Default title should contain node#idx: {t}"

    world.cleanup()
    print("OK: test_foreach_default_title_when_no_template")


def test_foreach_title_with_special_chars():
    """Title template with em-dashes and special characters in values."""
    world = FakeWorld()
    world.add_template({
        "id": "special-chars",
        "name": "Special Chars",
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "",
             "body_template": ""},
            {"id": "cards", "profile": "builder", "skill": "",
             "body_template": "Body for ${item.name}",
             "title_template": "Grill: ${item.name}",
             "foreach": "${nodes.src.output.ideas}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "cards"}],
    })

    world.start("special-chars")
    world.tick()
    conn = sqlite3.connect(str(world.board_db))
    src_card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(src_card, metadata={"ideas": [
        {"slug": "ai-smb", "name": "AI SMB — Bookkeeping Tool", "score": 18},
    ]})

    world.tick()

    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute("SELECT title, body FROM tasks WHERE assignee='builder'").fetchall()
    conn.close()

    assert len(cards) == 1
    assert "AI SMB — Bookkeeping Tool" in cards[0][0], f"Title should have em-dash: {cards[0][0]}"
    assert "AI SMB — Bookkeeping Tool" in cards[0][1], f"Body should have name: {cards[0][1]}"

    world.cleanup()
    print("OK: test_foreach_title_with_special_chars")


def test_command_output_feeds_foreach():
    """Command node outputs JSON list, foreach iterates over it."""
    world = FakeWorld()
    world.add_template({
        "id": "cmd-foreach",
        "name": "Command Foreach",
        "nodes": [
            {"id": "parse", "profile": "", "skill": "",
             "body_template": "", "type": "command",
             "command": "printf '%s' '{\"ideas\": [{\"slug\": \"a\", \"name\": \"A\", \"score\": 10}, {\"slug\": \"b\", \"name\": \"B\", \"score\": 20}], \"count\": 2}'"},
            {"id": "cards", "profile": "builder", "skill": "",
             "body_template": "Build: ${item.slug}",
             "title_template": "Build: ${item.name}",
             "foreach": "${nodes.parse.output.ideas}",
             "depends_on": ["parse"]},
        ],
        "edges": [{"from": "parse", "to": "cards"}],
    })

    world.start("cmd-foreach")
    actions = world.tick()

    # Command should run, then foreach should dispatch
    assert any("parse" in a and "DONE" in a for a in actions), f"command should run: {actions}"
    assert any("cards" in a and "DISPATCHED" in a for a in actions), f"foreach should dispatch: {actions}"

    conn = sqlite3.connect(str(world.board_db))
    cards = conn.execute("SELECT title, body FROM tasks WHERE assignee='builder'").fetchall()
    conn.close()

    assert len(cards) == 2, f"Expected 2 cards, got {len(cards)}: {cards}"
    titles = sorted([c[0] for c in cards])
    assert "Build: A" in titles and "Build: B" in titles, f"Titles: {titles}"

    world.cleanup()
    print("OK: test_command_output_feeds_foreach")


# ═══════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Dot-path resolution
        test_resolve_dot_path_basic,
        test_resolve_dot_path_missing_field,
        test_resolve_dot_path_nested_in_command,
        test_resolve_item_as_dict_string,
        # Title template
        test_foreach_custom_title,
        test_foreach_custom_title_with_dicts,
        test_foreach_default_title_when_no_template,
        test_foreach_title_with_special_chars,
        # Command + foreach
        test_command_output_feeds_foreach,
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
