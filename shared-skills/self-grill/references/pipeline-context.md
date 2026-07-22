# Pipeline Context

The builder's automated pipeline (cron-driven) feeds ideas into the grill. This reference documents the pipeline architecture for context when running grills.

## Entry: 3 Doors

- **Door A — Problem:** Reddit/HN complaints (pain-driven)
- **Door B — Opportunity:** tech launches, API releases, regulatory shifts (shift-driven)
- **Door C — Copycat:** Product Hunt, revenue reports, app rankings (success-driven)

## Downstream phases

```
PHASE 1: INGEST SIGNALS  — capture raw signals tagged by door
PHASE 2: SCORE           — score /25 with evidence, origin modifiers (copycat +1 market-proven)
PHASE 3: BUILD DOSSIERS  — full venture analysis per idea using template
PHASE 3.5: FACT-VERIFY   — independent subagent checks every claim
PHASE 4: GRILL           — REQUIRED: self-grill, builder answers PO as founder
PHASE 5: RANK AND PICK   — sort by score, take top 10 unbuilt
PHASE 6: QUEUE BUILDS    — kanban tasks chained SEQUENTIALLY (one at a time)
PHASE 7: REVIEW QUEUE    — move completed builds to "Awaiting Review"
```

## Artifacts

| Artifact | Path | Purpose |
|----------|------|---------|
| Signal buffer | `~/vault/ventures/signals/daily-scan.md` | Raw signals tagged by door |
| Dossiers | `~/vault/ventures/ideas/<slug>.md` | Full 13-section venture analysis |
| Verification reports | `~/vault/ventures/ideas/<slug>-verification.md` | Independent fact-check per dossier |
| Dossier template | `~/vault/ventures/templates/idea-dossier-template.md` | Template for new dossiers |
| Verification template | `~/vault/ventures/templates/fact-verification-template.md` | Template for verification reports |
| Idea bank | `~/vault/ventures/idea-bank.md` | Lightweight index linking to dossiers |
| Portfolio | `~/vault/ventures/portfolio.md` | Status tracker (Awaiting Review at top) |
| Specs | `~/vault/ventures/specs/` | Written specs for spec'd ventures |

## Cron jobs

1. **Daily Discovery Scan** (every 3h, guarded once/day) — 3-door scan
2. **RequestHunt Weekly** (Mon/Wed/Fri) — multi-platform deep scan
3. **Pipeline + Build Cycle** (4x/day, 3-day cooldown) — full pipeline

Full cron prompts: `cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -m json.tool`
