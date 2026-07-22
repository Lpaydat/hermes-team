#!/usr/bin/env bash
# Add a new branch to the grill dynamically.
#
# Usage: add_branch.sh <state_dir> "<branch_name>" ["<seed question>"]

set -euo pipefail

STATE_DIR="${1:?Usage: add_branch.sh <state_dir> <branch_name> [seed_question]}"
BRANCH_NAME="${2:?Usage: add_branch.sh <state_dir> <branch_name> [seed_question]}"
SEED="${3:-}"
CONTEXT_DIR="$STATE_DIR/context"
STATE_FILE="$CONTEXT_DIR/_state.md"
SLUG=$(echo "$BRANCH_NAME" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')

# Create branch file
BRANCH_FILE="$CONTEXT_DIR/${SLUG}.md"
if [[ -f "$BRANCH_FILE" ]]; then
    echo "Branch '$BRANCH_NAME' already exists: $BRANCH_FILE" >&2
    exit 0
fi

cat > "$BRANCH_FILE" << EOF
# ${BRANCH_NAME}

## Decisions
(none yet)

## Questions asked
(none yet)
EOF

# Add row to _state.md table
BRANCH_NUM=$(grep -c '^| [0-9]' "$STATE_FILE" 2>/dev/null || true)
BRANCH_NUM=${BRANCH_NUM:-0}
BRANCH_NUM=$((BRANCH_NUM + 1))

# Insert row before the empty line after table
sed -i "/^|---|/a | ${BRANCH_NUM} | ${BRANCH_NAME} | pending | 0 |" "$STATE_FILE"

echo "Added branch: ${BRANCH_NAME} (#${BRANCH_NUM})"
echo "File: ${BRANCH_FILE}"
