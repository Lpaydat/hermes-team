# Workflow Engine State Management & Persistence

> Where does workflow execution state live? How does the engine resume after restart? How are variable bindings tracked across nodes? How does the engine know which instance a card belongs to?
>
> Sibling design docs in `crr-pos-v2/docs/`: `workflow-state-persistence-design.md` (full 10-section design), `workflow-node-io-schema.md` (node contracts), `workflow-composition-design.md` (subworkflow recursion), `workflow-engine-card-creation-design.md` (card creation modes).

## The three options analyzed

| Option | Mechanism | Verdict |
|--------|-----------|---------|
| **(1) Cards ARE the state** | Card status = node status; no separate store | ✗ Insufficient — no place for variable bindings, no instance identity on cards |
| **(2) Separate state table** | Dedicated DB tracks instances, nodes, bindings | ✅ Primary — but only as a re-derivable cache |
| **(3) Derived each tick** | Engine re-reads kanban+beads every cycle (current cron) | ✅ As the recovery model — but can't track bindings |

## Decision: Hybrid (2)+(3)

**The engine maintains a dedicated `workflow-state.db` (SQLite), but it is a CACHE, not the source of truth.**

| Concern | Where it lives | Why |
|---------|---------------|-----|
| Node execution status | **Kanban DB** (card status) | Ground truth — the dispatcher owns card lifecycle |
| Node output values | **`task_runs.metadata`** (on the kanban card) | Ground truth — the agent writes it at completion |
| Workflow instance metadata | **State DB** | Not derivable — instance IDs, trigger context, invocation chains |
| Node→instance→card mapping | **State DB** + kanban `idempotency_key` | Not derivable from card alone |
| Resolved variable bindings | **State DB** | A cache of `task_runs.metadata` — re-derivable if lost |

**Principle: the state DB is a denormalized index over facts that live in kanban. It can always be rebuilt.** This extends the current cron's crash-safe statelessness with a persistent cache for bindings.

## The `idempotency_key` link mechanism

Cards link to workflow instances via their `idempotency_key`:

```
wf:<instance_id>:<node_id>
```

Example: `wf:wi-a1b2c3d4:architect`

- Already indexed in kanban (`idx_tasks_idempotency`)
- Engine-controlled (the engine always sets the key from the node's template)
- Queries: forward (card → instance) and reverse (instance → all cards) via `LIKE 'wf:wi-abc:%'`
- Zero kanban schema changes needed

The kanban schema has forward-compat columns `workflow_template_id` and `current_step_key` (currently unused — verified 0 rows across all boards). These could store instance_id/node_id as a secondary link, but **`idempotency_key` is the primary mechanism** because it's already indexed and already the dedup surface.

## Variable bindings: how `${nodes.spec.output.spec_path}` resolves

1. At card completion, the engine reads `task_runs.metadata` (ground truth).
2. Validates against the node's output schema.
3. Extracts the `emit` keys and writes them to `node_states.outputs` (JSON column).
4. At dispatch of a downstream node, resolves `${nodes.<id>.output.<key>}` via a single PK lookup on `node_states`.

Expression roots: `${nodes.<id>.output.<key>}` (sibling node output), `${parent.<key>}` (instance inputs), `${trigger.<key>}` (trigger context), `${child.outputs.<key>}` (subworkflow return), `${env.<key>}`, `${instance.<key>}`.

## Restart and recovery

**The tick loop is stateless between ticks** — same as the current cron. Each tick re-reads card status from kanban and reconciles the state DB.

- **Mid-execution restart:** Cards keep running (dispatcher is independent). The engine catches up on the next tick — a restart only delays workflow advancement, never interrupts running work.
- **State DB corrupt/lost:** Rebuild from kanban. Find all `wf:`-prefixed idempotency keys → group by instance_id → reconstruct node_states from card statuses → extract outputs from `task_runs.metadata` for done cards.
- **The one gap:** `workflow_ref` (template ID) isn't recoverable from the card alone. Solution: write `[workflow:dev-pipeline@1.0.0]` footer into card body at creation, OR use the kanban `workflow_template_id` column if the kernel exposes it.

## The schema (distilled)

```sql
CREATE TABLE workflow_instances (
    instance_id        TEXT PRIMARY KEY,    -- wi-<uuid>
    workflow_ref       TEXT NOT NULL,       -- template ID
    status             TEXT NOT NULL DEFAULT 'running',
    parent_instance_id TEXT,                -- NULL = root
    root_instance_id   TEXT NOT NULL,
    invocation_chain   TEXT NOT NULL,       -- JSON array of workflow_refs
    depth              INTEGER NOT NULL DEFAULT 0,
    idempotency_key    TEXT,
    board              TEXT NOT NULL,
    project_dir        TEXT NOT NULL,
    inputs             TEXT,                -- JSON: frozen snapshot
    outputs            TEXT,                -- JSON: set on completion
    trigger_context    TEXT,                -- JSON
    created_at INTEGER, updated_at INTEGER, completed_at INTEGER
);

CREATE TABLE node_states (
    instance_id  TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    card_id      TEXT,
    outputs      TEXT,             -- JSON: validated binding cache
    error        TEXT,
    retries      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (instance_id, node_id)
);
```

Single DB at `~/.hermes-teams/startup/workflow-engine/workflow-state.db`. Not per-board (engine manages all boards; `board` column provides isolation). Single-writer (one engine process, one tick loop). SQLite WAL for crash consistency.

## Why not store state tables in the kanban DB?

The kanban DB is per-board and kernel-owned. Coupling engine tables to it ties the engine to the kernel's migration lifecycle and prevents cross-board queries. The engine's state is its own concern — keep it in its own DB. The link is `card_id` (state DB) ↔ `idempotency_key` (kanban DB).

## Migration from the current cron

`qa-trigger-state.json` (the sole out-of-band state file — `{board: last_sha}`) is absorbed into the state DB. The `{board: last_sha}` mapping becomes a field on the root `dev-pipeline` instance or a dedicated `engine_state` table. First run seeds from the JSON file.

Three phases: (1) shadow mode — state DB records the cron's actions without dispatching; (2) engine takes over dispatch — old cards adopted via existing `bead-<id>` / `qa-merge-<sha>` keys; (3) variable bindings go live for new workflow instances.
