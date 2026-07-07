#!/usr/bin/env bash
# beads-watchdog.sh — scans ACTIVE beads projects for ready work
# and creates a kanban task on the PROJECT'S OWN BOARD for tech-lead.
#
# BOARD LAYOUT (hybrid model):
#   hermes-hq    → scout + researcher tasks (cross-project research)
#   <project>    → tech-lead coding tasks (one board per project)
#
# SAFETY: three controls prevent duplicate/parallel tasks:
#   1. Checks if tech-lead already has a running task → skips if yes
#   2. Uses --idempotency-key per beads issue → prevents duplicate tasks
#   3. max_in_progress_per_profile: 1 in config → dispatcher caps at 1 running
#
# Silent when nothing ready. Reports when work exists. Zero token cost.

set -euo pipefail

WORKSPACE="$HOME/workspace"
ACTIVE_FILE="${HERMES_HOME:-$HOME/.hermes/profiles/tech-lead}/config/active-projects.json"
PROCESSOR="${HERMES_HOME:-$HOME/.hermes/profiles/tech-lead}/scripts/process-beads.py"
PROFILE="tech-lead"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# ─── Read active projects ───────────────────────────────────────────
if [ ! -f "$ACTIVE_FILE" ]; then exit 1; fi

ACTIVE_PROJECTS=$(python3 -c "
import json
with open('$ACTIVE_FILE') as f: cfg = json.load(f)
for p in cfg.get('active_projects', []): print(p)
" 2>/dev/null)

if [ -z "$ACTIVE_PROJECTS" ]; then exit 0; fi

# ─── CONTROL 1: Check if tech-lead already running on ANY project board ─
is_running=0
for project_name in $ACTIVE_PROJECTS; do
  hermes kanban --board "$project_name" list --assignee "$PROFILE" --status running --json 2>/dev/null > "$TMP_DIR/running.json" || echo "[]" > "$TMP_DIR/running.json"
  count=$(python3 -c "import json; print(len(json.load(open('$TMP_DIR/running.json'))))" 2>/dev/null || echo "0")
  if [ "$count" -gt 0 ]; then
    is_running=1
    break
  fi
done

if [ "$is_running" -eq 1 ]; then exit 0; fi

# ─── Scan beads projects ────────────────────────────────────────────
output=""
tasks_created=0

for project_name in $ACTIVE_PROJECTS; do
  project_dir="$WORKSPACE/$project_name"
  if [ ! -d "$project_dir/.beads" ]; then continue; fi
  if ! command -v bd &>/dev/null; then continue; fi

  # Get ready issues
  (cd "$project_dir" && bd ready --json 2>/dev/null) > "$TMP_DIR/ready.json" || continue

  # Get existing tasks on THIS PROJECT'S board
  hermes kanban --board "$project_name" list --assignee "$PROFILE" --json 2>/dev/null > "$TMP_DIR/existing.json" || echo "[]" > "$TMP_DIR/existing.json"

  # Process: filter duplicates, create tasks, build report
  python3 "$PROCESSOR" "$project_name" "$project_dir" "$PROFILE" \
    "$TMP_DIR/ready.json" "$TMP_DIR/existing.json" "$TMP_DIR/report.txt" "$TMP_DIR/created.txt" \
    "$project_name" \
    2>/dev/null && {
      report=$(cat "$TMP_DIR/report.txt" 2>/dev/null)
      created=$(cat "$TMP_DIR/created.txt" 2>/dev/null)
      if [ -n "$report" ]; then
        output+="$report"
        tasks_created=$((tasks_created + ${created:-0}))
      fi
    }
done

# ─── Output ─────────────────────────────────────────────────────────
if [ -z "$output" ]; then exit 0; fi

echo "🔔 **Beads Watchdog Report**"
echo ""
echo -e "$output"
if [ "$tasks_created" -gt 0 ]; then
  echo "⚡ $tasks_created task(s) created on project boards for tech-lead."
  echo "   Dispatcher will pick them up within 60 seconds."
else
  echo "All ready issues already have tasks on their project boards."
fi
