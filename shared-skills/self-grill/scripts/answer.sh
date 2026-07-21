#!/usr/bin/env bash
# Grill RPC v0.3 — graph-backed state, tag extraction.
#
# Three responsibilities:
# 1. Before sending: inject [STATE: ...] prefix so PO sees what's locked/open
# 2. After receiving: extract <Q> question, <LOCK> decisions, <DONE> signal
# 3. Write LOCKs to graph DB via graph_state.py
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md
#
# Env:
#   HERMES_GRILL_STATE_DIR — state directory (default: script dir)
#   HERMES_GRILL_TOPIC     — graph topic tag (required)

set -euo pipefail

STATE_DIR="${HERMES_GRILL_STATE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
SESSION_KEY_FILE="$STATE_DIR/SESSION.key"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GRAPH_CMD="python3 $(dirname "$(readlink -f "$0")")/graph_state.py"

# --- Topic must be set ---
TOPIC="${HERMES_GRILL_TOPIC:-}"
if [[ -z "$TOPIC" ]]; then
    # Try reading from TOPIC file
    if [[ -f "$STATE_DIR/TOPIC" ]]; then
        TOPIC=$(cat "$STATE_DIR/TOPIC")
    else
        echo "ERROR: HERMES_GRILL_TOPIC not set and no TOPIC file in $STATE_DIR" >&2
        exit 1
    fi
fi

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
    echo "ERROR: No SESSION.key found at $SESSION_KEY_FILE" >&2
    echo "       Launch PO first, then capture session key." >&2
    exit 1
fi
SESSION_ID=$(cat "$SESSION_KEY_FILE")

# --- 1. Inject state prefix ---
STATE_PREFIX=$($GRAPH_CMD status "$TOPIC" 2>/dev/null || echo "")

# --- 2. Send answer + capture PO output ---
RAW_OUTPUT=$(hermes -p product-owner --resume "$SESSION_ID" \
    -z "${STATE_PREFIX}

${ANSWER}" --cli 2>&1) || true

# --- 3. Check for <DONE> tag ---
if echo "$RAW_OUTPUT" | perl -0777 -ne 'exit 0 if /<DORF>/s || /<DONE>/s'; then
    $GRAPH_CMD done "$TOPIC" 2>/dev/null || true
    # Still try to extract any final locks
fi

if echo "$RAW_OUTPUT" | grep -q '<DONE>'; then
    $GRAPH_CMD done "$TOPIC" 2>/dev/null || true
fi

# --- 4. Extract <LOCK> tags and write to graph ---
# Format: <LOCK title="D5: Generation method">deterministic templates, NOT LLM</LOCK>
LOCKS=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'while(/<LOCK\s+title="([^"]*)"[^>]*>(.*?)<\/LOCK>/gs){print "$1\x1f$2\n"}' || true)
if [[ -n "$LOCKS" ]]; then
    while IFS=$'\x1f' read -r title content; do
        if [[ -n "$title" ]]; then
            $GRAPH_CMD lock "$TOPIC" "$title" "$content" 2>/dev/null || true
        fi
    done <<< "$LOCKS"
fi

# --- 5. Extract question ---
QUESTION=$(echo "$RAW_OUTPUT" | perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }' || true)

if [[ -n "$QUESTION" ]]; then
    echo "$QUESTION"
else
    # Check if grill is done
    if $GRAPH_CMD is-done "$TOPIC" 2>/dev/null; then
        # Grill complete — print nothing, exit clean
        exit 0
    fi
    # No <Q> tags found — fallback
    echo "WARNING: PO did not use <Q> tags. Raw output on stderr." >&2
    echo "---" >&2
    echo "$RAW_OUTPUT" >&2
    echo "---" >&2
    echo "ERROR: Could not extract question. Check stderr for raw output." >&2
    exit 1
fi
