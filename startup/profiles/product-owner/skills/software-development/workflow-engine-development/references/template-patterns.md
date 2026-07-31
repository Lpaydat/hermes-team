# Workflow Template Patterns

Reusable JSON template patterns distilled from the builder pipeline migration.
Each pattern is a concrete shape that appears across multiple real templates.

## Pattern: cron-wrapped manual trigger + command guard + conditional task

For replacing cron jobs that have a guard script + an agent prompt. Hermes cron
owns scheduling; the engine template uses a manual trigger and is started by a
cron job that calls `main.py start <workflow-id>`.

```json
{
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

No `trigger` field → manual trigger (started via CLI). A Hermes cron job wraps
`main.py start builder-signal-scan` on the desired schedule. The guard command
runs zero-token. Its stdout is captured and available as
`${nodes.guard.output.stdout}`. The conditional task only fires when the guard
output contains the right signal.

**Templates using this:** `builder-signal-scan.json`, `builder-idea-intake.json`.

## Pattern: zero-token pure command cron replacement

For cron scripts that don't need an agent at all (sorting, file manipulation,
kanban card creation). No trigger field — manual start wrapped by Hermes cron.

```json
{
  "nodes": [
    {"id": "queue", "type": "command",
     "command": "bash ~/.hermes-teams/.../queue-builds.sh --board ${trigger.board}"}
  ]
}
```

No agent, no tokens. The Hermes cron job calls `main.py start builder-queue-builds`
on schedule. The command runs, the workflow completes. If the script creates
kanban cards, those cards are picked up by the dispatcher independently.

**Templates using this:** `builder-queue-builds.json`.

## Pattern: command parse → chain dispatch (card creation from data)

For pipelines that read a data source, transform it, and create structured
kanban card pairs. A command node outputs JSON, a chain-mode task node creates
parent + child cards from that JSON.

```json
{
  "nodes": [
    {"id": "parse_data", "type": "command", "profile": "builder",
     "command": "python3 ~/.../parse-script.py --board ${trigger.board}"},
    {"id": "dispatch", "card_mode": "chain", "profile": "builder", "skill": "...",
     "body_template": "${nodes.parse_data.output.stdout}",
     "depends_on": ["parse_data"]}
  ],
  "edges": [{"from": "parse_data", "to": "dispatch"}]
}
```

The command node parses a file (idea-bank, config, CSV), sorts/filters, and
outputs a JSON list of child card specs: `[{"title": "...", "assignee": "...",
"body": "..."}, ...]`. The chain node parses this JSON from stdout, creates a
parent card, then creates each child linked via `--parent`. This replaces bash
scripts that call `hermes kanban create` in loops.

**Key insight:** the chain node's `body_template` references
`${nodes.parse_data.output.stdout}` — the command node's raw stdout is stored
in the output dict and available to downstream nodes.

**Templates using this:** `builder-queue-builds.json` (proposed Path C design).

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
| `builder-signal-scan.json` | manual (cron-wrapped, every 3h) | guard→scan | scan-guard.sh cron |
| `builder-idea-intake.json` | manual (cron-wrapped, 4x/day) | guard→intake | pipeline-guard.sh cron |
| `builder-queue-builds.json` | manual (cron-wrapped, every 6h) | queue (command) or parse→chain | queue-builds.sh cron |
| `builder-grill-build.json` | card_completed (Grill:) | grill→build→wait→handoff | queue-builds.sh card creation |
| `builder-promote.json` | card_completed (verdict=promote) | setup→git→board→dispatch PO | project-promotion skill |

## Trigger context variables available in templates

When a trigger fires, these variables are available via `${trigger.*}`:

- `card_completed`: `trigger.card_id`, `trigger.card_title`, `trigger.board`, and all card completion metadata (flattened into trigger context)
- `bead_ready`: `trigger.bead_id`, `trigger.bead_type`, `trigger.bead_label`
- `manual`: whatever the caller passes via `--var key=value`

**Note:** `scheduled` trigger source was removed — Hermes cron owns scheduling.
For scheduled workflows, omit the `trigger` field (manual) and let a Hermes
cron job call `main.py start <workflow-id>`.

These are substituted in `body_template` and `command` strings at dispatch time.
