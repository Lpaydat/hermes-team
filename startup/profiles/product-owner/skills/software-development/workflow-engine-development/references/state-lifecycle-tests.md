# State & Lifecycle Tests

12 adversarial tests targeting the **state persistence layer** — the
relationship between `StateDB` (the engine's SQLite cache), the board DB
(ground truth), and the workflow instance lifecycle. Added after the
graph-pathology and data-corruption rounds; **found 10 confirmed bugs**.

All tests follow the FakeWorld pattern (monkey-patched `KANBAN_HOME`, fake
`create_card` writing to temp SQLite). Append to `test_engine.py` before
the `# RUN ALL TESTS` section.

## How this category differs from the other adversarial rounds

- **graph-pathology** attacks the *shape* of the workflow graph (cycles, dead
  branches, fan-out). Weakness: silent eternal deadlock.
- **data-corruption** attacks the *content* of individual fields (null
  values, unicode, huge payloads). Weaknesses: crashes on null + data loss.
- **state-lifecycle** (this file) attacks the **state persistence layer** —
  what happens when the state DB disagrees with the board DB, when instances
  outlive their boards, when DB rows are mutated out-of-band, when the DB
  itself is corrupted/readonly/grows without bound. Weakness: the engine
  trusts its own state DB as ground truth and never reconciles against the
  board; every silent-swallow path in `StateDB` is a latent bug.

## The bug taxonomy (reusable for any stateful engine)

When testing a stateful scheduler, probe these 10 failure modes — they map
to the bugs found here:

| Failure mode | Bug | Where it lives in this engine |
|---|---|---|
| **Zombie instance** | completed instance flipped back to active re-dispatches | no completion-guard on `_check_instance` |
| **Dangling reference** | `card_id` points to a card that doesn't exist → node hangs forever | no existence/timeout check in Phase 1 |
| **Stale/orphan rows** | node_states for nodes no longer in template leak into context | `load_active_instances` returns all rows, not just template nodes |
| **Card regression** | board card flipped `done`→`todo` but node already DONE → orphan card, no reconciliation | engine never re-checks board after node DONE |
| **Orphaned instance** | board DB deleted but instance stays `active` forever, no error | `_check_instance` swallows missing board silently |
| **Silent swallow on dup ID** | `INSERT OR IGNORE` on duplicate instance_id drops the new values | `create_instance` |
| **Silent swallow on missing row** | `UPDATE` affects 0 rows, no error, state lost | `update_node_state` |
| **State trusted over ground truth** | instance marked complete based on state DB alone, card never verified | `all_done` completion check |
| **No input validation** | negative/garbage timestamps stored as-is | `create_instance` |
| **Uncaught DB error** | read-only DB → `OperationalError` crashes engine, no handler | every StateDB write method |

Generalize the pattern: for **every** write/read in the state layer, ask
"what if the row already exists / doesn't exist / the field is garbage /
the DB is unwritable?" If the answer is "silently does nothing," that's a
bug. The engine must either raise OR upsert — silent no-ops are always
wrong for state writes.

## The bug-finder test convention (IMPORTANT)

**The test suite is NOT expected to be all-green.** Adversarial tests that
find a bug are written to **FAIL with `AssertionError`** — the `BUG:` prefix
in the assertion message IS the bug report. A passing run means the engine
is hardened; a failing run means the bug is still there. Do not "fix" these
tests by relaxing the assertion — fix the engine, then the test flips to
passing and becomes a regression guard.

Each test docstring carries a `DESIRED:` line (what the engine SHOULD do)
and the assertion message carries a `BUG:` line (what it actually does).
This makes the test output self-documenting.

### Verifying a new batch of bug-finder tests

Run them in isolation with an expected-outcome map before trusting the
full suite. The split (N bug-finders expected to FAIL, M confirmed-OK
expected to PASS) validates that the tests actually exercise the code path
you intended, rather than erroring for an unrelated reason:

```python
EXPECTED = [
    ("test_adv_state_zombie_instance_reactivated", "fail"),  # bug-finder
    ("test_adv_state_multiple_instances_isolation", "pass"), # confirmed safe
]
for name, expected in EXPECTED:
    fn = getattr(te, name)
    try:
        fn(); actual = "pass"
    except AssertionError: actual = "fail"
    assert actual == expected, f"{name}: expected {expected}, got {actual}"
```

If a test you expected to FAIL instead ERRORs (not AssertionError), the
test itself has a bug — fix the test before reading it as an engine bug.

## The 12 tests

### test_adv_state_zombie_instance_reactivated → BUG

Completed instance manually flipped `status='active'` + node reset to
`pending`. Engine re-dispatches as if new — phantom work from an instance
the user believed finished. **No completion-guard**: `_check_instance` has
no check for "this instance was already completed once."

### test_adv_state_fake_card_id_dispatched → BUG

Node set to `DISPATCHED` with `card_id='FAKE-NONEXISTENT'`. `get_card`
returns `None`, the `if not card: continue` swallows it, node hangs forever
with zero diagnostics. **No existence check, no timeout, no recovery
action.** A stale card_id reference is indistinguishable from "still
running."

### test_adv_state_stale_node_states_after_template_edit → BUG

A `node_states` row for node `'ghost'` (not in the template) is inserted
directly. `load_active_instances` loads ALL node_states rows, so `'ghost'`
appears in `inst.node_states` and its output leaks into the template
context. **No reconciliation** between state DB rows and the current
template definition.

### test_adv_state_card_reuse_done_to_todo → BUG

Board card flipped `status='done'`→`'todo'` after the node is already DONE
in state. The engine's Phase 1 loop only inspects `DISPATCHED` nodes, so a
DONE node's card is never re-checked. The card becomes an orphan nobody
owns. **No reconciliation** of board state for completed nodes.

### test_adv_state_instances_for_deleted_board → BUG

Board DB deleted; instance stays `active`. Every tick: `get_card` returns
`None` (board missing), swallowed silently. Instance zombies forever, no
error, never completes. **No board-existence or liveness check.** The
instance should be marked failed/orphaned, not left active indefinitely.

### test_adv_state_create_instance_duplicate_id → BUG

`create_instance` called twice with the same `instance_id` but different
`board`. `INSERT OR IGNORE` silently keeps the first row; the board/project
change is lost with no error. **Should upsert or raise.**

### test_adv_state_update_node_before_create → BUG

`update_node_state` on an instance_id/node_id that doesn't exist. The
`UPDATE ... WHERE` affects 0 rows; no error, no insert. The state is
silently lost. **Should raise or upsert (INSERT ... ON CONFLICT).**

### test_adv_state_complete_while_card_running → BUG

All node_states set to `done` manually while the board card is still
`'todo'`. The `all_done` check iterates `node_states` only — it never
verifies the board card is actually `done`. Instance marked complete; card
becomes an orphan. **State DB trusted as ground truth over the board.**

### test_adv_state_bad_created_at → BUG

`WorkflowInstance(created_at=-1)`. No validation; `-1` stored in DB. Affects
any time-based logic (trigger lookback, GC, staleness). **No timestamp
validation** in `create_instance`.

### test_adv_state_multiple_instances_isolation → PASS (confirmed safe)

Two instances of the same workflow on the same board; completing one does
not affect the other. Instances are correctly isolated by `instance_id`.
**Regression guard** — would catch any future shared-state bug.

### test_adv_state_trigger_keys_unbounded → PASS (documents weakness)

10,000 trigger_keys inserted; lookup stays fast (0.16s/1000 lookups, indexed
by PRIMARY KEY). An ancient key (created_at=1) survives — **confirms no GC
or TTL**. This is a documented unbounded-growth weakness, not a crash.
Lookup is fine; the table just grows forever. A future hardening pass should
add a TTL or max-age sweep, but this is low priority.

### test_adv_state_readonly_db → BUG

State DB file chmod'd to 0o444 (read-only). `create_instance` →
`sqlite3.OperationalError: attempt to write a readonly database`, uncaught,
crashes the engine. **No exception handling** around any StateDB write. The
engine should catch `OperationalError` and report it as an action, not
crash the tick loop.

## Pitfalls specific to state-lifecycle testing

- **Don't assume `count_cards` reflects engine intent.** When a bug causes
  an extra card, `before == after` is the right assertion, not "cards == 1"
  — there may be pre-existing cards from setup.
- **Query the state DB for card IDs, not the board.** After a dispatch, the
  authoritative `card_id` is in `node_states.card_id`, not inferred from
  `SELECT id FROM tasks WHERE assignee=...` (multiple cards can share an
  assignee in fan-out scenarios — see graph-pathology-tests.md pitfall).
- **Restore file permissions in a `finally` or at end of test.** The
  readonly-DB test must `os.chmod(path, 0o644)` before cleanup or the temp
  dir removal fails.
- **Read the whole test file before patching when working concurrently.**
  A sibling subagent editing `test_engine.py` simultaneously will move line
  offsets and change the runner block. Re-read with offset near the runner
  before inserting; never trust a cached line count.
