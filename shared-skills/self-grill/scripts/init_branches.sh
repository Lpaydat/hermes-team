#!/usr/bin/env bash
# Initialize decision-tree branch structure for a grill session.
#
# Creates context/ directory with 8 branch files + _state.md.
# Each branch is a design category. PO explores one at a time.
#
# Usage: init_branches.sh <state_dir> "<idea>"

set -euo pipefail

STATE_DIR="${1:?Usage: init_branches.sh <state_dir> <idea>}"
IDEA="${2:?Usage: init_branches.sh <state_dir> <idea>}"
CONTEXT_DIR="$STATE_DIR/context"

mkdir -p "$CONTEXT_DIR"

# --- Branch definitions: filename | category name | seed question ---
BRANCHES=(
  "01-product|Product form|What is this? What does the user interact with?"
  "02-user|User & audience|Who picks this up and what do they do with it?"
  "03-mechanism|Core mechanism|How does it work under the hood?"
  "04-data|Data & inputs|What data goes in? Where does it come from?"
  "05-edges|Edge cases|What happens when there's nothing/empty/broken?"
  "06-output|Output & sharing|What comes out? How does the user share it?"
  "07-deployment|Deployment|Where does this run? What does it cost?"
  "08-constraints|Constraints & scale|Rate limits, cost ceiling, failure modes?"
)

# --- Create branch files ---
for entry in "${BRANCHES[@]}"; do
  IFS='|' read -r slug name seed <<< "$entry"
  cat > "$CONTEXT_DIR/${slug}.md" << EOF
# ${name}

## Decisions
(none yet)

## Questions asked
(none yet)
EOF
done

# --- Create _state.md (the orchestrator reads this every turn) ---
cat > "$CONTEXT_DIR/_state.md" << EOF
# Grill State

Idea: ${IDEA}

## Branches
| # | Branch | Status | Decisions |
|---|--------|--------|-----------|
| 1 | product | pending | 0 |
| 2 | user | pending | 0 |
| 3 | mechanism | pending | 0 |
| 4 | data | pending | 0 |
| 5 | edges | pending | 0 |
| 6 | output | pending | 0 |
| 7 | deployment | pending | 0 |
| 8 | constraints | pending | 0 |

## Active branch
product

## Questions asked (all branches)
0
EOF

echo "Initialized $CONTEXT_DIR with ${#BRANCHES[@]} branches"
echo "State file: $CONTEXT_DIR/_state.md"
