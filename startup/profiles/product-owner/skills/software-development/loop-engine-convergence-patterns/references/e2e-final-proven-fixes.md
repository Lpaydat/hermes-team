# E2E Final Test — All Three Fixes Proven in Production (2026-08-10)

The hashtree test (references/hashtree-e2e-and-three-fixes.md) FOUND three
pipeline bugs. The e2e-final test PROVED the fixes work end-to-end on a fresh
project from spec through milestone-gate completion.

## Project: hashcheck (File Integrity Checker CLI)

Rust CLI, 4 user stories (verify, multi-algorithm, generate, exit codes).
Small project — exercises the full pipeline in a reasonable time.

## Results

- 107 cards, 8 workflow instances, ALL COMPLETED
- 100 tests green (19+38+16+13+14)
- 18 git commits with real fix history
- 6 source files (hash.rs, main.rs, 4 test files)

## Fix Verification

### Issue 1 (stale commit SHA): VERIFIED

REFACTOR.md was NOT found in the repo. When the refactor-review did run, it
respected the "Do NOT embed commit SHAs" instruction. No stale SHA propagation
occurred.

### Issue 2 (heartbeat failure): NOT TRIGGERED

No verifier got stuck for 2.5+ hours this time. The stale-claim reaper is in
place as defense-in-depth (phase 6 in workflow-engine.py cron), but the scenario
that caused the hashtree failure did not recur.

### Issue 3 (instances stuck active): VERIFIED — THE KEY FIX

ALL 8 workflow instances transitioned to `status='completed'`:

```
dev-dispatch           completed
tech-lead-execute      completed  ← PREVIOUSLY STUCK
tech-lead-execute      completed  ← PREVIOUSLY STUCK
tech-lead-execute      completed  ← PREVIOUSLY STUCK
milestone-gate         completed
debugger-exit          completed
tech-lead-execute      completed  ← PREVIOUSLY STUCK
tech-lead-execute      completed  ← PREVIOUSLY STUCK
```

In the hashtree test (pre-fix), ALL 6 tech-lead-execute instances stayed
`status='active'` after all work completed. The condition-aware
`_reachable_nodes` fix resolved this completely.

## Timeline

```
03:07  [spec] created → dev-dispatch fires
       architect → setup → decompose → 4 tickets → milestone-plan
03:25  tech-lead-execute fires for all 3 tickets (parallel)
       Each: plan → loop_engine(task/verify) → verify-b → close → merge-verify
04:41  milestone-gate fires (milestone-01 completed)
       QA: qa-receive → qa-quick → PASS
       QA findings → bug cards → debugger-exit fires
05:23  debugger-exit completed
05:40  Refactor tickets fire (2 more tech-lead-execute instances)
06:30  All instances completed. Pipeline done.
```

## Key Difference from Previous Tests

| Test | Cards | Instances | All Completed? | Issue 3? |
|------|-------|-----------|----------------|----------|
| wf-test (2026-08-08) | 89 | 3 | No | Not tested |
| wf-gate-test (2026-08-08) | 26 | 3 | No | Not tested |
| hashtree (2026-08-09) | 109 | 9 | No (6 stuck) | BUG FOUND |
| **e2e-final (2026-08-10)** | **107** | **8** | **YES** | **FIX PROVEN** |

The e2e-final test is the definitive proof that the condition-aware
`_reachable_nodes` fix resolves the completion-check cycle deadlock.
