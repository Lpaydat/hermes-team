#!/usr/bin/env python3
"""Integration test: PROVES the kanban dispatcher spawns N>1 workers CONCURRENTLY
for ONE profile in a SINGLE dispatch tick under OUR config.

Our config (loop_engine gateway):
    max_in_progress_per_profile = 6
    max_in_progress             = 6
    max_spawn                   = None  (no live-concurrency cap)

Within a loop_engine workflow the phases are serial BY DESIGN (converge). The
parallelism that SHOULD exist is the fan-out the dispatcher launches in one
tick: multiple ready tasks for one profile spawn up to the per-profile cap.
This test proves that fan-out is real parallelism: 8 ready tasks for one
profile with cap=6 -> 6 workers spawned in ONE tick, 2 deferred.

THIS IS OUR TEST (repo-side, under startup/tests/). It IMPORTS the upstream
``dispatch_once`` from ``hermes_cli.kanban_db`` (the NousResearch/hermes-agent
clone at startup/hermes-agent/) but does NOT modify it. A mock spawn_fn records
every spawn and returns a fake pid -- isolating the dispatch DECISION (how many
workers it launches in one tick) without spawning real ``hermes chat`` processes.

Fixture mechanics mirror startup/hermes-agent/tests/hermes_cli/
test_kanban_per_profile_cap.py (temp HERMES_HOME, profile dir created so
profile_exists() is True, hermes_cli modules purged so the DB path re-resolves
to the throwaway home). Nothing under startup/hermes-agent/ is touched.

Run:
    cd /home/lpaydat/.hermes-teams/startup/hermes-agent && \\
    PYTHONPATH=. ./venv/bin/python -m pytest \\
        /home/lpaydat/.hermes-teams/startup/tests/test_parallel_dispatch.py -q
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# The single profile we fan out across. A real profile dir is created in the
# fixture so hermes_cli.profiles.profile_exists() returns True (the dispatcher
# skips non-profile assignees as 'skipped_nonspawnable').
ASSIGNEE = "developer"
READY_N = 8  # ready tasks, all assigned to the one profile


@pytest.fixture()
def isolated_kanban(monkeypatch):
    """Fresh throwaway HERMES_HOME + kanban DB; one real profile dir.

    Purges cached hermes_cli/hermes_state/hermes_constants modules so kanban_db
    re-resolves its DB path against the temp home (kanban_db caches the path at
    import time). Yields the freshly-imported ``hermes_cli.kanban_db`` module.
    """
    test_home = tempfile.mkdtemp(prefix="parallel_dispatch_test_")
    os.makedirs(os.path.join(test_home, "profiles", ASSIGNEE), exist_ok=True)
    os.makedirs(os.path.join(test_home, "profiles", "default"), exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", test_home)
    for mod in list(sys.modules.keys()):
        if (
            mod.startswith("hermes_cli")
            or mod.startswith("hermes_state")
            or mod == "hermes_constants"
        ):
            del sys.modules[mod]
    from hermes_cli import kanban_db  # imported AFTER env + module purge
    yield kanban_db


class _SpawnRecorder:
    """Mock spawn_fn: records every invocation, returns a unique fake pid.

    No real subprocess is launched. dispatch_once calls
    ``spawn_fn(task, workspace_path[, board=...])``; we accept ``*args, **kwargs``
    so all call shapes are handled. The dispatch decision (concurrent spawn
    count) is captured BOTH here (.spawns) and in DispatchResult.spawned.
    """

    def __init__(self):
        self.spawns: list[tuple] = []
        self._next_pid = 40000

    def __call__(self, *args, **kwargs):
        self.spawns.append(args)
        self._next_pid += 1
        return self._next_pid


def _seed_ready_tasks(kb, n=READY_N, assignee=ASSIGNEE):
    """Create ``n`` ready tasks all assigned to one profile on a throwaway
    board. Parentless tasks land in status='ready' (create_task default branch)."""
    with kb.connect_closing() as conn:
        kb.create_board(slug="default", name="Parallel Dispatch Proof")
        for i in range(n):
            kb.create_task(conn, title=f"{assignee}-task-{i:02d}", assignee=assignee)


# ── Positive: the parallelism proof ──────────────────────────────────────────

def test_positive_six_concurrent_for_one_profile(isolated_kanban):
    """OUR config (per_profile=6, max_in_progress=6, max_spawn=None) with 8
    ready tasks for ONE profile must fill all 6 per-profile slots in a SINGLE
    dispatch tick -> 6 concurrent workers, 2 deferred."""
    kb = isolated_kanban
    _seed_ready_tasks(kb)
    rec = _SpawnRecorder()
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(
            conn,
            spawn_fn=rec,
            dry_run=False,  # real decision path; mock fn => no subprocess
            max_spawn=None,
            max_in_progress=6,
            max_in_progress_per_profile=6,
            board="default",
        )
    # DECISIVE: 6 workers spawned in ONE tick. Recorder + DispatchResult agree.
    assert len(rec.spawns) == 6, (
        f"expected 6 concurrent spawns in one tick, recorder saw "
        f"{len(rec.spawns)} | spawned={len(res.spawned)} "
        f"capped={len(res.skipped_per_profile_capped)} "
        f"nonspawnable={len(res.skipped_nonspawnable)} "
        f"unassigned={len(res.skipped_unassigned)}"
    )
    assert len(res.spawned) == 6
    assert all(s[1] == ASSIGNEE for s in res.spawned), "all spawns one profile"
    # The cap BOUND the fan-out: not all 8 spawned. With max_in_progress=6 the
    # global-derived max_spawn=6 breaks the loop (running_count+spawned >= 6)
    # BEFORE the per-profile cap check sees tasks 7/8, so they are NOT in
    # skipped_per_profile_capped -- they simply stay 'ready' for the next tick
    # (correct concurrency-bounded behaviour, not a permanent block).
    assert len(res.spawned) < READY_N, "cap must bound the fan-out (< 8)"
    assert not res.skipped_nonspawnable, "profile dir must make assignee spawnable"
    with kb.connect_closing() as conn:
        still_ready = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'ready'"
        ).fetchone()[0]
    assert still_ready == READY_N - 6, "remaining tasks deferred to next tick"


# ── Negative control A: per-profile cap binds ────────────────────────────────

def test_negA_per_profile_cap_binds_to_one(isolated_kanban):
    """Same workload, per_profile=1 -> exactly 1 spawn. Proves the positive is
    not trivially passing: the per-profile cap actually gates the fan-out."""
    kb = isolated_kanban
    _seed_ready_tasks(kb)
    rec = _SpawnRecorder()
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(
            conn,
            spawn_fn=rec,
            dry_run=False,
            max_spawn=None,
            max_in_progress=6,
            max_in_progress_per_profile=1,
            board="default",
        )
    assert len(rec.spawns) == 1, (
        f"per_profile=1 must bind to 1 spawn; recorder saw {len(rec.spawns)} | "
        f"spawned={len(res.spawned)} capped={len(res.skipped_per_profile_capped)}"
    )
    assert len(res.spawned) == 1
    assert len(res.skipped_per_profile_capped) == READY_N - 1


# ── Negative control B: global cap binds ─────────────────────────────────────

def test_negB_global_in_progress_binds_to_one(isolated_kanban):
    """max_in_progress=1 (global) -> exactly 1 spawn even though per-profile cap
    is loose (6). Proves the global cap independently gates."""
    kb = isolated_kanban
    _seed_ready_tasks(kb)
    rec = _SpawnRecorder()
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(
            conn,
            spawn_fn=rec,
            dry_run=False,
            max_spawn=None,
            max_in_progress=1,
            max_in_progress_per_profile=6,
            board="default",
        )
    assert len(rec.spawns) == 1, (
        f"max_in_progress=1 must bind to 1 spawn; recorder saw {len(rec.spawns)} "
        f"| spawned={len(res.spawned)}"
    )
    assert len(res.spawned) == 1
