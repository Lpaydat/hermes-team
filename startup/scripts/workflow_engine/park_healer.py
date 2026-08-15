#!/usr/bin/env python3
"""park_healer — release stranded dependency parks (wf-livetest 2026-08-15 postmortem).

What this heals
---------------
A dispatcher-spawned worker that wants to dependency-park itself but issues the
block WITHOUT ``--kind dependency`` lands STICKY in ``blocked``: upstream's
``_has_sticky_block`` (#28712) is reason-blind, ``recompute_ready`` never
promotes it, and the worker cannot self-repair — ``kanban_unblock`` is
orchestrator-only and refuses in worker context. Every downstream card freezes
until a human unblocks (observed: 2h and 4h strands on wf-livetest/-2).

This healer runs from the product-owner cron (wf-engine-tick.py) and releases
exactly that class of card:

    status = blocked
    AND latest block event (no unblocked since) has kind=='dependency'
        OR reason starting with 'dependency:'
    AND has >=1 parent link, all parents done/archived
    AND the block is stale (> STALE_SECS, so we never race an agent
        mid-repair or a parent completing within the same minute)

Heal = ``hermes kanban --board <board> unblock <id>`` (operator semantics,
flips sticky predicate; recompute_ready promotes to ready).

Deliberately NOT healed: review-required/needs_input/capability blocks (no
'dependency' marker), orphan cards with no parents, dependency waits whose
parents are still running (they should keep waiting — promotion is correct
only when parents finish; untyped ones unfortunately need this heal, typed
ones never reach 'blocked' at all).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

STALE_SECS = 300  # ignore blocks younger than 5 minutes


def _active_boards(kanban_boards_dir: Path) -> list[str]:
    """Boards listed in active-projects.json (same contract as the engine)."""
    projects_file = kanban_boards_dir.parent.parent / "active-projects.json"
    if not projects_file.exists():
        return []
    try:
        data = json.loads(projects_file.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    projects = data.get("active_projects", data if isinstance(data, dict) else [])
    if isinstance(projects, dict):  # legacy {board: path}
        return [b for b in projects if (kanban_boards_dir / b / "kanban.db").exists()]
    return [
        p.get("board")
        for p in projects
        if p.get("board") and (kanban_boards_dir / p["board"] / "kanban.db").exists()
    ]


def _stranded_parks(db: Path) -> list[dict]:
    """Cards stranded in a sticky, semantically-dependency block."""
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id FROM tasks WHERE status = 'blocked'").fetchall()
    except sqlite3.OperationalError:  # uninitialized/corrupt board
        return []
    stranded = []
    now = int(time.time())
    for row in rows:
        tid = row["id"]
        ev = conn.execute(
            "SELECT kind, payload, created_at FROM task_events "
            "WHERE task_id = ? AND kind IN ('blocked', 'unblocked') "
            "ORDER BY id DESC LIMIT 1",
            (tid,),
        ).fetchone()
        if not ev or ev["kind"] != "blocked":
            continue
        try:
            payload = json.loads(ev["payload"] or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
        kind = payload.get("kind")
        reason = str(payload.get("reason") or "")
        if kind != "dependency" and not reason.lower().startswith("dependency:"):
            continue  # genuine human-review block — leave it
        if now - int(ev["created_at"]) < STALE_SECS:
            continue  # fresh; an agent may be mid-repair
        parents = conn.execute(
            "SELECT p.status FROM task_links l JOIN tasks p ON p.id = l.parent_id "
            "WHERE l.child_id = ?",
            (tid,),
        ).fetchall()
        if not parents:
            continue  # no parents — a human should look at this
        if any(p["status"] not in ("done", "archived") for p in parents):
            continue  # legitimately still waiting
        stranded.append({"id": tid, "reason": reason[:80]})
    conn.close()
    return stranded


def heal(boards_root: Path | None = None, run_unblock=True) -> list[str]:
    """Scan active boards; release stranded dependency parks. Returns log lines."""
    if boards_root is None:
        try:
            from .kanban_adapter import KANBAN_HOME  # package context
        except ImportError:
            from kanban_adapter import KANBAN_HOME  # direct-run context
        boards_root = KANBAN_HOME
    lines: list[str] = []
    for board in _active_boards(boards_root):
        db = boards_root / board / "kanban.db"
        for card in _stranded_parks(db):
            if run_unblock:
                r = subprocess.run(
                    ["hermes", "kanban", "--board", board, "unblock", card["id"]],
                    capture_output=True, text=True, timeout=60,
                )
                lines.append(
                    f"PARK-HEAL {board}/{card['id']} unblock rc={r.returncode}: {card['reason']}"
                )
            else:
                lines.append(f"PARK-STRANDED {board}/{card['id']}: {card['reason']}")
    return lines


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from park_healer import heal  # direct-run (python3 park_healer.py)
    out = heal(run_unblock="--dry-run" not in sys.argv)
    for line in out:
        print(line)
