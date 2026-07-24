#!/usr/bin/env bash
# Grill RPC v0.7 — dynamic branches, no-tag-tolerant, auto-state.
#
# Responsibilities:
# 1. Extract LOCK decisions from builder's answer → write to branch file
# 2. Inject [GRILL STATE] prefix (branch table + active branch Q&A)
# 3. Send answer to PO via session resume
# 4. Extract question: <Q> tags first, fallback to last paragraph with ?
# 5. Log Q&A to active branch file
# 6. Auto-update _state.md decision counts (dynamic, not hardcoded)
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md

set -euo pipefail

STATE_DIR="${HERMES_GRILL_STATE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
SESSION_KEY_FILE="$STATE_DIR/SESSION.key"
CONTEXT_DIR="$STATE_DIR/context"
STATE_FILE="$CONTEXT_DIR/_state.md"

[[ -f "$STATE_FILE" ]] || { echo "ERROR: No context/_state.md. Run init_branches.sh first." >&2; exit 1; }

# --- Build the answer text ---
if [[ "${1:-}" == "--file" ]]; then
    ANSWER=$(cat "$2")
elif [[ -n "${1:-}" ]]; then
    ANSWER="$1"
else
    echo "Usage: $0 \"<answer text>\" | --file <path>" >&2
    exit 1
fi

# --- Get session key ---
if [[ ! -f "$SESSION_KEY_FILE" ]]; then
    echo "ERROR: No SESSION.key at $SESSION_KEY_FILE" >&2
    exit 1
fi
SESSION_ID=$(cat "$SESSION_KEY_FILE")

# --- Resolve active branch ---
# Branch name in _state.md may have spaces; file is slugified (spaces→hyphens)
ACTIVE_BRANCH=$(grep '^## Active branch' -A1 "$STATE_FILE" | tail -1 | sed 's/^ *//;s/ *$//')
ACTIVE_SLUG=$(echo "$ACTIVE_BRANCH" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')

# Try: exact slug, then glob match
ACTIVE_FILE="$CONTEXT_DIR/${ACTIVE_SLUG}.md"
if [[ ! -f "$ACTIVE_FILE" ]]; then
    # Try globbing — maybe slug has extra characters
    ACTIVE_FILE=$(ls "$CONTEXT_DIR"/*"${ACTIVE_SLUG}"*.md 2>/dev/null | head -1 || true)
fi
if [[ ! -f "$ACTIVE_FILE" ]]; then
    # Try matching by the raw branch name
    ACTIVE_FILE=$(ls "$CONTEXT_DIR"/*"$(echo "$ACTIVE_BRANCH" | tr '[:upper:]' '[:lower:]')"*.md 2>/dev/null | head -1 || true)
fi
[[ -f "$ACTIVE_FILE" ]] || { echo "ERROR: No branch file for '$ACTIVE_BRANCH' (tried slug: '$ACTIVE_SLUG')." >&2; exit 1; }

# --- 1. Extract LOCK decisions from builder's answer ---
LOCKS=$(echo "$ANSWER" | grep -iE 'Lock D[0-9]+:' || true)
if [[ -n "$LOCKS" ]]; then
    _tmp=$(mktemp)
    _lock_written=0
    while IFS= read -r line; do
        echo "$line" >> "$_tmp"
        if echo "$line" | grep -q '^## Decisions'; then
            echo "$LOCKS" >> "$_tmp"
            _lock_written=1
        fi
    done < "$ACTIVE_FILE"
    if [[ "$_lock_written" -eq 0 ]]; then
        echo "" >> "$_tmp"
        echo "## Decisions" >> "$_tmp"
        echo "$LOCKS" >> "$_tmp"
    fi
    cp "$_tmp" "$ACTIVE_FILE"
    rm -f "$_tmp"
fi

# --- 2. Build state prefix ---
STATE_TABLE=$(sed -n '/^| #/,/^$/p' "$STATE_FILE")
BRANCH_DECISIONS=$(grep -iE '^Lock D[0-9]|^D[0-9]' "$ACTIVE_FILE" 2>/dev/null || echo "(none yet)")
BRANCH_QUESTIONS=$(grep '^Q[0-9]' "$ACTIVE_FILE" 2>/dev/null || echo "(none yet)")

PREFIX="[GRILL STATE
${STATE_TABLE}
Active branch: ${ACTIVE_BRANCH}
Decisions locked: ${BRANCH_DECISIONS}
Questions already asked: ${BRANCH_QUESTIONS}
Do NOT re-ask these questions.]"

# --- 3. Send answer to PO ---
GRILL_TIMEOUT="${HERMES_GRILL_TIMEOUT:-600}"
# CRITICAL: unset HERMES_KANBAN_* so PO doesn't inherit builder's kanban task
# and load the worker protocol (which causes it to block the builder's card).
RAW_OUTPUT=$(env -u HERMES_KANBAN_TASK \
    -u HERMES_KANBAN_WORKSPACE \
    -u HERMES_KANBAN_RUN_ID \
    -u HERMES_KANBAN_CLAIM_LOCK \
    -u HERMES_KANBAN_BOARD \
    -u HERMES_KANBAN_DB \
    -u HERMES_PROFILE \
    timeout "$GRILL_TIMEOUT" hermes -p product-owner --resume "$SESSION_ID" \
    -z "${PREFIX}

${ANSWER}" --cli 2>&1) || true

if [[ -z "$RAW_OUTPUT" ]]; then
    echo "ERROR: hermes --resume produced no output — likely timed out after ${GRILL_TIMEOUT}s or API dropped." >&2
    echo "Fix: increase HERMES_GRILL_TIMEOUT env var, or check that the model/provider is responding." >&2
    exit 1
fi

# --- 4. Extract question ---
QUESTION=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }' || true)

if [[ -z "$QUESTION" ]]; then
    QUESTION=$(echo "$RAW_OUTPUT" | awk '/^$/{p=""} {p=p"\n"$0} END{print p}' | grep -v '^$' | tail -10 | awk '/\?/{found=1} found{print}' | head -10 | tr '\n' ' ' | sed 's/^ *//;s/ *$//' || true)
fi

# --- 5. Log Q&A to branch file ---
LOG_TIMESTAMP=$(LC_ALL=C date -u +%Y-%m-%dT%H:%M:%SZ)
Q_NUM=$(grep -c "^Q[0-9]" "$ACTIVE_FILE" 2>/dev/null || true)
Q_NUM=${Q_NUM:-0}
Q_NUM=$((Q_NUM + 1))

{
    echo ""
    echo "Q${Q_NUM} [${LOG_TIMESTAMP}]"
    echo "A: ${ANSWER:0:200}"
    if [[ -n "$QUESTION" ]]; then
        echo "Q: ${QUESTION}"
    else
        echo "Q: (extraction failed — see raw output)"
    fi
} >> "$ACTIVE_FILE"

# --- 6. Auto-update _state.md decision counts (dynamic) ---
# Parse each branch row from _state.md and update its decision count
while IFS='|' read -r _num _name _status _decisions; do
    num=$(echo "$_num" | tr -d ' ')
    name=$(echo "$_name" | sed 's/^ *//;s/ *$//')
    [[ -z "$name" || "$name" == "#" ]] && continue
    
    slug=$(echo "$name" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')
    bfile="$CONTEXT_DIR/${slug}.md"
    [[ -f "$bfile" ]] || bfile=$(ls "$CONTEXT_DIR"/*"${slug}"*.md 2>/dev/null | head -1 || true)
    
    if [[ -f "$bfile" ]]; then
        count=$(grep -ic '^Lock D[0-9]\|^D[0-9]' "$bfile" 2>/dev/null || echo "0")
        count=${count:-0}
        # Escape sed special chars in name
        esc_name=$(echo "$name" | sed 's/[&/\]/\\&/g')
        sed -i "s/| ${num} | ${esc_name} | \([a-z]*\) | [0-9]* |/| ${num} | ${esc_name} | \1 | ${count} |/" "$STATE_FILE" 2>/dev/null || true
    fi
done < <(grep '^| [0-9]' "$STATE_FILE" 2>/dev/null || true)

# --- Print question ---
if [[ -n "$QUESTION" ]]; then
    echo "$QUESTION"
else
    echo "WARNING: Could not extract question. Raw output on stderr." >&2
    echo "$RAW_OUTPUT" >&2
    exit 1
fi
