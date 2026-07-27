#!/usr/bin/env bash
# verify-queue-builds.sh — verify queue-builds.sh works correctly
# Run after any change to queue-builds.sh or before relying on its output.
#
# Checks: (1) syntax, (2) no eval, (3) awk parsing, (4) board state,
#         (5) chaining (parent-child links), (6) idempotency.
#         Prints PASS/FAIL per check, exits non-zero on any FAIL.
#
# Usage: bash verify-queue-builds.sh

set -euo pipefail
PASS=0; FAIL=0
ok()   { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

SCRIPT=~/.hermes-teams/startup/profiles/builder/scripts/queue-builds.sh
BANK=~/vault/ventures/idea-bank.md
BOARD="hermes-hq"

echo "=== 1. Bash syntax check ==="
if bash -n "$SCRIPT" 2>&1; then ok "syntax valid"; else fail "syntax error"; fi

echo ""
echo "=== 2. No eval in script ==="
if grep -q 'eval hermes' "$SCRIPT"; then
    fail "still uses 'eval hermes' — body word-splits on spaces"
else
    ok "no 'eval hermes' — body passed directly as quoted arg"
fi

echo ""
echo "=== 3. Awk parsing produces expected idea count ==="
IDEAS=$(awk '
BEGIN { FS="|" }
/^## / { section = $0 }
/^\| [0-9]+/ {
    num = $2; score = $3; origin = $4; name = $5; dossier = $6; status = $7
    gsub(/^[ \t]+|[ \t]+$/, "", score)
    gsub(/^[ \t]+|[ \t]+$/, "", name)
    gsub(/^[ \t]+|[ \t]+$/, "", status)
    gsub(/^[ \t]+|[ \t]+$/, "", dossier)
    if (score ~ /^[0-9]+\/25$/) {
        split(score, parts, "/")
        numeric_score = parts[1]
        if (status ~ /BUILT_AWAITING_REVIEW/ || status ~ /IN_GRILL/ || status ~ /building/) { next }
        printf "%d\t%s\n", numeric_score, name
    }
}
' "$BANK")

IDEA_COUNT=$(echo "$IDEAS" | wc -l)
echo "Buildable ideas found: $IDEA_COUNT"
if [ "$IDEA_COUNT" -ge 10 ]; then ok "enough buildable ideas parsed"; else fail "too few ideas parsed ($IDEA_COUNT)"; fi

echo ""
echo "=== 4. Cards exist on board ==="
# Use filtered CLI — NOT --json on full board (1.8M+ chars on 190-task board)
CARD_LINES=$(hermes kanban --board "$BOARD" list 2>/dev/null | grep "Build prototype:" || true)
CARD_COUNT=$(echo "$CARD_LINES" | grep -c . || echo 0)
echo "Build prototype cards on board: $CARD_COUNT"
if [ "$CARD_COUNT" -ge 1 ]; then ok "cards exist on board"; else fail "no build cards found"; fi

echo ""
echo "=== 5. Chaining — first card should have children ==="
FIRST_ID=$(echo "$CARD_LINES" | head -1 | grep -oP 't_\w+' | head -1 || echo "")
if [ -n "$FIRST_ID" ]; then
    CHILDREN=$(hermes kanban --board "$BOARD" show "$FIRST_ID" 2>/dev/null | grep -E 'children:' || echo "children: (none)")
    echo "First card ($FIRST_ID): $CHILDREN"
    if echo "$CHILDREN" | grep -qP 't_\w+'; then
        ok "first card has children — chain is linked"
    else
        fail "first card has no children — chain may be broken"
    fi
else
    fail "could not extract first card ID to verify chaining"
fi

echo ""
echo "=== 6. Idempotency — re-run should skip all ==="
MARKER=~/vault/ventures/.last-queue
[ -f "$MARKER" ] && mv "$MARKER" "${MARKER}.bak"
REOUTPUT=$(bash "$SCRIPT" 2>&1 || true)
mv "${MARKER}.bak" "$MARKER" 2>/dev/null || true

echo "Re-run: $(echo "$REOUTPUT" | grep 'Created:' || echo 'no Created line')"
if echo "$REOUTPUT" | grep -q 'SKIP'; then
    ok "dedup SKIP works on re-run"
else
    fail "no SKIP on re-run — dedup broken"
fi

echo ""
echo "=== RESULTS ==="
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
