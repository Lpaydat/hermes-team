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
import subprocess
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
    """Isolated real kernel on a throwaway HERMES_HOME with a REAL registered
    board.

    The subprocess-based tools resolve every call via
    ``hermes kanban --board <BOARD>``; the CLI validates board existence
    against the home's boards registry BEFORE the HERMES_KANBAN_DB pin
    applies, so a bare tmp DB (the old in-process-generation fixture) makes
    every create fail with "board does not exist". Registering the board in
    a throwaway home keeps both subprocess CLI and in-process kb calls on the
    same isolated DB with no leakage into the live home.
    """
    home = tmp_path / "e2e-home"
    home.mkdir()
    subprocess.run(
        ["hermes", "kanban", "boards", "create", BOARD, "--name", "e2e kernel"],
        env={**os.environ, "HERMES_HOME": str(home)},
        capture_output=True, timeout=60, check=True,
    )
    db_path = home / "kanban" / "boards" / BOARD / "kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db_path))
    monkeypatch.setenv("HERMES_KANBAN_BOARD", BOARD)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_KANBAN_RUN_ID", raising=False)
    _unshadow_tools()
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

    # current contract: `after` is always present, empty when no after-steps
    assert out["after"] == []
    assert set(out["terminal_ids"]) == {a1, b1}
    with kb.connect(board=BOARD) as conn:
        # both chain ends ready off the done root; caller waits on both
        assert _status(conn, a1) == "ready"
        assert _status(conn, b1) == "ready"
        assert set(kb.parent_ids(conn, caller)) == {a1, b1}
        assert _status(conn, caller) == "todo"
        assert _block_kind(conn, caller) == "dependency"


def test_kernel_runid_gate_refuses_stale_run(kernel, monkeypatch):
    """The run-id gate is KERNEL-side (block_task CAS on current_run_id), not
    plugin-side: the subprocess `hermes kanban block` CLI used by this plugin
    is orchestrator-context by design (worker ownership rules live in
    kanban_tools, not the CLI). Assert the invariant where it actually lives:
    a stale/wrong expected_run_id refuses the block (caller untouched), the
    real run id parks it as a dependency-wait."""
    caller = _running_caller(monkeypatch)  # sets HERMES_KANBAN_RUN_ID to real run
    real = int(os.environ["HERMES_KANBAN_RUN_ID"])

    with kb.connect(board=BOARD) as conn:
        # stale run id (e.g. a reclaim replaced the run) → CAS misses, no-op
        refused = kb.block_task(
            conn, caller, reason="waiting_for_matrix:x",
            kind="dependency", expected_run_id=real + 12345,
        )
        conn.commit()
        assert refused is False, "stale run id must NOT be able to block"
        assert _status(conn, caller) == "running"  # untouched, not mis-parked

        # the real run id parks it: running → todo with block_kind=dependency
        ok = kb.block_task(
            conn, caller, reason="waiting_for_matrix:x",
            kind="dependency", expected_run_id=real,
        )
        conn.commit()
        assert ok is True
        assert _status(conn, caller) == "todo"
        assert _block_kind(conn, caller) == "dependency"


def _task_count():
    with kb.connect(board=BOARD) as conn:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def _body(tid):
    with kb.connect(board=BOARD) as conn:
        return kb.get_task(conn, tid).body or ""


def test_idempotency_key_dedupes_root_card(kernel, monkeypatch):
    """Current idempotent surface: `idempotency_key` dedupes the ROOT card.
    Chain cards carry no keys — re-invocation builds a duplicate graph, which
    is exactly why the plugin's error returns forbid blind re-calls and hand
    out repair instructions instead (no 'recovered' retry path exists)."""
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E idempotency",
        "idempotency_key": "e2e-root-key-1",
        "chains": [[{"assignee": "qa", "title": "A1", "body": "a1"}]],
    }
    out1 = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    assert out1["status"] == "blocked"
    n1 = _task_count()

    # Second call with the same key: the kernel dedupes the root create.
    caller2 = _running_caller(monkeypatch)
    out2 = json.loads(kc.kanban_chains(args, task_id=caller2, _profile="qa"))
    assert out2["root_id"] == out1["root_id"], \
        "same idempotency_key must resolve to the same root card"


def test_blackboard_context_lands_on_root_comment(kernel, monkeypatch):
    """Current blackboard mechanism: context is a prefixed COMMENT on the root
    card (BLACKBOARD_PREFIX JSON), not text injected into worker bodies —
    worker bodies keep the author's text verbatim."""
    caller = _running_caller(monkeypatch)
    args = {
        "goal": "E2E context",
        "chains": [[{"assignee": "qa", "title": "A1", "body": "do a1"}]],
        "blackboard": {"env_facts": "python3.14", "spec_path": "/tmp/SPEC.md"},
    }
    out = json.loads(kc.kanban_chains(args, task_id=caller, _profile="qa"))
    root = out["root_id"]
    a1 = out["chains"][0][0]

    with kb.connect(board=BOARD) as conn:
        rows = conn.execute(
            "SELECT body FROM task_comments WHERE task_id = ? ORDER BY id",
            (root,),
        ).fetchall()
    comments = [r["body"] if hasattr(r, "keys") else r[0] for r in rows]
    bb = [c for c in comments if c.startswith("[swarm:blackboard] ")]
    assert bb, f"blackboard comment missing on root; comments: {comments}"
    payload = json.loads(bb[0].removeprefix("[swarm:blackboard] "))
    assert payload["key"] == "matrix_context"
    assert payload["value"]["env_facts"] == "python3.14"
    assert payload["value"]["spec_path"] == "/tmp/SPEC.md"
    assert payload["value"]["goal"] == "E2E context"

    # worker bodies carry the author's text verbatim (no protocol injection)
    assert _body(a1) == "do a1"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
