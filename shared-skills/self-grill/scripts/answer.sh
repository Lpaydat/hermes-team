#!/usr/bin/env bash
# Grill RPC — send answer to PO, extract next question from output.
#
# Captures PO's full output, extracts ONLY the question (wrapped in <Q>...</Q> tags),
# and prints it. PO's verbose reasoning stays here, never reaches the orchestrator's context.
#
# Also handles session tracking: captures the real hermes session key on first launch,
# saves to SESSION.key, and resumes it on subsequent calls.
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md
#
# Exit codes:
#   0  — question extracted and printed to stdout
#   0  — DONE.flag detected (stdout empty, check $STATE_DIR/DONE.flag)
#   1  — error (message to stderr)

set -euo pipefail

STATE_DIR="${HERMES_GRILL_STATE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
SESSION_KEY_FILE="$STATE_DIR/SESSION.key"
DONE_FILE="$STATE_DIR/DONE.flag"

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
if [[ -f "$SESSION_KEY_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_KEY_FILE")
else
    echo "ERROR: No SESSION.key found at $SESSION_KEY_FILE" >&2
    echo "       The PO session must be launched first. See SKILL.md." >&2
    exit 1
fi

# --- Resume PO session with our answer, capture full output ---
# hermes --resume blocks until PO finishes its turn
RAW_OUTPUT=$(hermes -p product-owner --resume "$SESSION_ID" -z "$ANSWER" --cli 2>&1) || true

# --- Check if PO wrote DONE ---
if [[ -f "$DONE_FILE" ]]; then
    # Grill is done — print nothing, exit clean
    exit 0
fi

# --- Extract question from <Q>...</Q> tags ---
# Use perl for multiline extraction (sed is unreliable across newlines)
QUESTION=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }' || true)

if [[ -n "$QUESTION" ]]; then
    # Clean extraction — print just the question
    echo "$QUESTION"
else
    # No <Q> tags found — PO didn't follow the format.
    # Fallback: print the full output so the orchestrator can read it manually.
    # This is a safety net, not the happy path.
    echo "WARNING: PO did not use <Q> tags. Raw output below." >&2
    echo "---" >&2
    echo "$RAW_OUTPUT" >&2
    echo "---" >&2
    echo "ERROR: Could not extract question. Check stderr for raw output." >&2
    exit 1
fi
