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
