# loop_engine metric_type Trap — Spurious Replan on PASS Verdicts

## Problem

loop_engine returns `decision=replan` even when the verifier returns `dod_met=true, recommendation=advance, score=1.0`. The loop burns all iterations and hits the hard cap despite every verify returning PASS.

## Root Cause

loop_engine's `_validate_dod_artifact()` (plugins/loop_engine/tools.py:1034-1109) applies a count invariant when `metric_type` is absent or `"proxy"`:

```python
if not is_ground_truth:
    if not behaviors or not traces:
        return False
    if len(traces) < len(behaviors):
        return False  # ← THIS FIRES
```

A decomposition verifier produces 15 `behaviors` (one per spec requirement) but only 3 `defect_traces` (one per DoD dimension). `3 < 15` → `artifact_complete=False` → `dod_met and artifact_complete` (line 2651) is False → falls through to `_replan`.

The invariant is designed for design-council convergence (every design behavior needs a defect trace proving it was checked). But a decomposition verifier's `behaviors` are "what I checked" (spec requirements), not "what needs 1:1 trace coverage."

## Fix

Set `metric_type: "ground_truth"` on the verifier spec:

```json
"verifier": {
  "title": "[plan-review] Review ticket plan",
  "body": "...",
  "assignee": "verifier",
  "metric_type": "ground_truth"
}
```

Ground-truth metrics skip the count invariant (line 1088: `is_ground_truth = metric_type == "ground_truth"` → skips lines 1089-1095). Zero traces = clean pass.

## Proven

Same spec that previously burned all 3 iterations (all returning dod_met=true but replanning anyway) converged on iteration 1 and advanced cleanly. 8 tickets created immediately. Commit `6151a11`.

## Detection

If loop_engine returns `decision=replan` but the verdict says `dod_met=true`, check the loop_state blackboard comment on the root card. If `behaviors` count > `defect_traces` count, the count invariant is the culprit.

## Generalization

Any loop_engine verifier that produces artifacts (behaviors + defect_traces) but isn't doing design-council-style coverage needs `metric_type: "ground_truth"`. The default (None/proxy) applies the coverage count invariant which is wrong for most non-design-council use cases.
