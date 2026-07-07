# Workflow Engine — Combined Cron Script (Jul 2026)

## What It Is

A single Python script (`scripts/workflow-engine.py`) that replaces three separate
cron jobs. Runs every 1 minute as a `no_agent=True` cron. Zero tokens, zero LLM calls.

## Why Combined

Three separate crons (auto-dispatch.sh, bead-sync.py, board-scanner.py) had an
ordering problem: bead-sync might close a bead (promoting a dependent) AFTER
auto-dispatch already ran that tick — the dependent wouldn't dispatch until the
NEXT tick (1 min delay). Combining them into one script guarantees correct
ordering within a single tick.

## Execution Order (critical)

```
Phase 1: bead-sync    — sync kanban card status → bd bead status
                         Closes done beads → may promote dependents via bd ready
Phase 2: auto-dispatch — check bd ready → create tech-lead cards
                         Picks up newly-promoted dependents immediately (same tick)
Phase 3: board-scanner — detect blocked tasks → escalate to proper profile
                         Catches any new blocks created by the above phases
```

## Deployment

```python
cronjob(
    action='create',
    no_agent=True,
    script='workflow-engine.py',
    schedule='* * * * *',
    deliver='local',
    name='Dev Workflow Engine — bead-sync + dispatch + scanner'
)
```

## What Was Removed

| Old cron | Schedule | Old script | Status |
|---|---|---|---|
| Beads Dispatch | 1m | auto-dispatch.sh | Removed (now Phase 2) |
| Bead-Sync | 1m | bead-sync.py | Removed (now Phase 1) |
| Board Scanner v2 | 3m | board-scanner.py | Removed (now Phase 3) |
| Tripwire | 1m | tripwire.py | Removed (workflow proven, no longer needed) |

All four old scripts deleted from `scripts/` directory.

## Design Rules

1. **One cron, one script** — when scripts have ordering dependencies, combine them
2. **Silent when idle** — script outputs nothing when there's no work (cron stays quiet)
3. **Never crash the cron** — every phase wrapped in try/except, errors logged as actions
4. **No LLM** — `no_agent=True`, pure Python + subprocess to `hermes kanban` CLI + `bd` CLI
5. **`deliver=local`** — never use Discord/Telegram for dev workflow crons (was broken for weeks)

## Cron Hygiene Rules (enforced Jul 2026)

- **active-projects.json gate**: ALL cron scripts that scan projects MUST read
  `active-projects.json` first. Empty list → `{"wakeAgent": false}` → zero tokens.
  No `find ~ -name .beads` — that scans real projects without permission.
- **No Discord delivery**: all product-owner crons use `deliver=local`. Discord was
  broken (401 Unauthorized) for weeks. Weekly Sprint Report writes to
  `reports/sprint-{YYYY-MM-DD}.md` instead.
- **Check ALL profiles for duplicates**: ghost crons on other profiles silently fail.
  Always run `hermes cron list --profile <each-profile>` when deploying.
- **Deepseek fallback removed from ALL configs**: global config + all 6 profile configs.
  `fallback_model: []` everywhere — no silent model switches.
