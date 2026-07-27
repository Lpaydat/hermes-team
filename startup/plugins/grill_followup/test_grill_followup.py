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
    parse_scan_output,
    spawn_async_chain,
    _venture_name_from_title,
    maybe_canonicalize_context_md,
    _canonical_target,
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


# --- broadened open-section detection (parser-miss fix) -----------------
# PO records open items under semantically-rich headers (hypotheses, gates,
# assumptions, TBD) per grill-with-docs' convention — NOT always "Open
# questions". The old parser matched only ^## Open and terminated the loop on
# a parser miss (grilllive42: 2 unmeasured hypotheses + 4 unpassed gates, all
# "ASSERTIONS, not measured data", yet extract returned "" -> loop died at 2
# iter). Broaden to recognize open-bearing sections.


def test_extract_open_questions_matches_hypotheses_section(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# V\n\n## Market hypotheses (two axes, to be tested)\n- H1: x (unmeasured)\n- H2: y\n\n## Resolved\n- done\n")
    out = extract_open_questions(str(ctx))
    assert "H1" in out and "H2" in out
    assert "done" not in out  # block ends at the next ##


def test_extract_open_questions_matches_gates_section(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# V\n\n## The four-gate risk structure\n1. Classifier gate (untested)\n2. Problem-frequency gate\n\n## Other\n")
    out = extract_open_questions(str(ctx))
    assert "Classifier gate" in out


def test_extract_open_questions_matches_assumptions_tbd_risk(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# V\n\n## Assumptions\n- A1\n\n## TBD\n- t1\n\n## Risks to verify\n- r1\n\n## Done\n")
    out = extract_open_questions(str(ctx))
    assert "A1" in out and "t1" in out and "r1" in out


def test_extract_open_questions_bold_form_broadened(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# V\n\n**Open hypotheses (parked):**\n- H1\n\nbody\n")
    out = extract_open_questions(str(ctx))
    assert "H1" in out


def test_extract_open_questions_still_matches_open_header(tmp_path):
    # regression: the original ## Open form must still work
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("## Open questions\n- Q1\n")
    assert "Q1" in extract_open_questions(str(ctx))


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


def test_find_context_md_in_venture_builder_home(tmp_path, monkeypatch):
    """Canonical home (absolute-path fix): venture-grill writes CONTEXT.md to
    ~/.venture-builder/<slug>/CONTEXT.md — absolute, survives the scratch
    rmtree that destroyed ~10% of grill outputs. find_context_md must search
    there (and first, since it's the new canonical location)."""
    import grill_followup
    monkeypatch.setenv("HOME", str(tmp_path))  # expanduser("~") -> tmp_path
    vb_dir = tmp_path / ".venture-builder" / "grilllive99"
    vb_dir.mkdir(parents=True)
    (vb_dir / "CONTEXT.md").write_text("## Open questions\n- Q1: x\n")
    # isolate from real repo/vault so ONLY the venture-builder home can match
    monkeypatch.setattr(grill_followup, "_REPO_ROOT", str(tmp_path / "norepo"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nohome"))
    p = find_context_md("[grill] AnyVenture", "Grill topic: venture-pitch/grilllive99")
    assert p is not None
    assert ".venture-builder" in p
    assert "grilllive99" in p


# --- maybe_canonicalize_context_md (tool-level CONTEXT.md rescue) -------


def test_canonical_target_path():
    p = _canonical_target("grilllive99")
    assert p.endswith(".venture-builder/grilllive99/CONTEXT.md")


def test_canonicalize_copies_write_file_of_context_md(tmp_path, monkeypatch):
    """The fix: PO writes CONTEXT.md somewhere (here a throwaway src); the
    post_tool_call hook copies it to ~/.venture-builder/<slug>/ so it survives
    the scratch rmtree. Fires AT WRITE TIME, before kanban_complete cleanup."""
    import grill_followup
    monkeypatch.setenv("HOME", str(tmp_path))  # ~ -> tmp_path
    src = tmp_path / "scratch_workdir" / "docs" / "ventures" / "grilllive99" / "CONTEXT.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Grilllive99\n## Open questions\n- Q1\n")
    target = maybe_canonicalize_context_md(
        "write_file", {"path": str(src)}, "Grill topic: venture-pitch/grilllive99"
    )
    assert target is not None
    assert target == str(tmp_path / ".venture-builder" / "grilllive99" / "CONTEXT.md")
    assert (tmp_path / ".venture-builder" / "grilllive99" / "CONTEXT.md").read_text().startswith("# Grilllive99")


def test_canonicalize_copies_patch_of_context_md(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "ctx" / "CONTEXT.md"
    src.parent.mkdir(parents=True)
    src.write_text("updated")
    target = maybe_canonicalize_context_md(
        "patch", {"path": str(src)}, "Grill topic: venture-pitch/grilllive42"
    )
    assert target is not None and "grilllive42" in target


def test_canonicalize_ignores_read_only_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "CONTEXT.md"; src.write_text("x")
    # read_file / search_files must NOT trigger a copy
    assert maybe_canonicalize_context_md(
        "read_file", {"path": str(src)}, "Grill topic: venture-pitch/grilllive99"
    ) is None
    assert not (tmp_path / ".venture-builder").exists()


def test_canonicalize_ignores_non_context_md_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "notes.md"; src.write_text("x")
    assert maybe_canonicalize_context_md(
        "write_file", {"path": str(src)}, "Grill topic: venture-pitch/grilllive99"
    ) is None


def test_canonicalize_no_slug_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "CONTEXT.md"; src.write_text("x")
    # body has no venture-pitch/<slug> -> can't key the canonical dir
    assert maybe_canonicalize_context_md("write_file", {"path": str(src)}, "no slug here") is None


# --- parse_scan_output (scanner-driven follow-up) -----------------------
# The follow-up is now an LLM scanner (grill skill, read-only over CONTEXT.md)
# that outputs NEXT:<question> or CONVERGED:<reason>. These test the pure
# output parser; the subprocess itself is integration (validated end-to-end).


def test_parse_scan_output_next():
    status, q = parse_scan_output("NEXT: Is X universal? — no evidence — 5 calls")
    assert status == "next"
    assert "Is X universal?" in q


def test_parse_scan_output_converged():
    status, q = parse_scan_output("CONVERGED: every claim has a cited source")
    assert status == "converged"
    assert q is None


def test_parse_scan_output_unclear_on_empty_or_garbage():
    assert parse_scan_output("")[0] == "unclear"
    assert parse_scan_output("blah blah no marker")[0] == "unclear"


def test_parse_scan_output_finds_next_in_wrapped_output():
    # the scanner subprocess wraps output in chat-UI boxes; the NEXT line lands
    # somewhere in stdout — find it regardless of surrounding noise.
    raw = ("Initializing agent...\n...box...\n"
           "NEXT: the real next question — why — evidence\n"
           "Resume this session...")
    status, q = parse_scan_output(raw)
    assert status == "next"
    assert "the real next question" in q


def test_parse_scan_output_skips_prompt_template_echo():
    # the scan prompt's own "NEXT: <single most...>" format-spec line gets echoed
    # in stdout before the real answer. Must skip placeholder lines + take the
    # filled answer (this was the grilllive44 root bug: iter2 got an empty slot).
    raw = ("NEXT: <single most important unanswered question> — <why unanswered> — <evidence>\n"
           "scanner reasons...\n"
           "NEXT: Is the bookkeeper universal at $240-480/report — no evidence — 5 calls\n")
    status, q = parse_scan_output(raw)
    assert status == "next"
    assert "bookkeeper" in q
    assert "<" not in q


def test_parse_scan_output_takes_last_next_line():
    raw = "NEXT: first attempt\nNEXT: the final answer\n"
    status, q = parse_scan_output(raw)
    assert status == "next"
    assert q == "the final answer"


def test_decide_carryover_converged_forces_deeper(monkeypatch):
    # experiment mode: scanner CONVERGED no longer terminates the loop — it
    # forces one more drill so we can observe what a non-terminating grill does.
    import grill_followup
    monkeypatch.setattr(grill_followup, "scan_for_next_question", lambda slug: "CONVERGED: all claims evidenced")
    out = grill_followup.decide_carryover("[grill] X", "Grill topic: venture-pitch/grilllive99")
    assert out  # non-empty — loop continues, does not terminate
    assert "deeper" in out.lower() or "drill" in out.lower()


def test_decide_carryover_next_returns_the_question(monkeypatch):
    import grill_followup
    monkeypatch.setattr(grill_followup, "scan_for_next_question",
                        lambda slug: "NEXT: Is X universal? — no evidence — 5 calls")
    out = grill_followup.decide_carryover("[grill] X", "Grill topic: venture-pitch/grilllive99")
    assert "Is X universal?" in out


def test_spawn_async_chain_detaches_nonblocking(monkeypatch):
    # the hook must NOT block on the scan — detach async_chain.py so the worker
    # exits immediately + the scan/create run after (survives max-runtime).
    import grill_followup
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            captured["cmd"] = cmd
            captured["kw"] = kw

    monkeypatch.setattr(grill_followup.subprocess, "Popen", FakePopen)
    spawn_async_chain("[grill] X", "Grill topic: venture-pitch/grilllive99")
    assert captured["kw"].get("start_new_session") is True  # detached
    assert captured["kw"]["env"]["HERMES_ASYNC_SLUG"] == "grilllive99"
    assert any("async_chain.py" in str(c) for c in captured["cmd"])


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


def test_next_spec_iter2_framing_tells_po_to_grill_not_dedup_close():
    # PO self-closes iter2 cards as "duplicate re-fire" when it sees the prior
    # done [grill] card. The injected body must frame: MUST intercom VB on THIS
    # question; prior card done != this answered; don't dedup-close.
    spec = build_next_spec(
        task_title="[grill] X",
        task_body="brief...",
        open_questions="Is X universal? — no evidence — 5 calls",
    )
    assert "ITERATION" in spec["body"]
    assert "intercom" in spec["body"].lower()
    assert "Is X universal?" in spec["body"]


def test_next_spec_no_injection_when_open_empty():
    spec = build_next_spec(task_title="[grill] X", task_body="brief...", open_questions="")
    assert spec["body"] == "brief..."
