#!/usr/bin/env python3
"""
TDD tests for loop_engine v2 — the evidence-evaluator (T3, bead hermes-teams-cca).

This is the OUTPUT side of the fact-based loop: it makes ``dod_met`` mean
"DoD met AND every material claim cited", not just a self-claim. Evidence GATES
``dod_met`` (hard-fail on an un-cited material claim, per T1). ``score`` stays
DoD-quality (informational/trend) — evidence is a BINARY gate, not scored.

The engine enforces STRUCTURE only (per T1's re-open contract): it CALLS
``validate_claim`` (the B2 primitive) on each evidence Claim; if any MATERIAL
claim carries zero citations, the verdict's ``dod_met`` is forced false and the
recommendation becomes "replan". The engine does NOT re-open files/run probes
(that is the independent verifier card's job).

Scope under test (the public seam):
  * tools._evidence_gate(verdict)         -> (ok, reason)
  * tools._apply_evidence_gate(verdict)   -> verdict (dod_met/recommendation corrected)

Cutover reconciliation (s54): the gate is REAL on the verifier-returned verdict
path (an un-cited material claim trips it -> dod_met=false -> replan), while the
SCHEMA stays ADDITIVE — a bare v1 verdict (no ``evidence`` key) constructs and
evaluates without error. "Required" = the gate fires on un-cited material, NOT
"the dict key must always be present". This keeps the 167-test baseline green
AND makes the gate real. (s54's hard-cutover applies to the consumer's verifier
returning evidence, not to internal engine fixtures.)
"""

import json
import sys
import unittest
from pathlib import Path

# -- Path setup (mirror test_loop_engine.py: import loop_engine as a PACKAGE) ----
PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))
sys.path.insert(0, str(PLUGIN_DIR))  # so the sibling test_loop_engine module is importable

import loop_engine  # noqa: E402  (package; register() callable)
from loop_engine import tools as le_tools  # noqa: E402


# -- verdict/claim builders ----------------------------------------------------

def _cite(locator="calc.py:10", artifact_type="file_line", quote=None):
    """A structurally-valid Citation dict (the on-the-wire shape)."""
    c = {"artifact_type": artifact_type, "locator": locator}
    if quote is not None:
        c["quote"] = quote
    return c


def _claim(text, citations=None, material=True):
    """A Claim dict. citations defaults to one valid cite (so the claim is
    well-formed unless the test explicitly omits evidence)."""
    return {"text": text,
            "citations": citations if citations is not None else [_cite()],
            "material": material}


def _verdict(dod_met=True, recommendation="advance", score=None, gaps=None,
             evidence=None):
    """Build a dod_verdict as the verifier writes it, with optional v2 fields."""
    v = {"dod_met": dod_met, "recommendation": recommendation}
    if score is not None:
        v["score"] = score
    v["gaps"] = gaps if gaps is not None else []
    if evidence is not None:
        v["evidence"] = evidence
    return v


# =============================================================================
# _evidence_gate / _apply_evidence_gate — the binary evidence gate (T3)
# =============================================================================

class TestEvidenceGatePositive(unittest.TestCase):
    """The gate PASSES when DoD is met AND every material claim is cited."""

    def test_cited_material_claim_keeps_dod_met_true(self):
        """Case 1 (positive): dod_met=true + material claim WITH a valid
        citation -> dod_met stays true (gate passes)."""
        verdict = _verdict(dod_met=True, recommendation="advance",
                           evidence=[_claim("tests pass for calc.py",
                                            citations=[_cite("calc.py:42",
                                                             quote="assert add(2,3)==5")])])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertTrue(out["dod_met"])
        self.assertEqual(out["recommendation"], "advance")

    def test_many_cited_material_claims_pass(self):
        verdict = _verdict(dod_met=True,
                           evidence=[_claim("c1"), _claim("c2"),
                                     _claim("c3", citations=[_cite("a.py:1"),
                                                             _cite("b.py:2")])])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertTrue(out["dod_met"])


class TestEvidenceGateHardFail(unittest.TestCase):
    """THE POINT: a 'done' verdict with an un-cited material claim does NOT
    advance. The gate trips -> dod_met forced false -> recommendation replan."""

    def test_uncited_material_claim_forces_dod_met_false_and_replan(self):
        """Case 2 (hard-fail): DoD met BUT a material claim has ZERO citations
        -> engine forces dod_met=false, recommendation='replan'."""
        verdict = _verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("the fix is complete and correct",
                             citations=[])])  # material (default True), no cite
        out = le_tools._apply_evidence_gate(verdict)
        self.assertFalse(out["dod_met"],
                         "an un-cited material claim must force dod_met=false")
        self.assertEqual(out["recommendation"], "replan",
                         "a gate-tripped verdict must recommend replan")

    def test_one_uncited_among_many_cited_trips(self):
        """A single un-cited material claim among otherwise-cited claims still
        trips the gate (every material claim must be cited)."""
        verdict = _verdict(
            dod_met=True,
            evidence=[_claim("cited one"),             # ok
                      _claim("uncited material", citations=[]),  # trips
                      _claim("cited two")])             # ok
        out = le_tools._apply_evidence_gate(verdict)
        self.assertFalse(out["dod_met"])
        self.assertEqual(out["recommendation"], "replan")

    def test_gate_does_not_mutate_input_verdict(self):
        """The helper returns a corrected copy; the original verdict's
        self-claim is left intact (the engine's view is corrected, not the
        verifier's record)."""
        verdict = _verdict(dod_met=True, recommendation="advance",
                           evidence=[_claim("x", citations=[])])
        original_dod_met = verdict["dod_met"]
        out = le_tools._apply_evidence_gate(verdict)
        self.assertFalse(out["dod_met"])
        self.assertTrue(original_dod_met, "input verdict must not be mutated")
        self.assertTrue(verdict["dod_met"], "input verdict must not be mutated")


class TestNonMaterialClaimExempt(unittest.TestCase):
    """A non-material claim (material=False) with no citations does NOT trip."""

    def test_nonmaterial_claim_zero_citations_passes(self):
        """Case 3: a framing/contextual claim marked material=False needs no
        citation — it is not load-bearing."""
        verdict = _verdict(
            dod_met=True,
            evidence=[_claim("for context, the module is named calc",
                             citations=[], material=False),
                      _claim("tests pass", citations=[_cite()])])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertTrue(out["dod_met"])
        self.assertEqual(out["recommendation"], "advance")


class TestScoreNotGated(unittest.TestCase):
    """score is informational/trend; evidence is the BINARY gate. A high score
    does NOT rescue an un-cited material claim; a low score does NOT block a
    fully-cited, DoD-met verdict."""

    def test_high_score_uncited_material_still_fails(self):
        """Case 5a: score=5 (max quality) + un-cited material -> dod_met=false.
        score is reported, not routed on; evidence is the gate."""
        verdict = _verdict(
            dod_met=True, recommendation="advance", score=5,
            evidence=[_claim("done", citations=[])])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertFalse(out["dod_met"])
        self.assertEqual(out["recommendation"], "replan")

    def test_low_score_cited_dodmet_advances(self):
        """Case 5b: score=1 (low quality) + full citations + dod_met -> the
        verdict advances (score does not gate; evidence does)."""
        verdict = _verdict(
            dod_met=True, recommendation="advance", score=1,
            evidence=[_claim("shipped", citations=[_cite("RELEASE.md:1")])])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertTrue(out["dod_met"])
        self.assertEqual(out["recommendation"], "advance")


class TestZeroRegressionAdditive(unittest.TestCase):
    """A bare v1 verdict (no evidence key) constructs and evaluates
    without error — the schema is additive, so the 167-test baseline stays
    green. The gate fires only when evidence IS carried."""

    def test_bare_verdict_no_evidence_key_passes_unchanged(self):
        """Case 6: a v1-shaped verdict (the existing fixture shape) constructs
        and evaluates without error; dod_met is unchanged."""
        bare = {"dod_met": True, "score": 3,
                "gaps": [], "recommendation": "advance"}
        out = le_tools._apply_evidence_gate(bare)
        self.assertTrue(out["dod_met"])
        self.assertEqual(out["recommendation"], "advance")
        # no v2 keys were injected into the corrected verdict
        self.assertNotIn("evidence", out)

    def test_bare_verdict_dod_met_false_stays_false(self):
        bare = {"dod_met": False, "gaps": [{"dimension": "x", "issue": "y"}],
                "recommendation": "replan"}
        out = le_tools._apply_evidence_gate(bare)
        self.assertFalse(out["dod_met"])
        self.assertEqual(out["recommendation"], "replan")

    def test_empty_evidence_list_passes(self):
        """An empty evidence list claims nothing -> no material claim to gate ->
        passes (additive: zero claims is not an un-cited claim)."""
        verdict = _verdict(dod_met=True, evidence=[])
        out = le_tools._apply_evidence_gate(verdict)
        self.assertTrue(out["dod_met"])

    def test_none_verdict_passes_through(self):
        """A missing/stale verdict (None) is additive-compat: passed through."""
        out = le_tools._apply_evidence_gate(None)
        self.assertIsNone(out)


# =============================================================================
# Integration: the gate is WIRED into the evaluate step (advance/replan)
# =============================================================================

class TestEvidenceGateWiredIntoEvaluate(unittest.TestCase):
    """Prove the gate trips inside the real evaluate path: a verifier returning
    a dod_met=true verdict with an un-cited material claim does NOT advance
    (the engine replans). Mirrors test_loop_engine.py's FakeKanbanDB harness."""

    def _run_with_seeded_verdict(self, verdict):
        """Seed a driver parked on a done verifier carrying `verdict`, run the
        engine, return (parsed_result, fake)."""
        # Imported lazily so the unit tests above run even if the heavy harness
        # changes shape; the harness is the established e2e pattern.
        from test_loop_engine import (
            _run_handler, _loop_state_comment_verifier, _verifier_run,
            _execution_t2, _verifier,
        )
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        return _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )

    def test_uncited_material_blocks_advance_in_evaluate(self):
        """End-to-end: dod_met=true + recommendation=advance BUT an un-cited
        material claim -> the evaluate step does NOT advance (replans). This is
        the whole point — a 'done' self-claim with no evidence must NOT advance."""
        verdict = _verdict(
            dod_met=True, recommendation="advance", score=5,
            evidence=[_claim("the fix is complete", citations=[])])
        parsed, _fake = self._run_with_seeded_verdict(verdict)
        self.assertNotEqual(parsed.get("status"), "complete",
                            "an un-cited 'done' verdict must not complete")
        self.assertNotEqual(parsed.get("decision"), "advance",
                            "an un-cited 'done' verdict must not advance")
        # The gated verdict surfaced in the result has dod_met corrected to false.
        surfaced = parsed.get("verdict") or {}
        self.assertFalse(surfaced.get("dod_met"),
                         "the evaluate step must surface the GATED dod_met=false")

    def test_cited_evidence_advances_in_evaluate(self):
        """End-to-end positive: dod_met=true + a cited material claim -> the
        evaluate step advances (gate passes inside the real path)."""
        verdict = _verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("tests pass", citations=[_cite("calc.py:42",
                                                            quote="assert ok")])])
        parsed, _fake = self._run_with_seeded_verdict(verdict)
        self.assertEqual(parsed.get("status"), "complete")
        self.assertEqual(parsed.get("decision"), "advance")
        self.assertTrue((parsed.get("verdict") or {}).get("dod_met"))


if __name__ == "__main__":
    unittest.main()
