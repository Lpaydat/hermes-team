# Enterprise Reliability Test Plan — 12 Tests

## Coverage Matrix

### What we've PROVEN works (Tests 1-10b):
- ✅ Auto-dispatch cron (bd ready → kanban card)
- ✅ Tech-lead plans + delegates to pi/claude harness (when tools restricted)
- ✅ Adversarial probing catches real bugs (AC5 comment preservation)
- ✅ Fix loop (tech-lead re-delegates to pi with findings)
- ✅ Crash recovery (auto-reclaim, independent re-verification)
- ✅ Bead dependencies (sequential enforcement)
- ✅ Idempotent dispatch (no duplicate cards)
- ✅ Toolset restriction forces harness usage (not delegate_task)
- ✅ **Full 3-role pipeline** (Test 10b): tech-lead → developer (pi GLM-4.5-air) → verifier (adversarial-review v4.0.0) — all profiles worked correctly, 37 green tests

### What we have NOT tested (GAPS — as of Test 10b):
- ❌ Two-phase verification protocol (delta + fresh-eyes subagent)
- ❌ Iteration 2+ (delta check against prior findings)
- ❌ Iteration cap (REVIEW-ITERATION ≥ 3 → escalation)
- ❌ Spec gap routing (verifier → tech-lead → PO)
- ❌ Warm-resume after harness session crash
- ❌ Parallel slice execution
- ❌ Large multi-slice project (5+ slices)
- ❌ Network instability mid-loop
- ❌ Merge slot serialization
- ❌ Developer crash mid-harness
- ❌ Verifier crash mid-review

## Test Plan

### Phase 1: Core 3-Role Pipeline (Tests 10-11) — ✅ PASSED (Test 10b)
Test 10b proved the full 3-role pipeline works: tech-lead → developer (pi GLM-4.5-air) → verifier (adversarial-review v4.0.0). Test 11 (consistency repeat) still pending.

### Phase 2: Failure-Fix Loop Depth (Tests 12-14)
- Test 12: Multi-iteration failure loop (JSON path query engine — hard for weak models)
- Test 13: Spec gap detection (PRD/AC conflict — verifier should escalate not fix)
- Test 14: Iteration cap escalation (≥3 failures → tech-lead takes over)

### Phase 3: Crash Recovery Depth (Tests 15-17)
- Test 15: Developer crash mid-harness
- Test 16: Verifier crash mid-review
- Test 17: Network instability mid-loop (429 rate limits)

### Phase 4: Edge Cases (Tests 18-19)
- Test 18: Empty/minimal spec (single function, 2 ACs)
- Test 19: Circular bead dependencies

### Phase 5: Scale (Tests 20-21)
- Test 20: 5-slice dependency chain (mini key-value store)
- Test 21: Parallel independent slices (3 utility functions, no deps)
