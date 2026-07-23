#!/usr/bin/env bash
# queue-builds.sh — reads idea-bank.md, picks top 10 unbuilt ideas by score,
# creates kanban cards assigned to 'builder' for prototype builds.
#
# No AI needed — scores already exist. This is pure sorting + kanban creation.
# Runs as a no_agent cron job (shell only, zero tokens).
#
# Door D (User) ideas always included first, regardless of score.

set -euo pipefail

IDEA_BANK="$HOME/vault/ventures/idea-bank.md"
MARKER="$HOME/vault/ventures/.last-queue"
BOARD="hermes-hq"
MAX_BUILDS=10
TODAY=$(date +%Y-%m-%d)

# Guard: only run once per 6h window
if [ -f "$MARKER" ]; then
    LAST=$(cat "$MARKER")
    NOW_EPOCH=$(date +%s)
    LAST_EPOCH=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
    ELAPSED=$((NOW_EPOCH - LAST_EPOCH))
    if [ "$ELAPSED" -lt 21600 ]; then
        echo "Already queued within last 6h (last: $LAST). Skipping."
        exit 0
    fi
fi

if [ ! -f "$IDEA_BANK" ]; then
    echo "idea-bank.md not found at $IDEA_BANK. Skipping."
    exit 0
fi

# Parse idea-bank.md for buildable ideas with scores
# Format: | # | Score | Origin | Idea | Dossier | Status |
# We want ideas that are unbuilt, deep_dived, spec_written, or killed_high_score
# with a numeric score — NOT BUILT_AWAITING_REVIEW or IN_GRILL

# Extract buildable rows with scores using awk
# Output: score|slug|name|status
IDEAS=$(awk '
BEGIN { FS="|" }
/^## / { section = $0 }
/^\| [0-9]+/ {
    # Columns: | # | Score | Origin | Idea | Dossier | Status |
    num = $2
    score = $3
    origin = $4
    name = $5
    dossier = $6
    status = $7

    # Clean up whitespace
    gsub(/^[ \t]+|[ \t]+$/, "", score)
    gsub(/^[ \t]+|[ \t]+$/, "", name)
    gsub(/^[ \t]+|[ \t]+$/, "", status)
    gsub(/^[ \t]+|[ \t]+$/, "", dossier)

    # Only process ideas with numeric scores
    if (score ~ /^[0-9]+\/25$/) {
        # Extract numeric score
        split(score, parts, "/")
        numeric_score = parts[1]

        # Extract slug from dossier link: [dossier](ideas/<slug>.md)
        if (match(dossier, /\[dossier\]\(ideas\/([^)]+)\.md\)/, slug_match)) {
            slug = slug_match[1]
        } else {
            slug = name
            gsub(/[^a-zA-Z0-9]+/, "-", slug)
            tolower(slug)
        }

        # Skip built or in-grill
        if (status ~ /BUILT_AWAITING_REVIEW/ || status ~ /IN_GRILL/ || status ~ /building/) {
            next
        }

        # Print: score|slug|name|status|origin
        printf "%d\t%s\t%s\t%s\t%s\n", numeric_score, slug, name, status, origin
    }
}
' "$IDEA_BANK")

if [ -z "$IDEAS" ]; then
    echo "No buildable ideas found in idea-bank.md."
    echo "$TODAY" > "$MARKER"
    exit 0
fi

# Sort by score descending, take top N
SORTED=$(echo "$IDEAS" | sort -t$'\t' -k1 -nr | head -n "$MAX_BUILDS")

# Check existing kanban cards — don't create duplicates
EXISTING=$(hermes kanban --board "$BOARD" list --json 2>/dev/null || echo "[]")

# Create kanban cards for each idea
CREATED=0
PREV_ID=""

while IFS=$'\t' read -r score slug name status origin; do
    # Skip if already has a kanban card for this slug
    if echo "$EXISTING" | python3 -c "
import json, sys
tasks = json.load(sys.stdin)
if isinstance(tasks, dict): tasks = tasks.get('tasks', [])
for t in tasks:
    if '$slug' in (t.get('title','') + t.get('body','')).lower():
        sys.exit(0)  # found — skip
sys.exit(1)  # not found — create
" 2>/dev/null; then
        echo "SKIP: $name (already has a kanban card)"
        continue
    fi

    # Create the kanban card
    TITLE="Build prototype: $name"

    BODY="Score: ${score}/25 | Origin: Door ${origin} | Status: ${status}

Read the dossier at ~/vault/ventures/ideas/${slug}.md
Grill with PO using self-grill skill (REQUIRED — answer as founder).
Build prototype. Drop in ~/vault/ventures/prototypes/${slug}/
Update ~/vault/ventures/portfolio.md 'Awaiting Review' section.
Complete this card when done."

    ARGS="--assignee builder --body \"$BODY\""

    if [ -n "$PREV_ID" ]; then
        # Chain sequentially — this card waits for the previous one
        ARGS="$ARGS --parent $PREV_ID"
    fi

    RESULT=$(eval hermes kanban --board "$BOARD" create "$TITLE" $ARGS --json 2>/dev/null || echo "{}")
    TASK_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

    if [ -n "$TASK_ID" ]; then
        PREV_ID="$TASK_ID"
        CREATED=$((CREATED + 1))
        echo "CREATED [$TASK_ID]: [$score] $name (chained to: ${PREV_ID:-none})"
    else
        echo "FAILED: $name"
    fi

done <<< "$SORTED"

# Update marker
echo "$(date -Iseconds)" > "$MARKER"

echo ""
echo "=== Queue Builds Complete ==="
echo "Created: $CREATED kanban cards for builder"
echo "Board: $BOARD"
echo "Marker updated: $MARKER"
