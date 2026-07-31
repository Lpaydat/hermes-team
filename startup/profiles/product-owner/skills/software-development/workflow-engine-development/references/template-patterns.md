# Workflow Template Patterns

Reusable JSON template patterns distilled from the builder pipeline migration.
Each pattern is a concrete shape that appears across multiple real templates.

## Pattern: scheduled trigger + command guard + conditional task

For replacing cron jobs that have a guard script + an agent prompt.

```json
{
  "trigger": {"source": "scheduled", "condition": {"schedule": "30 */3 * * *"}},
  "nodes": [
    {"id": "guard", "type": "command",
     "command": "bash ~/.hermes-teams/.../guard.sh"},
    {"id": "work", "profile": "builder", "skill": "...",
     "body_template": "...",
     "condition": "${nodes.guard.output.stdout} contains 'DUE'"}
  ],
  "edges": [{"from": "guard", "to": "work"}]
}
```

The guard command runs zero-token. Its stdout is captured and available as
`${nodes.guard.output.stdout}`. The conditional task only fires when the guard
output contains the right signal. This replaces the cron's "guard prints
STATUS:DUE, agent reads it and decides" pattern with a structural condition.

**Templates using this:** `builder-signal-scan.json`, `builder-idea-intake.json`.

## Pattern: zero-token pure command cron replacement

For cron scripts that don't need an agent at all (sorting, file manipulation,
kanban card creation).

```json
{
  "trigger": {"source": "scheduled", "condition": {"schedule": "0 */6 * * *"}},
  "nodes": [
    {"id": "queue", "type": "command",
     "command": "bash ~/.hermes-teams/.../queue-builds.sh --board ${trigger.board}"}
  ]
}
```

No agent, no tokens. The scheduled trigger fires, the command runs, the
workflow completes. If the script creates kanban cards, those cards are picked
up by the dispatcher independently.

**Templates using this:** `builder-queue-builds.json`.

## Pattern: card_completed trigger with title_prefix matching

For workflows that fire when a specific card type completes. Use
`title_prefix` to match cards by title convention.

```json
{
  "trigger": {
    "source": "card_completed",
    "condition": {"assignee": "builder", "title_prefix": "Grill:"}
  }
}
```

This fires when ANY builder card whose title starts with "Grill:" completes.
The trigger context includes `trigger.card_id`, `trigger.card_title`. For
slug extraction, the template body can parse the title or use a separate
command node.

**Templates using this:** `builder-grill-build.json`.

## Pattern: command chain for setup → dispatch

For promotion/deployment workflows where mechanical steps (mkdir, git init,
board creation) precede an agent task.

```json
{
  "nodes": [
    {"id": "setup", "type": "command", "command": "mkdir -p ~/projects/${trigger.slug}/.context && ..."},
    {"id": "init_git", "type": "command", "command": "cd ~/projects/${trigger.slug} && git init && git add -A && git commit -m 'promote'", "depends_on": ["setup"]},
    {"id": "create_board", "type": "command", "command": "hermes kanban create --board ${trigger.slug}", "depends_on": ["init_git"]},
    {"id": "dispatch", "profile": "product-owner", "skill": "project-promotion", "body_template": "...", "depends_on": ["create_board"]}
  ],
  "edges": [
    {"from": "setup", "to": "init_git"},
    {"from": "init_git", "to": "create_board"},
    {"from": "create_board", "to": "dispatch"}
  ]
}
```

All mechanical steps run zero-token. Only the final dispatch creates a kanban
card for an agent. Each command can fail independently (non-zero exit → FAILED
→ downstream blocked).

**Templates using this:** `builder-promote.json`.

## Pattern: wait node as promotion gate

For workflows that need to wait for a condition before proceeding, without
polling via command or blocking on a card.

```json
{
  "id": "gate",
  "type": "wait",
  "wait_condition": "${nodes.build.output.prototype_built} == 'True'",
  "depends_on": ["build"]
}
```

The wait node polls each tick. When the condition passes, it marks DONE and
the downstream nodes advance. Use this for "wait until X is confirmed done"
checkpoints that don't map to a card completion.

**Templates using this:** `builder-grill-build.json` (waits for build confirmation).

## Existing builder templates

Located at `~/.hermes-teams/startup/scripts/workflow_engine/templates/`:

| Template | Trigger | Nodes | Replaces |
|----------|---------|-------|----------|
| `builder-signal-scan.json` | scheduled (every 3h) | guard→scan | scan-guard.sh cron |
| `builder-idea-intake.json` | scheduled (4x/day) | guard→intake | pipeline-guard.sh cron |
| `builder-queue-builds.json` | scheduled (every 6h) | queue (command) | queue-builds.sh cron |
| `builder-grill-build.json` | card_completed (Grill:) | grill→build→wait→handoff | queue-builds.sh card creation |
| `builder-promote.json` | card_completed (verdict=promote) | setup→git→board→dispatch PO | project-promotion skill |

## Trigger context variables available in templates

When a trigger fires, these variables are available via `${trigger.*}`:

- `card_completed`: `trigger.card_id`, `trigger.card_title`, `trigger.board`
- `scheduled`: `trigger.scheduled_at` (epoch)
- `bead_ready`: `trigger.bead_id`, `trigger.bead_type`, `trigger.bead_label`
- `manual`: whatever the caller passes via `--var key=value`

These are substituted in `body_template` and `command` strings at dispatch time.
