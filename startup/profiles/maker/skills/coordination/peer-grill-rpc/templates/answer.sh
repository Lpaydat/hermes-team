#!/usr/bin/env bash
# Grill RPC answer helper — sends the builder's answer to the griller via session resume.
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md
#
# Reads SESSION_ID from QUESTION.md, calls hermes -p <griller> --resume <id> -z "<answer>" --cli.
# Blocks until griller finishes its turn (writes next Q or DONE.flag).
#
# Customize GRILL_PROFILE and STATE_DIR for your setup.

set -euo pipefail

GRILL_PROFILE="${GRILL_PROFILE:-product-owner}"
STATE_DIR="${GRILL_STATE_DIR:-/home/lpaydat//tmp/grill-rpc}"
QUESTION_FILE="$STATE_DIR/QUESTION.md"

[[ -f "$QUESTION_FILE" ]] || { echo "ERROR: No QUESTION.md found at $QUESTION_FILE" >&2; exit 1; }

SESSION_ID=$(grep -m1 '^SESSION_ID: ' "$QUESTION_FILE" 2>/dev/null | sed 's/^SESSION_ID: //' || true)
[[ -n "${SESSION_ID:-}" ]] || { echo "ERROR: No SESSION_ID found in $QUESTION_FILE" >&2; exit 1; }

if [[ "${1:-}" == "--file" ]]; then
    ANSWER=$(cat "$2")
elif [[ -n "${1:-}" ]]; then
    ANSWER="$1"
else
    echo "Usage: $0 \"<answer text>\" | --file <path>" >&2
    exit 1
fi

hermes -p "$GRILL_PROFILE" --resume "$SESSION_ID" -z "$ANSWER" --cli
