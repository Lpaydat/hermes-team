# Cron-to-Engine Migration Planning

> Distilled from a full 8-profile migration plan (2026-07-31). The source
> artifact is `MIGRATION-PLAN.md` in the engine package dir — 982 lines with
> exact JSON for 6 templates, per-profile classification, risk matrix, rollback.

## The Core Principle

```
SKILLS (stay)                        ENGINE TEMPLATES (move)
What an agent does INSIDE a card     Which cards get created, in what
(behavior, judgment, craft)          order, with what conditions
```

**The test:** If the logic decides *which card to create next* or *which profile
to wake*, it's engine orchestration. If the logic decides *how to do the work
once woken*, it's a skill.

**The exception:** Skills that call `kanban_create`/`kanban_chains` internally
(e.g., `dev-dispatch`, `qa-protocol`, `loop_engine`-driven skills) are doing
*profile-managed dynamic orchestration*. These stay as skills — the engine
handles them via the **static-dynamic coexistence pattern** (engine dispatches a
parent card; the profile creates children; the engine waits for `done`).

## Classification Method (apply to every task on every profile)

For each task, classify into exactly one:

| Class | Stays/Moves | Example |
|-------|-------------|---------|
| ✅ Engine template | Moves to engine | bead_ready → dispatch card |
| 🔄 Profile-managed | Stays in skill (dynamic) | kanban_chains dev+verifier inside loops-engineering |
| 📝 Agent skill | Stays as skill | project-kickoff, adversarial-review |
| ⚙️ Cron script | Stays as no_agent cron | healthcheck.sh, bead-sync |
| ❌ Cannot migrate | Stays (needs human judgment) | project-discovery, design decisions |

**Most profiles need ZERO engine migration.** In the 8-profile diagnosis, only
PO and QA had migratable tasks. Architect, developer, verifier, debugger,
tech-lead, ops, scout, researcher — all purely card-driven or profile-managed.

## Coexistence Safety (the key to low-risk migration)

The old cron and new engine run **simultaneously without conflict** because:

1. **Matching idempotency keys.** Templates must specify
   `idempotency_key_template: "bead-${trigger.bead_id}"` to match the old
   cron's key format. Without this, the engine uses `wf:<instance>:<node>`
   keys that don't match, causing duplicate cards during transition.

2. **Phase-by-phase disable.** Disable one cron phase at a time (comment out
   in `main()`). The engine template handles that phase. If it breaks,
   re-enable the cron phase — the idempotency keys prevent duplicates.

3. **30-day parallel run.** Keep both running. Only retire the old cron after
   30+ days of stable engine operation.

## Engine Enhancements Often Needed

When migrating cron logic to templates, these trigger/condition features are
commonly needed but may not exist yet:

- `not_labels` / `label_any` / `or_labels_contains` on `bead_ready` triggers
  (to exclude bugs from the feature-dispatch template, or match wayfinder labels)
- `task_blocked` trigger source (fires when a task transitions to `blocked`)
- `board` override on nodes (for cards that go to a different board, e.g. `hermes-hq`)
- Internal action nodes (SQL unblock, comment) that don't wake an agent
- `status_not` condition on `bead_ready` (filter closed beads)

If an enhancement is too complex (e.g., the blocked-escalation scanner with its
SQL queries for resolved-escalation detection), **keep it as a cron script** —
that's a valid permanent state, not a failure.

## Template Patterns for Common Migrations

### Pattern: bead_ready → single dispatch card

```json
{
  "trigger": {"source": "bead_ready", "condition": {"type": "feature", "not_labels": ["gt:slot"]}},
  "nodes": [{
    "id": "dispatch", "profile": "product-owner", "skill": "dev-dispatch",
    "body_template": "Ready bead: ${trigger.bead_id} — ${trigger.bead_title}. Run dev-dispatch.",
    "idempotency_key_template": "bead-${trigger.bead_id}"
  }]
}
```

### Pattern: bead_ready → conditional routing (multi-path)

```json
{
  "trigger": {"source": "bead_ready", "condition": {"label_any": ["wayfinder:research", "wayfinder:task"]}},
  "nodes": [
    {"id": "research", "profile": "scout", "condition": "${trigger.bead_label} == 'wayfinder:research'"},
    {"id": "task", "profile": "ops", "condition": "${trigger.bead_label} == 'wayfinder:task'"}
  ]
}
```

Only one node fires per trigger; the rest are SKIPPED (terminal state).

### Pattern: card_completed → downstream card

```json
{
  "trigger": {"source": "card_completed", "condition": {"assignee": "verifier", "metadata.verdict": "PASS"}},
  "nodes": [{"id": "qa", "profile": "qa", "skill": "live-testing"}]
}
```

## Risk Assessment Matrix

| Template type | Risk | Why | Rollback |
|---------------|------|-----|----------|
| Single-node card_completed | LOW | Well-defined trigger, one card | Re-enable cron phase |
| Single-node bead_ready (bug routing) | LOW | Simple trigger, idempotent | Same |
| Multi-node conditional routing | LOW-MED | Label matching needs engine support | Same |
| Core dispatch (pipeline entry) | MEDIUM | If broken, no new work enters | Same — keys prevent dupes |
| Blocked-task scanner | HIGH | Complex SQL, may need new trigger type | Keep as cron script |

## What NOT to Migrate

- **Bead-sync** — data synchronization, not card-creation orchestration. Keep as script.
- **System healthchecks** — system monitoring, not kanban orchestration. Keep as cron.
- **Interactive planning** (project-kickoff, dev-planning) — requires human dialogue.
- **Judgment-heavy scanning** (project-discovery) — too subjective for templates.
- **Profile-internal converge loops** (debug-loop, design-council) — `loop_engine` handles these.
