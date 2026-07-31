# Workflow Engine — Design Decisions

## Terminology

**Call it "workflow engine", NOT "graph engine".** The engine orchestrates workflows — tasks, conditions, routing. "Graph engine" implies graph algorithms (pathfinding, centrality). Different thing.

## Scheduling split

**Hermes cron owns scheduling. The engine owns orchestration.** We built and then removed a `scheduled` trigger source and `schedule` node type because Hermes cron already does scheduling. The engine has: `card_completed`, `bead_ready`, and `manual` triggers only. Hermes cron calls `main.py start <workflow-id>` to trigger a scheduled workflow.

## Templates format

**JSON, not YAML.** Machine-generated, JSON Schema validated.

## State storage

**Kanban-only (no beads in engine scope).** Bead-sync is data sync between two stores — not a workflow. It stays as imperative code.

## Node types

| Type | What it does |
|------|-------------|
| `task` | Creates a kanban card for an agent (default) |
| `command` | Runs a shell command synchronously, zero tokens. stdout parsed as JSON if possible. |
| `subworkflow` | Starts a child workflow, blocks until done |
| `wait` | Polls a condition each tick until it passes |

## Edge semantics

- **Unconditional edges (no condition field): AND** — ALL sources must be DONE (dependency convergence)
- **Conditional edges (has condition field): OR** — ANY source DONE + condition passes activates (conditional diamond routing)
- **Edges from SKIPPED/FAILED sources are ignored**

## Foreach + title_template

Foreach nodes can have `title_template` for custom card titles: `"Grill: ${item.name}"`. Without it, defaults to `[node#idx] skill`. Dot-path resolution supports `${item.slug}` when item is a dict.
