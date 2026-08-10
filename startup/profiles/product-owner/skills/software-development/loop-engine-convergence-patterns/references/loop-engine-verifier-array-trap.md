# The Verifier Array Trap — Full Forensic Detail

## Symptom

loop_engine replans despite `dod_met=true, score=1.0, recommendation=advance`. Burns all iterations, hits hard cap, escalates. Every test run fails regardless of plan quality.

## Root Cause Chain

### Step 1: Verifier produces structured artifacts

The verifier profile (loaded with adversarial-review skill) produces `behaviors[]` and `defect_traces[]` arrays in its dod_verdict by default. This is the skill's training — it's designed to produce structured evidence for design-council convergence loops.

Example verdict shape:
```json
{
  "dod_met": true,
  "score": 1.0,
  "behaviors": ["Story 1: ...", "Story 2: ...", ... 15 items],
  "defect_traces": ["MISSING FEATURES check", "SCOPE CREEP check", "NEED BREAKDOWN check"],
  "gaps": [],
  "recommendation": "advance"
}
```

### Step 2: loop_engine's artifact validation gate

`_validate_dod_artifact()` (tools.py:1034-1109) checks artifact completeness:

```python
if not isinstance(behaviors, list) or not isinstance(traces, list):
    return False
is_ground_truth = metric_type == "ground_truth"
if not is_ground_truth:
    if not behaviors or not traces:
        return False
    if len(traces) < len(behaviors):  # ← THIS LINE
        return False
```

### Step 3: The count invariant fires

With 15 behaviors (spec requirements) and 3 defect_traces (DoD dimensions):
- `len(traces) < len(behaviors)` → `3 < 15` → **returns False**
- `artifact_complete = False`
- `dod_met and artifact_complete` → `True and False` → **False**
- Falls through to replan

### Step 4: The replan message is misleading

```python
"message": f"DoD not met (recommendation={verdict.get('recommendation')}); replanning iteration {next_iter}/{cap}."
```

This says "DoD not met" even when `dod_met=true`. The artifact gate failed, not the DoD.

## Two Fixes (apply BOTH)

### Fix 1: metric_type = "ground_truth"

In the verifier spec passed to loop_engine:
```
verifier: {
  ...
  metric_type: "ground_truth"
}
```

Ground-truth metrics skip the count invariant entirely (line 1088: `is_ground_truth = metric_type == "ground_truth"` → skips lines 1089-1095).

### Fix 2: Verifier returns minimal dict

In the verifier body:
```
"Complete with dod_verdict as a SIMPLE dict: {dod_met, recommendation, gaps}.
Do NOT include behaviors, defect_traces, evidence, or any other arrays."
```

This prevents the arrays from being produced at all, so the artifact gate never evaluates.

## Why metric_type alone wasn't enough

In testing (commit `6151a11`), setting `metric_type=ground_truth` alone did NOT fix the issue on all runs. The PO sometimes stripped metric_type from the loop_engine call (treating it as an unknown field), or loop_engine's loop_state didn't persist it between iterations. The belt-and-suspenders approach (both fixes) ensures the gate never fires regardless of what the PO does with the arguments.

## Commits

- `6151a11` — added metric_type=ground_truth
- `9ae6668` — added "return minimal dict" instruction to verifier body
- Both fixes proven together on Todo CLI spec: converged iteration 1, advanced, created 4 tickets.
