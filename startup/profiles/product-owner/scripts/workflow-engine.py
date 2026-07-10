#!/usr/bin/env python3
"""
Workflow Engine — combined cron for the dev workflow.

Runs three phases per project board, every tick:
  1. bead-sync:   sync kanban card status → bd bead status (closes done beads)
  2. dispatch:    bd ready → create PO dispatch card
  3. scanner:     detect blocked tasks → escalate to proper profile

Reads active-projects.json for the project list. Empty list = silent exit.
Each project maps to its own kanban board (1 project = 1 board).

Usage:
  python3 workflow-engine.py [--dry-run]
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
# HERMES_ACTIVE_PROJECTS lets drills point the engine at a fixture project list
# without touching the live registration (the cron ticks every minute).
CONFIG_FILE = Path(
    os.environ.get("HERMES_ACTIVE_PROJECTS", "").strip()
    or str(Path.home() / ".hermes-teams/startup/active-projects.json")
)
KANBAN_ROOT = Path.home() / ".hermes-teams/startup/kanban/boards"

# ── Config ────────────────────────────────────────────────────────────────

def load_projects():
    """Read active-projects.json. Returns list of {name, path, board}."""
    if not CONFIG_FILE.exists():
        return []
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return data.get("active_projects", [])
    except (json.JSONDecodeError, OSError):
        return []

def board_db_path(board):
    return KANBAN_ROOT / board / "kanban.db"

# ── Helpers ───────────────────────────────────────────────────────────────

def run_kanban(board, args):
    cmd = ["hermes", "kanban", "--board", board] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stdout.strip()

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def bd(project_dir, *args):
    r = subprocess.run(["bd"] + list(args), cwd=project_dir, capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stdout.strip()

def bd_json(project_dir, *args):
    ok, out = bd(project_dir, *args, "--json")
    if not ok:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None

# ══════════════════════════════════════════════════════════════════════════
# PHASE 1: BEAD-SYNC — kanban card status → bd bead status
# ══════════════════════════════════════════════════════════════════════════

STATUS_MAP = {
    "ready": "in_progress",
    "running": "in_progress",
    "blocked": "blocked",
    "done": "closed",
    "archived": "open",
}

def read_kanban_card_status(board, bead_id):
    key = f"bead-{bead_id}"
    db = board_db_path(board)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT status FROM tasks WHERE idempotency_key = ?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None

def phase_bead_sync(board, project_dir):
    """Sync bd bead status from kanban card status for one project."""
    changes = []
    bead_map = bd_json(project_dir, "list", "--all")
    if not isinstance(bead_map, list):
        return changes

    for bead in bead_map:
        if not isinstance(bead, dict) or "id" not in bead:
            continue
        bead_id = bead["id"]
        if "gt:slot" in bead.get("labels", []):
            continue
        card_status = read_kanban_card_status(board, bead_id)
        if not card_status or card_status not in STATUS_MAP:
            continue
        target = STATUS_MAP[card_status]
        current = bead.get("status", "open")
        if current == "closed" or current == target:
            continue
        if DRY_RUN:
            changes.append(f"bead-sync: {bead_id} {current} → {target}")
        else:
            ok, _ = bd(project_dir, "update", bead_id, "-s", target)
            if ok:
                changes.append(f"bead-sync: {bead_id} {current} → {target}")
    return changes

# ══════════════════════════════════════════════════════════════════════════
# PHASE 2: DISPATCH — bd ready → PO dispatch card
# ══════════════════════════════════════════════════════════════════════════

def card_exists_for_bead(board, bead_id):
    key = f"bead-{bead_id}"
    db = board_db_path(board)
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT 1 FROM tasks WHERE idempotency_key = ? AND status != 'archived'", (key,)).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

def has_active_po_dispatch_card(board):
    db = board_db_path(board)
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE assignee = 'product-owner' "
            "AND title LIKE '[dispatch]%' AND status NOT IN ('done', 'archived') LIMIT 1"
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

# Wayfinder frontier tickets route by type label straight to the profile that
# can resolve them (autonomous venture pipeline). grilling/prototype are the
# HITL-substitute types — PO<->VB over intercom via work-the-map cards — and
# must NEVER be headless-dispatched by the engine.
WAYFINDER_ROUTES = {
    "wayfinder:research": "scout",
    "wayfinder:task": "ops",
}
# grilling/prototype are HITL-substitute work; the map epic is an index, not
# work; an idea brief is a citable record, not work.
WAYFINDER_SKIP = ("wayfinder:grilling", "wayfinder:prototype", "wayfinder:map", "venture:brief")

def dispatch_wayfinder_ticket(board, project_dir, bead, assignee):
    """Create one routed card for a wayfinder research/task ticket."""
    bead_id = bead["id"]
    detail = bd_json(project_dir, "show", bead_id) or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    map_id = detail.get("parent") or ""
    question = detail.get("description") or bead.get("title", "")

    if DRY_RUN:
        return [f"dispatch: would route wayfinder ticket {bead_id} → {assignee} on {board}"]

    body = (
        f"## Wayfinder ticket {bead_id} — {bead.get('title', '?')}\n\n"
        f"Map: `{map_id}` (the venture's wayfinding map — its Notes name the idea "
        f"brief and prior decisions; read it with `bd show {map_id}`).\n\n"
        f"{question}\n\n"
        f"## Resolve protocol (run bd from {project_dir})\n\n"
        f"1. Investigate (AFK). Long artifacts go to a file; link them, don't paste.\n"
        f"2. Record the resolution on the ticket: `bd comment {bead_id} \"<answer + "
        f"citation of your sources>\"`\n"
        f"3. Append the decision to the map's Decisions-so-far index: read "
        f"`bd show {map_id}`, rewrite its description via `bd update {map_id} "
        f"--description=...` with the added line `- {bead.get('title', '?')} "
        f"({bead_id}) — <one-line gist>`.\n"
        f"4. Complete this card with the answer as summary. Do NOT `bd close` the "
        f"ticket yourself — bead-sync closes it when this card is done."
    )
    ok, _ = run_kanban(board, [
        "create", f"[wayfinder] {bead.get('title', bead_id)}"[:120],
        "--assignee", assignee,
        "--body", body,
        "--workspace", f"dir:{project_dir}",
        "--idempotency-key", f"bead-{bead_id}",
        "--json",
    ])
    return [f"dispatch: {'routed' if ok else 'FAILED to route'} wayfinder ticket {bead_id} → {assignee} on {board}"]

def phase_dispatch(board, project_dir):
    """Check bd ready and create a PO dispatch card for one project."""
    actions = []

    ready = bd_json(project_dir, "ready")
    if not isinstance(ready, list):
        return actions

    new_beads = []
    for bead in ready:
        if not isinstance(bead, dict) or not bead.get("id"):
            continue
        labels = bead.get("labels") or []
        if "gt:slot" in labels:
            continue
        if any(lab in WAYFINDER_SKIP for lab in labels):
            continue  # HITL-substitute tickets: PO<->VB own these, never headless
        if card_exists_for_bead(board, bead["id"]):
            continue
        route = next((WAYFINDER_ROUTES[lab] for lab in labels if lab in WAYFINDER_ROUTES), None)
        if route:
            actions.extend(dispatch_wayfinder_ticket(board, project_dir, bead, route))
            continue
        new_beads.append(bead)

    if has_active_po_dispatch_card(board):
        return actions

    if not new_beads:
        return actions

    bead_list = "\n".join(f"- `{b['id']}` — {b.get('title', '?')}" for b in new_beads)
    idem_key = f"po-dispatch-{board}-{int(time.time())}"

    if DRY_RUN:
        actions.append(f"dispatch: would create PO card for {len(new_beads)} bead(s) on {board}")
        return actions

    ok, out = run_kanban(board, [
        "create", f"[dispatch] {len(new_beads)} ready bead(s)",
        "--assignee", "product-owner",
        "--body", f"## Ready beads to dispatch\n\n{bead_list}\n\nRun `dev-dispatch` to create tech-lead cards.",
        "--workspace", f"dir:{project_dir}",
        "--priority", "20",
        "--idempotency-key", idem_key,
        "--json",
    ])
    actions.append(f"dispatch: {'created' if ok else 'FAILED'} PO card for {len(new_beads)} bead(s) on {board}")
    return actions

# ══════════════════════════════════════════════════════════════════════════
# PHASE 2b: HUMAN ESCALATION PING — human-flagged beads → operator card
# ══════════════════════════════════════════════════════════════════════════

OPERATOR_BOARD = "hermes-hq"

def hq_ping_exists(bead_id):
    db = board_db_path(OPERATOR_BOARD)
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE idempotency_key = ? AND status != 'archived'",
            (f"bead-human-{bead_id}",),
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

def phase_human_escalations(board, project_dir):
    """Async operator ping: every open human-flagged bead gets ONE hq card.

    The flag (`bd tag <id> human`) is set by whoever escalates (e.g. the
    wayfinding citation rule); this phase makes it VISIBLE without relying on
    the escalating agent also remembering to ping. Idempotent per bead.
    """
    actions = []
    flagged = bd_json(project_dir, "list", "--all", "--label", "human")
    if not isinstance(flagged, list):
        return actions
    for bead in flagged:
        if not isinstance(bead, dict) or not bead.get("id"):
            continue
        if bead.get("status") == "closed":
            continue
        bead_id = bead["id"]
        if hq_ping_exists(bead_id):
            continue
        if DRY_RUN:
            actions.append(f"human-ping: would create hq card for {bead_id}")
            continue
        title = f"[ESCALATION] human answer needed: {bead.get('title', bead_id)}"[:120]
        body = (
            f"## Human-flagged bead: {bead_id}\n\n"
            f"{(bead.get('description') or '')[:1200]}\n\n"
            f"Answer with: `bd human respond {bead_id}` (comments + closes the bead) "
            f"from {project_dir}. Board: {board}."
        )
        ok, _ = run_kanban(OPERATOR_BOARD, [
            "create", title,
            "--assignee", "default",
            "--priority", "10",
            "--body", body,
            "--idempotency-key", f"bead-human-{bead_id}",
            "--json",
        ])
        actions.append(f"human-ping: {'created' if ok else 'FAILED'} hq card for {bead_id}")
    return actions

# ══════════════════════════════════════════════════════════════════════════
# PHASE 3: BOARD SCANNER — blocked task escalation
# ══════════════════════════════════════════════════════════════════════════

ESCALATION_CHAIN = {
    "developer": "tech-lead",
    "verifier": "tech-lead",
    "tech-lead": "product-owner",
    "product-owner": None,
}

def scan_board(board):
    """Run all scanner checks on one board. Returns list of action strings."""
    db = board_db_path(board)
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    actions = []

    rows = conn.execute(
        "SELECT id, assignee, title FROM tasks WHERE status = 'blocked' ORDER BY created_at"
    ).fetchall()

    for task in rows:
        task_id = task["id"]
        assignee = task["assignee"] or ""
        if assignee in ("default", ""):
            continue

        # HUMAN_REQUIRED comment → skip
        hreq = conn.execute(
            "SELECT 1 FROM task_comments WHERE task_id = ? AND body LIKE '%HUMAN_REQUIRED%'", (task_id,)
        ).fetchone()
        if hreq:
            continue

        # Check if escalation was resolved
        resolved = conn.execute(
            "SELECT t.id FROM tasks t "
            "JOIN task_runs r ON r.task_id = t.id AND r.outcome = 'completed' "
            "WHERE t.title LIKE ? AND t.status = 'done' AND r.summary LIKE 'RESOLVED:%' "
            "ORDER BY t.completed_at DESC LIMIT 1",
            (f"[ESCALATION] %{task_id}%",)
        ).fetchone()
        if resolved:
            if not DRY_RUN:
                run_kanban(board, ["unblock", task_id])
            actions.append(f"scanner: unblocked {task_id} on {board}")
            continue

        # Already has an active escalation
        existing = conn.execute(
            "SELECT 1 FROM tasks WHERE title LIKE ? AND status NOT IN ('done','archived')",
            (f"[ESCALATION] %{task_id}%",)
        ).fetchone()
        if existing:
            continue

        # Create escalation
        target = ESCALATION_CHAIN.get(assignee)
        if not target:
            if not DRY_RUN:
                run_kanban(board, ["comment", task_id, "--author", "board-scanner",
                                   f"HUMAN_REQUIRED: No higher profile for {assignee}"])
            actions.append(f"scanner: HUMAN_REQUIRED on {task_id} ({board})")
            continue

        block_row = conn.execute(
            "SELECT payload FROM task_events WHERE task_id = ? AND kind IN ('blocked','gave_up') "
            "ORDER BY created_at DESC LIMIT 1", (task_id,)
        ).fetchone()
        reason = "unknown"
        if block_row and block_row["payload"]:
            try:
                reason = json.loads(block_row["payload"]).get("reason", "unknown")
            except json.JSONDecodeError:
                pass

        title = f"[ESCALATION] Resolve block on {task_id}: {task['title'][:40]}"
        body = (
            f"## Blocked: {task_id}\n\n"
            f"**Assignee**: {assignee}\n"
            f"**Reason**: {reason[:500]}\n\n"
            f"1. `kanban_show(task_id=\"{task_id}\")`\n"
            f"2. Resolve → comment on blocked task → complete with `RESOLVED: ...`\n"
            f"3. Can't resolve → block this card (needs_input)"
        )

        if DRY_RUN:
            actions.append(f"scanner: would escalate {task_id} → {target} on {board}")
            continue

        ok, out = run_kanban(board, ["create", title, "--assignee", target, "--priority", "10", "--body", body, "--json"])
        if ok:
            actions.append(f"scanner: escalated {task_id} → {target} on {board}")

    conn.close()
    return actions

# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    projects = load_projects()
    if not projects:
        return  # empty list = silent exit

    all_actions = []
    for project in projects:
        board = project.get("board", "")
        path = project.get("path", "")
        name = project.get("name", board)

        if not board or not path:
            continue
        if not Path(path).is_dir():
            continue

        try:
            all_actions.extend(phase_bead_sync(board, path))
        except Exception as e:
            all_actions.append(f"bead-sync ERROR [{name}]: {e}")

        try:
            all_actions.extend(phase_dispatch(board, path))
        except Exception as e:
            all_actions.append(f"dispatch ERROR [{name}]: {e}")

        try:
            all_actions.extend(phase_human_escalations(board, path))
        except Exception as e:
            all_actions.append(f"human-ping ERROR [{name}]: {e}")

        try:
            all_actions.extend(scan_board(board))
        except Exception as e:
            all_actions.append(f"scanner ERROR [{name}]: {e}")

    if all_actions:
        log(f"{len(all_actions)} action(s):")
        for a in all_actions:
            print(f"  - {a}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[workflow-engine ERROR] {e}", file=sys.stderr)
        sys.exit(0)
