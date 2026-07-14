#!/usr/bin/env python3
"""
TDD red-green tests for B5 — loop_engine v2 metric-typing (T4).

Design authority: SPEC.md §4 (T4/T5) + bd hermes-teams-h40 comment.
  * ``metric_type`` is a VERIFIER-SPEC field (parallel to assignee/title/body),
    NOT a dod_verdict field. The verdict is the RESULT; metric_type is the SPEC.
  * Values: ``ground_truth`` (mechanical check — no battery needed) |
            ``proxy`` (judgment/gameable — battery MANDATORY).
  * THE RULE (the autoresearch overfitting guard): a verifier that declares
    ``metric_type: proxy`` WITHOUT a well-formed ``battery`` spec is a
    VALIDATION ERROR — the loop REFUSES to run. Proxy-without-battery is the
    exact failure this layer exists to prevent.
  * Default-compat (zero-regression): a verifier that declares NO metric_type
    is accepted unchanged. "Required" = the proxy->battery rule is enforced
    when proxy is declared; existing v1 phases/tests are unaffected.

These tests run WITHOUT a kanban DB: they exercise the validation seam
(``_validate`` / ``_validate_phases``) directly — the same gate the handler
calls at tools.py:1102 (``err = _validate(args); if err: return {"error": err}``)
and which therefore is exactly where "the loop refuses to run" is decided.
"""

import sys
import unittest
from pathlib import Path

# Import loop_engine as a PACKAGE (parent dir on sys.path) so __init__.py's
# `from . import schemas, tools` resolves — mirrors how the plugin loader
# imports plugins (same setup as test_loop_engine.py).
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/loop_engine
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine as le_init                        # noqa: F401  (registers plugin)
from loop_engine import tools as le_tools


# ── minimal self-contained builders (no dependency on other test files) ──────

def _execution():
    """A minimal valid execution step."""
    return {"title": "build the thing", "body": "ship it", "assignee": "developer"}


def _verifier(**overrides):
    """A minimal valid verifier step; metric_type/battery added via overrides."""
    v = {"title": "verify the thing",
         "body": "DoD: tests pass; no regressions. Write dod_verdict.",
         "assignee": "verifier"}
    v.update(overrides)
    return v


class MetricTypeValidationTest(unittest.TestCase):
    """The proxy->battery rule, exercised at the single-phase _validate seam."""

    # Case 1 — ground_truth + NO battery: ACCEPTED (mechanical checks need none).
    def test_ground_truth_no_battery_accepted(self):
        err = le_tools._validate({
            "goal": "fix the bug", "execution": _execution(),
            "verifier": _verifier(metric_type="ground_truth")})
        self.assertIsNone(err)

    # Case 2 — proxy + well-formed battery: ACCEPTED.
    def test_proxy_with_battery_accepted(self):
        err = le_tools._validate({
            "goal": "grade the design", "execution": _execution(),
            "verifier": _verifier(
                metric_type="proxy",
                battery={"path": "verifier/secrets/dc-val-battery.md",
                         "runner": "verifier"})})
        self.assertIsNone(err)

    # Case 3 — THE RULE: proxy + NO battery -> VALIDATION ERROR (overfitting guard).
    def test_proxy_without_battery_rejected(self):
        err = le_tools._validate({
            "goal": "grade the design", "execution": _execution(),
            "verifier": _verifier(metric_type="proxy")})
        self.assertIsNotNone(err)
        self.assertIn("battery", err)

    # Case 4 — proxy + malformed battery (missing path/runner) -> VALIDATION ERROR.
    def test_proxy_with_malformed_battery_rejected(self):
        err = le_tools._validate({
            "goal": "grade the design", "execution": _execution(),
            "verifier": _verifier(metric_type="proxy", battery={})})
        self.assertIsNotNone(err)
        self.assertIn("battery", err)

    # Case 5 — default-compat (zero-regression): NO metric_type -> ACCEPTED.
    def test_no_metric_type_accepted_default_compat(self):
        err = le_tools._validate({
            "goal": "fix the bug", "execution": _execution(),
            "verifier": _verifier()})
        self.assertIsNone(err)

    # Case 6 — field placement: metric_type is a VERIFIER-spec field, not on the
    # execution step (and not on a dod_verdict). A metric_type placed on the
    # EXECUTION spec is IGNORED; the verifier declares none -> default-compat.
    def test_metric_type_on_execution_is_ignored(self):
        err = le_tools._validate({
            "goal": "grade the design",
            "execution": dict(_execution(), metric_type="proxy"),
            "verifier": _verifier()})  # no metric_type on the verifier spec
        self.assertIsNone(err)


class MetricTypePhasesValidationTest(unittest.TestCase):
    """The proxy->battery rule, exercised at the multi-phase _validate_phases seam
    (the path debug-loop / design-council actually take via ``phases: [...]``)."""

    def test_proxy_without_battery_rejected_in_phases(self):
        err = le_tools._validate_phases([
            {"execution": _execution(),
             "verifier": _verifier(metric_type="proxy")}])
        self.assertIsNotNone(err)
        self.assertIn("battery", err)

    def test_proxy_with_battery_accepted_in_phases(self):
        err = le_tools._validate_phases([
            {"execution": _execution(),
             "verifier": _verifier(
                 metric_type="proxy",
                 battery={"path": "dc-val-battery.md", "runner": "verifier"})}])
        self.assertIsNone(err)

    # Zero-regression at the phases seam: existing debugger v1 phases (no
    # metric_type) pass _validate_phases unchanged.
    def test_no_metric_type_accepted_in_phases(self):
        err = le_tools._validate_phases([
            {"execution": _execution(), "verifier": _verifier(),
             "max_iterations": 3}])
        self.assertIsNone(err)


class MetricTypeNotADodVerdictFieldTest(unittest.TestCase):
    """metric_type lives on the verifier SPEC, not on the returned dod_verdict
    (the verdict is the RESULT). The rule reads the spec; a verdict's
    spurious metric_type is never consulted by the config validator."""

    def test_unknown_metric_type_value_rejected(self):
        # Only ground_truth | proxy are valid; a typo is a validation error.
        err = le_tools._validate({
            "goal": "grade the design", "execution": _execution(),
            "verifier": _verifier(metric_type="judgement")})
        self.assertIsNotNone(err)
        self.assertIn("metric_type", err)

    def test_battery_ignored_when_metric_type_ground_truth(self):
        # A ground_truth metric ignores any battery field (mechanical checks
        # need none); even an empty battery is not an error for ground_truth.
        err = le_tools._validate({
            "goal": "fix the bug", "execution": _execution(),
            "verifier": _verifier(metric_type="ground_truth", battery={})})
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
