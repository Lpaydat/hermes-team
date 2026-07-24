#!/usr/bin/env bash
# validate-grill-output.sh — verifies grill output structure matches spec.
#
# Usage: validate-grill-output.sh <slug>
# Exit 0 = pass, exit 1 = fail (with specific error message)
#
# Checks:
#   1. ~/projects/<slug>/grill/ directory exists
#   2. _state.md exists and has at least one branch entry
#   3. Each branch file exists with required sections
#   4. At least 1 locked decision across all branch files
#   5. No files still stuck in /tmp/grill-<slug>/context/

set -euo pipefail

SLUG="${1:?Usage: validate-grill-output.sh <slug>}"
PROJECT_DIR="$HOME/projects/$SLUG"
CONTEXT_DIR="$PROJECT_DIR/context"
PASS=0
FAIL=0
ERRORS=""

ok()   { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); ERRORS="${ERRORS}\n  ✗ $1"; }

# 1. Context directory exists
if [ -d "$CONTEXT_DIR" ]; then
    ok
else
    fail "Context directory missing: $CONTEXT_DIR"
    # Nothing else to check if the dir doesn't exist
    echo "=== GRILL OUTPUT VALIDATION: FAIL ==="
    echo -e "$ERRORS"
    echo ""
    echo "Passed: $PASS  Failed: $FAIL"
    exit 1
fi

# 2. _state.md exists and has branch entries
STATE_FILE="$CONTEXT_DIR/_state.md"
if [ -f "$STATE_FILE" ]; then
    ok
    # Count branches in state table (lines matching | N | name | status |)
    BRANCH_COUNT=$(grep -cP '^\| \d+ \|' "$STATE_FILE" 2>/dev/null || echo 0)
    if [ "$BRANCH_COUNT" -ge 1 ]; then
        ok
    else
        fail "_state.md has no branch entries (expected at least 1)"
    fi
else
    fail "_state.md missing in $CONTEXT_DIR"
    BRANCH_COUNT=0
fi

# 3. Each branch file exists with required sections
if [ "$BRANCH_COUNT" -ge 1 ] 2>/dev/null; then
    # Extract branch slugs from _state.md table
    BRANCH_SLUGS=$(grep -oP '^\| \d+ \| \K[^ |]+' "$STATE_FILE" 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr ' ' '-' || true)
    
    for slug in $BRANCH_SLUGS; do
        BRANCH_FILE="$CONTEXT_DIR/${slug}.md"
        if [ -f "$BRANCH_FILE" ]; then
            ok
            # Check for ## Decisions section
            if grep -q '## Decisions' "$BRANCH_FILE" 2>/dev/null; then
                ok
            else
                fail "Branch file ${slug}.md missing '## Decisions' section"
            fi
            # Check for ## Questions asked section
            if grep -q '## Questions asked' "$BRANCH_FILE" 2>/dev/null; then
                ok
            else
                fail "Branch file ${slug}.md missing '## Questions asked' section"
            fi
        else
            fail "Branch file missing: ${slug}.md (listed in _state.md but not found)"
        fi
    done
fi

# 4. At least 1 locked decision across all branch files
DECISION_COUNT=0
for f in "$CONTEXT_DIR"/*.md; do
    [ "$f" = "$STATE_FILE" ] && continue
    [ -f "$f" ] || continue
    # Count "Lock D" lines in decisions
    count=$(grep -c 'Lock D' "$f" 2>/dev/null || echo 0)
    DECISION_COUNT=$((DECISION_COUNT + count))
done

if [ "$DECISION_COUNT" -ge 1 ]; then
    ok
else
    fail "No locked decisions found across all branch files (expected at least 1)"
fi

# 5. No orphaned files in /tmp/
TMP_DIR="/tmp/grill-${SLUG}/context"
if [ -d "$TMP_DIR" ]; then
    TMP_COUNT=$(find "$TMP_DIR" -name '*.md' -type f 2>/dev/null | wc -l)
    PROJ_COUNT=$(find "$CONTEXT_DIR" -name '*.md' -type f 2>/dev/null | wc -l)
    if [ "$TMP_COUNT" -gt "$PROJ_COUNT" ]; then
        fail "Files still in $TMP_DIR ($TMP_COUNT files) — not fully persisted to $CONTEXT_DIR ($PROJ_COUNT files)"
    else
        ok
    fi
else
    ok
fi

# 6. REAL PO sessions exist (not builder self-play)
SESSION_KEY=""
if [ -f "/tmp/grill-${SLUG}/SESSION.key" ]; then
    SESSION_KEY=$(cat "/tmp/grill-${SLUG}/SESSION.key" 2>/dev/null | tr -d '[:space:]')
fi

if [ -n "$SESSION_KEY" ]; then
    PO_DB="$HOME/.hermes-teams/startup/profiles/product-owner/state.db"
    if [ -f "$PO_DB" ]; then
        # Check that the PO session actually asked questions (not self-play)
        PO_QUESTIONS=$(python3 -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('$PO_DB')
    c = conn.cursor()
    c.execute(\"SELECT COUNT(*) FROM messages WHERE session_id='$SESSION_KEY' AND role='assistant' AND content LIKE '%<Q>%'\")
    print(c.fetchone()[0])
    conn.close()
except:
    print(0)
" 2>/dev/null || echo 0)

        if [ "$PO_QUESTIONS" -ge 5 ]; then
            ok
        else
            fail "PO session $SESSION_KEY only asked $PO_QUESTIONS questions with <Q> tags (expected 5+). Builder may have self-played the grill instead of using real PO."
        fi
    else
        fail "PO state.db not found at $PO_DB"
    fi
else
    fail "No SESSION.key found in /tmp/grill-${SLUG}/ — builder never launched a real PO session"
fi

# Report
echo "=== GRILL OUTPUT VALIDATION: $SLUG ==="
if [ "$FAIL" -eq 0 ]; then
    echo "RESULT: PASS"
    echo "  Branches: $BRANCH_COUNT"
    echo "  Locked decisions: $DECISION_COUNT"
    echo "  Branch files verified: $(find "$CONTEXT_DIR" -name '*.md' ! -name '_state.md' -type f 2>/dev/null | wc -l)"
    echo "  Passed: $PASS  Failed: $FAIL"
    exit 0
else
    echo "RESULT: FAIL"
    echo -e "$ERRORS"
    echo ""
    echo "  Passed: $PASS  Failed: $FAIL"
    exit 1
fi
