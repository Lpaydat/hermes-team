# Back-Edge Annotation and Reset — Implementation Lessons

> Hard-won patterns from implementing the stateless graph engine's loop support.
> These are non-obvious and caused multiple test failures before resolution.

## 1. DFS-based back-edge annotation (NOT SCC membership)

**Problem:** Tarjan SCC marks ALL edges within a cycle as back-edges. In a 2-node cycle (build→review, review→build), BOTH edges get marked. This breaks the activation rule — the forward edge (build→review) blocks build from dispatching because it looks like a conditional dependency that hasn't fired.

**Solution:** Use DFS discovery order instead. A back-edge is an edge where the target was discovered BEFORE the source AND both are in the same SCC. This marks only the cycle-CLOSING edge (review→build), not the forward edge (build→review).

```python
# DFS gives discovery times. An edge is a back-edge iff:
# - dst discovered before src (going backward in DFS tree)
# - both nodes in same SCC (real cycle, not cross-edge)
for edge in edges:
    if edge.from_node == edge.to_node:
        edge.is_back_edge = True  # self-loop
    elif discovered[edge.to_node] < discovered[edge.from_node]:
        # verify same SCC
        if same_scc(edge.from_node, edge.to_node):
            edge.is_back_edge = True
```

**Reachability validation must exclude back-edges** from the `has_incoming` set. A back-edge can't be traversed on the first pass — it only fires after a reset. Without this exclusion, entry nodes in cyclic templates are classified as unreachable.

## 2. Source-node clearing on back-edge reset

**Problem:** When a back-edge (review→build) fires and resets build, only build's state was cleared. Review stayed "done" with its FAIL output. On the next tick, the back-edge re-fired because review's output still said FAIL — even though build had just re-dispatched.

**Solution:** When a back-edge resets its target, also clear the SOURCE node:
- Clear `done`, `failed`, `skipped` flags
- Clear `card_id`, `card_status`
- Clear `output` (prevents stale FAIL verdict from re-triggering)
- Bump `iteration` (changes idempotency key → fresh card on re-dispatch)

The source is part of the same cycle — it needs to re-run too.

## 3. Activation rule: back-edges from unrun sources don't block

**Problem:** An entry node (build) whose only incoming edge is a back-edge (review→build) can't dispatch because the activation rule sees a conditional dependency that hasn't fired.

**Solution:** If ALL incoming edges are back-edges AND none of their sources have run yet (all pending), treat the node as an entry node. Back-edges can't fire until the source completes at least once — so on iteration 0 they shouldn't block.

```python
if incoming and all(e.is_back_edge for e in incoming):
    sources_run = any(
        _phase_of(wf, e.from_node, state_nodes) in (DONE, RUNNING, FAILED)
        for e in incoming
    )
    if not sources_run:
        incoming = []  # treat as entry node on first iteration
```

## 4. Back-edge cap validation: per-cycle, not per-edge

**Problem:** In a 2-node cycle, both edges are in the same SCC. If only the back-edge (review→build) has `max_iterations`, the forward edge (build→review) gets flagged for lacking a cap.

**Solution:** Check if any SIBLING edge in the same cycle provides the cap. A sibling is an edge going the opposite direction (from this edge's target to its source).

## 5. Legacy mirror removal — _update_blob_after_dispatch

**Problem:** `_mirror_legacy_to_blob` re-read from `node_states` table after each dispatch, creating a triple-representation hazard (DB table + inst.node_states + state blob).

**Solution:** Replace with `_update_blob_after_dispatch(inst, node, ns, ok, msg)` that writes directly to the blob based on dispatch return values + board lookups. Key nuances:
- **Wait nodes:** `ok=False` means "still waiting," NOT "failed." Only set `done` when condition resolves.
- **Transient failures:** Card creation errors should leave the node pending (retry on next tick), NOT mark it `failed`. Only schema validation failures are permanent.
- **Command/wait output:** Read from legacy `node_states` table (command runners write there synchronously).

The dispatch methods still call `update_node_state` for backwards compat, but the blob is authoritative.

## 6. Loop test card queries — use status='todo'

When testing loops, querying for the latest card by `ORDER BY created_at DESC LIMIT 1` returns the WRONG card if timestamps are close (same millisecond). Always filter: `WHERE assignee='X' AND status='todo'` to get the current iteration's dispatched card.
