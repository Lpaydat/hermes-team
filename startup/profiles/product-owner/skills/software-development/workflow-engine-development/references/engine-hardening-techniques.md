# Engine Hardening Techniques

The concrete fixes applied to the workflow engine (`runtime.py`) when the
adversarial state-lifecycle and concurrency test suites were hardened. Each
entry names the bug, the technique, the before/after shape, and which tests
flipped. Read this when (a) re-implementing a hardened engine from scratch,
(b) porting a fix to a similar scheduler, or (c) triaging whether a failing
adversarial test needs an engine fix or a test-assertion update.

---

## 1. Zombie instance detection (`completed_at` column)

**Bug:** A completed instance is manually flipped back to `active` (SQL
`UPDATE ... status='active'`) and a node reset to `pending`. The engine
re-dispatches it — phantom work from an "finished" instance.

**Fix:** Add a `completed_at INTEGER` column to `workflow_instances`.
`complete_instance` sets it to `int(time.time())`. At the top of
`_check_instance`, guard before any other logic:

```python
if inst.completed_at is not None:
    actions.append(f"SKIP zombie instance {inst.instance_id}: previously completed ...")
    self.state.complete_instance(inst.instance_id)  # re-mark complete
    return actions
```

`load_active_instances` must populate `completed_at` on the `WorkflowInstance`
dataclass. Use `"completed_at" in row.keys()` guards for DBs created before the
column existed (see migration below).

**Tests flipped:** `test_adv_state_zombie_instance_reactivated` (FAIL → PASS).

---

## 2. Deleted-board detection

**Bug:** The board DB is deleted/unmounted but the instance stays `active`
forever — loaded every tick, no error, no completion, pure zombie.

**Fix:** At the top of `_check_instance`, before loading the template:

```python
if not board_db_path(inst.board).exists():
    actions.append(f"WARNING instance {inst.instance_id}: board '{inst.board}' not found (missing) — marking complete")
    self.state.complete_instance(inst.instance_id)
    return actions
```

**Tests flipped:** `test_adv_state_instances_for_deleted_board` (FAIL → PASS).

---

## 3. Negative `created_at` validation

**Bug:** `create_instance` accepted `created_at=-1` (and any garbage) silently.

**Fix:** Validate at the top of `create_instance`, before opening a connection:

```python
if instance.created_at is not None and instance.created_at < 0:
    raise ValueError(f"created_at must be non-negative, got {instance.created_at}")
```

The row is never written because the exception fires before the INSERT.

**Tests flipped:** `test_adv_state_bad_created_at` (FAIL → PASS).

---

## 4. Stale node-state filtering (`node_ids` snapshot)

**Bug:** After a template edit removes a node, orphan `node_states` rows persist
in the DB and leak into the loaded instance — orphan outputs pollute variable
resolution context.

**Fix — two layers:**

**(a) Snapshot at creation time.** `create_instance` stores a JSON array of the
valid node IDs: `node_ids = json.dumps(list(instance.node_states.keys()))` in a
`node_ids TEXT NOT NULL DEFAULT '[]'` column.

**(b) Filter during load.** `load_active_instances` skips any node_state whose
`node_id` is not in the snapshot:

```python
if inst.node_ids and ns_row["node_id"] not in inst.node_ids:
    continue
```

**(c) Defense in depth.** `_check_instance` ALSO filters against the *live*
template (in case the DB row predates the snapshot column) via
`valid_node_ids = {n.id for n in wf.nodes}` and `del inst.node_states[nid]`.

**Tests flipped:** `test_adv_state_stale_node_states_after_template_edit`.

---

## 5. Card-regression check on DONE nodes

**Bug:** A card flips from `done` back to `todo` (manual reuse) after the node
is already DONE in state. The engine never re-examines DONE nodes, so the
orphaned/regressed card is never flagged.

**Fix:** Add PHASE 1b in `_check_instance`, after the dispatched-node completion
scan, that re-checks DONE nodes whose cards regressed:

```python
for node in wf.nodes:
    ns = inst.node_states.get(node.id)
    if not ns or ns.status != NodeStatus.DONE or not ns.card_id:
        continue
    card = get_card(inst.board, ns.card_id)
    if not card:
        actions.append(f"WARNING node {node.id}: DONE card ... no longer exists (orphan)")
        continue
    if card.status in ("todo", "ready", "running"):
        actions.append(f"WARNING node {node.id}: card ... regressed to '{card.status}' (orphan reuse)")
```

**Caveat for test setup:** the regression check only runs while the instance is
*active*. A single-node workflow completes immediately, so by the time the card
is flipped back the instance is no longer loaded. Tests that exercise this path
must use a ≥2-node workflow so the instance stays active when the card is
regressed. (This was a category-2 test edit, not an engine limitation.)

**Tests flipped:** `test_adv_state_card_reuse_done_to_todo` (test setup updated
to a 2-node workflow so the instance stays active; engine phase added).

---

## 6. Board re-verification before instance completion

**Bug:** `complete_instance` fired based on the state DB alone — a node marked
DONE in state while its card is still `todo` on the board let the instance
complete prematurely.

**Fix:** In the all-nodes-done completion block, treat a *missing* card the same
as a non-done card (the old code's `if card and card.status != "done"` silently
passed when `card` was None):

```python
card = get_card(inst.board, ns.card_id)
if card is None:
    cards_verified = False
    actions.append(f"WARNING: node ... card ... is missing on board — cannot complete instance")
    break
if card.status != "done":
    cards_verified = False
    break
```

**Tests flipped:** `test_adv_state_complete_while_card_running` (FAIL → PASS).

---

## 7. Atomic `update_node_state` (COALESCE-merge UPSERT)

**Bug:** `update_node_state` was a non-atomic read-modify-write: it SELECTed the
existing row, merged omitted fields in Python, then UPDATEd. Two concurrent
calls that each omitted a different field both read the stale row and clobbered
each other — one field was lost.

**Fix — single-statement UPSERT with COALESCE, no SELECT:**

```python
conn.execute(
    """INSERT INTO node_states (instance_id, node_id, status, card_id, output)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(instance_id, node_id) DO UPDATE SET
         status=excluded.status,
         card_id=COALESCE(?, node_states.card_id),
         output=CASE WHEN ? = 1 THEN ? ELSE node_states.output END""",
    (instance_id, node_id, status.value,
     card_id,                          # INSERT (NULL ok for nullable col)
     output_json if output_json is not None else "{}",  # NOT NULL col → non-NULL default
     card_id,                          # COALESCE fallback in UPDATE
     1 if output is not None else 0,   # CASE flag
     output_json if output_json is not None else None), # CASE value
)
```

**The NOT NULL trap (IMPORTANT):** `output TEXT NOT NULL DEFAULT '{}'` rejects
an explicit NULL in the VALUES clause *before* the ON CONFLICT clause runs.
Always pass a non-NULL placeholder (`"{}"`) for NOT NULL columns in the INSERT
half, then let ON CONFLICT's COALESCE/CASE preserve the existing value for
omitted fields. If you skip this, you get `NOT NULL constraint failed:
node_states.output` on the INSERT path.

**Tests flipped:** `test_adv_concurrency_concurrent_state_writes`. The test was
rewritten (category-2) to call the engine's atomic method directly instead of
replicating the old raw read-modify-write, and asserts both fields survive.

---

## 8. Concurrency test assertion updates (category-2)

After the engine gained locks, the concurrency tests that *forced races open*
with `threading.Barrier` no longer worked as written — the lock prevents the
race, so the barrier-protected second writer never runs its create, and the
test sees 0 cards instead of the expected 2 (old buggy) or 1 (desired).

**Updated pattern — assert the serialization, not the race:**

- `test_adv_concurrency_two_engines_double_dispatch`: removed the
  `synced_create`/barrier harness; just run two engines concurrently and assert
  exactly 1 card (the file lock SKIPs the second engine's tick entirely).
- `test_adv_concurrency_overlapping_ticks`: removed the barrier harness; assert
  1 card (the internal `_tick_lock` SKIPs the second thread's tick).
- Capture each thread's return value (`results[name] = eng.tick()`) so the
  assertion message can show the SKIP actions for debugging.

The tests remain regression guards — they now guard that the locks stay in
place.

---

## Schema migration (for pre-existing DBs)

New columns (`completed_at`, `node_ids`) must be added to DBs created before
they existed. Run this in `_init_schema` *and* `_ensure_schema`:

```python
def _migrate_columns(self, conn):
    for col, ddl in [
        ("completed_at", "ALTER TABLE workflow_instances ADD COLUMN completed_at INTEGER"),
        ("node_ids", "ALTER TABLE workflow_instances ADD COLUMN node_ids TEXT NOT NULL DEFAULT '[]'"),
    ]:
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
            if col not in cols:
                conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
```

And in `load_active_instances`, guard column access so old DBs don't crash:
`row["completed_at"] if "completed_at" in row.keys() else None`.
