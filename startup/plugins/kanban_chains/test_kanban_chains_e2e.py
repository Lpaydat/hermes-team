#!/usr/bin/env python3
"""End-to-end tests for kanban_chains — driven through the REAL kanban_db kernel.

The companion suite (test_kanban_chains.py) mocks kanban_db and asserts the
handler makes the right *sequence of calls*. Those mocks CANNOT catch the class
of bug this plugin actually hit in practice: wrong runtime behaviour of the real
kernel (blocked-vs-todo routing, run_id gating, parent-gated auto-promotion).

These tests import the real `hermes_cli.kanban_db`, point it at a throwaway DB
via HERMES_KANBAN_DB, and drive the caller card into `running` exactly like the
dispatcher does (create -> recompute_ready -> claim_task) before invoking the
handler. They then assert the swarm-aligned invariants end to end:

  * root card is completed immediately (parallel work can start)
  * chain step 1 is `ready` (parent = done root); later steps are `todo`
  * an `after` step fans in on ALL chain terminals
  * the CALLER waits as a *dependency* block -> lands in `todo` with
    block_kind='dependency' (NEVER the human `blocked` bucket)
  * once every terminal completes, `recompute_ready` auto-promotes the caller
    back to `ready` — no cron, no human, no escalation

Skipped automatically when hermes_cli is not importable (e.g. plugin checked out
without the agent runtime).
"""

import json
import os
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent
# Import the handler as the PACKAGE `kanban_chains.tools` (put the *plugins*
# parent on the path), NOT as top-level `tools`. The kernel's lifecycle hooks
# import hermes-agent's real `tools` package (`tools.registry`); registering the
# plugin's tools.py as top-level `tools` — which the mock suite does — would
# shadow it and break every real-kernel call. Production loads it package-
# qualified too, so this mirrors reality.
sys.path.insert(0, str(PLUGIN_DIR.parent))
from kanban_chains import tools as kc  # noqa: E402

kb = pytest.importorskip(
    "hermes_cli.kanban_db",
    reason="hermes_cli not importable — E2E kernel tests need the agent runtime",
)


def _unshadow_tools():
    """Un-shadow hermes-agent's real `tools`/`schemas` packages.

    The companion mock suite (test_kanban_chains.py) does
    ``sys.path.insert(0, PLUGIN_DIR); import tools`` — registering the plugin's
    tools.py as top-level `tools` AND leaving the plugin dir on sys.path. If it
    ran first in the same session, the kernel's lifecycle hooks fail on
    ``from tools.registry import tool_error`` (the plugin module has no
    `.registry`). Remove both the plugin-dir path entry and the shadowing
    sys.modules entries so the real packages resolve.
    """
    pdir = str(PLUGIN_DIR)
    while pdir in sys.path:
        sys.path.remove(pdir)
    for name in ("tools", "schemas"):
        mod = sys.modules.get(name)
        if mod is not None and str(getattr(mod, "__file__", "")).startswith(pdir):
            del sys.modules[name]

BOARD = "team"


# -- fixtures -------------------------------------------------------------------


@pytest.fixture()
def kernel(tmp_path, monkeypatch):
    """Isolated real kanban_db on a throwaway file; env wired like a worker."""
    db_path = tmp_path / "kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db_path))
    monkeypatch.setenv("HERMES_KANBAN_BOARD", BOARD)
    # Pin HERMES_HOME so lifecycle hooks don't warn/route to the default profile.
    monkeypatch.setenv(
        "HERMES_HOME", "/home/lpaydat/.hermes-teams/startup/profiles/qa"
    )
    monkeypatch.delenv("HERMES_KANBAN_RUN_ID", raising=False)
    _unshadow_tools()
    kb.init_db(db_path=db_path)
    return db_path


def _running_caller(monkeypatch, title="QA orchestrator (caller)"):
    """Create a caller card and drive it to `running` like the dispatcher does.

    create_task -> recompute_ready (=> ready) -> claim_task (=> running + Run).
    Publishes the claimed run id into HERMES_KANBAN_RUN_ID so the handler's
    block_task passes its expected_run_id gate, mirroring a real worker.
    """
    with kb.connect(board=BOARD) as conn:
        caller = kb.create_task(
            conn, title=title, body="I call kanban_chains then wait.",
            assignee="qa", created_by="qa",
        )
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        claimed = kb.claim_task(conn, caller, claimer="qa")
        conn.commit()
        assert claimed is not None, "caller should be claimable into running"
        run = kb.latest_run(conn, caller)
        assert run is not None
        monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(run.id))
    return caller


def _status(conn, tid):
    return kb.get_task(conn, tid).status


def _block_kind(conn, tid):
    t = kb.get_task(conn, tid)
    return getattr(t, "block_kind", None)


def _drain(ids):
    """Complete every card in `ids`, honouring dependency order via repeated
    recompute_ready passes. Returns the list still not completed (should be [])."""
    remaining = list(ids)
    with kb.connect(board=BOARD) as conn:
        for _ in range(20):
            kb.recompute_ready(conn)
            conn.commit()
            progressed = False
            for tid in list(remaining):
                if _status(conn, tid) in ("ready", "running", "todo"):
                    if kb.complete_task(conn, tid, summary="done"):
                        remaining.remove(tid)
                        progressed = True
            conn.commit()
            if not remaining or not progressed:
                break
        kb.recompute_ready(conn)
        conn.commit()
    return remaining


# -- tests ----------------------------------------------------------------------


def test_topology_and_caller_is_dependency_wait_not_blocked(kernel, monkeypatch):
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E topology",
        "chains": [
            [{"assignee": "qa", "title": "A1", "body": "a1"},
             {"assignee": "qa", "title": "A2", "body": "a2"}],
            [{"assignee": "qa", "title": "B1", "body": "b1"},
             {"assignee": "qa", "title": "B2", "body": "b2"}],
        ],
        "after": [{"assignee": "qa", "title": "synthesize", "body": "combine"}],
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))

    assert out["status"] == "blocked"
    root = out["root_id"]
    (a1, a2), (b1, b2) = out["chains"]
    after0 = out["after"][0]
    assert out["terminal_ids"] == [after0]

    with kb.connect(board=BOARD) as conn:
        # root completed immediately so workers can start
        assert _status(conn, root) == "done"
        # chain heads are ready (parent = done root); tails wait in todo
        assert _status(conn, a1) == "ready"
        assert _status(conn, b1) == "ready"
        assert _status(conn, a2) == "todo"
        assert _status(conn, b2) == "todo"
        assert kb.parent_ids(conn, a1) == [root]
        assert kb.parent_ids(conn, a2) == [a1]
        assert kb.parent_ids(conn, b2) == [b1]
        # `after` fans in on BOTH chain terminals
        assert _status(conn, after0) == "todo"
        assert set(kb.parent_ids(conn, after0)) == {a2, b2}
        # THE key invariant: caller is a dependency-wait in `todo`, NOT `blocked`
        assert _status(conn, caller) == "todo"
        assert _block_kind(conn, caller) == "dependency"
        assert kb.parent_ids(conn, caller) == [after0]


def test_caller_auto_promotes_when_all_terminals_complete(kernel, monkeypatch):
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E auto-promote",
        "chains": [
            [{"assignee": "qa", "title": "A1", "body": "a1"},
             {"assignee": "qa", "title": "A2", "body": "a2"}],
            [{"assignee": "qa", "title": "B1", "body": "b1"}],
        ],
        "after": [{"assignee": "qa", "title": "synthesize", "body": "combine"}],
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    work_ids = [c for chain in out["chains"] for c in chain] + out["after"]

    assert _drain(work_ids) == [], "all chain + after cards should complete"

    with kb.connect(board=BOARD) as conn:
        # dependency-gated caller is auto-promoted back into the work pool
        assert _status(conn, caller) == "ready"
        assert _status(conn, caller) != "blocked"


def test_no_after_fans_caller_into_every_chain_end(kernel, monkeypatch):
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E no-after",
        "chains": [
            [{"assignee": "qa", "title": "A1", "body": "a1"}],
            [{"assignee": "qa", "title": "B1", "body": "b1"}],
        ],
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    (a1,), (b1,) = out["chains"]

    assert "after" not in out
    assert set(out["terminal_ids"]) == {a1, b1}
    with kb.connect(board=BOARD) as conn:
        # both chain ends ready off the done root; caller waits on both
        assert _status(conn, a1) == "ready"
        assert _status(conn, b1) == "ready"
        assert set(kb.parent_ids(conn, caller)) == {a1, b1}
        assert _status(conn, caller) == "todo"
        assert _block_kind(conn, caller) == "dependency"


def test_block_fails_loudly_on_runid_mismatch_while_running(kernel, monkeypatch):
    """The real production fragility: the caller IS running, but the env run_id
    is stale (e.g. a reclaim gave it a new run). block_task refuses on the
    run_id gate and the handler surfaces a loud, retry-safe error instead of
    silently leaving the caller un-gated. Also proves the hardening does NOT
    misread a genuinely-running caller as 'already parked'."""
    caller = _running_caller(monkeypatch)  # sets HERMES_KANBAN_RUN_ID to real run
    real = int(os.environ["HERMES_KANBAN_RUN_ID"])
    monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(real + 12345))  # stale/wrong
    args = {
        "goal": "E2E runid-mismatch",
        "chains": [[{"assignee": "qa", "title": "A1", "body": "a1"}]],
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    assert "error" in out
    assert "Block failed" in out["error"]
    assert "Retry is safe" in out["error"]  # idempotency makes re-invoke recover
    with kb.connect(board=BOARD) as conn:
        assert _status(conn, caller) == "running"  # untouched, not mis-parked


def _task_count():
    with kb.connect(board=BOARD) as conn:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def _body(tid):
    with kb.connect(board=BOARD) as conn:
        return kb.get_task(conn, tid).body or ""


def test_idempotent_reinvocation_recovers_not_duplicates(kernel, monkeypatch):
    """Swarm-parity: a retry/respawn recovers the SAME topology instead of
    building a duplicate graph (kanban_swarm.create_swarm behaviour)."""
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E idempotency",
        "chains": [
            [{"assignee": "qa", "title": "A1", "body": "a1"},
             {"assignee": "qa", "title": "A2", "body": "a2"}],
            [{"assignee": "qa", "title": "B1", "body": "b1"}],
        ],
        "after": [{"assignee": "qa", "title": "synthesize", "body": "combine"}],
    }
    out1 = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    assert out1["status"] == "blocked"
    assert not out1.get("recovered")
    n1 = _task_count()  # caller + root + 3 chain cards + 1 after = 6

    # Re-invoke with the SAME caller + run_id (simulates a respawn/retry).
    out2 = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    n2 = _task_count()

    assert out2.get("recovered") is True
    assert out2["root_id"] == out1["root_id"]
    assert out2["terminal_ids"] == out1["terminal_ids"]
    assert n2 == n1, f"re-invocation duplicated cards: {n1} -> {n2}"
    with kb.connect(board=BOARD) as conn:
        assert _status(conn, caller) == "todo"
        assert _block_kind(conn, caller) == "dependency"


def test_worker_bodies_carry_blackboard_context(kernel, monkeypatch):
    """Swarm-parity: every worker body gets a pointer to the shared root card
    (mirrors kanban_swarm._swarm_context)."""
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E context suffix",
        "chains": [[{"assignee": "qa", "title": "A1", "body": "do a1"}]],
        "after": [{"assignee": "qa", "title": "synthesize", "body": "combine"}],
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    root = out["root_id"]
    a1 = out["chains"][0][0]
    after0 = out["after"][0]
    for tid in (a1, after0):
        body = _body(tid)
        assert "## Chains protocol" in body
        assert root in body, "worker must know the shared root/blackboard id"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
