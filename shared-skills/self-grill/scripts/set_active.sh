#!/usr/bin/env bash
# Set the active branch for grilling.
#
# Usage: set_active.sh <state_dir> "<branch_name>"

set -euo pipefail

STATE_DIR="${1:?Usage: set_active.sh <state_dir> <branch_name>}"
BRANCH_NAME="${2:?Usage: set_active.sh <state_dir> <branch_name>}"
STATE_FILE="$STATE_DIR/context/_state.md"

# Mark all branches as not active, then set target as active
sed -i "s/| \([^|]*\) | active |/| \1 | done |/g" "$STATE_FILE"
sed -i "s/| \(${BRANCH_NAME}\) | pending/| \1 | active/" "$STATE_FILE"

# Update active branch line
sed -i "/^## Active branch/{n;s/.*/${BRANCH_NAME}/}" "$STATE_FILE"

echo "Active branch: ${BRANCH_NAME}"
