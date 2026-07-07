#!/bin/bash
# Task Hygiene guard — runs BEFORE the agent (wakeAgent gate, zero tokens on skip).
#
# Runs the existing zero-token hygiene scanner across ACTIVE projects only.
# All clean → skip the agent entirely. Any findings → print them (they become
# the agent's context) and wake the agent to apply the auto-action policy.
#
# Fail-open: scanner errors on a project are reported and wake the agent.

SCANNER="$HOME/.hermes/profiles/product-owner/skills/software-development/task-hygiene-validator/scripts/scan_hygiene.py"
ACTIVE_PROJECTS_FILE="$HOME/.hermes-teams/startup/profiles/product-owner/config/active-projects.json"
FINDINGS=""
ERRORS=""
SEEN_REMOTES=""

# Read active projects from the config file (same gate as discovery-guard)
if [ ! -f "$ACTIVE_PROJECTS_FILE" ]; then
    echo '{"wakeAgent": false}'
    exit 0
fi

ACTIVE_COUNT=$(python3 -c "
import json
try:
    data = json.load(open('$ACTIVE_PROJECTS_FILE'))
    print(len(data.get('active_projects', [])))
except:
    print(0)
" 2>/dev/null)

if [ "$ACTIVE_COUNT" = "0" ]; then
    echo '{"wakeAgent": false}'
    exit 0
fi

# Get the list of active project paths
ACTIVE_PATHS=$(python3 -c "
import json
try:
    data = json.load(open('$ACTIVE_PROJECTS_FILE'))
    for p in data.get('active_projects', []):
        print(p)
except:
    pass
" 2>/dev/null)

for project_dir in $ACTIVE_PATHS; do
    [ ! -d "$project_dir/.beads" ] && continue

    remote=$(git -C "$project_dir" remote get-url origin 2>/dev/null)
    if [ -n "$remote" ] && echo "$SEEN_REMOTES" | grep -qF "$remote"; then
        continue  # worktree/clone dedup
    fi
    SEEN_REMOTES="$SEEN_REMOTES$remote
"
    OUT=$(cd "$project_dir" && python3 "$SCANNER" "$project_dir" 2>&1)
    RC=$?
    if [ $RC -ne 0 ]; then
        ERRORS="$ERRORS
[scanner error rc=$RC] $project_dir: $(echo "$OUT" | head -3)"
    elif [ -n "$OUT" ]; then
        FINDINGS="$FINDINGS
=== $project_dir ===
$OUT"
    fi
done

if [ -n "$FINDINGS" ] || [ -n "$ERRORS" ]; then
    echo "STATUS:FINDINGS — hygiene issues (or scanner errors) detected; apply the auto-action policy."
    [ -n "$ERRORS" ] && echo "SCANNER ERRORS (investigate, fail-open):$ERRORS"
    [ -n "$FINDINGS" ] && echo "$FINDINGS"
else
    echo "STATUS:ALL_CLEAN — every active project passed the hygiene scan."
    echo '{"wakeAgent": false}'
fi
