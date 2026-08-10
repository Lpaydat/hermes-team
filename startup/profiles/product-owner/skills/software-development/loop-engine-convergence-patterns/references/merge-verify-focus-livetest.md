# merge-verify Focus Livetest

## Test: Can the merge-verify node mechanically verify a real git merge?

**Date:** 2026-08-06
**Branch:** fix-v1-merge-gap
**Template:** merge-test.json (throwaway, deleted after)
**Result:** PASS

## Setup

Mini template with only two nodes (close + merge-verify), no plan/dev/verify.
Pre-built git repo at `/tmp/merge-test-repo`:
- master: calc.py with add+sub (2 tests)
- ticket-focus: calc.py with add+sub+mul+div (5 tests)

## What happened

1. Trigger card `[merge-test] Calc mul+div` completed
2. Close node (tech-lead) ran:
   - `git checkout master && git merge --no-ff ticket-focus` → clean merge, commit a5191ab
   - `pytest -q` → 5 passed
   - `git log master..ticket-focus` → empty (nothing lost)
   - verdict=merged
3. merge-verify node (verifier) ran independently:
   - Check 1: `git log master..ticket-focus` → empty ✓
   - Check 2: `git fsck --unreachable | grep commit` → none ✓
   - Check 3: `pytest -q` on master → 5/5 passed ✓
   - Check 4: `git worktree list` + `git stash list` → clean ✓
   - verdict=PASS: "substantive merge, not pointer-only"

## Independent confirmation

```
git log --oneline --all --graph:
*   a5191ab Merge: add multiply and divide from ticket-focus
|\
| * a0dba3c feat: add multiply and divide
|/
* a93e0e2 feat: calc module with add+sub

pytest -q: 5 passed
```

## Key insight

The verifier independently confirmed the merge was real — it didn't
trust the close node's self-reported `verdict=merged`. It ran actual
git commands and checked the results. It even noted "substantive merge,
not pointer-only" meaning it verified calc.py actually contains mul+div
on master, not just that the merge commit exists.

This is separation of duties: the merger doesn't verify their own merge.
