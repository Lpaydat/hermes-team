# merge-verify Extreme Tests — Adversarial Scenarios

## Test: Can merge-verify catch planted failures?

**Date:** 2026-08-06
**Branch:** fix-v1-merge-gap
**Board:** ext-test (single board, 4 sequential scenarios)

## Scenarios and Results

| Scenario | Close Node | Merge-Verify | Expected | Caught? |
|---|---|---|---|---|
| EXT-1: merge conflict | Resolved correctly | PASS (all 4 checks) | PASS | N/A (clean) |
| EXT-2: failing tests | **FIXED the bug(!)** | PASS (tests now pass) | FAIL | no |
| EXT-3: destroyed commits | Merged (truncated branch) | **FAIL (dangling commit)** | FAIL | yes |
| EXT-4: stray worktree | Merged (clean) | **FAIL (unmerged work)** | FAIL | yes |

## EXT-1: Merge Conflict (PASS)

master changed calc.py (`add+0`), ticket-focus added `mul`. Close node
resolved the conflict correctly (kept both changes). Merge-verify confirmed:
2-parent merge commit, tests pass, no dangling commits, no stray worktrees.

## EXT-2: Failing Tests (NOT CAUGHT — known gap)

ticket-focus had `mul(a,b)` returning `a+b` instead of `a*b` — a real bug.
test_mul fails on the branch.

**What happened:** The close node body says "ESCALATE if tests fail" but the
tech-lead decided to FIX the bug instead (changed `a+b` to `a*b`), then merged
the fix. Merge-verify saw passing tests and said PASS.

**Root cause:** Close node overstepped its role. It's supposed to MERGE, not FIX.
The body says "ESCALATE" but doesn't say "Do NOT fix bugs."

**Fix:** Close node should NOT escalate to a human and NOT fix itself. It should
**create a `[bug]` card assigned to debugger**. The existing `debugger-exit.json`
workflow handles reproduce→fix→verify→converge automatically (3 loop_engine phases:
reproduce, hypothesise+fix+falsify, converge). Only escalate to PO if the debugger
escalates (design-level issue or genuine human blocker). See Pattern 9 in SKILL.md.

## EXT-3: Destroyed Commits (CAUGHT)

ticket-focus had a `div()` commit that was `git reset --hard` away. The commit
became dangling (git fsck shows unreachable commit `b8ea56b`). Close node merged
the truncated branch (add+mul only). Merge-verify caught it:

> "FAIL — dangling commit b8ea56b 'feat: add divide' carries a div() feature
> present in neither master nor ticket-focus. A git gc would permanently delete
> the orphaned div feature."

The verifier noted the test suite was "hollow" — master tests only `add()`, the
destroyed commit's `test_mul` was dropped. This is exactly the real-world
failure mode from the Todo CLI incident.

## EXT-4: Stray Worktree (CAUGHT)

An unregistered directory `/tmp/ext-test-wt` held uncommitted changes (added
`div()` function) not on any branch. Close node merged cleanly (the stray work
wasn't on ticket-focus). Merge-verify caught it:

> "FAIL — unregistered stray dir /tmp/ext-test-wt holds unmerged ticket work
> (calc.py defines `def div(a,b)`, absent from BOTH master and ticket-focus)."

Impressively, the verifier found a worktree that `git worktree list` doesn't
show — it checked the filesystem directly, not just git's worktree registry.

## Key Findings

1. **merge-verify catches 2 of 3 planted failures.** Destroyed commits and
   stray worktrees are detected. The third failure (failing tests) is masked
   by the close node fixing the bug during merge.

2. **depends_on is required for edge routing.** The initial mini-template had
   `merge-verify` without `depends_on: ["close"]`. The engine didn't route
   to it after close completed. Adding `depends_on` fixed it. Both edges AND
   depends_on are needed for reliable routing — edges alone are insufficient.

3. **Verifier independently verifies, doesn't trust self-reports.** In every
   scenario the verifier ran actual git commands (git log, git fsck, pytest,
   git worktree list, filesystem checks). It never took the close node's
   verdict at face value. This is the correct posture.
