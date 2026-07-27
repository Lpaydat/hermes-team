# Build-Queue Pipeline Architecture (updated 2026-07-23)

## What changed

Pipeline shifted from **kill-funnel** to **build-queue** (2026-07-22), then upgraded to **three-door model with full dossiers** (2026-07-23). Core shift: nothing is killed. Ideas are scored, ranked, built, and the human decides promotion.

### Old model (pre-2026-07-22)
```
Scan → Score → KILL weak ones → Deep-dive survivors → Spec → Build → Gate
```

### Build-queue model (2026-07-22)
```
Scan → Score → Rank pool → Pick top 10 → Write venture brief → Queue build (sequential) → Review queue
```

### Three-door model (current, 2026-07-23)
```
ENTRY (3 doors):
  Door A — Problem     → Reddit/HN complaints (pain-driven)
  Door B — Opportunity → tech launches, API releases, regulatory shifts (shift-driven)
  Door C — Copycat     → Product Hunt, revenue reports, app rankings (success-driven)

DOWNSTREAM (same for all):
  Score /25 (with origin modifiers) → Build full dossier → Rank → Pick top 10
  → Queue builds sequentially (kanban chain) → Move to review queue
```

## Three-door scoring modifiers

| Origin | Modifier | Rationale |
|--------|----------|-----------|
| Problem (A) | None | Standard scoring |
| Opportunity (B) | Weight WhyNow 2x | Pain is latent — the shift IS the thesis |
| Copycat (C) | +1 effective total | Market is proven by the original's revenue |
| Mashup (D) | Evaluate each parent | Emergent from combining ideas across doors/domains |

## Artifact map (updated 2026-07-23)

| Artifact | Path | Purpose |
|----------|------|---------|
| idea-bank.md | `~/vault/ventures/idea-bank.md` | Lightweight INDEX — slug, score, origin, status, link to dossier |
| ideas/ | `~/vault/ventures/ideas/<slug>.md` | Full 13-section dossier per idea (the single source of truth) |
| templates/ | `~/vault/ventures/templates/idea-dossier-template.md` | Dossier template (13 sections, origin field, copycat strategy) |
| briefs/ | `~/vault/ventures/briefs/<slug>.md` | Three-pillar venture brief (produced from dossier for grill/build) |
| portfolio.md | `~/vault/ventures/portfolio.md` | Status tracker. "Awaiting Review" at TOP. Build queue, grill status. |
| signals/ | `~/vault/ventures/signals/` | Raw signal data from 3-door daily scans |
| specs/ | `~/vault/ventures/specs/` | Written specs for promoted ventures |
| killed-ideas.md | `~/vault/ventures/killed-ideas.md` | Historical log (181 ideas). Kept for reference, no longer written to. |

## Dossier structure (13 sections)

Every scored idea MUST become a full dossier. NOT a one-liner. The dossier replaces the old thin idea-bank entries. Sections:

1. Origin (Problem/Opportunity/Copycat/Mashup + entry signal)
2. Problem & Pain Points (macro + enumerated micro moments with evidence)
3. Evidence & Signals (quote table with URLs, dates, engagement)
4. Competitive Landscape (competitor table with gaps)
5. Copycat & Cross-Domain Strategy (copy target, what to steal, cross-domain analog, mashup potential)
6. Scoring Rationale (each sub-score with evidence-based reasoning + origin modifier)
7. Core Idea (pitch + mechanism + why it beats existing)
8. Core Features (3-7, mapped to pain points)
9. User Stories (5-10, as-a/I want/so-that)
10. Market & Money (ICP size, price evidence, revenue model)
11. Why Now (enabling shift + window estimate)
12. Risks & Unknowns (riskiest assumption called out)
13. Source References (full URL list)

## Cron jobs

| Job | ID | Schedule | Purpose |
|-----|----|---------|---------| 
| Daily Discovery Scan | 9493ebf6c4e2 | Every 3h (guarded once/day) | 3-door scan: Problem (Reddit/HN), Opportunity (PH/GitHub/tech news), Copycat (PH/revenue/app store) |
| RequestHunt Weekly Deep Scan | a9b7d447f13e | Mon/Wed/Fri 05:00 | Multi-platform signal collection (currently broken — script path issue) |
| Pipeline + Build Cycle | 7872dbc93ab1 | 4x/day, 3-day cooldown | 3-door signals → score → build dossiers → rank → pick top 10 → queue sequential builds → move to review |

## Pipeline phase structure (current)

```
PHASE 1: INGEST SIGNALS  — read daily-scan.md, new signals tagged by door (A/B/C)
PHASE 2: SCORE           — score /25 with evidence-based rubric + origin modifiers
PHASE 3: BUILD DOSSIERS  — full 13-section venture analysis per idea
PHASE 4: RANK AND PICK   — sort by score, take top 10 unbuilt
PHASE 5: QUEUE BUILDS    — kanban tasks chained SEQUENTIALLY (one at a time)
PHASE 6: REVIEW QUEUE    — move completed builds to "Awaiting Review"
```

## Sequential build chain (Phase 5)

Builds run ONE AT A TIME via kanban dependency links:

```
LeadPilot (21/25) ──completes──> OSINT Desk (20/25) ──completes──> Bookkeeping (20/25) ──> ...
   ↑ READY NOW                         ↑ todo (waiting)                   ↑ todo (waiting)
```

Implementation:
1. Create N kanban tasks (assigned to tech-lead)
2. `kanban_link(parent=A, child=B)` — B waits for A
3. `kanban_link(parent=B, child=C)` — C waits for B
4. Only A is `ready` — dispatcher picks it up
5. When A completes → B auto-promotes to `ready`
6. Next pipeline cycle moves completed builds to "Awaiting Review"
7. Before creating new tasks: check board for existing queued tasks — don't duplicate

## Pipeline prompt location

`cronjob action='list'` only shows truncated previews. Full prompt:
```bash
cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -m json.tool
```

## Known issues

1. **RequestHunt cron broken** — error "Script not found" even though script exists on disk. Path resolution issue in no_agent mode. Low priority (supplementary signal source).
2. **Pipeline delivery invisible** — cron deliver='local' means output goes to a file, not to the user. User missed 2 completed products for 17 days. Delivery mechanism needs fixing (Telegram or similar) but user is "still deciding."
3. **Self-grill symlink quirk** — skill_manage write_file fails for support files under self-grill (symlinked from shared-skills). Use action=create to overwrite SKILL.md, or write directly to disk at ~/.hermes-teams/shared-skills/self-grill/references/.
