# Graph Topology & Pathology Tests

10 adversarial tests targeting the *shape* of the workflow graph itself —
disconnected components, cycles, impossible conditions, fan-out, star
topology. Added after the original 13 adversarial tests; all pass against
the current engine (verified via `pytest -k test_adv_graph`).

All tests follow the FakeWorld pattern (monkey-patched `KANBAN_HOME`,
fake `create_card` writing to temp SQLite). Append to `test_engine.py`.

## The core weakness: silent eternal deadlock

**Every pathological graph (cycles, self-deps, dead branches, impossible
conditions, disconnected components) causes the instance to hang
`active` forever with zero diagnostics.** The engine has:
- No cycle detection (at definition time or runtime)
- No reachability analysis (unreachable nodes silently block completion)
- No liveness analysis (can't distinguish "condition not yet met" from
  "condition can never be met")
- No staleness/deadlock timeout on instances

The `all_done` completion check iterates every node; any node stuck at
`PENDING` blocks it permanently. When writing these tests, assert the
deadlock behavior exists (so a future fix is caught) but document it as a
weakness, not a desired property.

## The 10 tests

### test_adv_graph_disconnected_node
Reachable component `e→f` plus an unreachable cycle `x↔y`. E and F complete
normally, but the workflow NEVER completes because X and Y stay PENDING.
Asserts: e/f dispatch, x/y don't, workflow not complete, instance stays
active. **Demonstrates missing reachability analysis.**

### test_adv_graph_conflicting_diamond
Diamond `a→(b,c)→d` where B runs on PASS and C runs on FAIL, D depends on
both. Only one of B/C can ever dispatch, so D's deps can NEVER all be DONE.
Asserts: B dispatches on PASS, C doesn't, D never dispatches, workflow
never completes. **Demonstrates missing condition-liveness analysis.**
Key: the engine treats "condition failed" the same as "waiting for deps"
— both stay PENDING.

### test_adv_graph_self_dependency
Node A `depends_on: ["a"]` — simplest cycle. Never dispatches.
Asserts: no dispatch, no cards, instance stays active. Same weakness as
multi-node cycles but the smallest possible trigger.

### test_adv_graph_three_node_cycle
`a→b→c→a`. Extends the pre-existing 2-node circular test. With 3+ nodes,
cycles are harder to spot by eye in a real template. Asserts no dispatch
across two ticks, no crash.

### test_adv_graph_two_entry_nodes
Two nodes, no deps — both dispatch on tick 1. **Valid behavior, not a bug.**
Regression guard: confirms the engine handles multiple independent entry
points fanning out simultaneously. Would catch any order-dependent
processing bug.

### test_adv_graph_forward_reference
Consumer (defined first) depends on producer (defined later). The engine
builds `node_states` from all nodes at `start_manual` time and checks deps
by dict lookup, not positional — so forward refs work fine. **Valid
behavior.** Regression guard against any future order-dependent change.

### test_adv_graph_all_conditions_impossible
Every node's condition references trigger keys that don't exist. No node
ever dispatches. Asserts no dispatch, no cards, instance stuck.
**Demonstrates missing liveness analysis.**

### test_adv_graph_50_node_fanout
One root → 50 parallel children. When root completes, all 50 children must
dispatch in a single tick. Stress test: 50 idempotency lookups + 50 card
creations + 50 state DB updates in one pass. Asserts exactly 50 dispatches
and 51 total cards. **Valid behavior — confirms the tick loop scales.**

### test_adv_graph_star_topology
10 satellites (entry nodes) → 1 sink depending on all 10. Tests
many-dependency fan-in on a single node. Asserts sink waits until ALL
satellites done, dispatches only on the last completion.

### test_adv_graph_empty_vs_missing_depends_on
`"depends_on": []` vs the key absent entirely. `from_dict` uses
`n.get("depends_on", [])` so both resolve to `[]` — both are entry nodes.
**Valid behavior.** Regression guard for model-parsing equivalence.

## Test-writing pattern for deadlocks

For deadlock tests (cycles, dead branches, impossible conditions), the
assertion shape is always:

```python
actions = world.tick()
assert not any("DISPATCHED" in a for a in actions)      # nothing ran
assert count_cards(world.board_db) == 0                   # nothing created
assert not any("WORKFLOW COMPLETE" in a for a in actions) # didn't finish
active = world.engine.state.load_active_instances()
assert len(active) == 1                                   # instance stuck
```

Use `idempotency_key LIKE '%:<node_id>'` to find a specific node's card
when multiple nodes share an assignee (common in fan-out tests where all
children use profile "qa"). This is more robust than querying by assignee.

## Pitfalls specific to graph testing

- **Don't query by assignee when fan-out gives every child the same
  assignee.** Multiple "qa" cards collide. Query by idempotency key suffix:
  `SELECT id FROM tasks WHERE idempotency_key LIKE '%:child5'`.
- **A tick that dispatches a card does NOT complete it in the same tick.**
  Completion only registers on the NEXT tick (Phase 1 before Phase 2). When
  testing fan-in (sink waits for N satellites), complete satellites across
  multiple tick+complete cycles, then tick once to check the sink.
- **The 50-node fanout test must assert in ONE tick**, not 50. The point is
  that all children dispatch simultaneously when the parent completes. If
  you tick once per child you're testing the wrong thing.
