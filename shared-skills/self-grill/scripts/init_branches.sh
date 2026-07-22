#!/usr/bin/env bash
# Initialize grill state with NO hardcoded branches.
# Branches are added dynamically during the grill via add_branch.sh.
#
# Usage: init_branches.sh <state_dir> "<idea>"

set -euo pipefail

STATE_DIR="${1:?Usage: init_branches.sh <state_dir> <idea>}"
IDEA="${2:?Usage: init_branches.sh <state_dir> <idea>}"
CONTEXT_DIR="$STATE_DIR/context"

mkdir -p "$CONTEXT_DIR"

cat > "$CONTEXT_DIR/_state.md" << EOF
# Grill State

Idea: ${IDEA}

## Branches
| # | Branch | Status | Decisions |
|---|--------|--------|-----------|

## Active branch
(none — add branches as the grill progresses)

## How to manage branches
# Add a branch:
#   add_branch.sh "<name>" "<seed question>"
# Set active:
#   set_active.sh "<name>"
# Mark done:
#   sed -i 's/| <name> | active/| <name> | done/' "$CONTEXT_DIR/_state.md"
EOF

echo "Initialized $CONTEXT_DIR (no branches yet — add them as needed)"
