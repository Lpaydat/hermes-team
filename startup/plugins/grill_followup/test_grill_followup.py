"""Tests for grill_followup — spawn the next grill card on kanban_complete,
with open questions (parsed from CONTEXT.md) injected into the body.

Pure logic only (decisions + the CONTEXT.md parser). The kanban-wiring hook is
integration (lives in __init__.py); these cover the decisions it makes.
"""
from . import (
    is_grill_intercom,
    build_next_spec,
    _extract_call,
    extract_open_questions,
    find_context_md,
    _venture_name_from_title,
)


# --- _extract_call (the kwarg shape the emitter actually sends) ----------

def test_extract_call_reads_emit_kwarg_shape():
    fn, fa = _extract_call(
        {"tool_name": "intercom", "args": {"action": "ask", "to": "venture-builder"}}
    )
    assert fn == "intercom"
    assert fa == {"action": "ask", "to": "venture-builder"}


def test_extract_call_reads_legacy_shape():
    fn, fa = _extract_call(
        {"function_name": "intercom", "function_args": {"action": "send"}}
    )
    assert fn == "intercom"
    assert fa == {"action": "send"}


# --- is_grill_intercom --------------------------------------------------

def test_ask_to_venture_builder_is_grill():
    assert is_grill_intercom(
        "intercom", {"action": "ask", "to": "venture-builder", "topic": "x"}
    ) is True


def test_send_to_venture_builder_is_grill():
    assert is_grill_intercom("intercom", {"action": "send", "to": "venture-builder"}) is True


def test_reply_is_not_grill():
    assert is_grill_intercom(
        "intercom", {"action": "reply", "to": "venture-builder", "reply_to": "abc"}
    ) is False


def test_ask_to_other_profile_is_not_grill():
    assert is_grill_intercom("intercom", {"action": "ask", "to": "tech-lead"}) is False


def test_non_intercom_tool_is_not_grill():
    assert is_grill_intercom("kanban_complete", {"summary": "..."}) is False


def test_cross_team_venture_builder_is_grill():
    assert is_grill_intercom(
        "intercom", {"action": "ask", "to": "team-alpha/venture-builder"}
    ) is True


# --- _venture_name_from_title ------------------------------------------

def test_venture_name_from_title():
    assert _venture_name_from_title("[grill] ScriptSync") == "scriptsync"


def test_venture_name_from_title_strips_next():
    assert _venture_name_from_title("[grill] BriefMate (next)") == "briefmate"


# --- extract_open_questions (the CONTEXT.md parser) ---------------------

def test_extract_open_questions_finds_section(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# Venture\n\n## Resolved\n- done\n\n## Open questions\n"
        "- **Q1**: foo\n- **Q2**: bar\n\n## Summary\nstuff\n"
    )
    oq = extract_open_questions(str(ctx))
    assert "## Open questions" in oq
    assert "Q1" in oq and "Q2" in oq
    assert "Resolved" not in oq  # didn't bleed from the prior section
    assert "Summary" not in oq  # stopped at the next heading


def test_extract_open_questions_matches_branches_variant(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("## Open grill branches\n- branch A\n")
    assert "branch A" in extract_open_questions(str(ctx))


def test_extract_open_questions_matches_bold_line_form(tmp_path):
    """PO sometimes writes open questions as a bold line, not a heading:
    '**Open questions (parked...):**' followed by '- OQ-N:' items."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "## Grill summary\nblah\n\n**Open questions (parked, not blocking iter-1/2):**\n"
        "- OQ-1: first\n- OQ-2: second\n"
    )
    oq = extract_open_questions(str(ctx))
    assert "Open questions" in oq
    assert "OQ-1" in oq and "OQ-2" in oq
    assert "Grill summary" not in oq  # didn't bleed from the prior section


def test_extract_open_questions_empty_when_no_section(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# V\n\n## Resolved\n- x\n")
    assert extract_open_questions(str(ctx)) == ""


def test_extract_open_questions_missing_file():
    assert extract_open_questions("/nonexistent/path/CONTEXT.md") == ""


def test_extract_open_questions_none_path():
    assert extract_open_questions(None) == ""


# --- find_context_md ----------------------------------------------------

def test_find_context_md_by_venture_name(tmp_path, monkeypatch):
    venture_dir = tmp_path / "docs" / "ventures" / "scriptsync"
    venture_dir.mkdir(parents=True)
    (venture_dir / "CONTEXT.md").write_text("x")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    p = find_context_md("[grill] ScriptSync", "Grill topic: venture-pitch/grilllive99")
    assert p is not None
    assert p.endswith("scriptsync/CONTEXT.md")


def test_find_context_md_falls_back_to_slug(tmp_path, monkeypatch):
    # venture-name dir absent, slug dir present
    slug_dir = tmp_path / "docs" / "ventures" / "grilllive99"
    slug_dir.mkdir(parents=True)
    (slug_dir / "CONTEXT.md").write_text("x")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    p = find_context_md("[grill] NoMatchingDir", "Grill topic: venture-pitch/grilllive99")
    assert p is not None
    assert "grilllive99" in p


def test_find_context_md_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert find_context_md("[grill] Ghost", "Grill topic: venture-pitch/ghost") is None


def test_find_context_md_under_profile_scoped_hermes_home(tmp_path, monkeypatch):
    """Regression: the worker's HERMES_HOME is PROFILE-scoped
    (<repo>/startup/profiles/<p>), NOT the team home (<repo>/startup). So
    HERMES_HOME/.. missed docs/ventures and find_context_md returned None —
    silently breaking the open-questions injection. The fix derives the repo
    root from the plugin's own path (_REPO_ROOT), stable regardless of
    HERMES_HOME. This simulates the exact worker env."""
    import grill_followup
    fake_repo = tmp_path
    # profile-scoped HERMES_HOME (the worker's actual setting)
    fake_profile_home = fake_repo / "startup" / "profiles" / "testprofile"
    fake_profile_home.mkdir(parents=True)
    # CONTEXT.md at <repo>/docs/ventures/<venture>/ (real location)
    venture_dir = fake_repo / "docs" / "ventures" / "testventure"
    venture_dir.mkdir(parents=True)
    (venture_dir / "CONTEXT.md").write_text("## Open questions\n- Q1: x\n")
    # _REPO_ROOT anchored to the fake repo (simulating the plugin-path fix)
    monkeypatch.setattr(grill_followup, "_REPO_ROOT", str(fake_repo))
    monkeypatch.setenv("HERMES_HOME", str(fake_profile_home))
    p = find_context_md("[grill] TestVenture", "Grill topic: venture-pitch/test")
    assert p is not None
    assert p.endswith("testventure/CONTEXT.md")


# --- build_next_spec ----------------------------------------------------

def test_next_spec_clean_title_no_iteration_marker():
    spec = build_next_spec(
        task_title="[grill] PerfBudget", task_body="Grill topic: venture-pitch/grilllive99"
    )
    assert spec["title"] == "[grill] PerfBudget"
    assert "(next)" not in spec["title"]


def test_next_spec_strips_existing_next_marker():
    spec = build_next_spec(
        task_title="[grill] PerfBudget (next)", task_body="Grill topic: venture-pitch/grilllive99"
    )
    assert spec["title"] == "[grill] PerfBudget"


def test_next_spec_no_parent_link():
    spec = build_next_spec(task_title="[grill] X", task_body="Grill topic: venture-pitch/grilllive99")
    assert "parents" not in spec


def test_next_spec_idempotency_key_by_slug():
    spec = build_next_spec(task_title="[grill] X", task_body="Grill topic: venture-pitch/grilllive99")
    assert spec["idempotency_key"] == "venture-grill-next-grilllive99"


def test_next_spec_carries_brief_skill_assignee():
    spec = build_next_spec(task_title="[grill] X", task_body="brief...")
    assert spec["assignee"] == "product-owner"
    assert spec["skills"] == ["venture-grill"]
    assert spec["body"] == "brief..."


def test_next_spec_injects_open_questions():
    spec = build_next_spec(
        task_title="[grill] X",
        task_body="brief...",
        open_questions="## Open questions\n- **Q1**: foo",
    )
    assert "## Open questions" in spec["body"]
    assert "Q1" in spec["body"]


def test_next_spec_no_injection_when_open_empty():
    spec = build_next_spec(task_title="[grill] X", task_body="brief...", open_questions="")
    assert spec["body"] == "brief..."
