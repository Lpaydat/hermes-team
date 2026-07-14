#!/usr/bin/env python3
"""
TDD red-green tests for B9/T9 — loop_engine v2 ``strict_fact_basis`` opt-in flag.

Design authority: SPEC.md §7 (T9 migration) + bd hermes-teams-3g2.
MIRRORS the ``strict_dod`` opt-in pattern (B9/T8) EXACTLY:
  * ``strict_fact_basis`` is BOTH a top-level call arg AND a per-verifier-spec
    field (``verifier.strict_fact_basis``) — workflow-wide OR per-verifier,
    either opts the phase in. Default ``False`` = today's additive behavior.
  * Default OFF = zero-regression: the additive gates (B5 ``_validate_metric_type``
    accepts an absent ``metric_type``; B4 ``_evidence_gate`` passes a missing
    ``evidence`` key) keep accepting bare v1 shapes untouched.

THE TWO HARDEN-SEAMS (fire only when the flag opts a phase in):
  1. metric_type (validate-seam): under ``strict_fact_basis`` a verifier spec
     WITHOUT ``metric_type`` is a VALIDATION ERROR — the loop REFUSES to run.
     (Today: absent = accepted, treated ground_truth.)
  2. evidence (evidence-gate): under ``strict_fact_basis`` a verdict WITHOUT an
     ``evidence`` key forces ``dod_met=False`` (hard-fail -> replan; no advance).
     (Today: a missing evidence key passes; un-cited material already trips —
     that behavior is preserved, NOT regressed.)

These tests run WITHOUT a kanban DB: they exercise the two primitive seams
(``_validate`` / ``_validate_phases`` for metric_type; ``_evidence_gate`` /
``_apply_evidence_gate`` for evidence) directly — the same gates the handler
threads at tools.py (``err = _validate(args)`` is where "the loop refuses to
run" is decided; ``_apply_evidence_gate`` is where dod_met is gated). The flag
is the mechanism; a consumer skill (B10 debug-loop) opts in at its coupled
release — it is NOT wired here.
"""

import sys
import unittest
from pathlib import Path

# -- Path setup (mirror test_loop_engine_v2_evidence.py: package import) -------
PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine  # noqa: E402  (package; register() callable)
from loop_engine import tools as le_tools  # noqa: E402


# -- minimal self-contained builders (no dependency on other test files) -------

def _cite(locator="calc.py:42", artifact_type="file_line", quote=None):
    """A structurally-valid Citation dict (the on-the-wire shape)."""
    c = {"artifact_type": artifact_type, "locator": locator}
    if quote is not None:
        c["quote"] = quote
    return c


def _claim(text, citations=None, material=True):
    """A Claim dict. citations defaults to one valid cite (well-formed unless
    the test explicitly omits evidence)."""
    return {"text": text,
            "citations": citations if citations is not None else [_cite()],
            "material": material}


def _verdict(dod_met=True, recommendation="advance", evidence=None):
    """A dod_verdict as the verifier writes it. ``evidence`` omitted => the bare
    v1 shape (no ``evidence`` key) — the additive-gate default path."""
    v = {"dod_met": dod_met, "recommendation": recommendation, "gaps": []}
    if evidence is not None:
        v["evidence"] = evidence
    return v


def _execution():
    return {"title": "build the thing", "body": "ship it"}


def _verifier(**overrides):
    """A minimal valid verifier (pure-prose DoD, no metric_type — the v1 shape).
    metric_type / strict_fact_basis are added via overrides."""
    v = {"title": "verify the thing",
         "body": "DoD: the thing works. Write dod_verdict."}
    v.update(overrides)
    return v


# =============================================================================
# metric_type (validate-seam) — strict_fact_basis hardens the validate gate
# =============================================================================

class TestStrictFactBasisMetricType(unittest.TestCase):
    """``_validate`` / ``_validate_phases``: under ``strict_fact_basis`` a
    verifier WITHOUT ``metric_type`` is REJECTED (the loop refuses to run).
    Default-off keeps accepting bare v1 verifiers (zero-regression)."""

    # Case 1 — strict_fact_basis=True, bare metric_type -> REJECTED at validate.
    def test_strict_rejects_verifier_without_metric_type(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "execution": _execution(),
            "verifier": _verifier(),  # no metric_type
            "strict_fact_basis": True,
        })
        self.assertIsNotNone(err, "strict_fact_basis must reject a bare metric_type")
        self.assertIn("metric_type", str(err))

    # Case 4a (default-off half) — bare metric_type + default -> ACCEPTED.
    def test_default_accepts_verifier_without_metric_type(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "execution": _execution(),
            "verifier": _verifier(),  # no metric_type, no strict_fact_basis
        })
        self.assertIsNone(err, "default-off must accept a bare metric_type unchanged")

    # Case 3a — strict_fact_basis=True, metric_type declared -> ACCEPTED.
    def test_strict_accepts_verifier_with_metric_type(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "execution": _execution(),
            "verifier": _verifier(metric_type="ground_truth"),
            "strict_fact_basis": True,
        })
        self.assertIsNone(err)

    # Mirror strict_dod: the flag is ALSO a per-verifier-spec field.
    def test_per_verifier_strict_rejects_bare_metric_type(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "execution": _execution(),
            "verifier": _verifier(strict_fact_basis=True),  # per-verifier opt-in
        })
        self.assertIsNotNone(err)
        self.assertIn("metric_type", str(err))

    # Multi-phase: workflow-wide strict_fact_basis propagates into phases.
    def test_workflow_strict_rejects_bare_metric_type_in_phases(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "phases": [{"execution": _execution(), "verifier": _verifier()}],
            "strict_fact_basis": True,
        })
        self.assertIsNotNone(err)
        self.assertIn("metric_type", str(err))

    # Multi-phase zero-regression: v1 phases (no metric_type, no flag) proceed.
    def test_default_phases_accept_bare_metric_type(self):
        err = le_tools._validate({
            "goal": "fix the bug",
            "phases": [{"execution": _execution(), "verifier": _verifier()}],
        })
        self.assertIsNone(err)


# =============================================================================
# evidence (evidence-gate) — strict_fact_basis hardens the evidence gate
# =============================================================================

class TestStrictFactBasisEvidenceGate(unittest.TestCase):
    """``_apply_evidence_gate``: under ``strict_fact_basis`` a verdict WITHOUT an
    ``evidence`` key forces ``dod_met=False`` (hard-fail -> replan). Default-off
    keeps passing bare v1 verdicts (zero-regression). Un-cited material trips
    ALWAYS (preserved, not regressed)."""

    # Case 2 — strict_fact_basis=True, bare evidence verdict -> dod_met forced
    # false (hard-fail; doesn't advance).
    def test_strict_bare_verdict_forces_dod_met_false(self):
        bare = _verdict(dod_met=True, recommendation="advance")  # no evidence key
        out = le_tools._apply_evidence_gate(bare, strict_fact_basis=True)
        self.assertFalse(out["dod_met"],
                         "a bare verdict under strict_fact_basis must force "
                         "dod_met=false (no advance on assertion)")
        self.assertEqual(out["recommendation"], "replan")

    # Case 4b (default-off half) — bare evidence verdict + default -> ACCEPTED.
    def test_default_bare_verdict_passes_unchanged(self):
        bare = _verdict(dod_met=True, recommendation="advance")
        out = le_tools._apply_evidence_gate(bare)  # strict_fact_basis defaults False
        self.assertTrue(out["dod_met"], "default-off must pass a bare verdict")
        self.assertEqual(out["recommendation"], "advance")

    # Case 3b — strict_fact_basis=True, full (evidence cited) -> advances.
    def test_strict_cited_evidence_advances(self):
        good = _verdict(dod_met=True, recommendation="advance",
                        evidence=[_claim("tests pass for calc.py",
                                         citations=[_cite("calc.py:42",
                                                          quote="assert add(2,3)==5")])])
        out = le_tools._apply_evidence_gate(good, strict_fact_basis=True)
        self.assertTrue(out["dod_met"], "cited evidence must advance under strict")
        self.assertEqual(out["recommendation"], "advance")

    # Case 5 — strict_fact_basis=True, un-cited material -> still trips.
    # (This already works today; the flag must NOT regress the existing trip.)
    def test_strict_uncited_material_still_trips(self):
        bad = _verdict(dod_met=True, recommendation="advance",
                       evidence=[_claim("the fix is complete", citations=[])])
        out = le_tools._apply_evidence_gate(bad, strict_fact_basis=True)
        self.assertFalse(out["dod_met"], "un-cited material must still trip under strict")
        self.assertEqual(out["recommendation"], "replan")

    # Un-cited material trips under DEFAULT too (the existing behavior, proved
    # unchanged by the new flag).
    def test_default_uncited_material_still_trips(self):
        bad = _verdict(dod_met=True, recommendation="advance",
                       evidence=[_claim("the fix is complete", citations=[])])
        out = le_tools._apply_evidence_gate(bad)
        self.assertFalse(out["dod_met"], "un-cited material must trip by default too")

    # _evidence_gate primitive: strict + bare -> (False, reason).
    def test_evidence_gate_primitive_strict_bare_returns_false(self):
        ok, reason = le_tools._evidence_gate(
            _verdict(dod_met=True), strict_fact_basis=True)
        self.assertFalse(ok)
        self.assertIsInstance(reason, str)
        self.assertIn("evidence", reason)

    # _evidence_gate primitive: default + bare -> (True, None) (additive today).
    def test_evidence_gate_primitive_default_bare_passes(self):
        ok, reason = le_tools._evidence_gate(_verdict(dod_met=True))
        self.assertTrue(ok)
        self.assertIsNone(reason)

    # None verdict passes through under strict too (no verdict to gate).
    def test_strict_none_verdict_passes_through(self):
        out = le_tools._apply_evidence_gate(None, strict_fact_basis=True)
        self.assertIsNone(out)


# =============================================================================
# Evidence-gate vs verifier-output vocabulary reconciliation (bd hermes-teams-lf5)
# =============================================================================
# Review #4 claimed a deadlock: ``_evidence_gate`` checks ``evidence:[Claim]``
# but verifiers emit ``behaviors``/``defect_traces`` (read by
# ``_validate_dod_artifact``) -> the gate "REJECTS correctly-evidenced verdicts
# -> every strict phase needed manual force-advance." The smoke-calc/calc-add
# loop (debugger-smoke, strict_fact_basis=true) CONVERGED AUTONOMOUSLY, which
# contradicts the deadlock claim. These tests pin the resolution: the two gates
# are SEPARATE and BOTH must pass; a verdict that carries a cited defect-coverage
# artifact (``behaviors``/``defect_traces``) but NO ``evidence:[Claim]`` key
# REPLANS under strict (the contract — the artifact does not substitute for the
# fact-basis), and the SAME verdict with cited ``evidence:[Claim]`` ADDED
# ADVANCES (no deadlock). The smoke converged once the verifier emitted proper
# cited Claims; the gate is correct.

class TestEvidenceGateVocabularyReconciliation(unittest.TestCase):
    """Pin that ``evidence:[Claim]`` (evidence gate) and ``behaviors`` /
    ``defect_traces`` (artifact gate) are DISTINCT contracts, and that a
    correctly-evidenced verdict ADVANCES under strict_fact_basis (no false
    reject). Reconciles bd hermes-teams-lf5 review #4 vs the autonomous smoke."""

    # --- helpers: a valid defect-coverage artifact (the design-council shape) --

    def _artifact_verdict(self, dod_met=True, recommendation="advance",
                          evidence=None):
        """A verdict carrying a COMPLETE defect-coverage artifact (behaviors +
        defect_traces, each trace cited + non-latent). This is the shape
        ``_validate_dod_artifact`` accepts when ``artifact_required=True``.
        ``evidence`` omitted => artifact-only (NO evidence key) — the shape the
        review claimed the gate wrongly rejects."""
        v = {
            "dod_met": dod_met,
            "recommendation": recommendation,
            "gaps": [],
            "behaviors": [
                {"id": "B1", "statement": "calc.add returns a+b for all inputs"},
            ],
            "defect_traces": [
                {"behavior_id": "B1",
                 "citation": "test_calc.py:12::assert add(2,3)==5 (passed)",
                 "status": "verified",
                 "fabricated": False},
            ],
        }
        if evidence is not None:
            v["evidence"] = evidence
        return v

    # The reconciliation: artifact-only (no evidence key) REPLANS under strict.
    # Cited defect_traces do NOT satisfy the evidence gate — they are a DIFFERENT
    # gate (defect coverage), not the fact-basis primitive. This is BY DESIGN.
    def test_artifact_only_verdict_replans_under_strict(self):
        v = self._artifact_verdict()  # behaviors+defect_traces, NO evidence key
        out = le_tools._apply_evidence_gate(v, strict_fact_basis=True)
        self.assertFalse(out["dod_met"],
                         "an artifact-only verdict (no evidence:[Claim]) must NOT "
                         "advance under strict — defect_traces are not a substitute "
                         "for the cited-Claim fact basis")
        self.assertEqual(out["recommendation"], "replan")
        self.assertIn("evidence", out["evidence_gate"])

    # The reconciliation (inverse): the SAME artifact verdict WITH cited
    # evidence:[Claim] ADDED ADVANCES under strict. No deadlock — the gate
    # accepts correctly-evidenced verdicts. This is the false-reject the review
    # claimed; it does not occur.
    def test_artifact_plus_cited_evidence_advances_under_strict(self):
        v = self._artifact_verdict(
            evidence=[_claim("the add() flip is fixed: add(2,3)==5",
                             citations=[_cite("test_calc.py:12",
                                              quote="assert add(2,3)==5")])])
        out = le_tools._apply_evidence_gate(v, strict_fact_basis=True)
        self.assertTrue(out["dod_met"],
                        "a verdict carrying BOTH a cited artifact AND cited "
                        "evidence:[Claim] must ADVANCE under strict — no false reject")
        self.assertEqual(out["recommendation"], "advance")
        self.assertNotIn("evidence_gate", out)

    # The two gates compose at the routing seam: advance requires BOTH
    # dod_met (post evidence-gate) AND artifact_complete. Artifact-only fails the
    # evidence gate; artifact+cited-evidence passes both -> the advance condition
    # the handler uses at tools.py ``if dod_met and artifact_complete``.
    def test_routing_composition_artifact_only_blocks_advance(self):
        v = self._artifact_verdict()
        gated = le_tools._apply_evidence_gate(v, strict_fact_basis=True)
        dod_met = bool(gated and gated.get("dod_met"))
        artifact_complete = le_tools._validate_dod_artifact(gated, True)
        self.assertFalse(dod_met and artifact_complete,
                         "artifact-only must NOT satisfy the advance condition")

    def test_routing_composition_artifact_plus_evidence_advances(self):
        v = self._artifact_verdict(
            evidence=[_claim("add() fixed",
                             citations=[_cite("test_calc.py:12")])])
        gated = le_tools._apply_evidence_gate(v, strict_fact_basis=True)
        dod_met = bool(gated and gated.get("dod_met"))
        artifact_complete = le_tools._validate_dod_artifact(gated, True)
        self.assertTrue(dod_met and artifact_complete,
                        "artifact + cited evidence must satisfy the advance condition")

    # Default-off zero-regression: an artifact-only verdict (no evidence key)
    # PASSES the evidence gate when strict is off (additive — the gate fires only
    # when strict opts in or evidence is present-but-malformed).
    def test_artifact_only_passes_under_default(self):
        v = self._artifact_verdict()
        out = le_tools._apply_evidence_gate(v)  # strict_fact_basis defaults False
        self.assertTrue(out["dod_met"],
                        "default-off must pass an artifact-only verdict (additive)")
        self.assertEqual(out["recommendation"], "advance")


# =============================================================================
# per-verifier strict_fact_basis -> loop_state (input/decide symmetry)
# bd hermes-teams-qc4
# =============================================================================
# The validate-seam (metric_type) already ORs the per-verifier flag
# (``_validate`` v_sfb; ``_validate_phases`` pver_sfb), so a per-verifier opt-in
# correctly hard-rejects a bare metric_type at call time. BUT the value
# PERSISTED to loop_state — and therefore read by the DECIDE-time evidence gate
# (``_apply_evidence_gate(..., strict_fact_basis=loop_state.get("strict_fact_basis"))``
# at the discover / verifier / battery decide seams) — was sourced ONLY from
# top-level args (handler ``strict_fact_basis = bool(args.get("strict_fact_basis"))``).
# So a consumer setting ONLY ``verifier.strict_fact_basis=True`` got metric_type
# required (good) but the evidence gate silently DISABLED (bad): an un-cited
# material verdict ADVANCED. These tests pin the SINGLE resolution point that
# feeds loop_state (``_resolve_strict_fact_basis``): the effective flag is
# top-level OR any-verifier OR any-phase-verifier (true wins), so a
# per-verifier-only opt-in reaches the decide-time gate.

class TestPerVerifierStrictFactBasisLoopStateResolution(unittest.TestCase):
    """``_resolve_strict_fact_basis`` is the single resolution point whose result
    is persisted to loop_state and read by the decide-time evidence gate on every
    re-promotion. Per the schema's "per-verifier overrides upward (true wins)"
    promise, a per-verifier-only ``strict_fact_basis=True`` (NO top-level) must
    resolve True so the evidence gate honors it — the decide-time mirror of
    ``test_per_verifier_strict_rejects_bare_metric_type`` (the input half).
    (bd hermes-teams-qc4.)"""

    # THE BUG: a per-verifier-ONLY opt-in (NO top-level) resolves True so the
    # persisted loop_state value honors it at decide-time. Pre-fix the handler
    # read only top-level args -> this returned False -> evidence gate disabled.
    def test_per_verifier_only_resolves_true_single_phase(self):
        args = {"verifier": _verifier(strict_fact_basis=True)}
        self.assertTrue(
            le_tools._resolve_strict_fact_basis(args),
            "a per-verifier-only strict_fact_basis (no top-level) must resolve "
            "True so the decide-time evidence gate honors it")

    # Multi-phase: a per-phase-verifier opt-in aggregates upward (true wins).
    def test_per_verifier_only_resolves_true_multi_phase(self):
        args = {"phases": [
            {"execution": _execution(), "verifier": _verifier()},
            {"execution": _execution(),
             "verifier": _verifier(strict_fact_basis=True)},
        ]}
        self.assertTrue(
            le_tools._resolve_strict_fact_basis(args),
            "any phase's verifier.strict_fact_basis must aggregate upward")

    # Top-level still resolves True (the existing path — zero-regression).
    def test_top_level_resolves_true(self):
        self.assertTrue(le_tools._resolve_strict_fact_basis(
            {"strict_fact_basis": True}))

    # Default-off: no flag anywhere resolves False (additive zero-regression).
    def test_no_flag_anywhere_resolves_false(self):
        self.assertFalse(le_tools._resolve_strict_fact_basis(
            {"verifier": _verifier()}))

    # True wins: top-level True + a per-verifier False still resolves True.
    def test_top_level_true_with_verifier_false_resolves_true(self):
        self.assertTrue(le_tools._resolve_strict_fact_basis(
            {"strict_fact_basis": True,
             "verifier": _verifier(strict_fact_basis=False)}))

    # THE DECIDE-TIME CONSEQUENCE: a workflow with ONLY verifier.strict_fact_basis
    # (no top-level) -> the resolved value reaches the evidence gate -> a bare
    # (no-evidence-key) verdict REPLANS (no advance). Mirrors
    # test_strict_bare_verdict_forces_dod_met_false but with the per-verifier flag
    # routed through the resolution point that feeds loop_state. Pre-fix the gate
    # was silently disabled (resolved False) -> the bare verdict ADVANCED.
    def test_per_verifier_only_bare_verdict_replans_at_decide_time(self):
        args = {"verifier": _verifier(metric_type="ground_truth",
                                      strict_fact_basis=True)}
        resolved = le_tools._resolve_strict_fact_basis(args)
        bare = _verdict(dod_met=True, recommendation="advance")  # no evidence key
        out = le_tools._apply_evidence_gate(bare, strict_fact_basis=resolved)
        self.assertTrue(
            resolved,
            "per-verifier-only opt-in must resolve True (the loop_state value)")
        self.assertFalse(
            out["dod_met"],
            "a bare verdict under a per-verifier-only strict_fact_basis must "
            "force dod_met=false at decide-time (no advance on assertion)")
        self.assertEqual(out["recommendation"], "replan")


if __name__ == "__main__":
    unittest.main()
