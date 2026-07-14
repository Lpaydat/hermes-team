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


if __name__ == "__main__":
    unittest.main()
