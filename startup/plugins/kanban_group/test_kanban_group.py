#!/usr/bin/env python3
"""kanban_group — real-kernel e2e tests (harness: kanban_chains e2e /
test_ticket_serialization: throwaway HERMES_HOME + real registered board).

Proves the SPEC's semantics contract against the real kanban_db kernel:

  * unlock (AND): member held in todo + unclaimable until EVERY last-pre-stage
    marker is done; kernel promotion releases it
  * fan-in: first post stage promotes only when ALL member done-markers close
  * stage sub-lists parallel, stage array sequential
  * idempotency: same key re-invoke → same card ids, status 'recovered',
    zero duplicates, byte-same links
  * link failure → structured error naming both cards + exact repair; retry
    with the same key recovers cleanly
  * cycle rejection surfaced as a structured error
  * workflow-gate lane allowed for created markers; bogus profiles rejected
  * await_caller: dependency park (never sticky blocked) → auto-promote

Skipped automatically when hermes_cli is not importable.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_PARENT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = Path(__file__).resolve().parent


def _unshadow_tools():
    """Drop the plugin dir from sys.path + clear shadowing modules.

    When pytest is invoked from inside the plugin dir (the documented run
    mode), that dir lands on sys.path and hermes-agent's real `tools`
    package resolves to this plugin's tools.py — the kernel's lifecycle
    hooks then die on `from tools.registry import tool_error`. Same cure
    as kanban_chains' e2e suite.
    """
    pdir = str(PLUGIN_DIR)
    while pdir in sys.path:
        sys.path.remove(pdir)
    for name in ("tools", "schemas"):
        mod = sys.modules.get(name)
        if mod is not None and str(getattr(mod, "__file__", "")).startswith(pdir):
            del sys.modules[name]


# Import as the PACKAGE kanban_group.tools (plugins parent on sys.path),
# mirroring production's package-qualified load.
sys.path.insert(0, str(PLUGIN_PARENT))
_unshadow_tools()
from kanban_group import tools as kg  # noqa: E402

kb = pytest.importorskip(
    "hermes_cli.kanban_db",
    reason="hermes_cli not importable — kernel tests need the agent runtime",
)

BOARD = "grp-e2e"


@pytest.fixture()
def kernel(tmp_path, monkeypatch):
    """Throwaway HERMES_HOME with a real registered board (CLI validates board
    existence before HERMES_KANBAN_DB applies)."""
    home = tmp_path / "grp-home"
    home.mkdir()
    subprocess.run(
        ["hermes", "kanban", "boards", "create", BOARD, "--name", "group e2e"],
        env={**os.environ, "HERMES_HOME": str(home)},
        capture_output=True, timeout=60, check=True,
    )
    db_path = home / "kanban" / "boards" / BOARD / "kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db_path))
    monkeypatch.setenv("HERMES_KANBAN_BOARD", BOARD)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_KANBAN_RUN_ID", raising=False)
    return db_path


def _mk(conn, title, assignee="qa", parents=None, created_by="po"):
    kwargs = {"parents": parents} if parents else {}
    return kb.create_task(
        conn, title=title, body="", assignee=assignee,
        created_by=created_by, **kwargs,
    )


def _status(conn, tid):
    return kb.get_task(conn, tid).status


def _parents(conn, tid):
    return set(kb.parent_ids(conn, tid))


def _task_count():
    with kb.connect(board=BOARD) as conn:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def _running_caller(monkeypatch, title="group orchestrator"):
    """Caller card driven to running like the dispatcher does; publishes the
    claimed run id so the CLI dependency block passes the kernel CAS gate."""
    with kb.connect(board=BOARD) as conn:
        caller = kb.create_task(
            conn, title=title, body="I call group_cards then wait.",
            assignee="qa", created_by="qa",
        )
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        claimed = kb.claim_task(conn, caller, claimer="qa")
        conn.commit()
        assert claimed is not None
        run = kb.latest_run(conn, caller)
        assert run is not None
        monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(run.id))
    return caller


# ── unlock (AND) ──────────────────────────────────────────────────────────────


def test_member_held_until_pre_gate_completes(kernel):
    with kb.connect(board=BOARD) as conn:
        gate = _mk(conn, "[qa-done-1] M1 QA gate", assignee="workflow-gate")
        m1 = _mk(conn, "[ticket-01] a", assignee="tech-lead")
        m2 = _mk(conn, "[ticket-02] b", assignee="tech-lead")
        g1 = _mk(conn, "[done-01] a gate", assignee="workflow-gate")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "m2",
        "members": [{"card": m1, "done": g1}, m2],
        "pre": [{"gate": gate}],
    }))
    assert out["status"] == "wired", out
    assert out["members"] == [{"card": m1, "done": g1}, {"card": m2, "done": m2}]
    assert all(l["verified"] for l in out["links"])
    assert {l["parent"] for l in out["links"]} == {gate}
    assert {l["child"] for l in out["links"]} == {m1, m2}

    with kb.connect(board=BOARD) as conn:
        # held: todo, and the kernel refuses to claim it
        assert _status(conn, m1) == "todo"
        assert _status(conn, m2) == "todo"
        assert kb.claim_task(conn, m1, claimer="tech-lead") is None, \
            "kernel must refuse to claim a member while the pre gate is open"

        # gate closes → both members promote and become claimable
        assert kb.complete_task(conn, gate, summary="qa pass, milestone 1 clear")
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, m1) == "ready"
        assert _status(conn, m2) == "ready"
        assert kb.claim_task(conn, m1, claimer="tech-lead") is not None


def test_unlock_is_and_across_parallel_pre_markers(kernel):
    """Last pre stage has two parallel markers — member promotes only when
    BOTH close (AND), and earlier stages chain sequentially."""
    with kb.connect(board=BOARD) as conn:
        g0 = _mk(conn, "stage0 gate", assignee="workflow-gate")
        m = _mk(conn, "member", assignee="tech-lead")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "and-test",
        "members": [m],
        "pre": [
            {"gate": g0},
            [{"assignee": "qa", "title": "p1", "body": "x"},
             {"assignee": "qa", "title": "p2", "body": "x"}],
        ],
    }))
    assert out["status"] == "wired", out
    (p1, p2) = [s["card"] for s in out["pre"][1]]
    with kb.connect(board=BOARD) as conn:
        # stage 1 waits on stage 0; member waits on BOTH stage-1 markers
        assert _parents(conn, p1) == {g0} and _parents(conn, p2) == {g0}
        assert _parents(conn, m) == {p1, p2}

        # one marker done is not enough
        assert kb.complete_task(conn, g0, summary="")
        kb.recompute_ready(conn); conn.commit()
        assert kb.complete_task(conn, p1, summary="")
        kb.recompute_ready(conn); conn.commit()
        assert _status(conn, m) == "todo", "AND unlock: one of two markers is not enough"

        assert kb.complete_task(conn, p2, summary="")
        kb.recompute_ready(conn); conn.commit()
        assert _status(conn, m) == "ready", "both markers done must release the member"


# ── fan-in ────────────────────────────────────────────────────────────────────


def test_post_fans_in_on_all_member_done_markers(kernel):
    with kb.connect(board=BOARD) as conn:
        m1 = _mk(conn, "work 1", assignee="tech-lead")
        g1 = _mk(conn, "[done-1] gate", assignee="workflow-gate")
        m2 = _mk(conn, "work 2", assignee="tech-lead")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "fanin",
        "members": [{"card": m1, "done": g1}, m2],
        "post": [{"assignee": "verifier", "title": "post 0", "body": "check all"}],
    }))
    assert out["status"] == "wired", out
    post0 = out["post"][0][0]["card"]

    with kb.connect(board=BOARD) as conn:
        assert _parents(conn, post0) == {g1, m2}
        # ONE member truly done — post still held
        assert kb.complete_task(conn, m2, summary="")
        kb.recompute_ready(conn); conn.commit()
        assert _status(conn, post0) == "todo", "fan-in: post must wait for ALL done-markers"
        # the second done-marker closes the fan-in
        assert kb.complete_task(conn, g1, summary="")
        kb.recompute_ready(conn); conn.commit()
        assert _status(conn, post0) == "ready"


def test_post_stages_chain_sequentially(kernel):
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "work", assignee="tech-lead")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "chain",
        "members": [m],
        "post": [
            {"assignee": "qa", "title": "post a", "body": ""},
            [{"assignee": "qa", "title": "post b1", "body": ""},
             {"assignee": "qa", "title": "post b2", "body": ""}],
            {"assignee": "qa", "title": "post c", "body": ""},
        ],
    }))
    assert out["status"] == "wired", out
    a = out["post"][0][0]["card"]
    b1, b2 = [s["card"] for s in out["post"][1]]
    c = out["post"][2][0]["card"]
    with kb.connect(board=BOARD) as conn:
        assert _parents(conn, a) == {m}
        assert _parents(conn, b1) == {a} and _parents(conn, b2) == {a}
        assert _parents(conn, c) == {b1, b2}


# ── idempotency ───────────────────────────────────────────────────────────────


def test_same_key_reinvoke_recovers_byte_same_zero_duplicates(kernel):
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "work", assignee="tech-lead")
        g = _mk(conn, "gate", assignee="workflow-gate")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    args = {
        "key": "idem",
        "members": [{"card": m, "done": g}],
        "post": [{"assignee": "verifier", "title": "post 0", "body": "x"}],
    }
    out1 = json.loads(kg.group_cards(args))
    assert out1["status"] == "wired"
    n1 = _task_count()

    out2 = json.loads(kg.group_cards(args))
    assert out2["status"] == "recovered", "re-invoke with same key must recover"
    assert _task_count() == n1, "recovery must create ZERO duplicate cards"
    for field in ("pre", "members", "post", "links"):
        # ids + links are the idempotency contract — byte-same across re-invokes
        # ('origin' provenance labels legitimately flip created→recovered)
        strip = lambda stages: [[{k: v for k, v in s.items() if k != "origin"} for s in row] for row in stages]
        a, b = out1[field], out2[field]
        assert (strip(a) if isinstance(a, list) and a and isinstance(a[0], list) else a) == \
               (strip(b) if isinstance(b, list) and b and isinstance(b[0], list) else b), \
            f"{field} must be byte-same across re-invokes"
    assert all(l["verified"] for l in out2["links"]), "recovered links still verified"
    assert all(s["origin"] == "recovered" for row in out2["post"] for s in row)


# ── failure model ────────────────────────────────────────────────────────────


def test_link_failure_is_structured_error_then_retry_recovers(kernel, monkeypatch):
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "work", assignee="tech-lead")
        g = _mk(conn, "gate", assignee="workflow-gate")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    args = {"key": "failpath", "members": [{"card": m, "done": g}],
            "pre": [{"assignee": "qa", "title": "pre 0", "body": ""}]}
    real = kg._run_kanban

    def links_die(args_list, board=None):
        if args_list[:1] == ["link"]:
            return False, "simulated: db write burst killed the link after retries"
        return real(args_list, board=board)

    monkeypatch.setattr(kg, "_run_kanban", links_die)
    out = json.loads(kg.group_cards(args))
    monkeypatch.setattr(kg, "_run_kanban", real)  # restore WITHOUT undo() — undo nukes the fixture env

    assert out["status"] == "error"
    assert out["error"]["code"] == "link_unverified"
    assert all(not l["verified"] for l in out["links"])
    repair = out["error"]["repair"]
    assert "hermes kanban" in repair and "link" in repair
    assert out.get("link_command_failures"), "CLI failure detail must be surfaced"
    pre_id = out["pre"][0][0]["card"]
    assert f"link {pre_id} {m}" in repair, "repair must name both cards exactly"

    # RETRY IS SAFE: same key, now with links working → recovers cleanly
    out2 = json.loads(kg.group_cards(args))
    assert out2["status"] == "recovered", out2
    assert out2["pre"][0][0]["card"] == pre_id, "same idempotency key → same card"
    assert all(l["verified"] for l in out2["links"])
    with kb.connect(board=BOARD) as conn:
        assert _status(conn, m) == "todo", "member still held after recovery"


def test_cycle_rejection_is_structured_error(kernel):
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "member", assignee="tech-lead")
        g = _mk(conn, "gate", assignee="workflow-gate")
        kb.link_tasks(conn, m, g)  # m -> g already: wiring g -> m closes a loop
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({"key": "cyc", "members": [m], "pre": [{"gate": g}]}))
    assert out["status"] == "error"
    assert out["error"]["code"] == "cycle"
    assert f"{g} -> {m}" in out["error"]["message"]


# ── boundary validation ──────────────────────────────────────────────────────


def test_bad_args_and_unknown_cards(kernel):
    # no members
    out = json.loads(kg.group_cards({"key": "k", "members": []}))
    assert out["error"]["code"] == "bad_args"
    # whitespace key (it reaches CLI args + idempotency keys)
    out = json.loads(kg.group_cards({"key": "bad key", "members": ["t_x"]}))
    assert out["error"]["code"] == "bad_args"
    # unknown member card
    out = json.loads(kg.group_cards({"key": "k", "members": ["t_missing00"]}))
    assert out["error"]["code"] == "unknown_card"
    # unknown pre gate
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "m", assignee="tech-lead")
        conn.commit()
    out = json.loads(kg.group_cards({"key": "k", "members": [m], "pre": [{"gate": "t_missing00"}]}))
    assert out["error"]["code"] == "unknown_card"
    # create step without assignee
    out = json.loads(kg.group_cards({"key": "k", "members": [m], "post": [{"title": "no assignee"}]}))
    assert out["error"]["code"] == "bad_args"


def test_workflow_gate_lane_allowed_bogus_profile_rejected(kernel, monkeypatch):
    """Created markers may sit on the workflow-gate control lane; typo'd real
    profiles are rejected BEFORE any board write."""
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "m", assignee="tech-lead")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "lane",
        "members": [m],
        "post": [{"assignee": "workflow-gate", "title": "[qa-done-9] gate", "body": "control lane"}],
    }))
    assert out["status"] == "wired", out
    with kb.connect(board=BOARD) as conn:
        assert kb.get_task(conn, out["post"][0][0]["card"]).assignee == "workflow-gate"

    # point profile resolution at the LIVE home (throwaway home has no
    # profiles/ and defaults every name to True) — same dance as
    # test_gate_lane_is_nonspawnable in test_ticket_serialization.py
    import importlib
    from hermes_cli import profiles as _p
    saved = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = "/home/lpaydat/.hermes-teams/startup"
    try:
        if hasattr(_p, "_profile_cache"):
            _p._profile_cache.clear()
        importlib.reload(_p)
        assert kg._profile_ok("workflow-gate") is True
        assert kg._profile_ok("no-such-profile-xyz") is False
        # rejected pre-board: unknown_profile, nothing created
        out = json.loads(kg.group_cards({
            "key": "bogus", "members": ["t_missing00"],
            "post": [{"assignee": "no-such-profile-xyz", "title": "x"}],
        }))
        assert out["error"]["code"] == "unknown_profile"
    finally:
        os.environ["HERMES_HOME"] = saved
        importlib.reload(_p)


def test_member_already_in_flight_warns(kernel):
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "already running", assignee="qa")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        claimed = kb.claim_task(conn, m, claimer="qa")
        conn.commit()
        assert claimed is not None
        gate = _mk(conn, "gate", assignee="workflow-gate")
        conn.commit()

    out = json.loads(kg.group_cards({"key": "warn", "members": [m], "pre": [{"gate": gate}]}))
    assert out["status"] == "wired"
    assert any("already 'running'" in w for w in out.get("warnings", [])), out.get("warnings")


# ── await_caller ──────────────────────────────────────────────────────────────


def test_await_caller_dependency_park_then_auto_promote(kernel, monkeypatch):
    caller = _running_caller(monkeypatch)
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "work", assignee="tech-lead")
        g = _mk(conn, "[done] gate", assignee="workflow-gate")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "await1",
        "members": [{"card": m, "done": g}],
        "await_caller": True,
    }, task_id=caller))
    assert out["status"] == "wired", out

    with kb.connect(board=BOARD) as conn:
        t = kb.get_task(conn, caller)
        assert t.status == "todo", "caller parked as dependency-wait, not running"
        assert getattr(t, "block_kind", None) == "dependency", \
            "NEVER a plain block — plain blocks are sticky and never auto-promote"
        assert _parents(conn, caller) == {g}, "no post → caller waits on the done-marker"

        # terminus completes → caller auto-promotes into the work pool
        assert kb.complete_task(conn, m, summary="")
        assert kb.complete_task(conn, g, summary="")
        kb.recompute_ready(conn)
        conn.commit()
        assert _status(conn, caller) == "ready"


def test_await_caller_parks_on_last_post_stage(kernel, monkeypatch):
    caller = _running_caller(monkeypatch)
    with kb.connect(board=BOARD) as conn:
        m = _mk(conn, "work", assignee="tech-lead")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()

    out = json.loads(kg.group_cards({
        "key": "await2",
        "members": [m],
        "post": [{"assignee": "verifier", "title": "post 0", "body": ""}],
        "await_caller": True,
    }, task_id=caller))
    assert out["status"] == "wired", out
    post0 = out["post"][0][0]["card"]
    with kb.connect(board=BOARD) as conn:
        assert _parents(conn, caller) == {post0}, \
            "with post stages, the caller parks on the LAST post stage"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
