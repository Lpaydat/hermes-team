#!/bin/bash
# Project Discovery guard — runs BEFORE the agent (wakeAgent gate, zero tokens on skip).
#
# Wakes the discovery agent only when:
#   1. active-projects.json lists at least one project to scan, AND
#   2. something actually changed since the last discovery run (git HEAD moved,
#      or a .driver/goal.md was edited)
# When active_projects is empty → guard NEVER wakes (no projects to scan).
# Deliberately does NOT fingerprint .beads/ — discovery and hygiene mutate beads
# themselves, and including them would make the guard wake on its own wake.
#
# Fail-open: any error in fingerprinting → wake the agent (preserves old behavior).

SNAPSHOT="$HOME/.hermes/profiles/tech-lead/cron/.discovery-fingerprint"
ACTIVE_PROJECTS="$HOME/.hermes-teams/startup/active-projects.json"

# ── Gate 1: Check if any projects are in the active list ────────────────
# If active_projects is empty or missing → don't wake the agent at all.
ACTIVE_COUNT=$(python3 -c "
import json, sys
try:
    with open('$ACTIVE_PROJECTS') as f:
        data = json.load(f)
    print(len(data.get('active_projects', [])))
except:
    print(0)
" 2>/dev/null)

if [ -z "$ACTIVE_COUNT" ] || [ "$ACTIVE_COUNT" = "0" ]; then
    echo "STATUS:NO_ACTIVE_PROJECTS — active-projects list is empty, skipping discovery."
    echo '{"wakeAgent": false}'
    exit 0
fi

# ── Gate 2: Fingerprint only the active projects ────────────────────────
ACTIVE_DIRS=$(python3 -c "
import json, os
try:
    with open('$ACTIVE_PROJECTS') as f:
        data = json.load(f)
    for p in data.get('active_projects', []):
        # Resolve path (expand ~)
        path = os.path.expanduser(p.get('path', p if isinstance(p, str) else ''))
        if path and os.path.isdir(path):
            print(path)
except:
    pass
" 2>/dev/null)

if [ -z "$ACTIVE_DIRS" ]; then
    echo "STATUS:NO_ACTIVE_DIRS — active list has entries but no valid paths found."
    echo '{"wakeAgent": false}'
    exit 0
fi

FINGERPRINT=$(
  {
    echo "$ACTIVE_DIRS" | while read -r project_dir; do
      remote=$(git -C "$project_dir" remote get-url origin 2>/dev/null)
      head=$(git -C "$project_dir" rev-parse HEAD 2>/dev/null)
      goal_mtime=$(stat -c %Y "$project_dir/.driver/goal.md" 2>/dev/null)
      echo "$remote|$head|$goal_mtime"
    done
  } | sort -u | md5sum | cut -d' ' -f1
)

if [ -z "$FINGERPRINT" ]; then
    echo "STATUS:GUARD_ERROR — fingerprint empty, failing open."
    echo "ACTION:RUN — run the full discovery scan."
    exit 0
fi

LAST=$(cat "$SNAPSHOT" 2>/dev/null)

if [ "$FINGERPRINT" = "$LAST" ]; then
    echo "STATUS:NO_CHANGES — no git HEAD or goal.md changes across projects since last discovery."
    echo '{"wakeAgent": false}'
else
    # Update snapshot at wake time: if this run fails, we skip until the next
    # real change — acceptable for an advisory 4-hourly scan.
    echo "$FINGERPRINT" > "$SNAPSHOT"
    echo "STATUS:CHANGES_DETECTED — project state changed since last discovery."
    echo "ACTION:RUN — run the full discovery scan."
fi
