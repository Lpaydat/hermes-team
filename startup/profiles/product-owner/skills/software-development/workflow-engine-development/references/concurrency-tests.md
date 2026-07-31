# Concurrency Tests

6 adversarial tests targeting the engine's **concurrency model** — race
conditions, simultaneous access, partial writes, and database locking. These
are distinct from state-lifecycle (which probes state-vs-board disagreement
under single-threaded operation): concurrency tests probe what happens when
*two or more ticks run at once*, or when the engine races itself. **All 6
found confirmed bugs** — the engine has zero locking.

All tests follow the FakeWorld pattern (monkey-patched `KANBAN_HOME`, fake
`create_card`). Append to `test_engine.py` before the `# RUN ALL TESTS`
section, and add them to the `tests = [...]` runner list.

## How this category differs from the other adversarial rounds

- **graph-pathology** attacks the *shape* of the workflow graph.
- **data-corruption** attacks the *content* of individual fields.
- **state-lifecycle** attacks the state persistence layer *one operation at a
  time* (single-threaded disagreement).
- **concurrency** (this file) attacks what happens when **multiple control
  flows overlap in time**: two engines ticking the same DB, two threads
  updating the same node, a tick that snapshots state then mutates while
  another tick mutates the same snapshot, a DB locked by another writer, a
  crash that leaves a half-written trigger dedup key.

The core weakness is structural: **every `StateDB` method opens its own
`sqlite3.connect()`, does a non-atomic read-modify-write, and never catches
`OperationalError`.** There is no `BEGIN IMMEDIATE` transaction, no
`threading.Lock`, no single-writer assumption. The dispatch path is
check-then-create (`find_cards_by_idempotency_key` then `create_card`) across
two separate connections. Trigger dedup is check-then-act across **three**
separate connections. None of it is safe under concurrency.

## The bug taxonomy (concurrency-specific)

| Failure mode | Bug | Where it lives in this engine |
|---|---|---|
| **TOCTOU double dispatch** | two engines both observe "no existing card", both create one | `_dispatch_node`: `find_cards_by_idempotency_key` (read) then `create_card` (write), no transaction |
| **Lost update (read-modify-write)** | two concurrent updates each read stale row, last-write-wins drops one field | `update_node_state`: SELECT then UPDATE in separate statements, no atomic upsert |
| **Duplicate trigger instances** | two engines both see "no dedup key", both start an instance | `_check_triggers`: `_trigger_key_exists` then `_start_from_trigger` then `_record_trigger_key`, 3 connections |
| **Stale-snapshot double dispatch** | tick() snapshots active instances up front; overlapping tick re-dispatches from stale snapshot | `tick()` / `_check_instance`: load-then-mutate with no locking |
| **Uncaught DB-lock crash** | contended DB raises `OperationalError("database is locked")`, propagates out of tick, kills the loop | every `StateDB` method: no `except sqlite3.OperationalError` |
| **Partial-write duplicate** | instance created but trigger key write lost (crash between) → next tick re-triggers same card | `_check_triggers`: `create_instance` and `_record_trigger_key` not atomic |

Generalize: for **every** check-then-act or read-modify-write sequence, ask
"what if two flows execute this concurrently, or the write after the check
fails?" If the answer is "duplicate work / lost data / crash," that's a bug.
The fix patterns: `BEGIN IMMEDIATE` transactions (SQLite serializes writers),
`INSERT ... ON CONFLICT` atomic upserts, a single-writer lock around tick(),
and `except sqlite3.OperationalError` with retry/skip in every DB method.

## The bug-finder test convention

Same as the other categories: tests that find a bug **FAIL with
`AssertionError`** — the message IS the bug report. Do not relax the
assertion to make these pass; fix the engine. Each docstring states the
targeted code path; each assertion message names the defect. See
`state-lifecycle-tests.md` for the full convention and the
expected-outcome-map verification pattern.

## Making race windows deterministic (the key technique)

The hard part of concurrency testing is that races are *timing-dependent* —
a naive `threading.Thread` test will pass 99% of the time and only catch the
bug when the scheduler interleaves just so. **Use `threading.Barrier` to
force the interleaving**, closing the TOCTOU window deterministically:

```python
barrier = threading.Barrier(2)  # 2 threads must both arrive before either proceeds

def synced_create(*args, **kwargs):
    barrier.wait(timeout=5)   # both threads block here until both are ready
    return real_create(*args, **kwargs)

# Monkey-patch the function INSIDE the check-then-create window:
import workflow_engine.runtime as rt
rt.create_card = synced_create

# Now both threads are guaranteed to have passed the existence-check
# (find_cards_by_idempotency_key) before either executes the create.
```

The same barrier-in-the-middle pattern works for the read-modify-write race
(barrier between the SELECT and the UPDATE) and the trigger-dedup race
(barrier inside the `_record_trigger_key` that runs after instance creation).
Put the barrier at the **seam between the check and the act** — that's where
the bug lives. A 5-second `timeout` on `barrier.wait()` prevents a deadlocked
test from hanging the suite forever if the harness is broken.

**Building a second engine that shares state:** to test two concurrent
*engines* (not just two threads on one engine), construct a second `Engine`
pointed at the same `templates_dir` + `state_db_path`:

```python
def _make_second_engine(world):
    eng = Engine(world.templates_dir)
    eng.state = StateDB(world.state_db_path)  # same DB, fresh connection pool
    return eng
```

Both engines then race against the same state DB with no coordination between
them — exactly the production hazard.

## The 6 tests

### test_adv_concurrency_two_engines_double_dispatch → BUG

Two `Engine` instances share one state DB + board. Both tick concurrently.
`_dispatch_node` calls `find_cards_by_idempotency_key` (read) then
`create_card` (write) in two separate connections. A `Barrier` at the
`create_card` seam forces both threads past the existence-check before either
inserts. Result: **2 cards created for one node.** The idempotency key on the
*board* only deduplicates within a single check-then-create; the race defeats
it. Fix: wrap the check-then-create in a `BEGIN IMMEDIATE` transaction, or
use `INSERT ... ON CONFLICT DO NOTHING` on the board and rely on its returned
rowid rather than a separate existence query.

### test_adv_concurrency_concurrent_state_writes → BUG

Two threads each call a `update_node_state`-equivalent on the same node, one
setting `card_id` (omitting output), one setting `output` (omitting card_id).
`update_node_state` is a non-atomic read-modify-write: it SELECTs the existing
row, merges the omitted field from the DB, then UPDATEs. A `Barrier` between
the SELECT and UPDATE forces both threads to read the stale row before either
writes. Result: **last-write-wins loses one field** (`card_id='card_1'` but
`output={}`, or vice versa). Fix: use a single atomic `UPDATE ... SET
card_id=COALESCE(?, card_id), output=COALESCE(?, output)` so each field is
only overwritten when explicitly provided.

### test_adv_concurrency_trigger_dedup_race → BUG

Two engines detect the same trigger card concurrently. `_check_triggers` calls
`_trigger_key_exists` (read), then `_start_from_trigger` (creates instance),
then `_record_trigger_key` (write) — three separate connections, no
transaction. A `Barrier` inside `_record_trigger_key` forces both threads to
have created their instance before either records the dedup key. Result: **2
workflow instances** started for one trigger card. Fix: make the dedup-key
insert the *first* write in a transaction (`INSERT INTO trigger_keys ...
ON CONFLICT DO NOTHING; if 0 rows affected, skip`), and create the instance
only inside that same transaction.

### test_adv_concurrency_overlapping_ticks → BUG

Two threads call `tick()` on the *same* Engine concurrently. `tick()`
snapshots active instances up front (`load_active_instances`), then mutates
state across the rest of the tick. With overlapping ticks, the second tick's
snapshot is stale — it re-dispatches a node the first tick already dispatched.
A `Barrier` at `create_card` forces both past the dispatch check. Result: **2
cards for one node** from a single engine. Fix: a `threading.Lock` around
`tick()` (single-writer assumption), or `BEGIN IMMEDIATE` so concurrent ticks
serialize at the DB.

### test_adv_concurrency_db_locked → BUG

Another process holds a write lock on the state DB. Every `sqlite3.connect`
raises `OperationalError("database is locked")`. Simulated by monkey-patching
`sqlite3.connect` to raise. `StateDB` has **no `except OperationalError`**
anywhere; the error propagates straight out of `tick()`. Result: **tick
crashes** instead of degrading gracefully (skip + log + retry next tick).
Fix: wrap every DB operation in `try/except sqlite3.OperationalError`, return
a safe no-op action, and optionally set a short `busy_timeout` on connect so
SQLite waits briefly for the lock instead of failing immediately.

### test_adv_concurrency_partial_write_trigger_key → BUG

The engine creates a workflow instance, then records the trigger dedup key.
If the process crashes between the two (partial write / lost write), the key
is never persisted. Simulated by replacing `_record_trigger_key` with a no-op
lambda. On the next tick, `_trigger_key_exists` returns False for the same
card → the engine starts a **duplicate instance**. Fix: make
`create_instance` and `_record_trigger_key` atomic — record the key *first*
(inside the same transaction that creates the instance), or use a deferred
constraint so the instance can't exist without its dedup key.

## Pitfalls specific to concurrency testing

- **Use `threading.Barrier`, not bare threads, to expose races.** Bare
  `threading.Thread` tests pass ~99% of the time because the scheduler rarely
  interleaves at the exact vulnerable seam. A `Barrier(2)` placed at the seam
  (between check and act, or between read and write) forces both threads to
  the vulnerable point simultaneously, making the race **deterministic**.
- **Always set a `timeout` on `barrier.wait()`.** If the test harness is
  mis-wired (one thread never reaches the barrier), an unbounded wait hangs
  the entire suite. `barrier.wait(timeout=5)` turns that into a fast,
  diagnosable `BrokenBarrierError`.
- **Join threads with a timeout too.** `t.join(timeout=10)` — a deadlocked
  engine call should fail the test, not hang CI.
- **Collect thread exceptions into a list, assert it's empty.** If a thread
  raises, the exception is silently swallowed by `Thread` unless you capture
  it. An empty-errors check distinguishes "the race produced a wrong result"
  (the bug) from "a thread crashed" (a broken test):
  ```python
  errors = []
  def run():
      try: eng.tick()
      except Exception as e: errors.append(e)
  ...
  assert not errors, f"threads raised unexpectedly: {errors}"
  ```
- **Monkey-patch the module attribute, not a local.** To intercept
  `create_card` inside the engine, patch `workflow_engine.runtime.create_card`
  (the name the engine imports), not `kanban_adapter.create_card` directly —
  the engine holds its own reference at import time.
- **Test two engines by sharing the state DB path, not by cloning the
  Engine.** Two `StateDB(db_path)` instances open independent connection pools
  against the same file — that's the real multi-process hazard. Constructing
  one Engine and sharing its `StateDB` object would hide the bug (the single
  object serializes internally).
- **Restore monkey-patches in a `finally`.** `rt.sqlite3.connect`,
  `rt.create_card`, and any `_record_trigger_key` override must be restored
  or they leak into subsequent tests. The `FakeWorld.cleanup()` already
  restores `create_card`; add your own restores for anything else you patch.
- **Write to a standalone file first when sibling agents edit the same test
  file concurrently.** If `patch` reports the file was modified by a sibling
  and the anchor is no longer unique, don't fight for a stable anchor in a
  moving file. Write the tests to `test_<category>_standalone.py` that
  `import`s `FakeWorld` from `test_engine.py`, run them to confirm they break
  the engine, *then* append to the shared file once you have a fresh read.
  This avoids lost-write thrash and gets you real results faster.
