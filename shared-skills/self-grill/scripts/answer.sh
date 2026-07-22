#!/usr/bin/env bash
# Grill RPC v0.5 — branch-based, no-tag-tolerant, auto-state.
#
# Responsibilities:
# 1. Extract LOCK decisions from BUILDER's answer text → write to branch file
# 2. Inject [GRILL STATE] prefix (branch table + active branch Q&A history)
# 3. Send answer to PO via session resume
# 4. Extract question: try <Q> tags first, fallback to last paragraph with ?
# 5. Log Q&A to active branch file
# 6. Auto-update _state.md decision counts
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
ACTIVE_BRANCH=$(grep '^## Active branch' -A1 "$STATE_FILE" | tail -1 | tr -d '[:space:]')
ACTIVE_FILE=$(ls "$CONTEXT_DIR"/??-"${ACTIVE_BRANCH}".md 2>/dev/null | head -1)
[[ -f "$ACTIVE_FILE" ]] || ACTIVE_FILE="$CONTEXT_DIR/${ACTIVE_BRANCH}.md"
[[ -f "$ACTIVE_FILE" ]] || { echo "ERROR: No branch file for '$ACTIVE_BRANCH'" >&2; exit 1; }

# --- 1. Extract LOCK decisions from builder's answer ---
# Format: Lock D{n}: {title} = {content}
# Use grep -E with multiline-aware pattern (grep processes line-by-line)
LOCKS=$(echo "$ANSWER" | grep -iE 'Lock D[0-9]+:' || true)
if [[ -n "$LOCKS" ]]; then
    # Write LOCKs under the Decisions section (before Questions section)
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
# Wrap in timeout to prevent infinite hang if the model stalls or the API drops.
# 600s (10m) default — generous for slower models like glm-5.2.
# The || true catches the timeout's 124 exit code.
GRILL_TIMEOUT="${HERMES_GRILL_TIMEOUT:-600}"
RAW_OUTPUT=$(timeout "$GRILL_TIMEOUT" hermes -p product-owner --resume "$SESSION_ID" \
    -z "${PREFIX}

${ANSWER}" --cli 2>&1) || true

# Detect timeout: if RAW_OUTPUT is empty after a hermes call, the most likely
# cause is timeout killing the process (exit 124) or an API connection drop.
if [[ -z "$RAW_OUTPUT" ]]; then
    echo "ERROR: hermes --resume produced no output — likely timed out after ${GRILL_TIMEOUT}s or API dropped." >&2
    echo "Fix: increase HERMES_GRILL_TIMEOUT env var, or check that the model/provider is responding." >&2
    exit 1
fi

# --- 4. Extract question ---
# Try <Q> tags first
QUESTION=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }' || true)

# Fallback: last paragraph containing a question mark
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

# --- 6. Auto-update _state.md decision counts ---
update_state() {
    local branch_num="$1" branch_name="$2"
    local bfile
    bfile=$(ls "$CONTEXT_DIR"/0${branch_num}-"${branch_name}".md 2>/dev/null | head -1)
    [[ -f "$bfile" ]] || bfile=$(ls "$CONTEXT_DIR"/??-"${branch_name}".md 2>/dev/null | head -1)
    if [[ -f "$bfile" ]]; then
        local count
        count=$(grep -ic '^Lock D[0-9]\|^D[0-9]' "$bfile" 2>/dev/null || echo "0")
        count=${count:-0}
        sed -i "s/| ${branch_num} | ${branch_name} | \([a-z]*\) | [0-9]* |/| ${branch_num} | ${branch_name} | \1 | ${count} |/" "$STATE_FILE" 2>/dev/null || true
    fi
}

update_state 1 product
update_state 2 user
update_state 3 mechanism
update_state 4 data
update_state 5 edges
update_state 6 output
update_state 7 deployment
update_state 8 constraints

# --- Print question ---
if [[ -n "$QUESTION" ]]; then
    echo "$QUESTION"
else
    echo "WARNING: Could not extract question. Raw output on stderr." >&2
    echo "$RAW_OUTPUT" >&2
    exit 1
fi
