# Pipeline Context

The builder's pipeline architecture. Reference doc — not a process that runs. Matches PIPELINE-ARCHITECTURE.md (source of truth).

## Entry: 4 Doors

- **Door A — Problem:** Reddit/HN complaints (pain-driven)
- **Door B — Opportunity:** tech launches, API releases, regulatory shifts (shift-driven)
- **Door C — Copycat:** Product Hunt, revenue reports, app rankings (success-driven)
- **Door D — User:** Founder submits ideas to `~/vault/ventures/user-ideas.md`. PRIORITY — always in build list, first in queue, regardless of score. Flaws → blocked kanban card, never killed.

## Pipeline stages (split, independent)

```
STAGE 1 — AI PIPELINE (cron, no human)
  Scan 4 doors → Score /25 → Build 13-section dossier → Independent fact-verify
  → Verified dossiers land in idea-bank.md
  → Pipeline AI job ENDS here. No grill, no build.

STAGE 2 — QUEUE SCRIPT (cron, no AI)
  queue-builds.sh reads idea-bank.md → sorts by score → picks top 10
  → Creates kanban cards assigned to 'builder' (sequential chain via kanban_link)

STAGE 3 — BUILDER SESSIONS (background, separate context per card)
  Builder picks card → reads dossier → grills with PO → builds prototype
  → Drops in ~/vault/ventures/prototypes/<slug>/ → updates portfolio.md → completes card
  → No spec, no tickets, no epics (those are production artifacts)

STAGE 4 — INTERACTIVE REVIEW (user-driven)
  User reviews prototype → gives feedback to builder:
    "Fix X" → builder iterates (fast, fail fast)
    "Promote" → builder runs project-promotion → dispatches to PO
    "Shelve" → done

PRODUCTION (PO owns from here)
  PO reads dossier + spec + prototype from ~/projects/<slug>/
  PO creates: design goals, epics, milestones, beads tickets, dependencies
  PO controls tech-lead (implementation), verifier (review)
  PO owns STATUS.md
```

## Artifacts

| Artifact | Path | Stage |
|----------|------|-------|
| Raw signals | `~/vault/ventures/signals/daily-scan.md` | Scan |
| User ideas (Door D) | `~/vault/ventures/user-ideas.md` | Scan |
| Dossiers | `~/vault/ventures/ideas/<slug>.md` | Dossier |
| Verification reports | `~/vault/ventures/ideas/<slug>-verification.md` | Fact-verify |
| Dossier template | `~/vault/ventures/templates/idea-dossier-template.md` | Dossier |
| Verification template | `~/vault/ventures/templates/fact-verification-template.md` | Fact-verify |
| Idea bank (index) | `~/vault/ventures/idea-bank.md` | Score |
| Portfolio (status) | `~/vault/ventures/portfolio.md` | All |
| Prototypes | `~/vault/ventures/prototypes/<slug>/` | Build |
| Promoted projects | `~/projects/<slug>/` | Production |
| Architecture spec | `~/vault/ventures/PIPELINE-ARCHITECTURE.md` | Reference |

## Cron jobs

| Job | Type | Schedule | Script | What it does |
|-----|------|----------|--------|-------------|
| Daily Discovery Scan | AI | Every 3h (guarded once/day) | scan-guard.sh | 4-door scan → daily-scan.md |
| Pipeline + Build Cycle | AI | 4x/day (3-day cooldown) | pipeline-guard.sh | Score → Dossier → Fact-Verify ONLY |
| Queue Builds | Script | Every 6h | queue-builds.sh | Reads idea-bank, creates builder kanban cards for top 10 |
| RequestHunt Weekly | Script | Mon/Wed/Fri | scan-requesthunt.sh | Multi-platform deep scan |

Full cron prompts: `cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -m json.tool`
