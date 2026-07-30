# QA Timing Failure Modes — Per-Merge vs Post-All-Merge

When the user questions whether per-merge black-box QA adds value
(testing intermediate master states) or wastes cycles, use this
analysis. Produced from a failure-mode analysis of the Hermes pipeline
on 2026-07-30.

## The core question

The workflow engine auto-creates a QA card after every verifier merge
to master (phase 5). For an N-slice epic, this triggers N QA cycles.
The first N−1 test intermediate states where other slices are absent.
Are those cycles wasted?

## The four failure-mode scenarios

### 1. Slice A breaks Slice B (interface incompatibility)

A refactors a shared module; B depends on the old interface.

- **Per-merge QA:** ❌ Cannot catch. When A merges, B's code isn't on
  master — nothing to break. The break only manifests when B lands, by
  which point A is already merged.
- **Post-all-merge QA:** ✅ Catches. Both code paths present; the
  running system exercises B's broken call into A's refactored module.
- **Real defense in current design:** The verifier — but only if slices
  are sequential. B's verifier rebases onto post-A master and re-runs
  the suite. For parallel slices built against a shared baseline,
  neither verifier sees the other's changes.

### 2. Latent bug in A surfaces only under B's runtime usage

A's code is correct in isolation but harbors a race condition that only
triggers under B's call patterns, concurrency model, or data shapes.

- **Per-merge QA:** ❌ Cannot catch. B's triggering code is absent.
- **Post-all-merge QA:** ✅ Catches. B's usage drives A's code; QA's
  edge-case probing hits the latent bug.
- **Who else catches this:** **Nobody.** A's verifier tested A in
  isolation; B's verifier tested B's correctness. The bug lives in the
  interaction, which only black-box QA on the assembled system can
  surface. This is the hardest class to catch — pure runtime emergence.

### 3. Multi-slice integration break (N-way interaction)

Each slice passes its dev↔verifier loop, but the assembled system fails
because of emergent interaction (auth token format conflicts with
payment gateway, order schema mismatches, etc.).

- **Per-merge QA:** ⚠️ Only catches on the final merge (N−1 wasted
  cycles testing states that structurally cannot reveal the bug).
- **Post-all-merge QA:** ✅ Catches in one cycle.
- **Who else catches this:** **Nobody.** Integration bugs live in the
  interaction space, not in any single slice. This is a structural
  blind spot of the per-slice verifier model.

### 4. Regression in existing code

A new slice modifies a shared utility, subtly changing behavior that
existing code depends on.

- **Per-merge QA:** ✅ Catches immediately. Clear attribution (A's
  merge), small blast radius, no propagation.
- **Post-all-merge QA:** ✅ Catches, but delayed. Buried among multiple
  slices' changes; harder to attribute; regression has propagated.

## Summary matrix

| Scenario | Per-merge catches? | Post-all-merge catches? | Real defense |
|---|---|---|---|
| A breaks B (interface) | ❌ | ✅ | Verifier (sequential only) |
| Latent bug under B's usage | ❌ | ✅ | **Nobody but QA-on-assembled** |
| N-way integration break | ⚠️ (final merge only) | ✅ | **Nobody** |
| Regression in existing code | ✅ (immediate) | ✅ (delayed) | Both; per-merge faster |

## What per-merge QA CANNOT catch

1. **Cross-slice interaction bugs** — the absent slices' code paths
   can't be exercised. QA tests a system state that will never exist in
   production.
2. **Latent runtime bugs triggered by downstream usage** — scenario 2
   is the purest blind spot; only runtime QA on the assembled system
   catches it.
3. **Emergent multi-slice integration failures** — deferred to the last
   merge anyway, but charges N−1 wasted cycles.
4. **The cost of N−1 redundant QA cycles** — wasted compute, wall-clock
   on critical path, and noise (QA files findings about "missing
   features" that are just unbuilt slices).

## The optimal hybrid

The failure modes are orthogonal — neither approach is strictly dominant.

1. **Keep per-merge QA for regression detection** — it's the only
   defense that catches Scenario 4 early enough to prevent propagation.
2. **Add a post-all-merge integration QA pass** — the only defense for
   Scenarios 1–3, especially the latent runtime bugs (Scenario 2).
3. **Make per-merge QA lightweight** — scope to "did this merge break
   anything that already worked?" (regression-only), not "does the
   feature work end-to-end?" (requires all slices present).

Cost: one extra QA cycle at epic completion.
Benefit: coverage of the entire Scenario 1–3 failure space that
per-merge QA structurally cannot reach.

## The verifier as key variable

The per-merge QA weakness is partially mitigated by the verifier — but
**only for sequential slices**:

- **Sequential slices + strong verifier** → verifier catches A↔B
  interface breaks before merge. Remaining gap: Scenario 2 (latent
  runtime bugs that only surface under real usage, not test execution).
- **Parallel slices** → both verifiers test against the same baseline.
  Cross-slice breaks are completely invisible until merge, and per-merge
  QA on the first merge still can't see them.

This means the decision between per-merge and post-all-merge QA depends
on whether slices are developed sequentially or in parallel. Parallel
slices make the post-all-merge pass essential — there is no other
defense for the integration bug class.
