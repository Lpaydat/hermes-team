#!/usr/bin/env bash
# Grill RPC v0.4 — decision-tree branches.
#
# Three responsibilities:
# 1. Before sending: inject [BRANCH STATE] + active branch content as prefix
# 2. After receiving: extract <Q> question, detect <LOCK> and <NEXT-BRANCH>
# 3. Log Q&A to the active branch file so PO can't re-ask
#
# The orchestrator (builder) decides when to move between branches and locks
# decisions manually via branch file updates. PO just grills in natural prose.
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md
#
# Env:
#   HERMES_GRILL_STATE_DIR — state directory (default: script dir)

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

# --- 1. Build state prefix from _state.md + active branch file ---
get_active_branch() {
    # Extract active branch name from _state.md
    grep '^## Active branch' -A1 "$STATE_FILE" | tail -1 | tr -d '[:space:]'
}

ACTIVE_BRANCH=$(get_active_branch)
ACTIVE_FILE="$CONTEXT_DIR/${ACTIVE_BRANCH}.md"
if [[ ! -f "$ACTIVE_FILE" ]]; then
    # Try with number prefix (01-product.md)
    ACTIVE_FILE=$(ls "$CONTEXT_DIR"/??-"${ACTIVE_BRANCH}".md 2>/dev/null | head -1)
    [[ -f "$ACTIVE_FILE" ]] || { echo "ERROR: No branch file for '$ACTIVE_BRANCH'" >&2; exit 1; }
fi

# Extract just the table from _state.md (the branch overview)
STATE_TABLE=$(sed -n '/^| #/,/^$/p' "$STATE_FILE")
BRANCH_DECISIONS=$(sed -n '/^## Decisions/,/^## /p' "$ACTIVE_FILE" | grep -v '^##' | grep -v '^$' | head -20)

# Build the prefix — compact, shows what's locked + what's been asked
PREFIX="[GRILL STATE
${STATE_TABLE}

## Active branch: ${ACTIVE_BRANCH}
### Decisions locked:
${BRANCH_DECISIONS}

### Questions already asked in this branch:
$(sed -n '/^## Questions asked/,/^##\|^$/p' "$ACTIVE_FILE" | grep -v '^##' | grep -v '^$')
]"

# --- 2. Resume PO with state prefix + answer ---
RAW_OUTPUT=$(hermes -p product-owner --resume "$SESSION_ID" \
    -z "${PREFIX}

${ANSWER}" --cli 2>&1) || true

# --- 3. Log this Q&A to the active branch file ---
# Extract the question from PO output
QUESTION=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }' || true)

# Always log the exchange (even without <Q> tags, PO asked something)
LOG_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
Q_NUM=$(grep -c "^Q[0-9]" "$ACTIVE_FILE" 2>/dev/null || echo "0")
Q_NUM=$((Q_NUM + 1))

# Append Q&A to branch file
{
    echo ""
    echo "Q${Q_NUM} [${LOG_TIMESTAMP}]"
    echo "A: ${ANSWER:0:200}"
    if [[ -n "$QUESTION" ]]; then
        echo "Q: ${QUESTION}"
    else
        echo "Q: (no <Q> tag — see raw output)"
    fi
} >> "$ACTIVE_FILE"

# Update "Questions asked" count in _state.md
TOTAL_Q=$(grep -c "^Q[0-9]" "$CONTEXT_DIR"/*.md 2>/dev/null || echo "0")
sed -i "s/^## Questions asked.*/## Questions asked (all branches)\n${TOTAL_Q}/" "$STATE_FILE" 2>/dev/null || true

# --- 4. Extract and print question ---
if [[ -n "$QUESTION" ]]; then
    echo "$QUESTION"
else
    # Fallback: PO didn't use <Q> tags. Print raw output to stderr.
    echo "WARNING: PO did not use <Q> tags. Raw output on stderr." >&2
    echo "---" >&2
    echo "$RAW_OUTPUT" >&2
    echo "---" >&2
    echo "ERROR: Could not extract question. Check stderr." >&2
    exit 1
fi
