# Scenario-Based Adversarial Testing

Complementary to the weakness-targeted methodology (read source → name a
weakness → write a test that targets it). Scenario-based testing works from
the *outside*: name 10 system-level integration scenarios that stress the
engine as a whole, then document what actually happens for each.

## When to use this vs weakness-based

| Approach | Best for | Signal |
|---|---|---|
| Weakness-based (`references/adversarial-test-catalog.md`) | Finding *bugs* in specific code lines/statement | Engine bug count |
| Scenario-based (this file) | Discovering *system-level behaviors* — emergent interactions between trigger, dispatch, state, and board | Architectural findings (no cycle detection, no hot-reload, recovery characteristics) |

Both are adversarial; they differ in granularity. Write a scenario suite when
the engine has been hardened against the weakness-targeted suite and you need
to probe *integration* behavior — does the whole system hold up, or do
components interact in surprising ways?

## The 10-scenario template

Each scenario is a named system-level stress. Write one test per scenario,
asserting on the engine's *actual* behavior (not desired behavior) and
documenting the finding in the test docstring + a `[FINDING]` print line.

### 1. Trigger chain (A→B)

Two workflows where A's output triggers B (A's node assignee = B's trigger
condition). After completing A's card, one tick should: complete A's instance,
detect the completion via `_check_triggers`, start B.

**Finding:** Chains fire correctly within a single tick. `_check_triggers`
runs after `_check_instance` in the tick loop, so A completes and B triggers
in the same tick — no extra-tick delay. This is the correct ordering.

### 2. Circular trigger (A→B→A)

A triggers B, B triggers A. Each cycle creates NEW instances because trigger
dedup keys include the card ID, and every cycle produces a new card.

**Finding: UNBOUNDED.** No cycle detection, no max-depth guard. Each A→B→A
round creates ~2 new instances. After 3 cycles: 7 instances (started with 1).
In a fully automated system this loops forever. **This is a known limitation.**
The test documents the growth and asserts `total > initial * 3` to catch a
future fix — if cycle detection is added, this test will need updating
(dual-nature maintenance, see SKILL.md).

**Test pitfall:** fetch the latest card with `ORDER BY rowid DESC`, NOT
`ORDER BY created_at DESC` — seconds-resolution `created_at` makes the fetch
non-deterministic and the test flaky.

### 3. Card hijacking (human edits after dispatch)

Engine dispatches a card, then a human edits body/title/idempotency_key,
regresses status, or deletes the card entirely.

**Finding: Resilient.** The engine tracks cards by `card_id` stored in
`node_states`, not by body/title/idempotency_key. Body/title changes are
invisible. Status regression (done→todo) is detected and logged as a WARNING.
Card deletion is detected as "dangling card_id." The engine never crashes.

### 4. Rapid workflow starts (10 instances)

Start 10 instances of the same workflow in quick succession, then tick.

**Finding:** All 10 dispatch correctly in a single tick. The engine iterates
active instances and dispatches pending nodes for each. Instance IDs are
unique (timestamp + uuid hex). No collisions or dropped instances.

### 5. Failing node (card goes to 'blocked')

A node's card is set to `status='blocked'` instead of `done`.

**Finding: Correct behavior.** The engine detects blocked cards and reports
`BLOCKED node` on each tick. The instance stays active indefinitely. Downstream
nodes are not dispatched. This is correct for dynamic-child scenarios (card
blocked waiting for sub-tasks).

### 6. State DB corruption

Write garbage bytes to the state DB file, then tick.

**Finding:** `tick()` wraps everything in `try/except Exception`, so a corrupt
DB returns `['ERROR tick: ...']` instead of crashing the process. BUT the
engine CANNOT auto-recover — `_ensure_schema()` only catches
`OperationalError`, not `DatabaseError`, so it keeps returning errors every
tick. Deleting the corrupt file allows full recovery (schema is recreated),
but all workflow state is lost. **Manual intervention required for corruption.**

### 7. Template hot-reload

Change a template file on disk while a workflow instance is running.

**Finding: NO HOT-RELOAD.** `TemplateStore` caches templates in `_cache` and
never invalidates. Both running instances AND new instances started after the
file change use the originally-cached version. The only way to pick up changes
is to restart the engine (new `TemplateStore` = empty cache). **Known
limitation by design** (performance — avoids re-reading disk every tick).

### 8. Concurrent board access

Two threads writing to the same `kanban.db` simultaneously (50 cards each).

**Finding: No data loss.** SQLite handles concurrent inserts to different
rows correctly. With `timeout=10.0` on the connection, transient lock errors
retry and succeed. The adapter's read functions use plain `sqlite3.connect`
with no timeout, making them theoretically vulnerable under contention, but
the runtime's `_db_connect` uses WAL + 30s timeout, which is more resilient.

### 9. Engine kill mid-tick + recovery

Simulate crash (discard engine object), create new engine on same state DB,
verify recovery.

**Finding: Recovery works.** The state DB is the source of truth — a new
`Engine` object picks up where the old one left off. The idempotency_key
system also protects against partial dispatch: if the crash happened between
card creation and node-state update, the next tick finds the existing card via
`find_cards_by_idempotency_key` and re-links it.

### 10. Workflow storm (5 workflows, same trigger)

5 workflows with triggers all matching the same card completion. One card
fires all 5.

**Finding: All fire correctly.** Each gets a unique trigger key
(`trig:{wf.id}:{card.id}`), so dedup doesn't prevent any of them. 5 new
instances in a single tick. Second tick dispatches all 5 nodes. Third tick
does NOT re-trigger (dedup keys recorded).

## Test file structure

```
test_adversarial.py          # standalone runner + pytest-compatible
  test_01_trigger_chain
  test_02_circular_trigger
  ...
  test_10_workflow_storm
```

- Imports `FakeWorld` from `test_engine.py` (shared harness)
- `setup_world()` creates FakeWorld + patches `LOCK_FILE` to temp path
- `teardown_world()` restores all monkey-patches
- Helper: `get_card_id_by_assignee(board_db, assignee, status=None)` — uses
  `ORDER BY rowid DESC` for deterministic ordering
- Each test uses `try/finally teardown_world(world)` to guarantee cleanup
- `if __name__ == "__main__"` runner catches AssertionError (FAIL) and
  Exception (ERROR) separately, prints findings
