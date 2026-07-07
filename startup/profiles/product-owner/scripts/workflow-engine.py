#!/usr/bin/env python3
"""
Workflow Engine — combined cron for the dev workflow.

Runs three phases in order, every tick:
  1. bead-sync:   sync kanban card status → bd bead status (closes done beads, promotes dependents)
  2. auto-dispatch: check bd ready → create tech-lead cards for new work
  3. board-scanner:  detect blocked tasks → escalate to proper profile

Zero-token (no_agent=True). Pure Python + subprocess to hermes CLI.
Silent when nothing to do. Outputs only when actions are taken.

Usage:
  python3 workflow-engine.py [--board startup] [--dry-run]
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

BOARD = os.environ.get("HERMES_KANBAN_BOARD", "startup")
DRY_RUN = "--dry-run" in sys.argv
KANBAN_DB = str(Path.home() / ".hermes-teams/startup/kanban/boards" / BOARD / "kanban.db")
WORKSPACE_ROOT = "/home/lpaydat/dev-workflow-battle-tests"
INCIDENTS_FILE = Path.home() / "dev-workflow-battle-tests" / "INCIDENTS.md"

# ── Helpers ──────────────────────────────────────────────────────────────

def run_kanban(args):
    cmd = ["hermes", "kanban", "--board", BOARD] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stdout.strip()

def run_kanban_json(args):
    ok, out = run_kanban(args + ["--json"])
    if not ok:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

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

def find_bead_projects():
    root = Path(WORKSPACE_ROOT)
    if not root.is_dir():
        return []
    return [str(e) for e in sorted(root.iterdir()) if e.is_dir() and (e / ".beads").is_dir()]

def read_kanban_card_status(bead_id):
    key = f"bead-{bead_id}"
    try:
        conn = sqlite3.connect(KANBAN_DB)
        row = conn.execute("SELECT status FROM tasks WHERE idempotency_key = ?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None

def read_bead_statuses(project_dir):
    try:
        r = subprocess.run(["bd", "list", "--all", "--json"], cwd=project_dir, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        beads = json.loads(r.stdout)
        if not isinstance(beads, list):
            return None
        return {b["id"]: {"status": b.get("status", "open"), "labels": b.get("labels", [])} for b in beads if isinstance(b, dict) and "id" in b}
    except Exception:
        return None

def update_bead_status(project_dir, bead_id, target):
    if DRY_RUN:
        return True
    try:
        r = subprocess.run(["bd", "update", bead_id, "-s", target], cwd=project_dir, capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False

def phase_bead_sync():
    """Sync bd bead status from kanban card status."""
    changes = []
    projects = find_bead_projects()
    if not projects:
        return changes

    for project_dir in projects:
        bead_map = read_bead_statuses(project_dir)
        if not bead_map:
            continue
        for bead_id, info in bead_map.items():
            if "gt:slot" in info.get("labels", []):
                continue
            card_status = read_kanban_card_status(bead_id)
            if card_status is None or card_status not in STATUS_MAP:
                continue
            target = STATUS_MAP[card_status]
            current = info.get("status", "open")
            if current == "closed":
                continue
            if current == target:
                continue
            if update_bead_status(project_dir, bead_id, target):
                changes.append(f"bead-sync: {bead_id} {current} → {target}")
    return changes

# ══════════════════════════════════════════════════════════════════════════
# PHASE 2: AUTO-DISPATCH — bd ready → create tech-lead cards
# ══════════════════════════════════════════════════════════════════════════

def card_exists_for_bead(bead_id):
    """Check SQLite directly — API doesn't expose idempotency_key."""
    key = f"bead-{bead_id}"
    try:
        conn = sqlite3.connect(KANBAN_DB)
        row = conn.execute("SELECT 1 FROM tasks WHERE idempotency_key = ? AND status != 'archived' LIMIT 1", (key,)).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

def has_active_po_dispatch_card():
    """Check if there's already an active (not done/archived) PO dispatch card."""
    try:
        conn = sqlite3.connect(KANBAN_DB)
        row = conn.execute(
            "SELECT 1 FROM tasks WHERE assignee = 'product-owner' "
            "AND title LIKE '[dispatch]%' AND status NOT IN ('done', 'archived') LIMIT 1"
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

def phase_auto_dispatch():
    """Check bd ready and create a PO dispatch card when there's new work."""
    actions = []
    
    # If PO already has an active dispatch card, don't create another
    if has_active_po_dispatch_card():
        return actions
    
    new_beads = []
    
    for project_dir in find_bead_projects():
        try:
            r = subprocess.run(["bd", "ready", "--json"], cwd=project_dir, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                continue
            beads = json.loads(r.stdout)
            if not isinstance(beads, list):
                continue
        except Exception:
            continue

        for bead in beads:
            bid = bead.get("id", "")
            title = bead.get("title", "Untitled")
            labels = bead.get("labels", [])
            if "gt:slot" in labels:
                continue
            if not bid:
                continue

            if card_exists_for_bead(bid):
                continue
            
            new_beads.append((bid, title, project_dir))
    
    if not new_beads:
        return actions
    
    # Create ONE PO card listing all ready beads — PO dispatches them via dev-dispatch skill
    bead_list = "\n".join(f"- `{bid}` — {title} (project: {pdir})" for bid, title, pdir in new_beads)
    project_dir = new_beads[0][2]  # Use first project's dir as workspace
    
    # Time-based key: each batch is unique. PO completes the card, next batch gets a new one.
    idem_key = f"po-dispatch-{int(time.time())}"
    
    if DRY_RUN:
        actions.append(f"dispatch: would create PO card for {len(new_beads)} ready bead(s)")
        return actions
    
    ok, out = run_kanban([
        "create", f"[dispatch] {len(new_beads)} ready bead(s) to dispatch",
        "--assignee", "product-owner",
        "--body", f"## Ready beads to dispatch\n\n{bead_list}\n\nRun your `dev-dispatch` skill to create tech-lead cards for each.",
        "--workspace", f"dir:{project_dir}",
        "--priority", "20",
        "--idempotency-key", idem_key,
        "--json",
    ])
    if ok:
        actions.append(f"dispatch: created PO card for {len(new_beads)} ready bead(s)")
    else:
        actions.append(f"dispatch: FAILED to create PO card: {out[:80]}")
    
    return actions

# ══════════════════════════════════════════════════════════════════════════
# PHASE 3: BOARD SCANNER — blocked task escalation
# ══════════════════════════════════════════════════════════════════════════

ESCALATION_PREFIX = "[ESCALATION]"
HUMAN_REQUIRED = "HUMAN_REQUIRED"
RESOLVED_PREFIX = "RESOLVED:"

ESCALATION_CHAIN = {
    "developer": "tech-lead",
    "verifier": "tech-lead",
    "tech-lead": "product-owner",
    "product-owner": None,
}

def get_blocked_tasks():
    if not Path(KANBAN_DB).exists():
        return []
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, assignee, title FROM tasks WHERE status = 'blocked' ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_task_comments(task_id):
    if not Path(KANBAN_DB).exists():
        return []
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT body FROM task_comments WHERE task_id = ?", (task_id,)).fetchall()
    conn.close()
    return [r["body"] for r in rows]

def get_block_reason(task_id):
    if not Path(KANBAN_DB).exists():
        return "unknown"
    conn = sqlite3.connect(KANBAN_DB)
    row = conn.execute("SELECT payload FROM task_events WHERE task_id = ? AND kind IN ('blocked','gave_up') ORDER BY created_at DESC LIMIT 1", (task_id,)).fetchone()
    conn.close()
    if not row:
        return "unknown"
    try:
        payload = json.loads(row[0]) if row[0] else {}
        return payload.get("reason") or payload.get("error") or "unknown"
    except json.JSONDecodeError:
        return "unknown"

def has_human_required(task_id):
    return any(HUMAN_REQUIRED in c for c in get_task_comments(task_id))

def find_existing_escalation(blocked_task_id):
    if not Path(KANBAN_DB).exists():
        return None
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id FROM tasks WHERE title LIKE ? AND status NOT IN ('done','archived') ORDER BY created_at DESC",
        (f"{ESCALATION_PREFIX} %{blocked_task_id}%",)
    ).fetchall()
    conn.close()
    return rows[0]["id"] if rows else None

def find_resolved_escalation(blocked_task_id):
    if not Path(KANBAN_DB).exists():
        return None
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT t.id FROM tasks t
           JOIN task_runs r ON r.task_id = t.id AND r.outcome = 'completed'
           WHERE t.title LIKE ? AND t.status = 'done' AND r.summary LIKE ?
           ORDER BY t.completed_at DESC LIMIT 1""",
        (f"{ESCALATION_PREFIX} %{blocked_task_id}%", f"{RESOLVED_PREFIX}%")
    ).fetchall()
    conn.close()
    return rows[0]["id"] if rows else None

def create_escalation_card(blocked_task, target_profile, block_reason):
    task_id = blocked_task["id"]
    title = f"{ESCALATION_PREFIX} Resolve block on {task_id}: {blocked_task['title'][:40]}"
    body = f"""## Escalation: Task {task_id} is blocked

**Blocked task**: {task_id}
**Assignee**: {blocked_task.get('assignee', '?')}
**Title**: {blocked_task.get('title', '?')}
**Block reason**: {block_reason[:500]}

### Instructions
1. Read the blocked task: `kanban_show(task_id="{task_id}")`
2. Read the block reason and any comments
3. Decide: can you resolve this?

**If YES**: Comment your resolution on the blocked task, complete this card with `RESOLVED: <summary>`.
**If NO**: Comment what's needed, block this card (kind=needs_input).
**If HUMAN-ONLY**: Comment `HUMAN_REQUIRED: <reason>` on the blocked task, complete this card."""

    ok, out = run_kanban(["create", title, "--assignee", target_profile, "--priority", "10", "--body", body, "--json"])
    if not ok:
        return None
    try:
        return json.loads(out).get("id")
    except json.JSONDecodeError:
        m = re.search(r"(t_[a-f0-9]+)", out)
        return m.group(1) if m else None

def unblock_task(task_id):
    ok, _ = run_kanban(["unblock", task_id])
    return ok

def log_incident(task_id, incident_type, details):
    INCIDENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(INCIDENTS_FILE, "a") as f:
        f.write(f"\n## [{timestamp}] {incident_type} — {task_id}\n\n{details}\n\n---\n")

def phase_board_scanner():
    """Detect blocked tasks and manage escalations."""
    actions = []
    tasks = get_blocked_tasks()
    if not tasks:
        return actions

    for task in tasks:
        task_id = task["id"]
        assignee = task.get("assignee", "")
        if assignee in ("default", "", None):
            continue
        if has_human_required(task_id):
            continue

        resolved_id = find_resolved_escalation(task_id)
        if resolved_id:
            if DRY_RUN:
                actions.append(f"scanner: would unblock {task_id}")
            elif unblock_task(task_id):
                actions.append(f"scanner: unblocked {task_id} (escalation {resolved_id} resolved)")
                log_incident(task_id, "UNBLOCKED", f"Escalation {resolved_id} resolved.")
            else:
                actions.append(f"scanner: FAILED to unblock {task_id}")
            continue

        if find_existing_escalation(task_id):
            continue

        target = ESCALATION_CHAIN.get(assignee)
        if not target:
            if not DRY_RUN:
                run_kanban(["comment", task_id, "--author", "board-scanner", f"{HUMAN_REQUIRED}: No higher agent profile for {assignee}"])
            actions.append(f"scanner: HUMAN_REQUIRED flagged on {task_id}")
            continue

        block_reason = get_block_reason(task_id)
        if DRY_RUN:
            actions.append(f"scanner: would escalate {task_id} → {target}")
            continue

        card_id = create_escalation_card(task, target, block_reason)
        if card_id:
            actions.append(f"scanner: escalated {task_id} → {target} (card {card_id})")
            log_incident(task_id, f"ESCALATION → {target}", f"Block reason: {block_reason[:300]}\nEscalation card: {card_id}")
        else:
            actions.append(f"scanner: FAILED to escalate {task_id}")
    return actions

# ══════════════════════════════════════════════════════════════════════════
# MAIN — run all three phases in order
# ══════════════════════════════════════════════════════════════════════════

def main():
    all_actions = []

    # Phase 1: bead-sync (closes done beads → may promote dependents for phase 2)
    try:
        all_actions.extend(phase_bead_sync())
    except Exception as e:
        all_actions.append(f"bead-sync ERROR: {e}")

    # Phase 2: auto-dispatch (creates cards for newly-ready beads)
    try:
        all_actions.extend(phase_auto_dispatch())
    except Exception as e:
        all_actions.append(f"dispatch ERROR: {e}")

    # Phase 3: board-scanner (detects new blocks from above phases)
    try:
        all_actions.extend(phase_board_scanner())
    except Exception as e:
        all_actions.append(f"scanner ERROR: {e}")

    # Output — silent when nothing happened
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
