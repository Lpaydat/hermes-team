---
name: dev-dispatch
description: "Create tech-lead kanban cards for all bd ready beads. Use when you receive a kanban card from the workflow engine cron asking you to dispatch ready work."
---

# Dev Dispatch

The workflow engine cron detects `bd ready` beads and creates a kanban card for you. This skill runs when you work that card.

The leading word is _minimal_: the card you create carries only the bead ID and a pointer to the PRD — no contracts, no function signatures, no technical guidance. Tech-lead reads the bead and writes its own contract.

## Steps

### 1. Check what's ready

```bash
cd <project-dir>
bd ready --json
```

Filter out `gt:slot` beads — those are coordination primitives, not work.

**Completion criterion:** you have a list of ready bead IDs + titles, excluding `gt:slot`.

### 2. Create a _minimal_ card for each ready bead

Check for an existing card first — query SQLite directly (the JSON API does NOT expose `idempotency_key`):

```sql
SELECT 1 FROM tasks WHERE idempotency_key = 'bead-<bead-id>' AND status != 'archived' LIMIT 1;
```

If no card exists, create one:

```bash
hermes kanban --board startup create \
  "[auto] <bead-title>" \
  --assignee tech-lead \
  --body "## Your task

Bead: \`<bead-id>\` — <bead-title>

\`\`\`bash
cd <project-dir>
bd show <bead-id>
cat PRD.md
\`\`\`

Execute your loops-engineering doctrine. Close the bead with \`bd close <bead-id>\` when done." \
  --workspace "worktree:<project-dir>" \
  --branch "feature/<bead-id>" \
  --priority 30 \
  --idempotency-key "bead-<bead-id>" \
  --json
```

**Completion criterion:** every ready bead has either an existing non-archived card OR a newly created card.

### 3. Complete your card

Report what was dispatched in your card summary, then `kanban_complete`:

```
Dispatched N bead(s):
  ⚡ <bead-id> — <title> → card t_xxx
  ⊘ <bead-id> — <title> → already on board (skipped)
```

**Completion criterion:** all ready beads have tech-lead cards. Your own card is completed.

## Rules

- `--idempotency-key "bead-<bead-id>"` is the dedup — always include it.
- `--workspace worktree:<path>` gives each card its own `.worktrees/<task-id>/` — required for parallel execution.
- Never create dev/verifier cards — tech-lead does that via `kanban_delegate`.
- When the user has already given a clear instruction, execute it. Do not ask "want me to do X?" — they already told you to.
