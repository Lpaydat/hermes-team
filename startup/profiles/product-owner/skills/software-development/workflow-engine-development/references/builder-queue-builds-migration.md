# Builder Pipeline Migration — Final Pattern

## What was replaced

`queue-builds.sh` (293 lines bash): parsed idea-bank.md, filtered/sorted, created grill+build card pairs via `hermes kanban create --parent`.

## The 2-template solution (foreach + subworkflow)

**Parent (`builder-grill-build.json`):**
```
parse_idea_bank (command) → spawn_prototypes (foreach + subworkflow → builder-single)
```

**Child (`builder-single.json`):**
```
grill (task, self-grill) → build (task, venture-prototype) → handoff (task, prototype-review-handoff)
```

Each idea spawns its own independent child workflow. No barriers — grill(A) completing immediately dispatches build(A) while grill(B) is still running.

## Parse script (`parse-idea-bank.py`)

Python replacement for the awk/sed parsing. Reads idea-bank.md, filters statuses, sorts by score, dedupes against board, outputs JSON:
```json
{"ideas": [{"slug": "x", "name": "Y", "score": 18}, ...], "count": N}
```

Command node captures stdout, parses JSON, foreach iterates over `${nodes.parse_idea_bank.output.ideas}`.

## Item data flow

`_dispatch_foreach_subworkflow` injects item dict fields into child trigger context:
- `{"slug": "x", "name": "Y", "score": 18}` → child gets `trigger.slug`, `trigger.name`, `trigger.score`
- Child templates reference `${trigger.slug}`, `${trigger.name}` in body and title templates

## What stays as skills

Engine = orchestration (which cards, what order). Skills = behavior (what agent does inside a card):
- self-grill, venture-prototype, prototype-review-handoff

## Triggering

Hermes cron calls `main.py start builder-grill-build --board <board>`. Manual trigger. Schedule lives in Hermes cron, not the template.

## Livetest results (2026-08-01)

- 10 ideas parsed from real idea-bank.md
- 10 independent builder-single workflows spawned
- Each with custom titles: "Grill: LeadPilot — AI Local SMB Lead-Gen"
- Builder gateway processes grill cards (max 5 concurrent)
- When grill(A) completes, build(A) dispatches immediately

## What was tried and abandoned

1. **Single template with foreach barriers** — all 10 grills must complete before ANY build starts. Wrong for independent pipelines. User caught this: "I expect each prototype run in its workflow."
2. **Chain mode** — creates parent-child pairs but doesn't solve the barrier problem for multi-node pipelines.
3. **Two templates with card_completed trigger** — works but requires managing cross-workflow trigger context. Simpler to use foreach+subworkflow.
