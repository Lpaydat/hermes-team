#!/usr/bin/env python3
"""Ticket serialization via gate cards — real-kernel tests (Option A).

Proves the invariant the wf-livetest4 run violated: a dependent ticket cannot
even TRIGGER until its blocker's implementation workflow fully closes, and the
milestone card waits on real completion (gates), not on instant trigger stubs.

Mechanism under test (templates dev-dispatch / milestone-gate / tech-lead-execute):
  * each ticket gets a [done-NN] GATE card assigned to the `workflow-gate`
    control-plane lane — completed only by the ticket's tech-lead-execute close
    step (merge + tests green)
  * dependent tickets' TRIGGER cards are parented on GATES (not stubs)
  * milestone cards are parented on GATES

These tests exercise the KERNEL primitives (recompute_ready promotion, claim
gating, nonspawnable assignees) against a real kanban_db, plus pin the template
contracts so the bodies cannot silently drift.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

kb = pytest.importorskip(
    "hermes_cli.kanban_db",
    reason="hermes_cli not importable — kernel tests need the agent runtime",
)

BOARD = "ser-test"


@pytest.fixture()
def kernel(tmp_path, monkeypatch):
    """Throwaway HERMES_HOME with a real registered board (the CLI validates
    board existence before HERMES_KANBAN_DB applies)."""
    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(
        ["hermes", "kanban", "boards", "create", BOARD, "--name", "serialization test"],
        env={**os.environ, "HERMES_HOME": str(home)},
        capture_output=True, timeout=60, check=True,
    )
    db_path = home / "kanban" / "boards" / BOARD / "kanban.db"
    monkeypatch.setenv("HERMES_KANBAN_DB", str(db_path))
    monkeypatch.setenv("HERMES_KANBAN_BOARD", BOARD)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_KANBAN_RUN_ID", raising=False)
    return db_path


def _gate_kernel():
    """Gate on the throwaway home (not the live one) for profile_exists checks."""
    return os.environ.get("HERMES_HOME")


def test_dependent_trigger_blocked_until_gate_completes(kernel, monkeypatch):
    """Stub-02 (parented on gate-01) cannot be claimed while the blocker's
    implementation is in flight; completing the gate releases it."""
    with kb.connect(board=BOARD) as conn:
        gate1 = kb.create_task(
            conn, title="[done-01] walking skeleton", body="gate",
            assignee="workflow-gate", created_by="product-owner",
        )
        stub1 = kb.create_task(
            conn, title="[ticket-01] walking skeleton", body="trigger\nGATE: " + gate1,
            assignee="tech-lead", created_by="product-owner",
        )
        stub2 = kb.create_task(
            conn, title="[ticket-02] invocation contract",
            body="trigger — parented on the GATE, not the stub",
            assignee="tech-lead", created_by="product-lead" if False else "product-owner",
            parents=[gate1],
        )
        conn.commit()

        # While ticket-01's workflow is in flight (gate pending):
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, stub2).status == "todo", \
            "dependent trigger must stay todo while its gate is pending"
        claimed = kb.claim_task(conn, stub2, claimer="tech-lead")
        conn.commit()
        assert claimed is None, "kernel must refuse to claim a task with an undone parent"

        # ticket-01's close step completes the gate (merge + tests green):
        assert kb.complete_task(conn, gate1, summary="ticket merged, tests pass")
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, stub2).status == "ready", \
            "completing the gate must promote the dependent trigger to ready"
        assert kb.claim_task(conn, stub2, claimer="tech-lead") is not None, \
            "dependent trigger is claimable only after the gate closes"


def test_milestone_waits_on_gates_not_stubs(kernel):
    """A milestone parented on GATES stays todo while stubs are long done."""
    with kb.connect(board=BOARD) as conn:
        gate1 = kb.create_task(conn, title="[done-01] t", body="gate",
                               assignee="workflow-gate", created_by="po")
        stub1 = kb.create_task(conn, title="[ticket-01] t", body="trigger",
                               assignee="tech-lead", created_by="po")
        gate2 = kb.create_task(conn, title="[done-02] t", body="gate",
                               assignee="workflow-gate", created_by="po")
        stub2 = kb.create_task(conn, title="[ticket-02] t", body="trigger",
                               assignee="tech-lead", created_by="po")
        ms = kb.create_task(conn, title="[milestone-01] m", body="ms",
                            assignee="product-owner", created_by="po",
                            parents=[gate1, gate2])
        conn.commit()

        # Both trigger stubs complete instantly (as they do in production)…
        assert kb.complete_task(conn, stub1, summary="trigger")
        assert kb.complete_task(conn, stub2, summary="trigger")
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, ms).status == "todo", \
            "milestone must NOT promote on stub completion alone"

        # …one workflow closes its gate — still waiting on the other:
        assert kb.complete_task(conn, gate1, summary="merged")
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, ms).status == "todo", \
            "milestone must wait for ALL gates"

        assert kb.complete_task(conn, gate2, summary="merged")
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, ms).status == "ready", \
            "milestone promotes only when every gate (real completion) closes"


def test_gate_lane_is_nonspawnable(kernel):
    """`workflow-gate` is not a profile — the dispatcher's spawn filter must
    skip a ready gate card forever (never burn a worker session on it)."""
    import importlib
    import hermes_cli.profiles as profiles_mod
    from hermes_cli import profiles as _p
    saved = os.environ.get("HERMES_HOME")
    # profile_exists resolves profiles under HERMES_HOME — point it at the LIVE
    # home (the throwaway one has no profiles/ and defaults every name to True).
    os.environ["HERMES_HOME"] = "/home/lpaydat/.hermes-teams/startup"
    try:
        _p._profile_cache.clear() if hasattr(_p, "_profile_cache") else None
        importlib.reload(_p)
        assert _p.profile_exists("workflow-gate") is False, \
            "workflow-gate must NOT be a spawnable profile"
        assert _p.profile_exists("tech-lead") is True  # sanity: real profiles pass
    finally:
        os.environ["HERMES_HOME"] = saved
        importlib.reload(_p)

    with kb.connect(board=BOARD) as conn:
        gate = kb.create_task(conn, title="[done-01] t", body="gate",
                              assignee="workflow-gate", created_by="po")
        conn.commit()
        kb.recompute_ready(conn)
        conn.commit()
        assert kb.get_task(conn, gate).status == "ready"  # promotable…
        # …but the dispatch selection classifies it nonspawnable via
        # profile_exists — the exact check in dispatch_once's spawn loop.


# ── template contract pins (bodies cannot silently drift) ────────────────────

TEMPLATES = Path(__file__).parent / "templates"


def _body(template_id, node_id):
    t = json.loads((TEMPLATES / f"{template_id}.json").read_text())
    return next(n for n in t["nodes"] if n["id"] == node_id)["body_template"]


def test_templates_pin_gate_contracts():
    """Every stub-creating node instructs gate creation + gate-parenting, and
    tech-lead-execute's close step completes the gate via the CLI."""
    decompose = _body("dev-dispatch", "route-decompose")
    tickets = _body("dev-dispatch", "route-tickets")
    milestones = _body("dev-dispatch", "route-milestone")
    refactor = _body("milestone-gate", "refactor-decompose")
    close = _body("tech-lead-execute", "close")

    for body, label in ((decompose, "route-decompose"), (tickets, "route-tickets"),
                        (refactor, "refactor-decompose")):
        assert "[done-" in body and "workflow-gate" in body, \
            f"{label} must create gate cards on the workflow-gate lane"
        assert "GATE:" in body, f"{label} stub bodies must carry the GATE id"
    # parenting instructions name GATE ids explicitly (line-wrap-proof)
    assert "GATE card ids of each blocked-by" in decompose
    assert "GATE card ids for each" in tickets

    assert "GATE card IDs" in milestones and "NOT the [ticket-NN]" in milestones, \
        "milestone cards must parent on gate ids"
    assert "GATE: <card-id>" in close and "hermes kanban --board" in close, \
        "close step must complete the gate via the CLI (worker-tool ownership would refuse)"


def _template(template_id):
    return json.loads((TEMPLATES / f"{template_id}.json").read_text())


def test_templates_pin_milestone_barrier():
    """Milestone barrier contracts: route-milestone wires qa-done gates +
    group_cards; milestone-gate closes the gate ONLY on the PASS path."""
    dd = _template("dev-dispatch")
    mg = _template("milestone-gate")

    # route-milestone: qa-done gate cards created upfront on the control lane,
    # id embedded in the milestone body, barrier wired via group_cards
    milestones = next(n for n in dd["nodes"] if n["id"] == "route-milestone")["body_template"]
    assert "[qa-done-NN]" in milestones and "workflow-gate" in milestones, \
        "route-milestone must create [qa-done-NN] gates on the workflow-gate lane upfront"
    assert "QA gate: <the [qa-done-NN] card id" in milestones, \
        "milestone card body must embed the QA gate id (gate-close parses it)"
    assert 'key: "m<NN>"' in milestones and "group_cards" in milestones, \
        "route-milestone must wire the barrier through group_cards with key m<NN>"
    assert "pre: [{gate:" in milestones, "barrier pre = previous milestone's qa-done gate"
    assert "ENTRY ticket" in milestones, "barrier members = entry tickets only"

    # milestone-gate: gate-close terminal node on the PASS path only
    gc = next(n for n in mg["nodes"] if n["id"] == "gate-close")
    gc_body = gc["body_template"]
    assert "QA gate:" in gc_body and "hermes kanban --board" in gc_body, \
        "gate-close must parse the QA gate id and complete it via the CLI"
    assert "kanban_complete tool" in gc_body and "NOT the" in gc_body, \
        "gate-close must forbid the worker tool (ownership: control-lane card)"
    edges = {(e["from"], e["to"]) for e in mg["edges"]}
    assert ("refactor-decompose", "gate-close") in edges, \
        "PASS path (refactor tickets created) must close the gate"
    assert ("refactor-review", "gate-close") in edges, \
        "clean-codebase stop must ALSO close the gate — else a clean milestone deadlocks the next"
    # Merge-node convention (engine semantics): a node with ANY conditional
    # incoming edge makes the conditional firing MANDATORY (U_sat AND C_sat).
    # gate-close merges two ALTERNATIVE routes — every incoming edge must be
    # conditional, else the continue-path dead-branch-skips it (live bug on
    # grp-lt1 2026-08-18: unconditional decompose edge + conditional stop edge
    # → gate skipped, M2 held forever).
    gc_in = [e for e in mg["edges"] if e["to"] == "gate-close"]
    assert gc_in and all(e.get("condition") for e in gc_in), \
        "gate-close merge edges must ALL be conditional (engine AND/OR edge semantics)"
    bug_edges = [e for e in mg["edges"] if e["to"] == "gate-close" and e["from"] == "route-bug"]
    assert not bug_edges, \
        "FAIL path must NOT close the gate — QA failure holds the next milestone (by design)"
