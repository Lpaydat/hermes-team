# Loop Implementation — Back-Edge Iteration (T6 complete)

> 4/4 loop tests pass. 21/21 full suite green.
> Committed on `feat/workflow-dispatch`.

## The three bugs that made loops fail end-to-end

The loop machinery (back-edge detection, reset pass, iteration-aware keys)
was implemented across T3/T5/T6 but loops DIDN'T WORK until three bugs were
fixed in a dedicated loop-implementation session.

### Bug 1: SCC-based annotation marked forward edges as back-edges

**Symptom:** On PASS (review verdict=PASS), review got RESET instead of ship
dispatching. The back-edge `review→build` should only fire on FAIL, but the
forward edge `build→review` (unconditional) was ALSO marked as a back-edge.
When build was done, the unconditional "back-edge" `build→review` fired with
no condition → always true → review reset every tick.

**Root cause:** Tarjan SCC puts build+review in the same component. Both
edges have both endpoints in the same SCC → both marked. The old code's
pitfall ("both edges in a 2-node cycle are back-edges") was accepted as
correct but was actually wrong.

**Fix:** Replaced SCC-based annotation with DFS discovery order. Only edges
where `discovered[to] < discovered[from]` (target seen before source) are
back-edges. Self-loops handled specially (`from == to`).

```python
# In annotate_back_edges (model.py):
src_disc = discovered[edge.from_node]
dst_disc = discovered[edge.to_node]
if dst_disc <= src_disc and edge.from_node == edge.to_node:
    edge.is_back_edge = True  # self-loop
elif dst_disc < src_disc:
    # Goes back to earlier-discovered node + SCC confirms same cycle
    edge.is_back_edge = True
```

### Bug 2: Activation rule blocked entry nodes with back-edge incoming

**Symptom:** Build (the first node in the loop) never dispatched. Actions
empty on tick 1.

**Root cause:** Build's only incoming edge is the back-edge `review→build`
(conditional). The activation rule saw incoming edges, review wasn't done →
`C_sat = False` → build not dispatchable. But on iteration 0, the back-edge
CAN'T fire yet (review hasn't run). Build should be treated as an entry node.

**Fix:** If ALL incoming edges are back-edges AND the sources haven't run yet
(no source is done/running/failed), treat the node as an entry node:

```python
if incoming and all(e.is_back_edge for e in incoming):
    sources_run = any(
        _phase_of(wf, e.from_node, state_nodes) in (DONE, RUNNING, FAILED)
        for e in incoming
    )
    if not sources_run:
        incoming = []  # entry node on first iteration
```

### Bug 3: Reset pass didn't clear the SOURCE node

**Symptom:** After a FAIL→reset, the next tick re-triggered the back-edge
because review's stale FAIL output was still in the state blob. Review got
re-dispatched with the OLD card via dedup (iteration-0 idempotency key). The
loop never advanced past iteration 1.

**Root cause:** `_reset_pass` only reset the TARGET (build). Review (the
SOURCE of the back-edge) kept its `done` flag, `card_id`, and `output`
(FAIL verdict). The next tick saw review still done with FAIL → back-edge
condition true → reset build AGAIN. And review's idempotency key was the
same (iteration 0) → dedup adopted the old card.

**Fix:** Reset pass clears the SOURCE too:

```python
source_ns = state_nodes.get(source_id, {})
source_ns.pop("done", None)
source_ns.pop("failed", None)
source_ns.pop("skipped", None)
source_ns["card_id"] = None
source_ns["card_status"] = ""
source_ns["output"] = {}  # clear stale FAIL verdict
source_ns["iteration"] = source_ns.get("iteration", 0) + 1  # fresh idem key
```

**Why iteration bump on source is critical:** without it, the source's
idempotency key stays at iteration 0. The dedup lookup finds the old card.
The source re-dispatches the STALE card instead of creating a fresh one.
Bumping the source's iteration changes its idem key → fresh card.

## General lesson: cycles are bidirectional

In a loop, BOTH the target and source participate in the cycle. Resetting
only one leaves the other in a terminal state with stale output, causing:

1. **Re-firing:** the back-edge condition keeps evaluating true (stale FAIL)
2. **Dedup adoption:** stale idempotency key finds old card
3. **Completion deadlock:** source stays "done" → downstream sees stale output

**Always reset ALL nodes in the cycle**, not just the back-edge target.
For a simple 2-node loop (build↔review), reset both. For a 3-node loop
(a→b→c→a), reset a, b, AND c.

## Reachability validation must exclude back-edges

The load-time reachability check computes entry nodes as "no incoming
NON-BACK-EDGE." If you include back-edges in `has_incoming`, then build
(has the back-edge review→build pointing at it) is NOT an entry node →
no seeds → BFS finds nothing → "unreachable nodes" error.

```python
has_incoming = {e.to_node for e in edges if not e.is_back_edge}
```

## Back-edge cap validation: sibling-aware

In a 2-node cycle, both edges are in the SCC but only the cycle-closing edge
is a back-edge (after Bug 1 fix). However, the forward edge might also be
flagged in some SCC configurations. The validation checks that AT LEAST ONE
edge in the cycle has a cap — not that every edge does. This allows the
forward edge (build→review, unconditional) to lack max_iterations as long as
the back-edge (review→build) has one.

## Test query pitfall: filter by status='todo'

When querying for the "current" card in a loop test, the board has cards from
ALL iterations. `ORDER BY created_at DESC LIMIT 1` may return an OLD card if
timestamps are in the same millisecond. Always filter:

```sql
SELECT id FROM tasks WHERE assignee='developer' AND status='todo'
ORDER BY created_at DESC LIMIT 1
```

This gets the current iteration's card (todo = not yet completed), not a
previous iteration's completed card.
