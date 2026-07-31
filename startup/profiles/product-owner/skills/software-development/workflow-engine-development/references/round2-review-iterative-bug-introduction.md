# Round 2 Code Review: How Fixes Introduce New Bugs

## Session context

After implementing 12 code-review fixes (round 1), a second two-axis review
(round 2) found **3 production-blocking bugs** that were INTRODUCED by the
round-1 fixes themselves — plus 5 hard standards issues.

## The 3 production bugs introduced by fixes

### 1. Input validation key mismatch (false-positive FAILED)

**Round-1 fix:** Added input schema validation that checks if required
variables are present in context before dispatching.

**Bug introduced:** The check `if req_var not in ctx and f"nodes.{req_var}"
not in ctx` checks `"spec_path"` then `"nodes.spec_path"`. But context keys
are full paths like `nodes.plan.output.spec_path`. Neither check matches.
Every node with an input schema gets false-positive FAILED.

**Fix:** Validate against `node.input.sources` mapping (which explicitly
maps each required input to its context variable):
```python
source_expr = node.input.sources.get(req_var, "")
if source_expr:
    source_key = strip_template_var(source_expr)
    if source_key not in ctx:
        missing.append(req_var)
```

### 2. Conditional-skip deadlock (PENDING forever)

**Round-1 fix:** Added conditional node support with `evaluate_condition()`.

**Bug introduced:** When a condition evaluates false, the node is `continue`d
in PHASE 2, staying PENDING. The `all_done` check requires every node to be
DONE. A skipped condition blocks the workflow forever.

**Fix:** Mark condition-failed nodes as SKIPPED (new terminal state). Update
`all_done` to accept `{DONE, FAILED, SKIPPED}` as terminal.

### 3. FAILED-node deadlock

**Round-1 fix:** Added FAILED status for output-validation failures.

**Bug introduced:** `all_done` checked `ns.status == NodeStatus.DONE`. FAILED
!= DONE, so any validation failure stalls the instance indefinitely.

**Fix:** `all_done` checks `ns.status in {DONE, FAILED, SKIPPED}`.

## The pattern: fixes need their own review

A two-axis code review is not a one-shot check. The fixes themselves can
introduce new bugs, especially when:

1. **A new status/state is added** (SKIPPED, FAILED) but the completion
   check (`all_done`) isn't updated to recognize it as terminal.
2. **A new validation gate is added** (input schema) but the variable
   lookup mechanism doesn't match how context keys are actually structured.
3. **A new dispatch path is added** (delegate, chain, subworkflow) but
   it skips validation that the default path gets.

Always run: fix → review → fix → review until clean. Two rounds minimum
for any change that adds new states, new validation, or new dispatch paths.

## Tests that encoded old buggy behavior

Round-2 fixes changed observable behavior. Tests that asserted the OLD
behavior must be updated:

| Test | Old assertion (buggy) | New assertion (correct) |
|------|----------------------|------------------------|
| `test_dead_branch` | Workflow does NOT complete (deadlock) | Workflow DOES complete with SKIPPED node |
| `test_adv_graph_all_conditions_impossible` | Instance permanently stuck | All nodes SKIPPED, workflow completes |
| `test_07_template_hot_reload` | Cache never invalidated (old version) | Cache invalidated by mtime (new version) |

These are category-2 updates from the dual-nature test maintenance pattern:
the test's INTENT stays the same (prove correct behavior), but the ASSERTION
flips because the engine now does the right thing.
