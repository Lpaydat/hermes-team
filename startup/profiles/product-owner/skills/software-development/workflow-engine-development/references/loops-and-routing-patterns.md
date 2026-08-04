# Loops, Back-Edges, and Routing Diamonds

Patterns and pitfalls discovered during the stateless engine rewrite + dev-dispatch template build.

## 1. Back-Edge Annotation: DFS Discovery Order (NOT SCC)

**The bug:** Tarjan SCC marks ALL edges in a cycle as back-edges. In a 2-node cycle (A→B, B→A), BOTH edges get marked. This breaks the engine: the forward edge A→B fires the reset pass incorrectly (A is done, unconditional edge to B, B gets reset even though the cycle hasn't closed yet).

**The fix:** Use DFS discovery times. A back-edge is an edge whose target was discovered BEFORE the source (target is an ancestor in the DFS tree). In the A→B, B→A cycle:
- DFS visits A first (discovery=0), then B (discovery=1)
- Edge A→B: dst_disc(0) < src_disc(1)? No → NOT a back-edge (forward edge)
- Edge B→A: dst_disc(0) < src_disc(1)? Yes → IS a back-edge (cycle-closing)

Self-loops (A→A) need special handling: `dst_disc <= src_disc and from == to`.

```python
# Mark only cycle-CLOSING edges, not all edges in the SCC
for edge in edges:
    src_disc = discovered[edge.from_node]
    dst_disc = discovered[edge.to_node]
    if dst_disc <= src_disc and edge.from_node == edge.to_node:
        edge.is_back_edge = True  # self-loop
    elif dst_disc < src_disc:
        # Verify same SCC (not just a cross-edge)
        if node_to_comp[from] == node_to_comp[to]:
            edge.is_back_edge = True
```

## 2. Source-Node Clearing on Reset

**The bug:** When a back-edge fires (e.g., review→build on FAIL), only the TARGET (build) gets reset. The SOURCE (review) stays done with stale output (verdict=FAIL). On the next tick, the back-edge re-fires because review is still done and FAIL is still in context.

**The fix:** The reset pass must ALSO clear the source node:
- Clear `done`, `failed`, `skipped` flags
- Clear `card_id`, `card_status`
- Clear `output` (stale verdict must not persist)
- Bump `iteration` (so idempotency key changes → fresh card on re-dispatch)

```python
# After resetting target node:
source_ns = state_nodes[source_id]
source_ns.pop("done", None)
source_ns.pop("failed", None)
source_ns.pop("skipped", None)
source_ns["card_id"] = None
source_ns["card_status"] = ""
source_ns["output"] = {}
source_ns["iteration"] = source_ns.get("iteration", 0) + 1
```

## 3. Routing Diamond Pattern

For type-based routing (dispatch bugs→debugger, research→scout, etc.):

- Use a `command` type entry node (synchronous, no card) as the routing junction
- All conditional edges go FROM entry TO each route node
- Dead-branch skip propagation ensures only ONE route fires per trigger
- The non-matching routes get SKIPPED (terminal state)

```json
{
  "nodes": [
    {"id": "entry", "type": "command", "command": "echo '{\"status\":\"routing\"}'"},
    {"id": "route-bug", "profile": "debugger", "body_template": "..."},
    {"id": "route-dev", "profile": "tech-lead", "body_template": "..."}
  ],
  "edges": [
    {"from": "entry", "to": "route-bug", "condition": "${trigger.type} == 'bug'"},
    {"from": "entry", "to": "route-dev", "condition": "${trigger.type} != 'bug'"}
  ]
}
```

**Pitfall:** Don't make all route nodes entry nodes with self-conditions. They can't be dead-branched (no incoming source), so they stay pending forever and block completion.

## 4. Trigger Context Enrichment

`_start_from_trigger` builds the trigger context. Must include:
- `card_id` — the completing card's ID
- `board` — the board name
- `assignee` — the card's assignee
- `title` — the card's title (CRITICAL for `${trigger.title}` in body templates)
- All metadata fields spread via `**meta`

For routing by type, set `metadata.type` on the completing card. The trigger condition matches it:

```json
"trigger": {
  "source": "card_completed",
  "condition": {
    "assignee": "product-owner",
    "status": "done",
    "title_prefix": "[spec]"
  }
}
```

## 5. E2E Testing on Real Boards

**Metadata lives in `task_runs`, not `tasks`.** The kanban schema stores metadata on the run, not the task:

```sql
-- WRONG: tasks has no 'metadata' column
INSERT INTO tasks (..., metadata) VALUES (...)

-- RIGHT: insert task + task_run with metadata
INSERT INTO tasks (id, title, assignee, status, completed_at, ...) VALUES (...);
INSERT INTO task_runs (task_id, profile, status, started_at, ended_at, outcome, metadata)
VALUES (..., 'completed', ..., '{"type": "bug"}');
```

**Test card query pattern:** Filter for `status='todo'` when looking for the latest dispatched card. Multiple cards for the same assignee (different iterations) can have the same `created_at` second.

## 6. Iteration Cap Validation (Sibling Edges)

In a 2-node cycle, both edges are in the same SCC. The forward edge (A→B) has no `max_iterations`. The old validation rejected it. The fix: allow sibling edges to provide the cap — check that at least ONE edge in the cycle has an iteration cap, not every edge individually.
