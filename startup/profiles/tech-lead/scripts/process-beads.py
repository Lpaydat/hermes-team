#!/usr/bin/env python3
"""Process beads ready issues: filter duplicates, create kanban tasks, output report.

Args: project_name project_dir profile ready.json existing.json report.txt created.txt board_name
"""
import json, subprocess, sys

project_name = sys.argv[1]
project_dir = sys.argv[2]
profile = sys.argv[3]
ready_path = sys.argv[4]
existing_path = sys.argv[5]
report_path = sys.argv[6]
created_path = sys.argv[7]
board_name = sys.argv[8]

# Load ready issues
with open(ready_path) as f:
    ready = json.load(f)

if not ready:
    sys.exit(0)

# Load existing kanban tasks on this board
with open(existing_path) as f:
    existing = json.load(f)

# Build set of beads IDs already on the board
existing_ids = set()
for t in existing:
    title = t.get('title', '')
    if title.startswith('[') and ']' in title:
        bid = title[1:title.index(']')]
        if '-' in bid:
            existing_ids.add(bid)

# Split into new vs existing
new_issues = [i for i in ready if i.get('id', '') not in existing_ids]

# Build report
lines = []
for issue in ready:
    iid = issue.get('id', '?')
    title = issue.get('title', 'untitled')
    priority = issue.get('priority', 3)
    lines.append(f"  [P{priority}] {iid}: {title}")

report = f"\n📋 **{project_name}** ({len(ready)} ready"
if new_issues:
    report += f", {len(new_issues)} NEW"
report += ")\n" + "\n".join(lines) + "\n\n"

with open(report_path, 'w') as f:
    f.write(report)

# Create tasks for new issues only (on this project's board)
created = 0
for issue in new_issues:
    iid = issue.get('id', 'unknown')
    title = issue.get('title', 'untitled')
    priority = issue.get('priority', 3)
    kanban_priority = max(1, min(5, 5 - priority))

    task_title = f"[{iid}] {title}"
    body = (
        f"Auto-filed by beads-watchdog from project: {project_name}\n\n"
        f"Beads issue: {iid}\n"
        f"Priority: P{priority}\n"
        f"Source: bd ready in {project_dir}\n\n"
        f"Load the loops-engineering skill and execute this issue "
        f"through the 5-phase loop."
    )

    result = subprocess.run(
        ['hermes', 'kanban', '--board', board_name, 'create', task_title,
         '--assignee', profile,
         '--idempotency-key', f'beads-{iid}',
         '--priority', str(kanban_priority),
         '--body', body],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        created += 1

with open(created_path, 'w') as f:
    f.write(str(created))
