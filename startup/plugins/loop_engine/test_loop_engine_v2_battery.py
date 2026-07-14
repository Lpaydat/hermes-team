#!/usr/bin/env python3
"""
TDD tests for loop_engine v2 — held-out battery card (terminal independent gate),
bead hermes-teams-17p (B6 / SPEC §4 T5; design ticket hermes-teams-be2).

This is the autoresearch anti-overfitting defense: a proxy metric is gameable, so
a proxy phase that passes its per-phase verifier MUST ALSO pass a disjoint,
independently-run held-out battery before it may advance. The battery is a
SEPARATE CARD dispatched to the battery spec's ``runner`` profile — NEVER the
phase exec agent — and is a TERMINAL gate (both must pass; battery fail -> replan
the phase with the battery's gaps fed back).

Contract under test (SPEC §4 / be2 comment — the SPEC-clear CORE):
  * Terminal gate, both pass -> advance (per-phase verifier advance AND battery
    advance).
  * Terminal gate, battery FAILS -> replan the phase (the proxy was overfit) with
    the battery's gaps fed back. THIS IS THE WHOLE POINT.
  * Per-phase verifier fails -> battery card is NEVER created (don't run the
    expensive independent gate when the cheap one already failed).
  * Independence: battery card dispatched to the battery spec's ``runner``,
    NOT the phase exec agent.
  * Battery verdict is an evidence-cited dod_verdict (B4); it is run through the
    evidence gate (an un-cited material claim trips -> replan).
  * Battery card idempotency: a re-invocation for the same (phase, iteration)
    does NOT mint a second battery card (distinct role="battery" idempotency key;
    re-park on the existing in-flight battery).
  * Zero-regression (structural): a ground_truth phase (or a phase with no
    battery) advancing via its per-phase verifier -> advances normally, NO battery
    card created. Proves the 204 baseline is preserved by construction.

These tests run WITHOUT a live kanban DB: they mock kanban_db via the FakeKanbanDB
harness established in test_loop_engine.py (same pattern as the B3 discover / B4
evidence v2 tests). The seam is the public ``loop_engine`` entrypoint; assertions
are on external board state + the returned JSON.
"""

import json
import sys
import unittest
from pathlib import Path

# -- Path setup (mirror test_loop_engine.py: import loop_engine as a PACKAGE) ----
PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))
sys.path.insert(0, str(PLUGIN_DIR))  # so the sibling test_loop_engine module imports

import loop_engine  # noqa: E402  (package; register() callable)
from loop_engine import tools as le_tools  # noqa: E402

# Reuse the established mock harness (FakeKanbanDB + drive helpers) — the same
# reuse pattern as test_loop_engine_v2_discover.py / test_loop_engine_v2_evidence.py.
from test_loop_engine import (  # noqa: E402
    FakeKanbanDB, _FakeRun, _Comment, _run_with_fake,
    _execution_t2, _verifier, _dod_verdict, _verifier_run,
    _create_calls_new,
)


# =============================================================================
# Builders for battery fixtures
# =============================================================================

def _cite(locator="verifier/secrets/dc-val-battery.md:12",
          artifact_type="file_line", quote=None):
    """A Citation dict (the T1 primitive)."""
    c = {"artifact_type": artifact_type, "locator": locator}
    if quote is not None:
        c["quote"] = quote
    return c


def _claim(text, citations=None, material=True):
    """A Claim dict (text + its supporting citations)."""
    return {"text": text,
            "citations": citations if citations is not None else [],
            "material": material}


def _proxy_verifier(battery_runner="verifier",
                    battery_path="verifier/secrets/dc-val-battery.md",
                    assignee="proxy-eval"):
    """A proxy-metric verifier spec carrying a well-formed battery (B5 shape)."""
    return {
        "assignee": assignee,
        "title": "verify (proxy metric)",
        "body": "DoD: proxy metric met. Write dod_verdict.",
        "metric_type": "proxy",
        "battery": {"path": battery_path, "runner": battery_runner},
    }


def _gt_verifier(assignee="gt-eval"):
    """A ground-truth verifier spec (no battery needed — infallible metric)."""
    return {
        "assignee": assignee,
        "title": "verify (ground truth)",
        "body": "DoD: tests pass. Write dod_verdict.",
        "metric_type": "ground_truth",
    }


def _battery_verdict(dod_met, recommendation=None, evidence=None, gaps=None):
    """A battery dod_verdict (the battery card is itself a verifier — SPEC §4)."""
    if recommendation is None:
        recommendation = "advance" if dod_met else "replan"
    v = {"dod_met": dod_met, "recommendation": recommendation}
    v["gaps"] = (gaps if gaps is not None else
                 ([] if dod_met
                  else [{"dimension": "held-out-battery",
                         "issue": "a held-out check the proxy leaked"}]))
    if evidence is not None:
        v["evidence"] = evidence
    return v


def _battery_run(verdict, task_id="t_batt", summary="battery evaluated"):
    """A _FakeRun whose metadata carries the battery's dod_verdict."""
    return _FakeRun(task_id=task_id, summary=summary,
                    metadata={"dod_verdict": verdict}, outcome="completed")


def _battery_loop_state_comment(root_id="t_root", execution_card="t_exec",
                                verifier_card="t_verifier",
                                iteration_counter=1, max_iterations=5,
                                resolved_runner="developer"):
    """Pre-seed loop_state at the per-phase-verifier reinvoke point (driver parked
    on the verifier; the verifier is about to be read). Single-phase (no ``phases``
    key -> _resolve_phase_specs returns the args' execution/verifier)."""
    payload = json.dumps({
        "key": "loop_state",
        "value": {
            "phase_index": 0,
            "iteration_counter": iteration_counter,
            "terminal_ids": [verifier_card],
            "execution_card": execution_card,
            "verifier_card": verifier_card,
            "max_iterations": max_iterations,
            "resolved_runner": resolved_runner,
        },
    })
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


def _battery_card_creates(fake):
    """create_task calls that minted a BATTERY card (role='battery' idempotency
    key + parents present)."""
    return [kw for kw in _create_calls_new(fake)
            if (kw.get("idempotency_key") or "").endswith(":battery")]


# =============================================================================
# 1. Terminal gate — both pass -> advance
# =============================================================================

class TestBatteryTerminalGateBothPass(unittest.TestCase):
    """Per-phase verifier advances AND battery advances -> phase advances. The
    battery is an ADDITIONAL terminal gate; both must pass."""

    def test_both_pass_advances_to_complete(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt"],
                            preseed_comments={"t_root": [seeded]})
        # Per-phase (proxy) verifier PASSES the proxy DoD.
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True, recommendation="advance"))

        # 1) Re-invoke: verifier advance on a proxy phase -> dispatch the battery
        #    card (independent runner), park the driver on it. NOT complete yet.
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1.get("status"), "blocked",
                         "a proxy advance dispatches the battery, not completes")
        self.assertEqual(p1.get("battery_state"), "pending")
        self.assertEqual(p1.get("battery_card"), "t_batt")
        self.assertEqual(p1.get("terminal_ids"), ["t_batt"])

        # 2) Battery PASSES its own held-out checks -> now the phase may advance.
        fake.run_for_task["t_batt"] = _battery_run(
            _battery_verdict(dod_met=True, recommendation="advance"))

        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2.get("status"), "complete",
                         "both gates pass -> phase advances to complete")
        self.assertEqual(p2.get("decision"), "advance")


# =============================================================================
# 2. Terminal gate — battery FAILS -> replan the phase (the overfit catch)
# =============================================================================

class TestBatteryFailReplansPhase(unittest.TestCase):
    """The whole point of B6: a proxy 'success' that FAILS the held-out battery
    forces a replan of the phase, with the battery's gaps fed back."""

    def test_battery_fail_replans_with_battery_gaps(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        # Replan will mint a fresh exec + verifier for iteration 2.
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt",
                                        "t_exec2", "t_verifier2"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True, recommendation="advance"))
        _run_with_fake(fake, args)  # 1) verifier advance -> dispatch battery

        # Battery FAILS: the held-out check caught an overfit the proxy missed.
        battery_gaps = [{"dimension": "secret-leakage",
                         "issue": "API key exfiltration not caught by proxy"}]
        fake.run_for_task["t_batt"] = _battery_run(
            _battery_verdict(dod_met=False, recommendation="replan",
                             gaps=battery_gaps))

        # 2) Battery re-invoke: battery fail -> replan the phase.
        p2, _ = _run_with_fake(fake, args)
        self.assertNotEqual(p2.get("status"), "complete",
                            "battery fail must NOT advance/complete")
        self.assertEqual(p2.get("decision"), "replan",
                         "battery fail -> replan the phase (proxy was overfit)")
        self.assertEqual(p2.get("iteration"), 2,
                         "replan advances the iteration counter")
        # The battery's gaps are fed back into the replan verdict.
        verdict_blob = json.dumps(p2.get("verdict") or {})
        self.assertIn("secret-leakage", verdict_blob,
                      "the battery's gaps drive the replan")

    def test_battery_fail_creates_fresh_exec_and_verifier(self):
        """Battery-fail replan mints a fresh execution + verifier card (the proxy
        loop re-runs and will be re-checked by a fresh battery next iteration)."""
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt",
                                        "t_exec2", "t_verifier2"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True))
        _run_with_fake(fake, args)  # dispatch battery
        fake.run_for_task["t_batt"] = _battery_run(
            _battery_verdict(dod_met=False))

        _run_with_fake(fake, args)  # battery fail -> replan

        # A fresh exec + verifier card were created for iteration 2 (the preseeded
        # exec/verifier were planted in loop_state, not created via create_task, so
        # the replan's cards are the ONLY exec/verify creates here).
        exec_creates = [kw for kw in _create_calls_new(fake)
                        if (kw.get("idempotency_key") or "").endswith(":exec")]
        verify_creates = [kw for kw in _create_calls_new(fake)
                          if (kw.get("idempotency_key") or "").endswith(":verify")]
        self.assertGreaterEqual(len(exec_creates), 1,
                                "replan minted a fresh execution card")
        self.assertGreaterEqual(len(verify_creates), 1,
                                "replan minted a fresh verifier card")


# =============================================================================
# 3. Per-phase verifier fails -> battery NOT dispatched
# =============================================================================

class TestVerifierFailsBatteryNotDispatched(unittest.TestCase):
    """Don't run the expensive independent battery gate when the cheap per-phase
    verifier already failed — the phase is replanning regardless."""

    def test_verifier_replan_creates_no_battery_card(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_exec2", "t_verifier2"],
                            preseed_comments={"t_root": [seeded]})
        # Per-phase verifier FAILS (proxy DoD not met) -> replan directly.
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=False, recommendation="replan"))

        p, _ = _run_with_fake(fake, args)

        # No battery card was created.
        self.assertEqual(_battery_card_creates(fake), [],
                         "battery card must NOT be created when the per-phase "
                         "verifier already failed")
        self.assertNotIn("battery_card", p,
                         "no battery in the response when the verifier failed")


# =============================================================================
# 4. Independence — battery dispatched to the runner, NOT the phase exec agent
# =============================================================================

class TestBatteryIndependence(unittest.TestCase):
    """The battery card's assignee is the battery spec's ``runner`` profile —
    NEVER the phase exec agent. This is what makes the held-out check hard to
    game (autoresearch: 'independent evaluator, not the agent that produced the
    artifact')."""

    def test_battery_card_assignee_is_runner_not_exec(self):
        # Exec agent = 'developer'; battery runner = 'verifier' (independent).
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment(resolved_runner="developer")
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True))

        _run_with_fake(fake, args)  # dispatch battery

        batt = _battery_card_creates(fake)
        self.assertTrue(batt, "a battery card was created")
        assignee = batt[0]["assignee"]
        self.assertEqual(assignee, "verifier",
                         "battery card dispatched to the battery spec's runner")
        self.assertNotEqual(assignee, "developer",
                            "battery runner must NOT be the phase exec agent")


# =============================================================================
# 5. Battery verdict is evidence-cited + run through the evidence gate
# =============================================================================

class TestBatteryVerdictEvidenceGate(unittest.TestCase):
    """The battery card returns its own evidence-cited dod_verdict (B4/T3); the
    engine runs it through the evidence gate. A cited battery verdict advances;
    an UN-CITED material claim trips the gate -> replan."""

    def test_cited_battery_verdict_advances(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True))
        _run_with_fake(fake, args)  # dispatch battery

        # Battery passes WITH a cited material claim (evidence gate passes).
        fake.run_for_task["t_batt"] = _battery_run(_battery_verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("no secret leakage in the held-out traces",
                             citations=[_cite("verifier/secrets/dc-val-battery.md:7",
                                              quote="no API keys")])]))

        p, _ = _run_with_fake(fake, args)
        self.assertEqual(p.get("status"), "complete",
                         "a cited battery verdict advances")

    def test_uncited_material_battery_claim_trips_gate_to_replan(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt",
                                        "t_exec2", "t_verifier2"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True))
        _run_with_fake(fake, args)  # dispatch battery

        # Battery self-reports dod_met=True but its material claim is UN-CITED ->
        # the evidence gate forces dod_met=False -> replan (not advance).
        fake.run_for_task["t_batt"] = _battery_run(_battery_verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("held-out checks all pass", citations=[])]))

        p, _ = _run_with_fake(fake, args)
        self.assertNotEqual(p.get("status"), "complete",
                            "an un-cited material battery claim must NOT advance")
        self.assertEqual(p.get("decision"), "replan",
                         "evidence-gate trip on the battery verdict -> replan")


# =============================================================================
# 6. Battery card idempotency — no duplicate battery card on re-invocation
# =============================================================================

class TestBatteryCardIdempotency(unittest.TestCase):
    """A re-invocation for the same (phase, iteration) does NOT mint a second
    battery card. The battery carries a stable role='battery' idempotency key, and
    a re-invoke while the battery is still in-flight re-parks on the EXISTING card
    (mirrors the verifier/discover card pattern)."""

    def test_reinvoke_inflight_battery_reparks_no_duplicate(self):
        verifier = _proxy_verifier(battery_runner="verifier")
        args = {"goal": "ship the design",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root", "t_batt"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True))

        _run_with_fake(fake, args)  # dispatch battery -> t_batt created
        self.assertEqual(len(_battery_card_creates(fake)), 1,
                         "exactly one battery card after dispatch")

        # Battery still IN-FLIGHT (not done) -> re-invoke re-parks, no duplicate.
        fake._task_status["t_batt"] = "ready"
        p2, _ = _run_with_fake(fake, args)

        self.assertEqual(len(_battery_card_creates(fake)), 1,
                         "re-invoke did NOT mint a second battery card")
        self.assertNotEqual(p2.get("battery_state"), "pending",
                            "in-flight battery re-invoke re-parks (no re-dispatch)")


# =============================================================================
# 7. Zero-regression — ground_truth / no-battery phase advances unchanged
# =============================================================================

class TestZeroRegressionGroundTruth(unittest.TestCase):
    """A ground_truth phase (or any phase with no battery) advancing via its
    per-phase verifier advances normally and creates NO battery card. This proves
    the 204 baseline is structurally preserved: battery cards materialize ONLY for
    metric_type=proxy phases that carry a battery spec."""

    def test_ground_truth_advances_no_battery_card(self):
        verifier = _gt_verifier()
        args = {"goal": "fix the bug",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True, recommendation="advance"))

        p, _ = _run_with_fake(fake, args)

        self.assertEqual(p.get("status"), "complete",
                         "ground_truth phase advances normally")
        self.assertEqual(p.get("decision"), "advance")
        self.assertEqual(_battery_card_creates(fake), [],
                         "NO battery card created for a ground_truth phase")

    def test_no_metric_type_advances_no_battery_card(self):
        # A v1 verifier (no metric_type at all) is the default-compat case.
        verifier = _verifier(assignee="verifier")  # no metric_type/battery
        args = {"goal": "fix the bug",
                "execution": _execution_t2(assignee="developer"),
                "verifier": verifier}
        seeded = _battery_loop_state_comment()
        fake = FakeKanbanDB(create_ids=["t_root"],
                            preseed_comments={"t_root": [seeded]})
        fake.run_for_task["t_verifier"] = _verifier_run(
            _dod_verdict(dod_met=True, recommendation="advance"))

        p, _ = _run_with_fake(fake, args)

        self.assertEqual(p.get("decision"), "advance")
        self.assertEqual(_battery_card_creates(fake), [],
                         "NO battery card created when no metric_type is declared")


if __name__ == "__main__":
    unittest.main()
