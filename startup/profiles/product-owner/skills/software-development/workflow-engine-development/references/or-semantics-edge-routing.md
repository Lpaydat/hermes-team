# OR-Semantics Edge Routing for Conditional Diamonds

## The problem

A conditional diamond has a node with multiple incoming edges from different branches:

```json
{
  "edges": [
    {"from": "review", "to": "ship", "condition": "${nodes.review.output.verdict} == 'PASS'"},
    {"from": "review", "to": "fix", "condition": "${nodes.review.output.verdict} == 'FAIL'"},
    {"from": "fix", "to": "re-review"},
    {"from": "re-review", "to": "ship", "condition": "${nodes.re-review.output.verdict} == 'PASS'"}
  ]
}
```

When review=PASS: `fix` is SKIPPED, `re-review` is SKIPPED (dependency chain dead).
The `ship` node has TWO incoming edges: `review→ship` (source DONE) and `re-review→ship` (source SKIPPED).

## AND semantics (WRONG — deadlocks)

If the runtime requires ALL incoming edge sources to be DONE before activating:
- `review` is DONE ✓
- `re-review` is SKIPPED ✗
- Result: `ship` never activates → workflow deadlocks

## OR semantics (CORRECT — activates on any passing edge)

The runtime activates a node if ANY incoming edge has:
1. Source status = DONE
2. Edge condition passes (or no condition)

Edges from SKIPPED/FAILED sources are ignored (dead branches, not blocking).

```python
has_active_edge = False
all_sources_terminal = True
for edge in incoming:
    dep_ns = inst.node_states.get(edge.from_node)
    if dep_ns is None:
        all_sources_terminal = False
        continue
    if dep_ns.status == NodeStatus.DONE:
        if not edge.condition or evaluate_condition(edge.condition, ctx):
            has_active_edge = True
            break
    elif dep_ns.status in (NodeStatus.SKIPPED, NodeStatus.FAILED):
        continue  # Dead branch — ignore
    else:
        all_sources_terminal = False

if has_active_edge:
    pass  # Dispatch the node
elif all_sources_terminal:
    mark_skipped()  # All branches dead
else:
    continue  # Some sources still pending — wait
```

## How this was discovered

The initial explicit-edges implementation used AND semantics (copied from the implicit depends_on pattern). This worked for simple sequential and fan-out patterns but deadlocked on the dev-review-loop livetest — ALL downstream nodes got SKIPPED even though the PASS path should have activated `ship`.

The livetest output showed:
```
DONE node review
SKIPPED node fix (no edge condition passed)
SKIPPED node re-review (no edge condition passed)
SKIPPED node ship (no edge condition passed)  ← BUG: should have DISPATCHED
```

Root cause: `ship` had incoming edges from both `review` and `re-review`. The AND check required ALL sources DONE. Since `re-review` was SKIPPED (not DONE), `ship` couldn't activate.

Fix: switch to OR semantics. The livetest then correctly showed:
```
SKIPPED node fix (no edge condition passed)
SKIPPED node re-review (no edge condition passed)
DISPATCHED node ship → card t_574da92f  ← CORRECT
```
