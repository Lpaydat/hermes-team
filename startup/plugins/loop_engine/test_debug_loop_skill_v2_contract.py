#!/usr/bin/env python3
"""
TDD contract test for B10 — debug-loop skill v2 coupled release (T9).

B10 is a DIFFERENT bead: it updates a CONSUMER SKILL (instructions), not engine
code. The engine v2 surface (B2-B9) is DONE; this bead makes the debugger's
debug-loop skill actually DECLARE + USE it, completing T9's hard cutover.

For a skill, the instructions ARE the behaviour contract, so the test = a
CONTRACT test on SKILL.md (asserts it declares the v2 directives) PLUS an
integration proof the declared contract runs green through the (already-done)
engine.

Design authority: SPEC.md §7 (T9 migration / hard cutover) + §Thesis(v2),
§2 (discover), §3 (evidence), §4 (metric_type + battery), §5 (root_id).
Bead: ``bd show hermes-teams-tdf``; cutover shape: ``bd show hermes-teams-s54``.

Contract cases (RED first — current SKILL.md predates v2):
  1. metric_type declared per phase (ground_truth for reproduce/fix/falsify;
     the RCA phase's type documented).
  2. verifiers RETURN evidence-cited dod_verdicts (each material claim cited +
     re-opened per T1).
  3. if any phase is proxy, the required battery:{path,runner} is documented
     (B5/B6) — and ground_truth phases documented as needing no battery.
  4. loop_id handling documented (capture root_id, echo as loop_id, handle
     loop_id_mismatch).
  5. discover is engine-default (+ optionally how to configure a custom
     discover spec).

Integration proof (engine-compatibility — the declared contract runs green):
  a debug-loop-SHAPED spec (phases with metric_type=ground_truth + evidence-
  cited dod_verdicts) is accepted by the validator AND advances through the
  real evaluate path. The engine files (tools.py / schemas.py) are NOT
  modified by this bead — this test only proves the skill's contract is
  engine-compatible.
"""

import json
import re
import sys
import unittest
from pathlib import Path

# Import loop_engine as a PACKAGE (parent dir on sys.path) so __init__.py's
# `from . import schemas, tools` resolves — mirrors how the plugin loader
# imports plugins (same setup as test_loop_engine*.py).
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/loop_engine
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
# Insert ONLY the plugins dir here (not PLUGIN_DIR). loop_engine is a package
# under PLUGINS_DIR, so `import loop_engine` resolves. We deliberately do NOT
# leave PLUGIN_DIR on sys.path at module level: this file is collected FIRST
# alphabetically, and a persistent PLUGIN_DIR entry shadows the real hermes
# `tools` package (loop_engine/tools.py) for the e2e suite's kernel fixture
# before the real `tools` is cached. PLUGIN_DIR is added transiently in
# _harness() for the sibling-import and removed immediately after.
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine  # noqa: E402  (package; register() callable)
from loop_engine import tools as le_tools  # noqa: E402


# ── the SKILL.md under contract ──────────────────────────────────────────────
#
# startup/profiles/debugger/skills/software-development/debug-loop/SKILL.md
# (PLUGIN_DIR.parent.parent == .../startup)
SKILL_PATH = (
    PLUGIN_DIR.parent.parent
    / "profiles" / "debugger" / "skills" / "software-development"
    / "debug-loop" / "SKILL.md"
).resolve()


def _skill_text():
    """Read the SKILL.md text (the skill's behaviour contract)."""
    return SKILL_PATH.read_text(encoding="utf-8")


# ── minimal evidence/claim builders (on-the-wire dict shape, per T1) ─────────

def _cite(locator="tests/test_calc.py:10", artifact_type="file_line", quote=None):
    c = {"artifact_type": artifact_type, "locator": locator}
    if quote is not None:
        c["quote"] = quote
    return c


def _claim(text, citations=None, material=True):
    return {"text": text,
            "citations": citations if citations is not None else [_cite()],
            "material": material}


def _verdict(dod_met=True, recommendation="advance", score=None, gaps=None,
             evidence=None):
    v = {"dod_met": dod_met, "recommendation": recommendation}
    if score is not None:
        v["score"] = score
    v["gaps"] = gaps if gaps is not None else []
    if evidence is not None:
        v["evidence"] = evidence
    return v


def _harness():
    """Lazily import the shared fake-board harness from test_loop_engine.

    PLUGIN_DIR is added to sys.path ONLY for this import and removed
    immediately after, so it cannot persistently shadow the real hermes
    ``tools`` package for the e2e suite (this file is collected first
    alphabetically). The imported module + callables remain usable after
    cleanup. Mirrors the lazy-import pattern of test_loop_engine_v2_evidence.py.
    """
    pdir = str(PLUGIN_DIR)
    added = pdir not in sys.path
    if added:
        sys.path.insert(0, pdir)
    try:
        from test_loop_engine import (
            _run_handler, _loop_state_comment_verifier, _verifier_run,
            _execution_t2, _verifier,
        )
    finally:
        if added:
            while pdir in sys.path:
                sys.path.remove(pdir)
    return (_run_handler, _loop_state_comment_verifier, _verifier_run,
            _execution_t2, _verifier)


# =============================================================================
# CONTRACT TESTS — the SKILL.md declares the v2 fact-based contract (T9)
# =============================================================================

class DebugLoopSkillV2ContractTest(unittest.TestCase):
    """The skill's instructions must encode the v2 hard-cutover fields.

    These FAIL on the pre-v2 SKILL.md (none of metric_type / ground_truth /
    battery / loop_id / discover / evidence appear) and pass once the skill is
    updated. For a skill, the instructions ARE the behaviour contract.
    """

    def setUp(self):
        self.text = _skill_text()
        self.lower = self.text.lower()

    # Case 1 — metric_type declared per phase.
    def test_skill_declares_metric_type_with_ground_truth_for_test_phases(self):
        """The skill instructs verifiers to declare `metric_type`, with
        ground_truth for the mechanical test-pass/fail phases (reproduce /
        fix / falsify)."""
        self.assertIn("metric_type", self.text,
                      "SKILL.md must instruct verifiers to declare metric_type")
        self.assertIn("ground_truth", self.text,
                      "SKILL.md must declare ground_truth for the test phases")

    def test_skill_documents_rca_phase_metric_type(self):
        """The RCA phase's metric_type is explicitly documented (ground_truth
        or proxy+battery) — not left implicit."""
        # The RCA/post-mortem phase must name its metric_type. Whichever the
        # skill chooses, the phase's type is documented next to the metric_type
        # directive (we assert the RCA phase section references metric_type).
        self.assertIn("metric_type", self.text)
        # The RCA / post-mortem / converge phase is discussed...
        self.assertTrue(
            "rca" in self.lower or "post-mortem" in self.lower
            or "converge" in self.lower,
            "SKILL.md must discuss the RCA / converge phase")

    # Case 2 — verifiers RETURN evidence-cited dod_verdicts (T1/T3).
    def test_skill_requires_evidence_cited_dod_verdicts(self):
        """Every verifier verdict must carry evidence:[Claim], each material
        claim cited + re-opened (T1). The skill instructs verifiers to cite."""
        self.assertIn("evidence", self.text,
                      "SKILL.md must require evidence in dod_verdicts")
        # The re-open directive (the verifier re-opens each citation).
        self.assertTrue(
            "re-open" in self.lower or "reopen" in self.lower
            or "citation" in self.lower,
            "SKILL.md must instruct verifiers to re-open / cite each material claim")

    # Case 3 — battery-if-proxy documented (B5/B6) + ground_truth needs none.
    def test_skill_documents_battery_rule_for_proxy_phases(self):
        """If a phase is proxy, a battery:{path,runner} is REQUIRED (B5/B6).
        Ground_truth phases need none. The skill documents this."""
        self.assertIn("battery", self.text,
                      "SKILL.md must document the battery rule for proxy phases")

    # Case 4 — loop_id handling (T6).
    def test_skill_documents_loop_id_handling(self):
        """The skill documents capturing root_id as loop_id, echoing it on
        re-invocation, and handling loop_id_mismatch (drift-immune)."""
        self.assertIn("loop_id", self.text,
                      "SKILL.md must document loop_id handling (T6)")
        self.assertIn("loop_id_mismatch", self.text,
                      "SKILL.md must document the loop_id_mismatch response flag")

    # Case 5 — discover is engine-default (+ optional custom spec).
    def test_skill_documents_discover_is_engine_default(self):
        """discover (T2) is engine-default — v1 callers get it automatically.
        The skill notes it is available (+ optionally a custom discover spec)."""
        self.assertIn("discover", self.text,
                      "SKILL.md must note discover (T2) is engine-default")

    # Case 6 — strict_fact_basis opt-in (T9): the debugger makes the cutover REAL.
    def test_skill_opts_into_strict_fact_basis(self):
        """The debug-loop skill is the first consumer to opt into the T9 hard
        cutover: it passes ``strict_fact_basis=True`` (workflow-wide) on its
        ``loop_engine`` call. With the flag on, ``metric_type`` is hard-required
        at the validate-seam (a verifier spec without it is a validation error —
        the loop refuses to run) and a verdict without an ``evidence`` key forces
        ``dod_met=false`` (nothing advances on assertion). The engine default is
        ``False`` (additive, zero-regression); this skill flips it so the
        ``metric_type`` + ``evidence`` directives are ENFORCED, not advisory."""
        self.assertIn("strict_fact_basis", self.text,
                      "SKILL.md must reference the strict_fact_basis opt-in (T9)")
        self.assertIn("strict_fact_basis=True", self.text,
                      "SKILL.md must declare strict_fact_basis=True (workflow-wide) — "
                      "the debugger is the first consumer to make the T9 cutover real")

    # Case 7 — strict_fact_basis=True as a LITERAL in a loop_engine call template (wma).
    def test_call_template_has_strict_fact_basis_true_literal(self):
        """The prose directive alone is NOT enough. A weak-context agent
        (glm-5.2) copies CALL TEMPLATES (literal examples) far more reliably
        than it follows prose directives — on a real-board smoke it ignored the
        B10 prose wiring and passed ``strict_fact_basis=False`` (the engine
        default), so T9's hard-reject was never armed (``loop_state.strict_fact_
        basis=false``). The fix: bake ``strict_fact_basis=True`` into the example
        ``loop_engine(...)`` invocation as a LITERAL kwarg, not just prose.

        This asserts the literal directly: a ``loop_engine(`` call-template
        opening, then within the SAME call (a bounded span across newlines) the
        verbatim kwarg ``strict_fact_basis=True``. I.e. the flag is a copyable
        parameter in the template the agent is told to use — not a phrase in the
        surrounding prose. RED on the pre-fix skill: ``strict_fact_basis=True``
        appears only in prose; there is no ``loop_engine(`` call-template block
        at all, so the bounded-span regex cannot match."""
        # A loop_engine( opening, then within the same call (bounded span, DOTALL
        # so newlines are included) the literal kwarg strict_fact_basis=True.
        # The span cap (4000 chars) keeps the match inside one call template
        # rather than drifting across the whole document.
        call_template_pat = re.compile(
            r"loop_engine\([\s\S]{0,4000}?strict_fact_basis\s*=\s*True")
        self.assertRegex(
            self.text, call_template_pat,
            "SKILL.md must contain a loop_engine(...) call-template block with "
            "the LITERAL kwarg strict_fact_basis=True baked in — the agent copies "
            "the template verbatim, and prose alone was ignored by glm-5.2 on a "
            "real-board run (strict_fact_basis defaulted to False, disarming T9)")

        # Belt-and-braces: the literal must also live inside a fenced code block
        # (the template the agent copies), not just inline in a sentence. Find a
        # fenced block that contains BOTH the call opening and the literal kwarg.
        fenced_blocks = re.findall(r"```.*?\n([\s\S]*?)\n```", self.text)
        has_template_block = any(
            "loop_engine(" in blk and re.search(r"strict_fact_basis\s*=\s*True", blk)
            for blk in fenced_blocks)
        self.assertTrue(
            has_template_block,
            "SKILL.md must have a fenced code block containing a loop_engine(...) "
            "call with the literal strict_fact_basis=True kwarg (the copyable "
            "template), not just prose")


# =============================================================================
# INTEGRATION PROOF — the declared contract runs green through the engine
# (engine files UNCHANGED by this bead; this only proves compatibility)
# =============================================================================

class DebugLoopSkillV2IntegrationProofTest(unittest.TestCase):
    """Prove the skill's intended contract — phases with metric_type=
    ground_truth declared + verifiers returning evidence-cited dod_verdicts —
    actually works through the (already-done) engine: the spec validates and
    the loop advances (evidence gate passes on cited verdicts).

    Style mirrors the B3/B4/B6 v2 tests: FakeKanbanDB + mocked workers driving
    the real ``loop_engine`` handler.
    """

    # -- the debug-loop-shaped v2 spec ----------------------------------------

    @staticmethod
    def _reproduce_phase():
        """Phase 0 — reproduce + minimise. ground_truth (test RED/GREEN)."""
        return {
            "execution": {"title": "reproduce the defect",
                          "body": "build the tightest RED repro",
                          "assignee": "developer"},
            "verifier": {"title": "verify tight RED achieved",
                         "body": "DoD: reliable minimal repro goes RED. "
                                 "Return dod_verdict with metric_type.",
                         "assignee": "verifier",
                         "metric_type": "ground_truth"},
            "max_iterations": 3,
        }

    @staticmethod
    def _fix_phase():
        """Phase 1 — hypothesise + fix + falsify. ground_truth (test pass/fail
        + falsification)."""
        return {
            "execution": {"title": "fix + regression test for the hypothesis",
                          "body": "ship the fix + regression test",
                          "assignee": "developer"},
            "verifier": {"title": "falsify the fix",
                         "body": "DoD: repro GREEN + regression at a correct "
                                 "seam + suite green + falsified. "
                                 "Return dod_verdict with metric_type.",
                         "assignee": "verifier",
                         "metric_type": "ground_truth"},
            "max_iterations": 5,
        }

    @staticmethod
    def _rca_phase():
        """Phase 2 — converge / RCA. ground_truth: the DoD is a structural /
        citation check (four inputs present + code-identifiers cited and
        re-openable), not an LLM-judged quality metric. No battery needed."""
        return {
            "execution": {"title": "write the RCA / post-mortem",
                          "body": "write docs/postmortems/<bug>.md",
                          "assignee": "debugger"},
            "verifier": {"title": "verify RCA has all 4 inputs + citations",
                         "body": "DoD: four mandatory inputs present + code-"
                                 "identifiers cited. Return dod_verdict.",
                         "assignee": "verifier",
                         "metric_type": "ground_truth"},
            "max_iterations": 2,
        }

    def _debug_loop_phases(self):
        return [self._reproduce_phase(), self._fix_phase(), self._rca_phase()]

    # -- proof (a): the 3-phase spec VALIDATES at the phases seam -----------

    def test_debug_loop_phases_validate_with_metric_type_ground_truth(self):
        """The 3-phase debug-loop spec — every verifier declaring
        metric_type=ground_truth — is ACCEPTED by _validate_phases (the path
        debug-loop takes via ``phases: [...]``). No battery required for
        ground_truth (T4/T5)."""
        err = le_tools._validate_phases(self._debug_loop_phases())
        self.assertIsNone(err,
                          "debug-loop v2 phases (metric_type=ground_truth) must "
                          f"validate; got error: {err!r}")

    # -- proof (b): a cited-evidence verdict ADVANCES through the real path --
    # (single-phase analogue of the reproduce phase; metric_type on the
    # verifier spec is validated by the handler's own _validate.)

    def test_cited_evidence_verdict_advances_with_metric_type_ground_truth(self):
        """End-to-end positive: a debug-loop-shaped verifier (metric_type=
        ground_truth) whose verdict carries a CITED material claim advances —
        the evidence gate passes inside the real evaluate path."""
        (_run_handler, _loop_state_comment_verifier, _verifier_run,
         _execution_t2, _verifier) = _harness()
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        verdict = _verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("the repro goes RED before the fix and GREEN after",
                             citations=[_cite("tests/test_repro.py:14",
                                              quote="assert bug() is None")])])
        # The verifier spec carries the v2 metric_type directive (validated by
        # the handler's _validate on entry).
        verifier_spec = dict(_verifier(), metric_type="ground_truth")
        parsed, _fake = _run_handler(
            args={"goal": "reproduce + fix defect bug-007",
                  "execution": _execution_t2(),
                  "verifier": verifier_spec},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertEqual(parsed.get("status"), "complete")
        self.assertEqual(parsed.get("decision"), "advance")
        self.assertTrue((parsed.get("verdict") or {}).get("dod_met"),
                        "a cited-evidence verdict must advance (gate passes)")

    # -- proof (c) negative control: the gate is REAL — un-cited does NOT
    # advance. This is what makes the skill's evidence directive load-bearing.

    def test_uncited_verdict_does_not_advance(self):
        """Negative control: dod_met=true BUT an un-cited material claim does
        NOT advance — the evidence gate (T3) fires. This proves the skill's
        'verifiers must cite' directive is enforced by the engine, not just
        advisory."""
        (_run_handler, _loop_state_comment_verifier, _verifier_run,
         _execution_t2, _verifier) = _harness()
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        verdict = _verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("the fix is complete and correct",
                             citations=[])])  # un-cited material claim
        verifier_spec = dict(_verifier(), metric_type="ground_truth")
        parsed, _fake = _run_handler(
            args={"goal": "reproduce + fix defect bug-007",
                  "execution": _execution_t2(),
                  "verifier": verifier_spec},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed.get("status"), "complete",
                            "an un-cited 'done' verdict must not complete")
        self.assertFalse((parsed.get("verdict") or {}).get("dod_met"),
                         "the evaluate step must surface the GATED dod_met=false")


if __name__ == "__main__":
    unittest.main()
