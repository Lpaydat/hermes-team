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
