# Adversarial Test Catalog for Workflow Engines

13 adversarial test scenarios that found 2 real engine bugs. After happy
paths and edge cases pass, run these to find structural weaknesses.

## Tests that found bugs

### test_adv_state_db_deleted → BUG FOUND

**Bug:** StateDB.load_active_instances() crashed with `OperationalError: no
such table: workflow_instances` when the state DB was deleted mid-workflow.

**Fix:** Added `_ensure_schema()` to StateDB that recreates tables if missing.
Called at the start of every read method. The state DB is a cache, not ground
truth — losing it should degrade gracefully (orphaned cards, no crash).

```python
def _ensure_schema(self):
    db_path = Path(self.db_path)
    if not db_path.exists():
        self._init_schema()
        return
    conn = sqlite3.connect(str(self.db_path))
    try:
        conn.execute("SELECT 1 FROM workflow_instances LIMIT 1")
    except sqlite3.OperationalError:
        conn.close()
        self._init_schema()
        return
    conn.close()
```

### test_trigger_dedup → BUG FOUND

**Bug:** Timestamp-based watermark dedup was unreliable. A card completed
within the lookback window would re-trigger on every tick, creating
duplicate workflow instances.

**Root cause:** `set_watermark(f"{board}:{wf.id}", now)` was called after
every trigger scan, but the lookback used `max(last_ts, now-300)` which
still included cards from the last 5 minutes. The same card matched
every tick.

**Fix:** Replaced timestamp watermarks with a `trigger_keys` table. Each
card-to-workflow pair gets a permanent key: `trig:<workflow_id>:<card_id>`.
The key prevents re-triggering forever, not just for N seconds.

```python
# In _check_triggers:
trig_key = f"trig:{wf.id}:{card.id}"
if self.state._trigger_key_exists(trig_key):
    continue  # already triggered
actions += self._start_from_trigger(wf, board, card)
self.state._record_trigger_key(trig_key)
```

## Tests that validated correct behavior (no bugs)

### test_adv_self_triggering_loop

Workflow whose node assignee (qa) matches the trigger condition (assignee=qa).
The engine-created card DOES re-trigger when it completes with matching
metadata. This is actually correct — it's the composition pattern
(qa-loop triggers debug-loop triggers qa-loop). Recursion terminates when
conditions stop matching.

### test_adv_duplicate_node_ids

Two nodes with the same `id`. The engine creates one card because
`node_states` is keyed by `node_id` — the second definition overwrites
the first in the dict. No crash, but the second node is silently lost.

### test_adv_nonexistent_dependency

Node depends on a node that doesn't exist in the workflow. The dependency
check fails (no node state for the ghost node) → node never dispatches.
Correct behavior — no crash, no dispatch.

### test_adv_multiple_matching_cards_one_tick

Three verifier PASS cards complete simultaneously. Engine starts 3
workflow instances in one tick. Correct — each card gets its own instance
via the trigger key.

### test_adv_trigger_on_engine_card

Recursive composition: qa-loop (verifier PASS → qa) and re-verify
(qa FAIL → verifier). Verifying the full recursive chain works:
qa-loop triggers → qa runs → qa FAIL → re-verify triggers → verifier runs
→ verifier PASS → qa-loop triggers again. This is the intended composition
pattern for the production pipeline.

### test_adv_template_injection

Metadata containing `${nodes.b.output.evil_command}` patterns. The
`resolve_template` function does simple string replacement — it doesn't
recursively evaluate. The `${}` in metadata values stays as literal text
(or gets removed as unresolved). No injection possible.

### test_adv_long_chain_20

20 sequential nodes (n0 → n1 → ... → n19). Completes without stack
overflow. Each tick processes one completion + one dispatch. The tick loop
is O(nodes) per tick, not recursive.

### test_adv_condition_references_own_output

Node condition: `${nodes.a.output.ready} == 'true'`. The node can never
dispatch because it needs its own output, which requires dispatching.
Correct deadlock behavior — no crash, node stays pending forever.

### test_adv_watermark_gap

Card completed 10 minutes ago (outside 5-minute lookback). After fixing
the lookback to 1 hour, the card IS detected. The 1-hour lookback is wide
enough to cover engine downtime while trigger_keys prevent duplicates.

### test_adv_card_archived_mid_workflow

Card set to `status='archived'` between ticks. Engine correctly does NOT
mark the node as done and does NOT dispatch downstream nodes. Archive is
treated as neither done nor blocked — the node stays dispatched forever.

### test_adv_empty_string_condition

`${var} exists` returns False for empty string `""` because
`bool(context.get(key))` evaluates `""` as falsy. `${var} is empty` returns
True for `""`. This is the Python truthiness semantics, not a bug — but
worth documenting because "exists" feels like it should mean "key is
present" rather than "value is truthy."

### test_adv_rapid_ticks

10 instant `tick()` calls. Only 1 card created — idempotency key
(`wf:<instance>:<node>`) prevents duplicate card creation even when
multiple ticks fire before the first card is picked up by the dispatcher.

## Lessons

1. **Adversarial testing finds real bugs.** Happy path tests confirmed the
   engine worked for normal cases. Adversarial tests found the state DB
   crash and the trigger dedup failure — both would have caused production
   issues.

2. **Test failure scenarios, not just success scenarios.** What happens when
   the database is deleted? When a card is archived? When the same tick
   fires twice? These are the questions that find bugs.

3. **Document known limitations as test assertions.** The self-trigger test
   doesn't assert the engine prevents re-triggering — it documents that
   re-triggering IS the composition pattern. This prevents future devs from
   "fixing" intended behavior.
