#!/usr/bin/env python3
"""
TDD tests for loop_engine v2 — discover (input grounding), bead hermes-teams-4he.

This is the INPUT side of the fact-based loop. discover is the always-on,
engine-governed phase 0 that grounds the goal in evidence BEFORE planning
(SPEC.md §2; design ticket hermes-teams-ldr).

Contract under test (SPEC §2 — the SPEC-clear CORE):
  * Single-call w/ redirect: ``loop_engine({goal, discover:{assignee,dod,
    max_iterations}, phases:[...]})``. Engine runs discover FIRST.
      - discover verdict "scope clear"  -> continue to phases[0].
      - discover verdict "replan"       -> park driver, re-plan from the
        evidence-cited context brief (reuses phase-replan mechanics).
  * Structural fast-pass: goal arriving as ``[Claim]`` WITH citations SKIPS the
    discover worker (already grounded). Bare goal -> discover worker runs.
  * discover output = context brief as ``[Claim]`` on the root blackboard; each
    Claim passes ``validate_claim`` (the B2 primitive). The discover verdict is a
    ``dod_verdict`` (which B4 made carry ``evidence:[Claim]``).
  * Engine default / +1 phase: discover runs as phase 0 (the pre-phase before the
    user's phases[0]).

Ambiguity reconciliation (always-on vs zero-regression, per the bead brief):
discover is ALWAYS-ON as a PHYSICAL phase-0 — every loop mints a real discover
card on the board (SPEC §2: "v1 callers get it automatically, +1 phase"; the card
is the visible phase 0 / the skeleton an agent can expand). The card's COST is
adaptive: a cited goal fast-passes (``"skipped"``) and a v1 caller with NO
``discover:`` block + bare goal fast-passes (``"unconfigured"``) — in both cases
the card is minted but RESOLVED as a skeleton (no grounding worker dispatched,
the user's phases[0] runs directly). Only a configured ``discover:`` block
dispatches the grounding worker. This test file PROVES the always-on force (the
v1 case below GETS a physical discover phase-0 card) and its fast-pass (no worker
dispatched, card resolved as a skeleton, response shape otherwise stable).

Ambiguity 1 (invalidation) is FLAGGED, not implemented (SPEC §2 omits it; the ldr
comment describes it but it depends on the ``grounding`` field B4 removed). A
``# TODO(B3-followup)`` seam marks where it would hook.

These tests run WITHOUT a live kanban DB: they mock kanban_db via the FakeKanbanDB
harness established in test_loop_engine.py (the same pattern the B4 evidence tests
use). The seam is the public ``loop_engine`` entrypoint; assertions are on
external board state + the returned JSON.
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

# Reuse the established mock harness (FakeKanbanDB + drive helpers) — the same
# reuse pattern as test_loop_engine_v2_evidence.py.
from test_loop_engine import (  # noqa: E402
    FakeKanbanDB, _FakeRun, _run_handler, _run_with_fake,
    _execution, _execution_t2, _verifier, _create_calls_new, _calls,
)


# =============================================================================
# Builders for discover fixtures
# =============================================================================

def _cite(locator="calc.py:10", artifact_type="file_line", quote=None):
    """A Citation dict (the T1 primitive; reuses the open artifact_type enum)."""
    c = {"artifact_type": artifact_type, "locator": locator}
    if quote is not None:
        c["quote"] = quote
    return c


def _claim(text, citations=None, material=True):
    """A Claim dict (text + its supporting citations)."""
    return {"text": text,
            "citations": citations if citations is not None else [],
            "material": material}


def _discover_spec(assignee="scout",
                   dod="Ground the goal: name the failing test, the module "
                       "under test, and the reproduction command. Cite each.",
                   max_iterations=3):
    """The discover phase config (SPEC §2 contract: assignee + dod + cap)."""
    return {"assignee": assignee, "dod": dod, "max_iterations": max_iterations}


def _discover_verdict(dod_met, recommendation=None, evidence=None):
    """A discover verdict as the discover worker writes it (dod_verdict-shaped).

    The discover verdict IS a dod_verdict (SPEC §2): ``evidence`` carries the
    context brief as [Claim]. recommendation defaults to match dod_met.
    """
    if recommendation is None:
        recommendation = "advance" if dod_met else "replan"
    v = {"dod_met": dod_met, "recommendation": recommendation,
         "gaps": [] if dod_met else [{"dimension": "grounding",
                                      "issue": "under-grounded"}]}
    if evidence is not None:
        v["evidence"] = evidence
    return v


def _discover_run(verdict, task_id="t_discover", summary="discovered"):
    """A _FakeRun whose metadata carries the discover verdict (dod_verdict)."""
    return _FakeRun(task_id=task_id, summary=summary,
                    metadata={"dod_verdict": verdict}, outcome="completed")


def _phase(execution=None, verifier=None, max_iterations=None):
    """A phases[] entry (user phase). Defaults to a verifier-gated phase."""
    p = {"execution": execution or _execution_t2()}
    if verifier is not None:
        p["verifier"] = verifier
    if max_iterations is not None:
        p["max_iterations"] = max_iterations
    return p


def _assignees_in_created(fake):
    """The list of assignees for every create_task that minted a NEW card
    (parents present) — i.e. the worker/verifier cards the engine dispatched."""
    return [kw.get("assignee") for kw in _create_calls_new(fake)]


def _read_context_brief(fake, root_id="t_root"):
    """Read the context_brief [Claim] artifact the engine wrote on the root
    blackboard (uses the REAL read path so the write contract is exercised)."""
    return le_tools._read_blackboard(fake, "fake_conn", root_id, "context_brief")


# =============================================================================
# 1. Single-call redirect — scope clear -> proceed to user phase 0
# =============================================================================

class TestDiscoverScopeClearProceeds(unittest.TestCase):
    """discover verdict = scope clear -> engine proceeds to the user's phases[0]
    (the user-phase exec + verifier cards are built; driver parked on phase-0)."""

    def test_scope_clear_builds_user_phase_0_after_discover(self):
        discover = _discover_spec()
        args = {"goal": "fix the flaky calc test",
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"),
                                  _verifier(assignee="verifier"))]}
        # create_ids: root, discover, then user-phase exec + verifier (built only
        # AFTER discover completes on the re-invoke).
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_discover", "t_exec", "t_verifier"])

        # 1) First call dispatches discover (driver parks on the discover card).
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1.get("status"), "blocked",
                         "first call parks the driver on the discover card")
        self.assertEqual(p1.get("phase"), "discover",
                         "response identifies the active phase as discover")
        self.assertEqual(p1.get("discover_state"), "pending")
        self.assertEqual(p1.get("terminal_ids"), ["t_discover"])

        # No user-phase exec card built yet (only root + discover so far).
        new_before = _assignees_in_created(fake)
        self.assertNotIn("developer", new_before,
                         "user phase 0 must NOT run before discover completes")

        # 2) Seed the discover worker's scope-clear verdict (the context brief
        #    carries one cited material claim — the discover output).
        fake.run_for_task["t_discover"] = _discover_run(_discover_verdict(
            dod_met=True, recommendation="advance",
            evidence=[_claim("the failing test is test_calc at calc/tests/test_calc.py:42",
                             citations=[_cite("calc/tests/test_calc.py:42",
                                              quote="def test_add")])]))

        # 3) Re-invoke: discover done + scope clear -> build user phase 0.
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2.get("status"), "blocked",
                         "after discover scope-clear the driver parks on phase 0")
        # The user-phase exec + verifier cards are now built.
        new_after = _assignees_in_created(fake)
        self.assertIn("developer", new_after,
                      "user phase 0 execution card built after discover completes")
        self.assertIn("verifier", new_after,
                      "user phase 0 verifier card built after discover completes")


# =============================================================================
# 2. Single-call redirect — replan -> re-plan from the context brief
# =============================================================================

class TestDiscoverReplanRedirects(unittest.TestCase):
    """discover verdict = replan (under-grounded) -> driver parked on a FRESH
    discover card (re-plan), and the context brief ([Claim] discoveries) is on
    the root blackboard."""

    def test_replan_parks_on_new_discover_card(self):
        discover = _discover_spec(max_iterations=3)
        args = {"goal": "fix the bug",
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"))]}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_discover", "t_discover2"])

        # 1) First call dispatches discover.
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1.get("discover_card"), "t_discover")

        # 2) Seed an UNDER-GROUNDED replan verdict; the discover worker still
        #    produced a (partial) context brief — one cited claim.
        brief = [_claim("module under test is calc.py",
                        citations=[_cite("calc.py:1", quote="module")])]
        fake.run_for_task["t_discover"] = _discover_run(_discover_verdict(
            dod_met=False, recommendation="replan", evidence=brief))

        # 3) Re-invoke: discover replans -> driver parked on a NEW discover card.
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2.get("status"), "blocked",
                         "replan re-parks the driver (blocked, not complete)")
        self.assertEqual(p2.get("decision"), "replan",
                         "the redirect decision is 'replan'")
        self.assertEqual(p2.get("phase"), "discover")
        self.assertNotEqual(p2.get("discover_card"), "t_discover",
                            "replan mints a FRESH discover card")
        self.assertEqual(p2.get("iteration"), 2,
                         "discover iteration advances to 2 on replan")

    def test_replan_writes_context_brief_on_blackboard(self):
        """The context brief ([Claim] discoveries) lands on the root blackboard
        on replan — the re-plan (and any downstream worker) reads it from there."""
        discover = _discover_spec(max_iterations=3)
        args = {"goal": "fix the bug",
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"))]}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_discover", "t_discover2"])
        _run_with_fake(fake, args)  # dispatch discover

        brief = [_claim("reproducer is `pytest -x calc`",
                        citations=[_cite("calc/tests/test_calc.py:5",
                                         quote="pytest")])]
        fake.run_for_task["t_discover"] = _discover_run(_discover_verdict(
            dod_met=False, recommendation="replan", evidence=brief))
        _run_with_fake(fake, args)  # replan

        stored = _read_context_brief(fake, "t_root")
        self.assertEqual(stored, brief,
                         "the context brief is on the root blackboard on replan")


# =============================================================================
# 3. Structural fast-pass (goal as [Claim] -> discover worker SKIPPED)
# =============================================================================

class TestStructuralFastPass(unittest.TestCase):
    """Goal arriving as [Claim] with citations -> the discover WORKER is SKIPPED
    (the goal is already grounded); the engine proceeds straight to phases[0].
    Bare goal -> the discover worker runs."""

    def test_cited_goal_skips_discover_worker(self):
        # Goal arrives as a cited [Claim] — already grounded.
        goal_claims = [_claim(
            "the bug is a nil-pointer deref in calc.add at calc.py:12",
            citations=[_cite("calc.py:12", quote="return a + b")])]
        discover = _discover_spec()  # configured, but must be SKIPPED
        args = {"goal": goal_claims,
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"),
                                  _verifier(assignee="verifier"))]}
        fake = FakeKanbanDB(create_ids=["t_root", "t_exec", "t_verifier"])

        parsed, fake = _run_handler(args=args, create_ids=[
            "t_root", "t_exec", "t_verifier"])

        # The discover worker (assignee "scout") was NEVER dispatched.
        self.assertNotIn(
            "scout", _assignees_in_created(fake),
            "FAST-PASS: a cited goal must skip the discover worker entirely")
        # The user phase 0 cards ARE built (proceed straight to phases[0]).
        self.assertIn("developer", _assignees_in_created(fake),
                      "FAST-PASS: user phase 0 runs directly")
        # The goal claims themselves ARE the context brief (already grounded).
        self.assertEqual(_read_context_brief(fake, "t_root"), goal_claims,
                         "FAST-PASS: the goal claims become the context brief")

    def test_bare_goal_runs_discover_worker(self):
        discover = _discover_spec()
        args = {"goal": "fix the bug",  # bare string goal
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"))]}
        _run_handler(args=args, create_ids=["t_root", "t_discover"])
        # The discover worker (assignee "scout") IS dispatched for a bare goal.
        # (Re-run against a fresh fake to inspect just the first call.)
        fake = FakeKanbanDB(create_ids=["t_root", "t_discover"])
        from unittest.mock import patch
        with patch.object(le_tools, "_kb", return_value=fake):
            le_tools.loop_engine(args=args, task_id="t_driver")
        self.assertIn("scout", _assignees_in_created(fake),
                      "bare goal -> discover worker runs")


# =============================================================================
# 4. discover output = [Claim] on blackboard; each passes validate_claim
# =============================================================================

class TestDiscoverOutputClaimsOnBlackboard(unittest.TestCase):
    """After discover (scope clear), the root blackboard carries the context
    brief as [Claim]; every Claim passes validate_claim (the B2 primitive)."""

    def test_scope_clear_context_brief_claims_are_valid(self):
        discover = _discover_spec()
        args = {"goal": "fix the bug",
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"))]}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_discover", "t_exec"])
        _run_with_fake(fake, args)  # dispatch discover

        brief = [
            _claim("failing test is test_calc",
                   citations=[_cite("calc/tests/test_calc.py:8", quote="def test")]),
            _claim("root cause is missing None-check",
                   citations=[_cite("calc.py:12", quote="return a + b")]),
        ]
        fake.run_for_task["t_discover"] = _discover_run(_discover_verdict(
            dod_met=True, recommendation="advance", evidence=brief))
        _run_with_fake(fake, args)  # scope clear -> proceed

        stored = _read_context_brief(fake, "t_root")
        self.assertIsInstance(stored, list)
        self.assertGreaterEqual(len(stored), 1)
        for i, claim in enumerate(stored):
            self.assertIsNone(
                le_tools.validate_claim(claim),
                f"context_brief[{i}] must pass validate_claim (B2 primitive); "
                f"got: {le_tools.validate_claim(claim)}")


# =============================================================================
# 5. Engine default / +1 phase — discover runs as phase 0
# =============================================================================

class TestDiscoverRunsAsPhase0(unittest.TestCase):
    """discover runs FIRST (phase 0): when discover is configured, the discover
    card is the terminal and the user's phases[0] cards are NOT built yet."""

    def test_discover_is_phase_0_user_phases_deferred(self):
        discover = _discover_spec()
        args = {"goal": "fix the bug",
                "discover": discover,
                "phases": [_phase(_execution(assignee="developer"),
                                  _verifier(assignee="verifier"))]}
        parsed, fake = _run_handler(args=args, create_ids=[
            "t_root", "t_discover"])

        # discover is the active phase 0.
        self.assertEqual(parsed.get("phase"), "discover")
        self.assertEqual(parsed.get("phase_index"), 0)
        self.assertEqual(parsed.get("discover_state"), "pending")
        # The discover card is the terminal the driver parked on.
        self.assertEqual(parsed.get("terminal_ids"), ["t_discover"])
        self.assertEqual(parsed.get("discover_card"), "t_discover")
        # The user phase 0 worker/verifier are NOT yet dispatched.
        assigns = _assignees_in_created(fake)
        self.assertNotIn("developer", assigns,
                         "user phase 0 deferred until discover completes")
        self.assertNotIn("verifier", assigns,
                         "user phase 0 verifier deferred until discover completes")
        # The discover worker WAS dispatched (phase 0).
        self.assertIn("scout", assigns,
                      "discover worker dispatched as phase 0")


# =============================================================================
# 6. Zero-regression — v1-shape call (no discover block) behaves like today
# =============================================================================

class TestZeroRegressionNoDiscoverBlock(unittest.TestCase):
    """A v1-shape call (no ``discover:`` block, mocked worker) HONORS the
    ALWAYS-ON force: a PHYSICAL discover phase-0 card IS minted on the board
    (visible phase 0) but FAST-PASSES — resolved as a skeleton
    (``discover_state="unconfigured"``), no grounding worker dispatched, and the
    existing phases run directly. SPEC §2: discover is phase 0 for EVERY loop."""

    def test_v1_phases_call_noops_discover(self):
        """Mirror a v1 phases call: no discover block -> a discover phase-0 CARD
        is minted (visible) but FAST-PASSES (resolved skeleton, no worker); the
        user's phase 0 is built directly (driver parks on it)."""
        args = {"goal": "ship the thing",  # bare goal, NO discover block
                "phases": [_phase(_execution(assignee="developer"),
                                  _verifier(assignee="verifier"))]}
        parsed, fake = _run_handler(args=args, create_ids=[
            "t_root", "t_discover", "t_exec", "t_verifier"])

        # Phase 0 built directly (the existing T2 first-invocation behavior).
        self.assertEqual(parsed.get("status"), "blocked")
        self.assertIn("developer", _assignees_in_created(fake))
        self.assertIn("verifier", _assignees_in_created(fake))
        # ALWAYS-ON force: a physical discover phase-0 CARD is minted but
        # FAST-PASSES — discover_state="unconfigured", no grounding worker.
        self.assertEqual(parsed.get("discover_state"), "unconfigured",
                         "always-on: discover phase-0 fast-passes (accounted, "
                         "no worker) for a v1 no-block caller")
        self.assertEqual(parsed.get("discover_card"), "t_discover",
                         "always-on: a physical discover phase-0 card is minted")
        self.assertNotIn("scout", _assignees_in_created(fake),
                         "no discover block -> no discover WORKER (scout)")
        # Transparency: no discover phase field leaks (discover fast-passed; the
        # user phase 0 is the active phase).
        self.assertNotIn("phase", parsed,
                         "v1 response has no 'phase' (discover) field")
        # No context_brief written for a bare-goal no-discover v1 call.
        self.assertIsNone(_read_context_brief(fake, "t_root"))

    def test_v1_single_phase_execution_call_unchanged(self):
        """The T1 single-phase ``execution`` shorthand (no phases, no discover)
        mints the always-on discover phase-0 CARD (fast-pass skeleton); the T1
        spine itself is otherwise unchanged."""
        args = {"goal": "ship it", "execution": _execution()}
        parsed, fake = _run_handler(args=args, create_ids=[
            "t_root", "t_discover", "t_exec"])
        self.assertEqual(parsed.get("status"), "blocked")
        self.assertEqual(parsed.get("execution_card"), "t_exec")
        self.assertNotIn("phase", parsed)
        # always-on force: a physical discover phase-0 card is minted (fast-pass)
        # even for the T1 shorthand.
        self.assertEqual(parsed.get("discover_state"), "unconfigured")
        self.assertEqual(parsed.get("discover_card"), "t_discover")

    def test_discover_always_on_for_bare_goal_v1_caller(self):
        """SPEC §2 ALWAYS-ON (the force): a v1 caller with NO ``discover:`` block
        and a BARE goal STILL gets a PHYSICAL discover phase-0 card on the board
        (visible phase 0). The card FAST-PASSES — resolved as a skeleton
        (``discover_state="unconfigured"``), no grounding worker dispatched — and
        the loop proceeds straight to the user's phases[0]. discover is now phase
        0 for EVERY loop; the fast-pass keeps it cheap when there is nothing to
        ground."""
        args = {"goal": "ship the thing",  # bare goal, NO discover block
                "phases": [_phase(_execution(assignee="developer"),
                                  _verifier(assignee="verifier"))]}
        parsed, fake = _run_handler(args=args, create_ids=[
            "t_root", "t_discover", "t_exec", "t_verifier"])

        # The force: a PHYSICAL discover phase-0 card EXISTS on the board for a
        # bare-goal v1 caller (fast-pass — no discover block was configured).
        self.assertEqual(
            parsed.get("discover_state"), "unconfigured",
            "always-on: discover phase-0 fast-passes (accounted, no worker) "
            "for a bare-goal v1 caller (no discover block configured)")
        self.assertEqual(
            parsed.get("discover_card"), "t_discover",
            "always-on: a physical discover phase-0 card is minted for a "
            "bare-goal v1 caller")
        # The card is physically present (parented on root) + RESOLVED as a
        # fast-pass skeleton (complete_task recorded on it).
        discover_creates = [
            c for c in _create_calls_new(fake)
            if "discover" in (c.get("title") or "")]
        self.assertEqual(
            len(discover_creates), 1,
            "a physical discover phase-0 card is minted on the board")
        discover_completes = [
            c for (c, _kw) in _calls(fake, "complete_task")
            if c[1] == parsed.get("discover_card")]
        self.assertEqual(
            len(discover_completes), 1,
            "the discover card is resolved (fast-pass skeleton)")
        # Structural: loop_state on the blackboard records the discover phase-0.
        loop_state = le_tools._read_blackboard(
            fake, "fake_conn", "t_root", "loop_state")
        self.assertEqual(loop_state.get("discover_state"), "unconfigured")
        self.assertEqual(loop_state.get("discover_card"), "t_discover")

        # The fast-pass dispatches NO grounding worker (no "scout" discover
        # worker; the skeleton card is attributed to the runner, not a worker).
        self.assertNotIn(
            "scout", _assignees_in_created(fake),
            "fast-pass: no discover worker dispatched for an unconfigured "
            "bare-goal caller")
        # The user phase 0 still runs directly (driver parks on it).
        self.assertEqual(parsed.get("status"), "blocked")
        self.assertIn("developer", _assignees_in_created(fake))
        self.assertIn("verifier", _assignees_in_created(fake))
        # Transparency: no discover phase field leaks (discover fast-passed; the
        # user phase 0 is the active phase).
        self.assertNotIn("phase", parsed)
        # No context_brief written (bare goal — no claims to ground).
        self.assertIsNone(_read_context_brief(fake, "t_root"))


# =============================================================================
# Validation seam (goal polymorphism + discover block shape)
# =============================================================================

class TestDiscoverValidation(unittest.TestCase):
    """Goal accepts a non-empty string (v1) OR a non-empty [Claim] array (fast-
    pass). The discover block, when present, must be well-formed."""

    def test_goal_as_string_accepted(self):
        """v1 string goals are accepted unchanged (zero-regression)."""
        args = {"goal": "ship it", "execution": _execution()}
        parsed, _ = _run_handler(args=args, create_ids=["t_root", "t_exec"])
        self.assertNotIn("error", parsed,
                         "a valid v1 string-goal call must not error")

    def test_goal_as_claim_array_with_invalid_claim_rejected(self):
        """A [Claim] goal carrying an un-cited material claim is rejected at
        validation (the goal itself must be grounded to fast-pass)."""
        bad_goal = [_claim("an un-cited material assertion", citations=[])]
        args = {"goal": bad_goal, "execution": _execution()}
        parsed, _ = _run_handler(args=args, create_ids=[])
        self.assertIn("error", parsed)
        self.assertIn("goal[0]", parsed["error"])

    def test_discover_block_without_dod_rejected(self):
        args = {"goal": "x",
                "discover": {"assignee": "scout"},  # missing dod
                "phases": [_phase()]}
        parsed, _ = _run_handler(args=args, create_ids=[])
        self.assertIn("error", parsed)
        self.assertIn("discover.dod", parsed["error"])


if __name__ == "__main__":
    unittest.main()
