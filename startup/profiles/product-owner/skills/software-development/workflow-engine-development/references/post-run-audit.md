# Post-Run Workflow Audit — SQL Recipes & Engine State Quirks

How to verify a workflow run after execution by querying the engine's SQLite
state directly. Use when asked "did the routing work?", "were there errors?",
"did node X fire / get skipped correctly?", or after an A/B test of the engine.

## The two databases

| DB | Path | What it holds |
|----|------|--------------|
| **Workflow state DB** (central) | `~/.hermes-teams/startup/kanban/workflow-state.db` | `workflow_instances`, `node_states`, `engine_events`, `trigger_keys` — engine-level execution state across ALL boards. |
| **Board DB** (per-board) | `~/.hermes-teams/startup/kanban/boards/<board>/kanban.db` | The actual kanban tasks, task_events, task_comments for that one board. |

> **Pitfall:** The central `~/.hermes-teams/startup/kanban/kanban.db` does NOT
> contain per-board tasks. To read a dispatched card's output you must open the
> board-specific DB. The `engine_events.workflow_id` and `node_id` columns tell
> you which board/card to look in.

## Step 1 — Find instances

```sql
-- workflow-state.db
SELECT instance_id, workflow_id, status
FROM workflow_instances
WHERE workflow_id = '<workflow_id>';
```

If multiple instances exist (common for A/B tests), identify the interesting
one via the event log (Step 2) — look for the `check-merge` / first-node output
that took the path you care about.

## Step 2 — Read the event log (AUTHORITATIVE)

```sql
-- workflow-state.db — chronological event log for one instance
SELECT timestamp, level, event_type, node_id, message
FROM engine_events
WHERE instance_id = '<instance_id>'
ORDER BY id;   -- use id, not timestamp, for stable ordering within a tick
```

Key event types to look for:

- `command_run` (DEBUG) — a shell command node executed.
- `node_done` — node completed; message includes `(command: {...})` or `(card <id>)`.
- `node_skipped` — dead-branch skip; message is `SKIPPED node <name> (dead branch)`.
- `node_dispatched` — a card-backed node was dispatched; message names the card id.
- `workflow_completed` — instance finished.

### `engine_events` vs `node_states.status` — authority gap

> **Critical quirk:** `node_states.status` is NOT always rewritten on a
> dead-branch skip. A skipped node can remain `pending` in `node_states` while
> the `engine_events` log correctly records `node_skipped ... (dead branch)`.
>
> **`engine_events` is authoritative** for routing/skip decisions.
> `node_states.status` is best-effort and can be stale. When verifying, always
> trust the event log, not the status column. Do NOT report a node as
> "stuck pending" based on `node_states` alone — check the event log first.

## Step 3 — Check for errors / validation failures

```sql
-- workflow-state.db — zero rows == clean run
SELECT level, event_type, node_id, message
FROM engine_events
WHERE instance_id = '<instance_id>'
  AND (level IN ('ERROR','WARNING','WARN')
       OR event_type LIKE '%validation%'
       OR event_type LIKE '%schema%'
       OR message LIKE '%schema%'
       OR message LIKE '%validation%'
       OR message LIKE '%invalid%');
```

## Step 4 — Read dispatched-card outputs

Card outputs (the worker's summary, sizing, verdict) are NOT in the `tasks.result`
column (frequently empty). They live in the **`completed` event payload** on the
board DB:

```sql
-- boards/<board>/kanban.db
SELECT kind, payload
FROM task_events
WHERE task_id = '<card_id>' AND kind = 'completed';
-- payload JSON includes: summary, result_len, verified_cards, etc.
```

To map an engine node → its card id, use the `node_dispatched` event message
(`DISPATCHED node <name> → card <id>`).

## Step 5 — Confirm the full node-state picture

```sql
-- workflow-state.db
SELECT node_id, status, output
FROM node_states
WHERE instance_id = '<instance_id>'
ORDER BY node_id;
```

Remember: cross-reference any `pending` rows against `engine_events` before
concluding a node is genuinely stuck (see authority-gap pitfall above).

## Verification checklist (for adaptive-routing runs)

When verifying that conditional routing, dead-branch propagation, and output
schemas all worked on a given instance:

1. **Entry node fired** — `node_done` for the trigger node (e.g. `check-merge`)
   with the expected output (e.g. `should_test: "true"`).
2. **Condition routed correctly** — `node_dispatched` for the expected next node;
   the alternate branch's first node shows `node_skipped (dead branch)`.
3. **Dead-branch propagation** — every downstream node on the non-taken branch
   shows `node_skipped (dead branch)` in the same tick.
4. **Card output schema valid** — the dispatched card reached `done`; no
   `validation` / `schema` / `invalid` events (Step 3 query returns nothing).
5. **Zero errors** — Step 3 query returns zero rows at ERROR/WARNING level.
6. **Card output content** — Step 4 query shows the worker summary with the
   expected computed value (e.g. `sizing: small`, `verdict: PASS`).
