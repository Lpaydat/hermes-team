# Runtime Execution Model — how the tick loop actually flows

> Distilled from a full read of `runtime.py` (2055 lines). This is the mental
> model you need when debugging or extending the engine. For WHAT each node
> type does, see `node-types-and-capabilities.md`. For bugs found and fixed,
> see `engine-pitfalls.md` and `state-lifecycle-tests.md`.

## The tick loop (Engine.tick)

Guarded by a `threading.Lock` (in-process) + `fcntl.flock` on
`workflow-engine.lock` (cross-process). If either lock is held, the tick
is a no-op. All DB ops wrapped in try/except so transient errors don't crash.

**Exact phase ordering within a single tick:**

```
0. GC          — delete old trigger_keys, completed instances, stale watermarks
1. PHASE 1     — for each active instance: check DISPATCHED nodes for completion
1b. PHASE 1b   — for each active instance: regression-check DONE nodes
2. PHASE 2     — for each active instance: check PENDING nodes for dispatch
3. PHASE 3     — for each active instance: if all terminal → complete instance
4. TRIGGERS    — scan all boards for card completions matching workflow triggers
```

Instances are loaded ONCE at the start of PHASE 1 (`load_active_instances`).
Child instances spawned mid-tick (PHASE 2) won't dispatch their own nodes
until the NEXT tick. In tests, call `tick()` twice after child dispatch.

## Guard rails (all implemented — the bugs in state-lifecycle-tests are FIXED)

| Guard | Where | What it prevents |
|-------|-------|------------------|
| **Zombie guard** | `_check_instance` top | Instance with `completed_at` set but somehow reactivated → refuses to re-dispatch, re-marks completed |
| **Deleted-board guard** | `_check_instance` | Board DB missing → auto-completes instance (stops zombie cycling) |
| **Stale node filter** | `load_active_instances` + `_check_instance` | `node_ids` snapshotted at creation; node_states for removed nodes filtered on load AND on check |
| **Card regression** | PHASE 1b | DONE node whose card flipped back to todo/ready/running → WARNING logged (orphan reuse) |
| **Dangling card** | PHASE 1 | DISPATCHED node whose card vanished → WARNING, no crash |
| **Poison guard** | PHASE 1 completion | Card metadata failing `output.schema` → node = FAILED (not DONE), downstream never advances |
| **Completion verify** | PHASE 3 | All nodes terminal BUT a card not actually `done` on board → instance NOT completed |
| **Idempotency** | `_dispatch_node` + all foreach variants | Every card gets `wf:<instance>:<node>[:<idx>]` key; re-tick never duplicates |
| **Self-trigger block** | `_check_triggers` | Engine-created cards (`wf:` key) don't re-trigger same workflow; cross-workflow blocked if parent has explicit edges |

## StateDB schema (5 tables)

SQLite at `startup/kanban/workflow-state.db`, WAL mode, 30s busy timeout.

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `workflow_instances` | One row per running/completed workflow | instance_id (PK), workflow_id, board, project_dir, trigger_context (JSON), parent_instance_id, created_at, status ('active'/'completed'), completed_at, node_ids (JSON snapshot) |
| `node_states` | Per-node runtime state | (instance_id, node_id) PK, status, card_id, output (JSON) |
| `trigger_watermark` | Per-board watermark (currently unused for lookback — fixed 1h constant) | board (PK), last_ts |
| `trigger_keys` | Dedup: once a trigger fires for a card, never again | key (PK), created_at |
| `engine_events` | Append-only event log | id, timestamp, level, event_type, instance_id, workflow_id, node_id, board, card_id, message, metadata |

**Board is ground truth; state DB is a cache.** Read paths hit board SQLite
directly (fast). Write paths go through `hermes kanban` CLI subprocess.

## PHASE 1 — completion checking (DISPATCHED nodes)

Each node type has a different completion path:

- **Standard task**: `get_card(board, card_id)` → if `done`/`archived`:
  read metadata, validate against `output.schema`. Pass → DONE. Fail → FAILED.
- **Subworkflow**: check child instance `status == 'completed'` in state DB.
  On completion, map child outputs via `output_mapping` (or flatten all if none).
- **Foreach task**: check ALL cards (`_foreach_cards`). All done → aggregate
  results. Any blocked → wait. Dangling card → WARNING.
- **Foreach subworkflow**: check ALL child instances (`_foreach_instances`).
  All completed → aggregate. Still active → wait.

## PHASE 2 — dispatch checking (PENDING nodes)

Dependency resolution has two modes:

**Explicit edges** (when `workflow.edges` is non-empty):
- Find all edges pointing TO this node
- No incoming edges → entry node, always dispatchable
- Unconditional edges (no `condition`): ALL sources must be DONE (AND)
- Conditional edges (has `condition`): ANY source DONE + condition passes (OR)
- Edges from SKIPPED/FAILED sources are ignored
- All sources terminal but none activated → node SKIPPED

**Implicit** (fallback to `node.depends_on`):
- All deps must be DONE
- If `node.condition` fails → SKIPPED

Then: input schema validation (required inputs must resolve from context).
Then: dispatch by type (command/foreach/subworkflow/wait/task).

After a command or wait completes, `ctx` is rebuilt so downstream nodes in
the SAME tick see the output.

## PHASE 3 — instance completion

All nodes must be in a terminal state (DONE/FAILED/SKIPPED). Then every node
with a `card_id` is verified on the board — if any card is missing or not
`done`, the instance is NOT completed (prevents false completion from stale
state). Only when all cards verify does `complete_instance` fire.

## Trigger system

For each workflow with a `card_completed` trigger:
1. Find recently completed cards (1h lookback) on all boards
2. Skip engine-created cards per self-trigger rules (parse `wf:` idempotency key)
3. Match against condition: `assignee`, `status`, `metadata.*`, `title_prefix`,
   `title_not_prefix` (and `title_not_prefix2`, etc.)
4. Dedup via `trigger_keys` table (`trig:<wf_id>:<card_id>`)
5. Start new instance with trigger context (card_id, board, assignee, metadata)

**Atomicity caveat**: the trigger key is recorded in a SEPARATE connection
from instance creation. A crash between the two orphans the key (workflow
won't start, but key prevents future re-trigger). Low risk in practice.

## COALESCE UPSERT pattern (concurrent update safety)

`update_node_state` uses a COALESCE-based UPSERT so concurrent callers setting
different fields don't clobber each other. When `card_id` or `output` is None
(meaning "don't change"), COALESCE keeps the existing value. This prevents the
read-then-write lost-update problem.

## GC (runs every tick — cheap)

- Delete trigger_keys older than 7 days
- Delete completed instances (+ their node_states) older than 7 days
- Delete stale trigger_watermark entries

## For debugging

- **Event log**: `python3 main.py log --instance <id> --type node_failed --limit 20`
- **Active instances**: `python3 main.py list`
- **Render a workflow**: `python3 main.py render <workflow_id>` (mermaid graph)
- **State DB query**: connect to `workflow-state.db`, query `workflow_instances`
  + `node_states` + `engine_events` directly
