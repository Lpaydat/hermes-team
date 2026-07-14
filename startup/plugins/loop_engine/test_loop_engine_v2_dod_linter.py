#!/usr/bin/env python3
"""
TDD red-green tests for B9 — loop_engine v2 DoD-checkability linter (T8).

Design authority: SPEC.md §6 (T8) + bd hermes-teams-cqv comment.
  * INPUT-side linter, SYMMETRIC to the OUTPUT-side ``_validate_dod_artifact``
    gate (which lints a verdict's artifact at decide-time). T8 lints the DoD
    DECLARATION at call time, before any card is created.
  * THE CHECKABILITY RULE: a checkable DoD declares >=1 measurable
    ``DoDSignal{artifact_type, locator, expectation?}`` (artifact_type reuses
    the T1 open enum + the NEW ``count`` type). Pure-prose DoDs (no signals)
    are WARNED in compat (default; loop proceeds — zero-regression) and
    HARD-FAILED when ``strict_dod`` is opted in. Present-but-malformed signals
    always hard-fail (the consumer opted into structure).
  * STRUCTURED ERRORS: a rejection carries
    ``{phase_index, field, expected, got, hint}`` so the driver self-corrects on
    retry. The flat top-level ``{"error": str}`` shape is PRESERVED (the
    structured ``validation`` block is ADDITIVE) — nothing that parses today
    breaks.

These tests run WITHOUT a kanban DB: they exercise the validation seam
(``_validate`` / ``_validate_phases`` / the ``_validate_dod_signals`` linter)
directly — the same gate the handler calls at tools.py
(``err = _validate(args); if err: return json.dumps({"error": err})``) and
which is therefore exactly where "the loop refuses to run" is decided. A
REJECTION returns from the handler before any DB/task-id work, so the
structured-shape test drives the handler end-to-end with no board.
"""

import json
import sys
import unittest
from pathlib import Path

# Import loop_engine as a PACKAGE (parent dir on sys.path) so __init__.py's
# `from . import schemas, tools` resolves — mirrors how the plugin loader
# imports plugins (same setup as test_loop_engine.py / the B5 metric_type suite).
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/loop_engine
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine as le_init                         # noqa: F401  (registers plugin)
from loop_engine import tools as le_tools
from loop_engine import schemas as le_schemas


# ── minimal self-contained builders (no dependency on other test files) ──────

def _execution():
    """A minimal valid execution step."""
    return {"title": "build the thing", "body": "ship it", "assignee": "developer"}


def _verifier(**overrides):
    """A minimal valid verifier step. By default this is a PURE-PROSE DoD (body
    only, no ``dod_signals``) — the v1 shape. ``dod_signals`` / ``strict_dod``
    are added via overrides."""
    v = {"title": "verify the thing",
         "body": "DoD: the thing works. Write dod_verdict.",
         "assignee": "verifier"}
    v.update(overrides)
    return v


# ── the linter seam: the checkability rule, directly ─────────────────────────


class DodSignalsLinterTest(unittest.TestCase):
    """``_validate_dod_signals`` — the INPUT-side checkability rule, exercised
    directly (the primitive both _validate and _validate_phases wire in)."""

    # Case 1 — checkable DoD (a real measurable signal): ACCEPTED.
    def test_checkable_dod_with_signal_accepted(self):
        sig = le_tools._validate_dod_signals(
            {"body": "DoD: tests pass.",
             "dod_signals": [{"artifact_type": "test_output",
                              "locator": "pytest -q",
                              "expectation": "passes"}]},
            "verifier", strict_dod=False)
        self.assertIsNone(sig)

    # Case 2 — the NEW `count` artifact_type: ACCEPTED (proves the enum extension).
    def test_count_signal_accepted(self):
        # `count` is now a first-class seed enum member (numeric threshold/
        # occurrence — a cross-domain measurable, not a domain extension).
        self.assertIn("count", le_schemas.known_artifact_types())
        sig = le_tools._validate_dod_signals(
            {"body": "DoD: no TODOs left.",
             "dod_signals": [{"artifact_type": "count",
                              "locator": "grep -c TODO src/",
                              "expectation": "0 matches"}]},
            "verifier", strict_dod=False)
        self.assertIsNone(sig)

    # Case 3 — pure-prose DoD, COMPAT (default): WARNED, NOT rejected.
    # The linter returns a WARN (severity=warn); the loop proceeds (zero-reg).
    def test_pure_prose_compat_warns_not_rejects(self):
        sig = le_tools._validate_dod_signals(
            {"body": "the design is good"}, "verifier", strict_dod=False)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.get("severity"), "warn")
        self.assertIn("validation", sig)
        # And _validate does NOT reject it (compat tier -> loop proceeds).
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier()})
        self.assertIsNone(err)

    # Case 4 — pure-prose DoD, STRICT (strict_dod opt-in): HARD-FAILED.
    # THIS (paired with case 3) is the core: same prose DoD, strict -> rejected.
    def test_pure_prose_strict_rejected(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(), "strict_dod": True})
        self.assertIsNotNone(err)
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")
        self.assertIn("dod_signals", json.dumps(err))

    # Case 5 — present but malformed (signal with no locator): structured error.
    def test_malformed_signal_no_locator_rejected(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(
                 dod_signals=[{"artifact_type": "file_line"}])})
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")
        self.assertIn("locator", json.dumps(err))

    # Case 6 — unknown artifact_type: structured error.
    def test_unknown_artifact_type_rejected(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(
                 dod_signals=[{"artifact_type": "bogus_type",
                               "locator": "x"}])})
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")
        self.assertIn("artifact_type", json.dumps(err))

    # Case 7 — STRUCTURED ERROR SHAPE: rejection carries
    # {phase_index, field, expected, got, hint} AND the flat top-level
    # {"error": str} is PRESERVED (additive). Driven through the HANDLER
    # end-to-end (a rejection returns before any DB/task-id work).
    def test_structured_error_shape_flat_error_preserved(self):
        resp = le_tools.loop_engine(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(
                 dod_signals=[{"artifact_type": "bogus_type",
                               "locator": "x"}])})
        out = json.loads(resp)
        # (a) flat top-level error preserved (back-compat).
        self.assertIn("error", out)
        self.assertIsInstance(out["error"], str)
        self.assertTrue(out["error"])
        # (b) structured validation block is ADDITIVE.
        self.assertIn("validation", out)
        v = out["validation"]
        for key in ("phase_index", "field", "expected", "got", "hint"):
            self.assertIn(key, v, f"validation block missing {key!r}")
        self.assertIsNone(v["phase_index"])  # single-phase -> null phase_index

    # Case 8 — ZERO-REGRESSION (CRITICAL): an existing v1-shape call (prose DoD,
    # no dod_signals, no strict_dod) proceeds unchanged — the 214 baseline holds.
    def test_zero_regression_v1_shape_proceeds(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier()})
        self.assertIsNone(err)

    # Case 8b — empty dod_signals array (present but empty): always hard-fail
    # (the consumer opted into structure by providing the key).
    def test_empty_dod_signals_array_rejected(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(dod_signals=[])})
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")

    # Case 8c — strict_dod is ALSO a per-verifier flag (not only top-level).
    def test_strict_dod_per_verifier_rejects_pure_prose(self):
        err = le_tools._validate(
            {"goal": "fix the bug", "execution": _execution(),
             "verifier": _verifier(strict_dod=True)})
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")


# ── multi-phase seam: _validate_phases lints EACH phases[i].verifier ──────────


class DodSignalsPhasesLinterTest(unittest.TestCase):
    """``_validate_phases`` lints each ``phases[i].verifier``; the phase_index
    in a structured error is correct. Pure-prose phases are warned (compat) /
    rejected (strict) just like the single-phase path."""

    # Case 9 — EACH phase's verifier is linted; the offending phase's index is
    # reported correctly in the structured block.
    def test_each_phase_verifier_linted_correct_phase_index(self):
        err = le_tools._validate_phases([
            {"execution": _execution(),
             "verifier": _verifier(dod_signals=[
                 {"artifact_type": "test_output", "locator": "pytest -q"}])},
            # phase 1 has an unknown artifact_type -> structured error w/ index 1.
            {"execution": _execution(),
             "verifier": _verifier(dod_signals=[
                 {"artifact_type": "bogus_type", "locator": "x"}])},
        ])
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")
        self.assertEqual(err["validation"]["phase_index"], 1)

    # Multi-phase strict (top-level strict_dod propagates into phases).
    def test_workflow_strict_dod_rejects_pure_prose_in_phases(self):
        err = le_tools._validate_phases([
            {"execution": _execution(), "verifier": _verifier()}],
            strict_dod=True)
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")

    # Multi-phase zero-regression: v1 phases (prose DoDs, no strict_dod) pass.
    def test_pure_prose_phases_compat_proceeds(self):
        err = le_tools._validate_phases([
            {"execution": _execution(), "verifier": _verifier(),
             "max_iterations": 3}])
        self.assertIsNone(err)

    # A warn in an early phase MUST NOT mask a hard error in a later phase
    # (warns are non-blocking; the linter keeps checking).
    def test_warn_does_not_mask_later_error_in_phases(self):
        err = le_tools._validate_phases([
            # phase 0: pure-prose -> WARN (compat, non-blocking).
            {"execution": _execution(), "verifier": _verifier()},
            # phase 1: malformed -> hard ERROR (must surface, not be masked).
            {"execution": _execution(),
             "verifier": _verifier(dod_signals=[
                 {"artifact_type": "file_line"}])}])
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get("severity"), "error")
        self.assertEqual(err["validation"]["phase_index"], 1)


if __name__ == "__main__":
    unittest.main()
