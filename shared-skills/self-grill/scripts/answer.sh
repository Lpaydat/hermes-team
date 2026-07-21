#!/usr/bin/env bash
# Send an answer to PO's current question via session resume.
# Blocks until PO finishes its turn (writes next question or DONE.flag).
#
# Usage:
#   ./answer.sh "<answer text>"
#   ./answer.sh --file path/to/answer.md

set -euo pipefail

STATE_DIR="${HERMES_GRILL_STATE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
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

hermes -p product-owner --resume "$SESSION_ID" -z "$ANSWER" --cli
