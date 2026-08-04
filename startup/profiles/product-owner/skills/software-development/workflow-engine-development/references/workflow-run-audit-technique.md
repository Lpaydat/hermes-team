# Workflow Run Audit Technique

How to forensically verify a completed (or in-flight) workflow engine run's
mechanics by querying `workflow-state.db` directly. This is the technique for
answering "did the engine behave correctly on this specific run?" — distinct
from writing adversarial tests (which probe the engine in the abstract) or
reading the log via `main.py log` (which is a flat chronological stream).

## When to use this

- A workflow completed and you want to verify tick-level mechanics (conditional
  edges, fan-out/fan-in gating, dead-branch skip, schema enforcement).
- A workflow stalled and you need to find where/why.
- Regression check after an engine change: run the same audit before/after.

## The database

```
~/.hermes-teams/startup/kanban/workflow-state.db
```

Tables: `workflow_instances`, `node_states`, `engine_events`,
`trigger_keys`, `trigger_watermark`.

**Timestamps are in SECONDS** (`datetime(ts, 'unixepoch')`), not
milliseconds — the `datetime(ts/1000, ...)` form is wrong and yields 1970
dates. Check the column magnitude before choosing the divisor.

## The 5-query audit

Run these in order. Each answers one class of question.

### 1. Instance summary

```sql
SELECT instance_id, workflow_id, status, board,
       created_at, completed_at, version
FROM workflow_instances
WHERE workflow_id = '<wf-id>';
```

`status` should be `completed` for a finished run. `version` counts
state-blob writes (a rough proxy for engine activity). `node_ids` is a JSON
array of the template's nodes.

### 2. Per-node terminal state

```sql
SELECT node_id, status, card_id, output
FROM node_states
WHERE instance_id LIKE '%<wf-id>%'
ORDER BY node_id;
```

`status` ∈ {`pending`, `dispatched`, `done`, `failed`}. For skipped nodes,
`status='pending'` but `output` is `{}` and the node is marked `skipped:true`
in the denormalized `state` blob on `workflow_instances`. **Read the `state`
JSON blob too** — it is the authoritative post-T4 snapshot and carries
`iteration`, `skipped`, and `card_status` fields the `node_states` row lacks.

### 3. Full event timeline (the core)

```sql
SELECT id, timestamp, datetime(timestamp, 'unixepoch') AS t,
       level, event_type, node_id, card_id, message
FROM engine_events
WHERE instance_id LIKE '%<wf-id>%'
ORDER BY timestamp ASC, id ASC;
```

This is the audit backbone. Each row is one engine action. The sequence
reconstructs exactly what happened, tick by tick.

### 4. Tick boundaries (count ticks to completion)

```sql
SELECT DISTINCT timestamp
FROM engine_events
WHERE instance_id LIKE '%<wf-id>%'
ORDER BY timestamp;
```

Each distinct timestamp ≈ one engine tick (events within the same tick share
a timestamp). **Number of distinct timestamps = number of ticks to
completion.** This is the fastest way to answer "how many ticks?" without
reading the tick-loop source.

### 5. Schema-validation / error sweep

```sql
SELECT id, level, event_type, node_id, message
FROM engine_events
WHERE message LIKE '%schema%'
   OR message LIKE '%validation%'
   OR message LIKE '%invalid%'
   OR level IN ('ERROR', 'WARN')
ORDER BY id;
```

Query across ALL instances (no instance filter) to catch cross-run
contamination. Zero rows = clean run. **If you see `node_failed` events,
read the message — it carries the schema-violation detail.**

## The 9-point verification framework

For each completed run, verify these mechanics. Each maps to a specific
pattern in the event timeline:

| # | Mechanic | Pass criterion | How to verify |
|---|----------|----------------|---------------|
| 1 | **Command node detection** | Command ran, output parsed into node state | `command_run` event present; `node_done` message shows parsed output, not raw stdout |
| 2 | **Conditional edge firing** | Exactly one out-edge dispatched, the other(s) skipped | For a node with N conditional out-edges: 1 `node_dispatched` + (N-1) `node_skipped (dead branch)` in the same tick |
| 3 | **Parallel fan-out** | All children dispatched in the SAME tick (same timestamp) | Count `node_dispatched` events sharing the parent's done-tick timestamp |
| 4 | **Strict fan-in (AND-join)** | Fan-in node dispatched only after ALL dependencies done | Fan-in `node_dispatched` timestamp ≥ slowest dependency's `node_done` timestamp. No dispatch before last dep done. |
| 5 | **No premature dispatch / races** | Fan-in never fires on partial completion | If N-1 deps done at tick T, fan-in node must NOT appear at tick T. Check for a `SYNC` action event holding the node. |
| 6 | **Dead-branch skip** | Skipped node marked `skipped:true`, empty output, never dispatched | `node_skipped (dead branch)` event; `state` blob shows `{skipped: true, output: {}, iteration: 0}`; no `node_dispatched` for that node |
| 7 | **Schema enforcement timing** | Schema checked at node-done transition, before edge resolution | `node_failed` event (if violation) appears at done-time, not dispatch-time. Conforming nodes produce no error event. |
| 8 | **No false schema rejections** | Zero spurious validation failures | Query #5 returns zero rows for the instance. Every done node's output conforms to its declared schema. |
| 9 | **Tick count** | Reasonable for graph depth | Distinct timestamps (Query #4) ≈ longest path length + lag for slow workers. A diamond graph (fan-out + fan-in) needs ≥ depth + 1 ticks. |

## Common findings (from the version-C audit)

- **Fan-out is atomic within a tick:** all parallel children share the
  parent's done-tick timestamp. If you see staggered timestamps, fan-out is
  broken (serializing instead of parallelizing).
- **Fan-in is a strict AND-join:** the engine holds the fan-in node across
  ticks until the last dependency resolves. A `SYNC ready→running` action
  event mid-fan-in is normal — it means the engine re-evaluated and correctly
  held the node.
- **Dead-branch skip is a node-level state, not an edge-level event:** the
  skipped node gets `node_skipped` + a `skipped:true` flag in the state blob.
  It does NOT get a `node_dispatched` event.
- **The `state` JSON blob on `workflow_instances` is richer than
  `node_states`:** it carries `card_status`, `iteration`, `skipped`, and
  `worker_session_id`. Read both; the blob is the post-T4 source of truth.
- **Schema enforcement is silent on success:** there is no "schema OK" event.
  Compliance is verified by the absence of `node_failed` events and by
  checking the node output against the declared schema in the template JSON.

## Verifying schema enforcement via the engine's own validator

The DB-query audit (above) proves whether the engine *ran* schema validation
(event timeline). To prove whether a card's output *would actually pass*,
run the engine's real validator against the real schema. This is the
strongest possible verification: it uses the exact code path that runs in
production.

### When to use this

- Verifying that a specific completed card's metadata conforms to its
  declared schema (not just that the engine checked it).
- Proving schema enforcement is real (not cosmetic) by running a negative
  test: output from a pre-schema version must FAIL.
- Regression-testing a schema change before/after editing a template.

### The pattern

The validator lives in `kanban_adapter.py`, not `runtime.py`. Importing
`runtime` directly fails with a relative-import error because it uses
package-relative imports (`from .model import ...`).

```python
import sqlite3, json, sys
sys.path.insert(0, '<path-to>/scripts/workflow_engine')
from kanban_adapter import validate_against_schema

# 1. Load actual card metadata from the board DB
conn = sqlite3.connect('<path>/kanban/boards/<board>/kanban.db')
row = conn.execute(
    "SELECT metadata FROM task_runs WHERE task_id='<card_id>' ORDER BY id DESC LIMIT 1"
).fetchone()
conn.close()
metadata = json.loads(row[0])

# 2. Load the schema from the template JSON
tpl = json.load(open('<path>/templates/<template>.json'))
node = next(n for n in tpl['nodes'] if n['id'] == '<node-id>')
schema = node['output']['schema']

# 3. Run the real validator
valid, err = validate_against_schema(metadata, schema)
print(f'valid={valid}  err={err}')

# 4. NEGATIVE TEST: run a card that should FAIL through the same schema
#    (e.g. a pre-schema-version card missing the required arrays)
#    This proves the gate actually rejects non-compliant output.
```

### What to check

- **Top-level required fields:** `set(schema['required']) - set(metadata.keys())`
- **Nested item required fields:** for each item in `verdicts[]` or
  `checks[]`, check `set(item_schema['required']) - set(item.keys())`.
  The engine validates nested objects, not just top-level keys.
- **Evidence quality (not enforced by schema):** `evidence` and `reason` are
  free-text strings — the schema enforces *presence* but not *quality*.
  Check length and content manually if evidence depth matters.

### Pitfall: `runtime.py` relative import

```python
from runtime import validate_against_schema  # FAILS: relative import
```

`runtime.py` starts with `from .model import (...)`, so it can only be
imported as part of the package. The validator function
`validate_against_schema` is duplicated in `kanban_adapter.py` which has no
relative imports — import from there instead. The canonical home may move;
if `kanban_adapter` import fails, `grep -rn "def validate_against_schema"
<scripts/workflow_engine/>` finds the current location.

## Pitfalls

- **Don't filter events by node_id alone.** Workflow-level events
  (`workflow_completed`) have `node_id=NULL`. Filter by `instance_id`.
- **Don't trust `node_states.status` for skip detection.** A skipped node
  shows `status='pending'` in `node_states`; only the `state` blob carries
  the `skipped:true` flag. Always read the blob.
- **Event ordering is by `id`, not `timestamp` alone.** Events sharing a
  timestamp (same tick) have a deterministic insert order — sort by
  `timestamp ASC, id ASC` to reconstruct intra-tick sequence.
- **`engine_events.metadata` is usually NULL.** Only `command_run` populates
  it (with the command string). Don't rely on metadata for other event types.
- **Cross-instance pollution:** when auditing one run, the schema/error sweep
  (Query #5) should be global — a validation failure on a different instance
  can indicate an engine-level schema bug, not just a one-off.
- **`workflow_id` ≠ board — they are different namespaces.** The
  `workflow_id` is the template name (e.g. `qa-test-d`); the `board` is the
  target (e.g. `qa-ab-c`, `qa-ab-d`). Multiple instances of the SAME
  `workflow_id` can run against DIFFERENT boards. When a user says "compare C
  and D," they may mean boards (`qa-ab-c` vs `qa-ab-d`), not workflow_ids
  (`qa-test-c` vs `qa-test-d`). Always read the `board` column AND
  `trigger_context` (which carries `{board, card_id, assignee, verdict}`) —
  do not assume `workflow_id` encodes run identity. A `LIKE 'qa-test-d%'`
  filter can silently bundle together runs against different boards that
  happened to use the same template.
- **Historical failures may not be reproducible in the current DB.** The
  `workflow-state.db` reflects CURRENT state. If a baseline claim ("C had 2
  schema failures") returns zero rows, the failures were either (a) on a
  different template version whose instances were since reset/rotated, or (b)
  conflated with a same-named board that ran a different path (e.g. the
  `qa-ab-c` board took the skip branch and never reached schema-validated QA
  nodes). Cross-reference with per-board `kanban.db`
  (`~/.hermes-teams/startup/kanban/boards/<board>/kanban.db`, table `tasks`)
  for terminal card status, and with `references/qa-ab-test-results.md` for
  documented historical findings. State explicitly when a claim cannot be
  reproduced and why, rather than silently reporting "clean."
