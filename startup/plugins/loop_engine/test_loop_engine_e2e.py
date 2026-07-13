#!/usr/bin/env python3
"""End-to-end tests for loop_engine T4 layered exits — driven through the REAL
kanban_db kernel.

The companion mock suite (test_loop_engine.py) asserts the handler makes the
right *sequence of API calls*. Those mocks CANNOT verify the one property that
makes HITL escalation actually work: that ``block_task(kind="needs_input")`` is
STICKY — ``_has_sticky_block`` makes ``recompute_ready`` skip it, so the driver
stays in the human ``blocked`` bucket until an explicit ``unblock_task``.

These tests import the real ``hermes_cli.kanban_db``, point it at a throwaway
DB via HERMES_KANBAN_DB, drive the driver card into ``running`` exactly like the
dispatcher does, then for each layered exit assert end to end:

  * the exit fires (status=escalated, decision=<exit>)
  * the driver lands in ``blocked`` with block_kind=needs_input (sticky)
  * ``recompute_ready`` does NOT auto-promote it (the HITL guarantee)
  * a ``loop_escalated`` event row is recorded naming what the human owes
  * ``unblock_task`` is the resume path

Skipped automatically when hermes_cli is not importable.
"""

import json
import os
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))

from loop_engine import tools as le  # noqa: E402

kb = pytest.importorskip(
    "hermes_cli.kanban_db",
    reason="hermes_cli not importable — E2E kernel tests need the agent runtime",
)

BOARD = "team"


def _unshadow_tools():
    """Remove the plugin dir from sys.path so the kernel's lifecycle hooks
    resolve the real hermes-agent ``tools``/``schemas`` packages."""
    pdir = str(PLUGINS_DIR)
    while pdir in sys.path:
        sys.path.remove(pdir)
    for name in ("tools", "schemas"):
        mod = sys.modules.get(name)
        if mod is not None and str(getattr(mod, "__file__", "")) \
                .startswith(pdir):
            del sys.modules[name]


# -- fixtures -------------------------------------------------------------------


@pytest.fixture()
def kernel(tmp_path, monkeypatch):
    """Isolated real kanban_db on a throwaway file; env wired like a worker."""
    db_path = tmp_path / "kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db_path))
    monkeypatch.setenv("HERMES_KANBAN_BOARD", BOARD)
    monkeypatch.setenv(
        "HERMES_HOME", "/home/lpaydat/.hermes-teams/startup/profiles/qa"
    )
    monkeypatch.delenv("HERMES_KANBAN_RUN_ID", raising=False)
    _unshadow_tools()
    kb.init_db(db_path=db_path)
    return db_path


def _status(conn, tid):
    return kb.get_task(conn, tid).status


def _block_kind(conn, tid):
    return getattr(kb.get_task(conn, tid), "block_kind", None)


def _running_driver(monkeypatch, title="loop driver"):
    """Create a driver card and drive it to `running` like the dispatcher."""
    with kb.connect(board=BOARD) as conn:
        driver = kb.create_task(
            conn, title=title, body="I drive a loop_engine workflow.",
            assignee="qa", created_by="qa",
        )
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        claimed = kb.claim_task(conn, driver, claimer="qa")
        conn.commit()
        assert claimed is not None, "driver should be claimable into running"
        run = kb.latest_run(conn, driver)
        assert run is not None
        monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(run.id))
    return driver


def _loop_args(verifier_body, *, max_iterations=1, budget=None,
               no_progress_threshold=None):
    """Build loop_engine args with one execution + one verifier phase."""
    args = {
        "goal": "E2E layered exit",
        "execution": {"assignee": "qa", "title": "execute", "body": "do work"},
        "verifier": {"assignee": "qa", "title": "verify", "body": verifier_body},
        "max_iterations": max_iterations,
    }
    if budget is not None:
        args["budget"] = budget
    if no_progress_threshold is not None:
        args["no_progress_threshold"] = no_progress_threshold
    return args


def _complete_phase(monkeypatch, out, verdict):
    """Complete the execution + verifier cards so the driver re-promotes.

    ``out`` is the first-invocation JSON (carries execution_card + verifier_card).
    ``verdict`` is the dod_verdict dict written to the verifier's run metadata.
    Returns the driver's NEW run id (set into HERMES_KANBAN_RUN_ID) so the
    re-invoke's block_task passes its expected_run_id gate.
    """
    exec_id = out["execution_card"]
    verifier_id = out["verifier_card"]
    with kb.connect(board=BOARD) as conn:
        # execution card is ready (root done) -> complete it
        assert kb.complete_task(conn, exec_id, summary="exec done"), \
            "execution card should complete"
        conn.commit()
        kb.recompute_ready(conn)  # verifier becomes ready (parent done)
        conn.commit()
        # verifier ready -> complete with the dod_verdict metadata
        assert kb.complete_task(
            conn, verifier_id, summary="verdict",
            metadata={"dod_verdict": verdict},
        ), "verifier card should complete"
        conn.commit()
        kb.recompute_ready(conn)  # promote the dependency-parked driver
        conn.commit()
    return verifier_id


def _reclaim_driver(monkeypatch, driver_id):
    """After the dependency unblocks, re-claim the driver into running and
    publish the new run id."""
    with kb.connect(board=BOARD) as conn:
        kb.recompute_ready(conn)
        conn.commit()
        st = _status(conn, driver_id)
        assert st == "ready", f"driver should be ready to re-claim, was {st}"
        claimed = kb.claim_task(conn, driver_id, claimer="qa")
        conn.commit()
        assert claimed is not None, "driver should re-claim into running"
        run = kb.latest_run(conn, driver_id)
        assert run is not None
        monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(run.id))


def _escalation_events(conn, driver_id):
    return [e for e in kb.list_events(conn, driver_id)
            if getattr(e, "kind", None) == "loop_escalated"]


# -- baseline: DoD-met completes without blocking ------------------------------


def test_dod_met_completes_without_blocking(kernel, monkeypatch):
    """Baseline: a DoD-met verdict completes the loop; the driver is NOT
    sticky-blocked and emits no loop_escalated event."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    verdict = {"dod_met": True, "recommendation": "advance", "gaps": []}
    _complete_phase(monkeypatch, out, verdict)
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "complete"
    assert out2["decision"] == "advance"

    with kb.connect(board=BOARD) as conn:
        assert _escalation_events(conn, driver) == []


# -- hard cap -------------------------------------------------------------------


def test_hard_cap_escalation_is_sticky_hitl_block(kernel, monkeypatch):
    """max_iterations=1; verifier returns replan. The hard cap fires on the
    first re-invoke and sticky-blocks the driver (kind=needs_input).
    recompute_ready does NOT promote it; unblock_task is the resume."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=1)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    verdict = {"dod_met": False, "recommendation": "replan",
               "gaps": [{"dimension": "tests", "issue": "failing"}]}
    _complete_phase(monkeypatch, out, verdict)
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "escalated"
    assert out2["decision"] == "hard_cap"

    with kb.connect(board=BOARD) as conn:
        # Sticky block: kind=needs_input lands in `blocked`.
        assert _status(conn, driver) == "blocked"
        assert _block_kind(conn, driver) == "needs_input"
        # THE HITL guarantee: recompute_ready does NOT auto-promote it.
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, driver) == "blocked", (
            "sticky needs_input block must NOT be auto-promoted by "
            "recompute_ready — a human must unblock_task")
        # A loop_escalated event names what the human owes.
        events = _escalation_events(conn, driver)
        assert len(events) == 1
        payload = json.loads(events[0].payload) if isinstance(
            events[0].payload, str) else events[0].payload
        assert payload["exit"] == "hard_cap"
        assert "human_owes" in payload

    # Resume path: unblock_task flips the driver out of the sticky block.
    with kb.connect(board=BOARD) as conn:
        assert kb.unblock_task(conn, driver)
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, driver) in ("ready", "todo"), (
            "unblock_task is the resume — driver re-enters the work pool")


# -- budget exhaustion ----------------------------------------------------------


def test_budget_exhaustion_is_sticky_hitl_block(kernel, monkeypatch):
    """budget=1; verifier returns replan. The budget guard fires on the first
    re-invoke (budget_remaining hits 0) and sticky-blocks the driver."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=10, budget=1)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    verdict = {"dod_met": False, "recommendation": "replan",
               "gaps": [{"dimension": "tests", "issue": "failing"}]}
    _complete_phase(monkeypatch, out, verdict)
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "escalated"
    assert out2["decision"] == "budget_exhausted"

    with kb.connect(board=BOARD) as conn:
        assert _status(conn, driver) == "blocked"
        assert _block_kind(conn, driver) == "needs_input"
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, driver) == "blocked"
        events = _escalation_events(conn, driver)
        assert len(events) == 1


# -- no-progress ----------------------------------------------------------------


def test_no_progress_is_sticky_hitl_block(kernel, monkeypatch):
    """no_progress_threshold=1; any verdict trips the no-progress guard on the
    first re-invoke (streak=1 >= 1) and sticky-blocks the driver."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=10,
                      no_progress_threshold=1)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    verdict = {"dod_met": False, "recommendation": "replan",
               "gaps": [{"dimension": "tests", "issue": "failing"}]}
    _complete_phase(monkeypatch, out, verdict)
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "escalated"
    assert out2["decision"] == "no_progress"

    with kb.connect(board=BOARD) as conn:
        assert _status(conn, driver) == "blocked"
        assert _block_kind(conn, driver) == "needs_input"
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, driver) == "blocked"
        events = _escalation_events(conn, driver)
        assert len(events) == 1
        payload = json.loads(events[0].payload) if isinstance(
            events[0].payload, str) else events[0].payload
        assert payload["exit"] == "no_progress"


# -- verifier escalate ----------------------------------------------------------


def test_verifier_escalate_is_sticky_hitl_block(kernel, monkeypatch):
    """verifier recommendation=escalate routes straight to the sticky block."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=5)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    verdict = {"dod_met": False, "recommendation": "escalate",
               "gaps": [{"dimension": "auth", "issue": "needs human decision"}]}
    _complete_phase(monkeypatch, out, verdict)
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "escalated"
    assert out2["decision"] == "verifier_escalate"

    with kb.connect(board=BOARD) as conn:
        assert _status(conn, driver) == "blocked"
        assert _block_kind(conn, driver) == "needs_input"
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, driver) == "blocked"
        events = _escalation_events(conn, driver)
        assert len(events) == 1
        payload = json.loads(events[0].payload) if isinstance(
            events[0].payload, str) else events[0].payload
        assert payload["exit"] == "verifier_escalate"


# -- T5: runner profile config + fallback ---------------------------------------


def test_runner_set_cards_spawn_under_runner(kernel, monkeypatch):
    """A workflow that declares runner=qa spawns its execution + verifier cards
    under that profile (assignee omitted -> resolved runner fills it in)."""
    driver = _running_driver(monkeypatch)
    args = {
        "goal": "runner-set workflow",
        "runner": "qa",
        "execution": {"title": "exec", "body": "do work"},   # no assignee
        "verifier": {"title": "verify", "body": "DoD: pass"},  # no assignee
        "max_iterations": 3,
    }
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    with kb.connect(board=BOARD) as conn:
        assert kb.get_task(conn, out["execution_card"]).assignee == "qa"
        assert kb.get_task(conn, out["verifier_card"]).assignee == "qa"


def test_runner_unset_cards_spawn_under_worker(kernel, monkeypatch):
    """A workflow with NO runner resolves to 'worker' for cards that omit
    assignee."""
    driver = _running_driver(monkeypatch)
    args = {
        "goal": "runner-unset workflow",
        "execution": {"title": "exec", "body": "do work"},   # no assignee
        "verifier": {"title": "verify", "body": "DoD: pass"},  # no assignee
        "max_iterations": 3,
    }
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    with kb.connect(board=BOARD) as conn:
        assert kb.get_task(conn, out["execution_card"]).assignee == "worker"
        assert kb.get_task(conn, out["verifier_card"]).assignee == "worker"


def test_two_workflows_resolve_correct_assignees(kernel, monkeypatch):
    """AC (f) temp-board: two workflows on ONE board — one with a runner, one
    without — each resolve the correct card assignees independently."""
    # Workflow 1: runner set -> cards under the runner profile.
    driver1 = _running_driver(monkeypatch, title="loop driver 1")
    args1 = {
        "goal": "assigned workflow",
        "runner": "qa",
        "execution": {"title": "exec1", "body": "do work"},
        "verifier": {"title": "verify1", "body": "DoD: pass"},
        "max_iterations": 3,
    }
    out1 = json.loads(le.loop_engine(args1, task_id=driver1, _profile="qa"))
    assert out1["status"] == "blocked"

    # Workflow 2: no runner -> cards under 'worker'.
    driver2 = _running_driver(monkeypatch, title="loop driver 2")
    args2 = {
        "goal": "unassigned workflow",
        "execution": {"title": "exec2", "body": "do work"},
        "verifier": {"title": "verify2", "body": "DoD: pass"},
        "max_iterations": 3,
    }
    out2 = json.loads(le.loop_engine(args2, task_id=driver2, _profile="qa"))
    assert out2["status"] == "blocked"

    with kb.connect(board=BOARD) as conn:
        # Each workflow's cards carry their own resolved runner.
        assert kb.get_task(conn, out1["execution_card"]).assignee == "qa"
        assert kb.get_task(conn, out1["verifier_card"]).assignee == "qa"
        assert kb.get_task(conn, out2["execution_card"]).assignee == "worker"
        assert kb.get_task(conn, out2["verifier_card"]).assignee == "worker"


def test_runner_per_card_override_wins(kernel, monkeypatch):
    """A card that names its own assignee overrides the workflow runner."""
    driver = _running_driver(monkeypatch)
    args = {
        "goal": "override workflow",
        "runner": "qa",
        "execution": {"assignee": "developer",
                      "title": "exec", "body": "do work"},
        "verifier": {"assignee": "verifier",
                     "title": "verify", "body": "DoD: pass"},
        "max_iterations": 3,
    }
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"

    with kb.connect(board=BOARD) as conn:
        assert kb.get_task(conn, out["execution_card"]).assignee == "developer"
        assert kb.get_task(conn, out["verifier_card"]).assignee == "verifier"


# -- T6: durability — idempotent re-drive + crash-resume -----------------------
#
# These prove the durability property end-to-end against the REAL kanban_db
# kernel (a mock cannot prove cross-run resume). Scenarios:
#   * intent-stable idempotency keys on phase cards
#   * re-drive on a new run re-reads loop_state, does not duplicate phase cards
#   * crash between create-cards and park -> re-drive reconciles (no orphans)
#   * kill-mid-loop simulation: driver resumes and the workflow completes
#   * stale/missing-verdict detection triggers re-evaluate, not phantom advance


def _reclaim_run(monkeypatch, driver_id):
    """Simulate the dispatcher reclaiming a dead worker's run and re-queueing
    the driver so it re-claims into a NEW run. Mirrors ``release_stale_claims``:
    the stale run ends as ``reclaimed`` and the task's claim fields are cleared
    so ``claim_task``'s ``claim_lock IS NULL`` CAS mints a fresh run_id. This is
    the "kill mid-loop" primitive."""
    with kb.connect(board=BOARD) as conn:
        kb._end_run(conn, driver_id, outcome="reclaimed", status="reclaimed",
                    summary="worker killed mid-loop (simulated)")
        conn.execute(
            "UPDATE tasks SET status='ready', current_run_id=NULL, "
            "claim_lock=NULL, claim_expires=NULL, worker_pid=NULL "
            "WHERE id=?", (driver_id,))
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        claimed = kb.claim_task(conn, driver_id, claimer="qa")
        conn.commit()
        assert claimed is not None, "driver should re-claim into a new run"
        run = kb.latest_run(conn, driver_id)
        assert run is not None
        monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(run.id))


def _loop_card_count(conn, driver_id, suffix=None):
    """Count non-archived tasks carrying this driver's intent-stable idempotency
    keys (``loop:{driver}:...``). ``suffix`` filters by role (e.g. 'exec',
    'verify', 'reeval'). The root card is included when suffix is None."""
    pat = f"loop:{driver_id}:%"
    if suffix is not None:
        pat = f"loop:{driver_id}:%:{suffix}"
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks "
        "WHERE idempotency_key LIKE ? AND status != 'archived'",
        (pat,)).fetchone()
    return row["n"]


class _FailParkN:
    """Monkeypatch side-effect: make ``_park_driver`` return 'failed' (simulate
    a crash between create-cards and park) for the first N calls, then defer to
    the real implementation so subsequent parks succeed."""

    def __init__(self, real, fail_times):
        self._real = real
        self._fail_times = fail_times
        self._calls = 0

    def __call__(self, *a, **kw):
        self._calls += 1
        if self._calls <= self._fail_times:
            return "failed"
        return self._real(*a, **kw)


def test_phase_cards_carry_intent_stable_idempotency_keys(kernel, monkeypatch):
    """AC: idempotency salt stable for recovery — phase exec + verifier cards
    carry intent-stable keys (``loop:{driver}:phase0:iter1:{role}``) so a
    re-drive dedups against cards already created that iteration."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))

    with kb.connect(board=BOARD) as conn:
        exec_card = kb.get_task(conn, out["execution_card"])
        ver_card = kb.get_task(conn, out["verifier_card"])
        assert exec_card.idempotency_key == \
            f"loop:{driver}:phase0:iter1:exec"
        assert ver_card.idempotency_key == \
            f"loop:{driver}:phase0:iter1:verify"


def test_crash_before_park_reparks_existing_terminal_no_duplicates(
        kernel, monkeypatch):
    """AC: reclaim mid-loop -> driver re-reads board state; no orphan/partial
    topology.

    Simulate a crash BETWEEN creating the phase cards + writing loop_state and
    dependency-parking (the partial-topology crash window). On re-drive (a NEW
    run), the engine detects the in-flight terminal is NOT done and RE-PARKS on
    the existing verifier — it does not create duplicate phase cards and does
    not read a phantom verdict."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)

    # First invocation: create cards + write loop_state, but CRASH before park
    # (_park_driver returns 'failed' on the first call only).
    real_park = le._park_driver
    failer = _FailParkN(real_park, fail_times=1)
    monkeypatch.setattr(le, "_park_driver", failer)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert "error" in out, "first invocation should report the failed park"
    # Cards + loop_state were written before the park failed.
    exec_id = out["execution_card"]
    verifier_id = out["verifier_card"]

    # Kill mid-loop: reclaim the stale run, re-claim into a NEW run.
    _reclaim_run(monkeypatch, driver)

    # Re-drive on the new run: re-park on the EXISTING in-flight verifier.
    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "blocked", out2
    assert out2["decision"] == "repark", out2

    with kb.connect(board=BOARD) as conn:
        # THE durability property: no duplicate phase cards on re-drive.
        assert _loop_card_count(conn, driver, "exec") == 1
        assert _loop_card_count(conn, driver, "verify") == 1
        # The existing verifier is still in-flight (never ran).
        assert kb.get_task(conn, verifier_id).status != "done"
        # Driver is dependency-parked (todo) on the existing verifier.
        assert _status(conn, driver) == "todo"


def test_kill_mid_loop_resumes_and_completes(kernel, monkeypatch):
    """AC: kill-mid-loop test — driver resumes and the workflow completes.

    Full story: crash-before-park -> reclaim -> resume (re-park) -> phase
    completes -> workflow completes. Proves the whole property against the real
    kernel: the topology survives the crash, the driver re-reads board state on
    a NEW run, and convergence still succeeds."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)

    # 1. First invocation: cards + loop_state written, CRASH before park.
    real_park = le._park_driver
    monkeypatch.setattr(le, "_park_driver",
                        _FailParkN(real_park, fail_times=1))
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert "error" in out
    verifier_id = out["verifier_card"]

    # 2. Kill mid-loop + reclaim into a NEW run.
    _reclaim_run(monkeypatch, driver)

    # 3. Re-drive: reconcile -> re-park on the existing in-flight verifier.
    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["decision"] == "repark", out2

    # 4. Complete the phase (DoD met) and resume on a fresh run.
    verdict = {"dod_met": True, "recommendation": "advance", "gaps": []}
    exec_id = out["execution_card"]
    with kb.connect(board=BOARD) as conn:
        assert kb.complete_task(conn, exec_id, summary="exec done")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.complete_task(
            conn, verifier_id, summary="verdict",
            metadata={"dod_verdict": verdict})
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
    _reclaim_driver(monkeypatch, driver)

    # 5. Re-invoke: reads the advance verdict -> workflow completes.
    out3 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out3["status"] == "complete", out3
    assert out3["decision"] == "advance", out3

    with kb.connect(board=BOARD) as conn:
        # Exactly one exec + one verifier across the whole crash-resume story.
        assert _loop_card_count(conn, driver, "exec") == 1
        assert _loop_card_count(conn, driver, "verify") == 1


def test_redrive_after_replan_does_not_duplicate_iteration_cards(
        kernel, monkeypatch):
    """AC: no duplicate phase cards (dedup by intent) — a replan mints iter-2
    cards, then a crash-before-park on iter-2 leaves them in-flight; the re-drive
    re-parks on iter-2's verifier without minting iter-3 cards or duplicating."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=5)

    # Iter-1: first invocation parks normally.
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out["status"] == "blocked"
    # Verifier says replan.
    _complete_phase(monkeypatch, out,
                    {"dod_met": False, "recommendation": "replan",
                     "gaps": [{"dimension": "x", "issue": "1"}]})
    _reclaim_driver(monkeypatch, driver)

    # Iter-2 replan: create iter-2 cards, but CRASH before park.
    real_park = le._park_driver
    monkeypatch.setattr(le, "_park_driver",
                        _FailParkN(real_park, fail_times=1))
    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert "error" in out2, "replan should report the failed park"
    iter2_exec = out2["execution_card"]
    iter2_ver = out2["verifier_card"]

    # Kill mid-loop on iter-2 + reclaim.
    _reclaim_run(monkeypatch, driver)

    # Re-drive: reconcile iter-2's in-flight verifier -> re-park (no iter-3).
    monkeypatch.setattr(le, "_park_driver", real_park)
    out3 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out3["decision"] == "repark", out3

    with kb.connect(board=BOARD) as conn:
        # Two exec cards (iter1 + iter2) and two verifier cards — NO iter-3.
        assert _loop_card_count(conn, driver, "exec") == 2
        assert _loop_card_count(conn, driver, "verify") == 2
        # The iter-2 verifier is the one we re-parked on; still in-flight.
        assert kb.get_task(conn, iter2_ver).status != "done"


def test_stale_missing_verdict_triggers_reevaluate_not_phantom_advance(
        kernel, monkeypatch):
    """AC: stale/missing-verdict detection triggers re-evaluate, not phantom
    advance.

    The verifier completes WITHOUT a dod_verdict (the run was reclaimed
    mid-verdict — the silent optimistic-lock-drop residual risk). The engine
    must NOT act on that as a verdict (no phantom advance/replan); it dispatches
    a fresh verifier (re-evaluate) and re-parks."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    exec_id = out["execution_card"]
    verifier_id = out["verifier_card"]

    # Complete exec, then verifier with NO dod_verdict (stale/dropped).
    with kb.connect(board=BOARD) as conn:
        assert kb.complete_task(conn, exec_id, summary="exec done")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.complete_task(conn, verifier_id, summary="",
                                metadata=None)  # no verdict
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
    _reclaim_driver(monkeypatch, driver)

    # Re-invoke: done terminal + no verdict -> RE-EVALUATE (not advance/replan).
    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["status"] == "blocked", out2
    assert out2["decision"] == "reevaluate", out2
    fresh_verifier = out2["verifier_card"]
    assert fresh_verifier != verifier_id, "a FRESH verifier must be dispatched"
    assert out2["stale_verifier"] == verifier_id

    with kb.connect(board=BOARD) as conn:
        # The fresh verifier carries an intent-stable reeval1 key.
        assert kb.get_task(conn, fresh_verifier).idempotency_key == \
            f"loop:{driver}:phase0:iter1:reeval1"
        # Driver parked (todo) on the fresh verifier.
        assert _status(conn, driver) == "todo"


def test_reevaluate_then_advance_completes_workflow(kernel, monkeypatch):
    """After a re-evaluate, completing the fresh verifier with a real DoD-met
    verdict advances the workflow — the re-evaluate path is a real recovery, not
    a dead end."""
    driver = _running_driver(monkeypatch)
    args = _loop_args("DoD: pass", max_iterations=3)
    out = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    exec_id = out["execution_card"]
    verifier_id = out["verifier_card"]

    # Stale verdict (no metadata) -> re-evaluate dispatches a fresh verifier.
    with kb.connect(board=BOARD) as conn:
        assert kb.complete_task(conn, exec_id, summary="exec done")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.complete_task(conn, verifier_id, summary="", metadata=None)
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
    _reclaim_driver(monkeypatch, driver)

    out2 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out2["decision"] == "reevaluate"
    fresh_verifier = out2["verifier_card"]

    # Complete the fresh verifier with a real DoD-met verdict.
    verdict = {"dod_met": True, "recommendation": "advance", "gaps": []}
    with kb.connect(board=BOARD) as conn:
        assert kb.complete_task(
            conn, fresh_verifier, summary="verdict",
            metadata={"dod_verdict": verdict})
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
    _reclaim_driver(monkeypatch, driver)

    # Re-invoke reads the fresh verdict -> workflow completes.
    out3 = json.loads(le.loop_engine(args, task_id=driver, _profile="qa"))
    assert out3["status"] == "complete", out3
    assert out3["decision"] == "advance", out3
