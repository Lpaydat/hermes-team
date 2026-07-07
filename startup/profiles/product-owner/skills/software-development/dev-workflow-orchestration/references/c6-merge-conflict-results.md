# C6 Merge Conflict Resolution — 3/3 PASSED

## Test Setup

Two independent beads, both adding functions to the SAME `utils.py` file.
Both dispatched simultaneously via auto-dispatch cron.

## Results

| Run | Functions | First merge | Second merge (conflict) | Fix chain | Both on main | Verdict |
|-----|-----------|-------------|--------------------------|-----------|--------------|---------|
| R1  | clamp + lerp | lerp clean | clamp conflicts → FAIL | dev resolves, re-verify PASS | ✅ | PASS |
| R2  | normalize + escape_html | normalize clean | escape_html conflicts → FAIL | dev resolves, re-verify PASS | ✅ | PASS |
| R3  | slugify + truncate_text | slugify clean | truncate conflicts → FAIL | dev resolves, re-verify PASS | ✅ | PASS |

## The Pattern (identical in all 3 runs)

```
dispatch → dev (parallel) → ver_1 PASS+merge (first)
  → ver_2 CONFLICT on rebase → FAIL verdict
  → verifier creates fix card for developer
  → developer resolves conflict (appends after existing function)
  → new verifier re-reviews → PASS
  → tech-lead re-blocks on new verifier via delegate_and_wait
  → tech-lead completes after final merge
```

## Key Behaviors Proven

1. **Verifier correctly identifies conflict**: "CONFLICT in utils.py — append-only. Per my hard rules and the merge protocol: conflict resolution is code-writing, and I never write code. I must release the slot and FAIL."
2. **Fix card includes conflict context**: branch, worktree path, base SHA, instruction to resolve
3. **Developer preserves existing code**: appends new function after the already-merged one
4. **New verifier independently verifies resolved code**: full AC probes + mutation testing
5. **Tech-lead re-blocks on new verifier**: `delegate_and_wait` links tech-lead to new verifier automatically
6. **Both functions on main with all tests passing**

## Issues Observed

- **R3 duplicate fix cards (ROOT CAUSE ANALYZED)**: See "R3 Duplicate Fix Card Root Cause" below.
- **R1 stale escalation cards**: Old test artifacts ("Fix the deploy", "Broken pipeline") from previous sessions polluted the board and consumed agent cycles. Fix: archive ALL non-archived tasks before each test run.
- **Board scanner v2 proven in production**: During R1, detected stale-worktree-blocked tech-lead, escalated to PO, resolved, unblocked. First real production use of scanner v2.

## R3 Duplicate Fix Card Root Cause

### Timeline (C6 R3, truncate chain)

```
15:36:08  Verifier PASSes code (4/4 ACs) — implementation is correct
15:36:09  Verifier completes (summary: PASS)
15:36:20  Verifier tries to merge → CONFLICT
          (slugify merged first by concurrent verifier t_3204d4c6)
15:36:32  Verifier creates fix card t_e04e7c13 (parent: t_319a891b) ← CORRECT
15:37:20  Tech-lead ALSO creates fix card t_127331f5 (no parent, created_by=tech-lead) ← REDUNDANT
```

### Root Cause

Two DIFFERENT signals were conflated:
- **Code quality**: PASS (the implementation is correct — 4/4 ACs)
- **Merge outcome**: CONFLICT (another branch landed first during the review window)

The verifier PASSed the code, then tried to merge, hit a conflict, and created a fix card. **Both the verifier AND the tech-lead independently detected the conflict and created fix cards.** The verifier created one (correct — merge conflict is verifier's responsibility on FAIL). Tech-lead saw the completed verifier card + conflict and ALSO created a fix card 48 seconds later.

### Additional Problem: Tech-lead didn't use delegate_and_wait

The truncate tech-lead (t_8dc3b626) did NOT use `delegate_and_wait` — no `dependency_wait` event, no `linked` event. Compare with the slugify tech-lead which correctly blocked at 15:20 and was promoted at 15:32. The truncate tech-lead just created cards and kept running until 15:57.

### Impact

- Two developers resolved the same conflict independently (~5 min wasted)
- First chain (verifier-created) merged successfully at 15:54
- Second chain (tech-lead-created) also resolved and PASSed verification, but was a no-op (already on main)
- No data corruption — merge-slot serialization prevented double-merge

### Design Question (UNRESOLVED)

When a verifier PASSes code but can't merge (conflict), who should create the fix card?
- **Option 1**: Verifier only — it already handles FAIL routing. A merge conflict is a FAIL variant.
- **Option 2**: Tech-lead only — it's the orchestrator that decides routing.
- **Current**: Both do, causing duplicates. Needs a coordination mechanism (e.g., verifier comments "FIX_CARD_CREATED" so tech-lead knows not to create another).

## What C6 Also Proved (C9 — Tech-Lead Re-Block)

C6 inherently tested the re-block pattern in all 3 runs:
- Verifier FAILed → tech-lead promoted (first verifier done)
- Tech-lead read FAIL verdict
- Tech-lead used delegate_and_wait to re-block on the NEW verifier (from fix chain)
- Tech-lead stayed blocked until fix verifier PASSED
- Tech-lead then completed

This is exactly the C9 test case. No separate C9 test needed — C6 covered it 3/3.
