# Composition & Subworkflow Testing

How to test trigger-based composition — where one workflow's node completion
triggers another workflow via `card_completed` triggers. This is the current
(no native `subworkflow` node) composition mechanism. See
`docs/workflow-composition-design.md` for the planned subworkflow model.

## When to write composition tests

- After the FakeWorld suite (test_engine.py) passes — composition builds on
  the same FakeWorld harness.
- When the user asks to test "subworkflows", "workflow chains", "nested
  workflows", "recursive triggers", "parallel children", or "failure
  isolation".
- As tier 5 in the incremental validation sequence (see SKILL.md):
  FakeWorld → hybrid → adversarial → more adversarial → **composition**.

## Workflow template helpers

The key technique: parametric template generators so A's node output matches
B's trigger condition without copy-pasting JSON.

```python
def workflow_a(trigger_condition=None, assignee="worker-a", verdict="PASS"):
    """Parent workflow A. Its node completes with metadata matching B's trigger.
    If trigger_condition is provided, A is ALSO triggerable (for recursion)."""
    template = {
        "id": "workflow-a",
        "name": "Workflow A (parent)",
        "nodes": [{
            "id": "do_a",
            "profile": assignee,
            "skill": "work-skill",
            "body_template": "Do work A for ${trigger.task}",
        }],
    }
    if trigger_condition:
        template["trigger"] = {"source": "card_completed",
                               "condition": trigger_condition}
    return template


def workflow_b(trigger_condition, assignee="worker-b"):
    """Child workflow B. Triggered by A's node completion."""
    return {
        "id": "workflow-b",
        "name": "Workflow B (child of A)",
        "trigger": {"source": "card_completed", "condition": trigger_condition},
        "nodes": [{
            "id": "do_b",
            "profile": assignee,
            "skill": "work-skill",
            "body_template": "Do work B triggered by ${trigger.card_id}",
        }],
    }
```

The `verdict` param documents what metadata A's node will produce — it's not
read by the template itself but signals to the test author what trigger
condition B needs.

## Instance-count assertions

Composition tests need to verify child instances were actually created, not
just that cards were dispatched. Use a direct state-DB query:

```python
def get_instance_count(state_db, workflow_id=None):
    """Count instances in state DB, optionally filtered by workflow_id."""
    conn = sqlite3.connect(str(state_db))
    if workflow_id:
        count = conn.execute(
            "SELECT count(*) FROM workflow_instances WHERE workflow_id = ?",
            (workflow_id,)).fetchone()[0]
    else:
        count = conn.execute("SELECT count(*) FROM workflow_instances").fetchone()[0]
    conn.close()
    return count
```

After A→B: `get_instance_count(world.state_db_path) == 2`.
After A→B→C: `== 3`.
After A↔B recursion (one round): `a_count >= 2, b_count >= 1`.

## The six test categories

### 1. Trigger-based composition (A output triggers B)

The simplest chain. Start A manually, complete A's node with metadata matching
B's trigger, tick → B starts.

```
world.start("workflow-a", context={"task": "build-feature"})
world.tick()                          # dispatch A
world.complete_card(a_card, metadata={"verdict": "PASS"})
actions = world.tick()                # A done → B STARTED via trigger
world.tick()                          # B dispatches
assert get_instance_count(world.state_db_path) == 2
```

**Why it works in one tick:** `_check_triggers` runs AFTER `_check_instance`
in the tick loop. So in the same tick, A's node is marked DONE AND B is
started. This is correct tick-loop ordering (Phase 1 before Phase 2).

### 2. Nested chain (A → B → C)

Three-level deep chain. Each workflow's node output matches the next
workflow's trigger condition. The test follows the same complete→tick pattern
at each level:

```
Level 1: A completes → B starts
Level 2: B completes → C starts
Level 3: C dispatches
```

Assert `get_instance_count(world.state_db_path) == 3` and `count_cards == 3`.

### 3. Recursive triggers (A → B → A)

A and B both have triggers AND produce matching metadata. Each round creates
a new card → new trigger key → the cycle continues.

**Finding: UNBOUNDED.** trigger_keys dedup is `trig:{wf_id}:{card_id}` — per
card, not per workflow pair. A different card CAN trigger the same workflow.
After A1→B1→A2, there are ≥2 instances of A. The test asserts this growth
pattern. See also `references/scenario-adversarial-tests.md` §2 (circular
trigger) which found the same thing from the adversarial angle.

**Don't assert the cycle stops.** It doesn't. The test bounds itself by only
running N ticks. If `max_recursions` is ever implemented (design doc §7), this
test will need dual-nature maintenance.

### 4. Parallel children (one node triggers B and C)

A's single node completes. Both B and C have triggers matching A's output.
In one tick, both fire:

```
actions = world.tick()
assert any("STARTED" in a and "workflow-b" in a for a in actions)
assert any("STARTED" in a and "workflow-c" in a for a in actions)
```

This is fan-out composition. Verify `get_instance_count == 3` (1×A + 1×B + 1×C).

### 5. Failure isolation (child blocks, parent is unaffected)

**Finding: No back-propagation.** Without a native subworkflow node, parent
and child are independent instances linked only by a trigger. The parent
completes when ITS OWN nodes finish — it has no mechanism to observe or wait
for the child.

The test verifies:
1. After A completes and B starts, B's card is set to `blocked`.
2. A is NOT in the active instances list (it already completed).
3. B IS still active (blocked).
4. Tick reports B as BLOCKED but produces no A-related actions.

```python
active = world.engine.state.load_active_instances()
assert len([i for i in active if i.workflow_id == "workflow-a"]) == 0  # A done
assert len([i for i in active if i.workflow_id == "workflow-b"]) == 1  # B stuck
```

This is the core gap the `subworkflow` node type (design doc §3) would fill:
a `blocked` parent node that unblocks when the child instance completes.

### 6. Composition data flow (metadata → trigger context)

When A triggers B, A's card metadata becomes B's `trigger_context`, available
as `${trigger.*}` in node templates. This is the data-flow channel.

Verify by querying the state DB:
```python
conn = sqlite3.connect(str(world.state_db_path))
ctx = json.loads(conn.execute(
    "SELECT trigger_context FROM workflow_instances WHERE workflow_id='workflow-b'"
).fetchone()[0])
conn.close()
assert ctx.get("build_id") == "BUILD-12345"  # from A's card metadata
```

## Trigger dedup semantics (important for recursion tests)

| Question | Answer | Why |
|----------|--------|-----|
| Same card, same workflow, two ticks | Deduped (1 instance) | `trig:{wf}:{card}` recorded on first tick |
| Two different cards, same workflow | NOT deduped (2 instances) | Different card IDs → different trigger keys |
| Same card, two different workflows | NOT deduped (2 instances) | Different wf IDs → different trigger keys |

This is why A↔B recursion grows: each round's card is new. The dedup prevents
re-processing the SAME card, not re-triggering the SAME workflow.

## Pyright type warnings (not runtime errors)

`FakeWorld.find_card_by_assignee()` returns `str | None`. When passing the
result to `complete_card(card_id: str)`, Pyright flags a type mismatch. The
existing test_engine.py uses the same pattern. Fix with an assertion + type
annotation:

```python
a_card = world.find_card_by_assignee("worker-a")
assert a_card, "A's card not found"
a_card_id: str = a_card
world.complete_card(a_card_id, metadata={"verdict": "PASS"})
```

## File structure

```
test_composition.py    # 10 tests, FakeWorld-based, standalone + pytest
  # Helpers (mirrors test_engine.py):
  #   make_fake_board, make_fake_card, complete_fake_card, count_cards
  #   get_instance_count (composition-specific)
  #   FakeWorld fixture (with multi-board support)
  #   workflow_a(), workflow_b(), workflow_c() template generators
  #
  # Tests:
  #   test_trigger_composition_a_triggers_b
  #   test_nested_chain_a_b_c
  #   test_recursive_trigger_a_b_a
  #   test_trigger_dedup_is_per_card_not_per_workflow
  #   test_parallel_children_one_node_triggers_b_and_c
  #   test_subworkflow_failure_isolation
  #   test_subworkflow_child_stuck_parent_unaffected
  #   test_composition_data_flow_via_trigger
  #   test_composition_multiple_boards
  #   test_bounded_recursion_card_dedup
```

Imports `FakeWorld` pattern from `test_engine.py` conventions. Runs in ~0.1s.
All 10 tests are all-green (they document current behavior, not bugs).
