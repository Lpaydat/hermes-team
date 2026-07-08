# Per-Project Board Architecture

## Model

One kanban board per project. All profiles work across all boards (n-to-n). The dispatcher injects `HERMES_KANBAN_BOARD` into each worker's env, so agents never need to specify `--board` explicitly.

- `team` board: cross-project ops (workflow engine, hygiene scans, sprint reports)
- `<project>` board: all work for that project (PO dispatch, tech-lead, dev, verifier, escalation)

## Project Registry

`~/.hermes-teams/startup/active-projects.json` — shared across all profiles.

```json
{
  "active_projects": [
    {"name": "PIR", "path": "/home/lpaydat/workspace/pir", "board": "pir"}
  ],
  "paused_projects": [],
  "schema": {"fields": ["name", "path", "board"]}
}
```

Empty `active_projects` array = workflow engine exits silently (zero tokens, zero scanning).

## Adding a Project

1. Create the board:
   ```bash
   hermes kanban boards create <slug>
   ```

2. Add to registry:
   ```json
   {"name": "<Name>", "path": "<absolute-path>", "board": "<slug>"}
   ```

3. The workflow engine picks it up on the next tick (1 min). No restart needed.

## Board Resolution

No `--board` flag anywhere in skills or scripts. The kanban CLI resolves the board from `$HERMES_KANBAN_BOARD`, which the dispatcher sets when claiming a task. This means:
- PO gets a card on board X → creates tech-lead cards on board X
- Tech-lead gets a card on board X → creates dev/verifier cards on board X
- Scanner detects a blocked task on board X → creates escalation card on board X

Everything stays on the same board. No cross-board coordination.

## Dispatcher

The gateway dispatcher already iterates ALL boards on disk per tick (60s default). New boards are discovered automatically — no restart, no config change. Workers are scoped via:
- `HERMES_KANBAN_BOARD`
- `HERMES_KANBAN_DB`
- `HERMES_KANBAN_WORKSPACES_ROOT`

## Workflow Engine

Reads `active-projects.json`, loops through each project:
1. Bead-sync: sync card status → bd bead status (per board)
2. Dispatch: `bd ready` → create PO dispatch card (per board)
3. Scanner: detect blocked tasks → escalate (per board)

## Multi-Board Parallel — PROVEN (Jul 2026)

Two projects on two boards ran the full pipeline (PO dispatch → tech-lead → `kanban_delegate` → dev → verifier → merge) simultaneously with zero cross-board leakage:

- `startup-internal` board: throttle function — all roles completed, code merged ✅
- `multi-board-test` board: debounce function — all roles completed, fix chain caught delay=0 edge case, code merged ✅
- `team` board: zero dev/dispatch task leakage ✅

The dispatcher's `HERMES_KANBAN_BOARD` injection correctly scoped every worker. No `--board` flag needed anywhere.
