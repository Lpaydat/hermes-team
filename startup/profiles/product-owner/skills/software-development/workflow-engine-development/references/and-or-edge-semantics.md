# AND/OR Edge Semantics — Conditional Diamond Routing + Dependency Convergence

> **Hard-won lesson (2026-07-31):** the initial OR-only implementation broke
> dependency convergence. Pure AND broke conditional diamonds. The correct
> model separates unconditional edges (AND) from conditional edges (OR).

## The problem

A node with multiple incoming edges serves one of two purposes:

1. **Dependency convergence (AND):** `go` depends on `w1` AND `w2`. Both
   must complete before `go` dispatches. These edges have NO `condition`
   field — they're unconditional dependencies.

2. **Conditional diamond routing (OR):** `ship` can be reached from
   `review→ship (condition: PASS)` OR `re-review→ship (condition: PASS)`.
   Either path can activate the node. These edges HAVE a `condition` field.

A single node can have BOTH types of incoming edges.

## The bug

The initial implementation used pure OR for ALL edges:

```python
# WRONG: activates if ANY edge source is DONE
for edge in incoming:
    if dep_ns.status == NodeStatus.DONE:
        if not edge.condition or evaluate_condition(edge.condition, ctx):
            has_active_edge = True  # <-- breaks convergence
            break
```

This worked for conditional diamonds (review→ship fires when review is done
and condition passes) but BROKE convergence: a `go` node with unconditional
edges from `w1` (done) and `w2` (still pending) would dispatch prematurely
because `w1`'s unconditional edge satisfied the OR check.

**Found by adversarial test:** `test_multiple_waits_one_blocks` — w1 resolves
(flag1=true), w2 blocks (flag2=false), but `go` dispatched anyway because w1's
edge was DONE. The test caught it; the engine was wrong.

## The fix

Separate unconditional and conditional edges, evaluate each group with the
correct semantics:

```python
unconditional = [e for e in incoming if not e.condition]
conditional = [e for e in incoming if e.condition]

# Unconditional edges: ALL sources must be DONE (AND)
unconditional_ok = all(
    inst.node_states.get(e.from_node) and
    inst.node_states.get(e.from_node).status == NodeStatus.DONE
    for e in unconditional
)

# Conditional edges: ANY source DONE + condition passes (OR)
conditional_ok = any(
    inst.node_states.get(e.from_node) and
    inst.node_states.get(e.from_node).status == NodeStatus.DONE and
    evaluate_condition(e.condition, ctx)
    for e in conditional
)

# Activation: both groups must pass
has_active_edge = unconditional_ok and (conditional_ok or not conditional)
```

Edges from SKIPPED/FAILED sources are ignored (dead branches). If all sources
reach terminal state but none activated, the node is SKIPPED.

## Proof points

| Scenario | Edge type | Semantics | Test |
|----------|-----------|-----------|------|
| review→ship (PASS), review→fix (FAIL) | conditional | OR | `test_explicit_edges.py` |
| w1→go, w2→go (both must complete) | unconditional | AND | `test_schedule_wait_adversarial.py` |
| review→ship (conditional) + re-review→ship (conditional) | conditional | OR | dev-review-loop livetest |
| src→w1→go, src→w2→go (w2 blocks) | unconditional | AND | `test_multiple_waits_one_blocks` |

## Mermaid shapes

```
review ──(PASS)──→ ship     conditional edge, OR semantics
review ──(FAIL)──→ fix      conditional edge, OR semantics
w1 ──────────────→ go       unconditional edge, AND semantics
w2 ──────────────→ go       unconditional edge, AND semantics
```

The `condition` field on the Edge dataclass is the discriminator. No condition
= AND (convergence). Has condition = OR (routing).
