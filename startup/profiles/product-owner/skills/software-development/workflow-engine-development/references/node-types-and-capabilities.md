# Node Types and Engine Capabilities (current)

> Updated 2026-08-01 after command/wait/foreach enhancements.

## Node types

| Type | What it does | Tokens | Cards? |
|------|-------------|--------|--------|
| `task` | Creates kanban card for an agent profile | Agent | Yes |
| `command` | Runs shell command synchronously | Zero | No |
| `subworkflow` | Starts child workflow, blocks until done | Agent (child) | Yes (child nodes) |
| `wait` | Polls a condition each tick until true | Zero | No |

### command node

Runs `subprocess.run(cmd, shell=True)` with 300s timeout. Variable values
are `shlex.quote`d to prevent injection. stdout parsed as JSON if possible,
merged into node output. Exit 0 = DONE, non-zero = FAILED. Context rebuilt
after completion so downstream nodes in the same tick see output.

**Foreach command**: `type="command"` + `foreach` runs the command per item
without creating kanban cards. Each iteration gets `${item}` and
`${item_index}`. Results aggregated as `{results: [...]}`.

### wait node

Polls a `wait_condition` string each tick. Uses same condition format as
`node.condition`. Stays PENDING until condition evaluates true, then DONE.
Does not create cards. Empty condition fires immediately.

## Foreach modes (3)

`foreach` can be combined with node types:

| Combination | Behavior | Barrier? |
|-------------|----------|----------|
| `foreach` (task) | Creates N kanban cards, waits for ALL before advancing | YES — barrier |
| `foreach + command` | Runs command per item, no cards. Zero tokens | N/A (synchronous) |
| `foreach + subworkflow` | Spawns N independent child workflow instances | NO — each flows independently |

**Critical:** foreach on task nodes is a BARRIER. Use `foreach + subworkflow`
when items should flow independently through a multi-node pipeline.
See `references/foreach-enhancements.md` for the full pattern.

### foreach enhancements

- `title_template` field on Node: custom card titles (`"Grill: ${item.name}"`)
- Dot-path resolution in `resolve_template()`: `${item.slug}` resolves
  `value["slug"]` when item is a dict
- Falls back to `[node#idx]` when no title_template
- Without dot-path: `${item}` renders the whole dict as a string
- `title_template` works on ALL task nodes (not just foreach) — set it
  on any task node to control the card title

## Trigger sources

| Source | What fires it |
|--------|--------------|
| `card_completed` | Card matches condition (assignee, title_prefix, metadata fields) |
| `bead_ready` | `bd ready` returns beads matching type/label filter |
| `manual` | CLI `main.py start <template>` or Hermes cron calling it |

**No `scheduled` trigger.** Scheduling stays in Hermes cron. The engine had
a `scheduled` trigger source and `schedule` node type — both removed because
Hermes cron already owns scheduling. Two cron systems = unnecessary complexity.

## Key fields on Node

```python
type: str = "task"       # "task" | "subworkflow" | "command" | "wait"
command: str = ""        # for command: shell command (supports ${} vars)
wait_condition: str = "" # for wait: condition to poll each tick
title_template: str = "" # custom title for foreach cards
foreach: str | None      # iterate over a list
workflow_ref: str = ""   # for subworkflow: child template ID
card_mode: str = "template"  # "template" | "delegate" | "chain"
condition: str | None    # node-level condition (skip if false)
```

## Edge semantics

Unconditional edges (no `condition` field) = AND (all sources must be DONE).
Conditional edges (has `condition`) = OR (any condition passes).
See `references/and-or-edge-semantics.md` for the full analysis.
