# Workflow Engine — Design Decisions

## Terminology

**Call it "workflow engine", NOT "graph engine".** The engine orchestrates workflows — tasks, conditions, routing. "Graph engine" implies graph algorithms (pathfinding, centrality). Different thing.

## Scheduling split

**Hermes cron owns scheduling. The engine owns orchestration.** We built and then removed a `scheduled` trigger source and `schedule` node type because Hermes cron already does scheduling. The engine has: `card_completed`, `bead_ready`, and `manual` triggers only. Hermes cron calls `main.py start <workflow-id>` to trigger a scheduled workflow.

The `wait` node type IS kept — it polls a condition string each tick. That's workflow logic, not scheduling.

## Templates format

**JSON, not YAML.** Machine-generated, JSON Schema validated.

## State storage

**Kanban-only (no beads in engine scope).** Bead-sync is data sync between two stores — not a workflow. It stays as imperative code.

## Node types (4)

| Type | What it does | Creates cards? |
|------|-------------|----------------|
| `task` | Creates kanban card for an agent profile | Yes |
| `command` | Runs shell command synchronously, zero tokens. stdout parsed as JSON if possible. | No |
| `subworkflow` | Starts child workflow, blocks until done | No (child creates its own) |
| `wait` | Polls a condition string each tick until true | No |

## Foreach modes (3)

`foreach` can be combined with any node type:

| Combination | Behavior |
|-------------|----------|
| `foreach` (task) | Creates N kanban cards, **waits for ALL** before advancing. Barrier. |
| `foreach + command` | Runs command per item, no cards. Zero tokens. |
| `foreach + subworkflow` | Spawns N **independent** child workflow instances. No barrier — each runs its own pipeline. |

**Critical:** foreach on task nodes is a BARRIER. All N cards must complete before the next node dispatches. Use `foreach + subworkflow` when items should flow independently through a multi-node pipeline (e.g., grill→build→handoff per idea).

## Terminal card statuses

Both `"done"` and `"archived"` are treated as terminal by the engine. A node whose card is archived will complete (not hang forever). This handles manual cleanup, GC, and user-removed cards.

## title_template

Works on ALL node types, not just foreach. Set `title_template` on any task node to control the card title:

```json
{"id": "grill", "title_template": "Grill: ${trigger.name}", ...}
```

For foreach: `"Grill: ${item.name}"`. Without it, defaults to `[node.id] skill` or `[node#idx] skill` for foreach.

## Trigger sources (3)

| Source | What it does |
|--------|-------------|
| `card_completed` | Card matches condition (assignee, title_prefix, metadata) |
| `bead_ready` | bd ready matches type/label |
| `manual` | CLI start (Hermes cron calls `main.py start <id>`) |

## Edge semantics

- **Unconditional edges (no condition field): AND** — ALL sources must be DONE (dependency convergence)
- **Conditional edges (has condition field): OR** — ANY source DONE + condition passes activates (conditional diamond routing)
- **Edges from SKIPPED/FAILED sources are ignored**
- **Activation rule: all unconditional done AND (conditional ok OR no conditional edges)**

## Foreach + title_template

Foreach nodes can have `title_template` for custom card titles: `"Grill: ${item.name}"`. Without it, defaults to `[node#idx] skill`. Dot-path resolution supports `${item.slug}` when item is a dict.

## Logging

`engine_events` SQLite table: timestamp, level, event_type, instance_id, workflow_id, node_id, board, card_id, message, metadata. CLI: `main.py log --instance X --type Y --level Z --limit N`.

## Self-trigger prevention

Engine-created cards (idempotency_key `wf:...`) from workflows with explicit edges are blocked from triggering OTHER workflows. Same-workflow cards are always blocked. Cross-workflow cards from workflows WITHOUT explicit edges still fire (backward compat).

## Command node security

All variable values are shlex-quoted before substitution into command strings. Prevents shell injection via card metadata.

## Kanban concurrency config

The dispatcher reads `max_in_progress` and `max_in_progress_per_profile` from the **global** `startup/config.yaml`, NOT from the per-profile `config.yaml`. If you change per-profile config, the global overrides it.

- `max_in_progress` — global cap across ALL profiles on the board
- `max_in_progress_per_profile` — cap per individual profile (tighter constraint)

Requires gateway restart to take effect. Kill the gateway process and start a new one.

## Engine location

Shared infrastructure at `~/.hermes-teams/startup/scripts/workflow_engine/`. NOT inside any profile directory. All profiles can use it. The cron wrapper lives in the PO profile's `scripts/` dir (`wf-engine-tick.py`).

## Related reference: runtime execution model

This file documents the WHAT (node types, trigger sources, design decisions).
For the HOW — the exact tick-loop phase ordering, the guard rails in their
fixed state, the StateDB schema, and the completion-verification logic — see
`references/runtime-execution-model.md`. That's the mental model you need
when debugging or extending the engine.

## Related reference: orchestration vs choreography

For architecture-level guidance on WHEN to use explicit edges (orchestration)
vs `card_completed` triggers (choreography) vs `subworkflow` nodes (child
workflows) — with industry mapping to Camunda, Temporal, Airflow, Saga, and
multi-agent frameworks — see `references/orchestration-vs-choreography.md`.
That's the decision framework you need when choosing routing mechanisms for a
new pipeline template.
