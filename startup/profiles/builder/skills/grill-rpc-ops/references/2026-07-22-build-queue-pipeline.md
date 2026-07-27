# Build-Queue Pipeline Architecture (2026-07-22)

## What changed

Pipeline shifted from **kill-funnel** to **build-queue**. Core shift: nothing is killed. Ideas are scored, ranked, built, and the human decides promotion.

### Old model (pre-2026-07-22)
```
Scan → Score → KILL weak ones → Deep-dive survivors → Spec → Build → Gate
```
- Builder killed ideas below threshold (15/25)
- Grill was mandatory before building
- SOUL.md: "NEVER write code without launching self-grill"
- killed-ideas.md was actively written to (400+ lines, 181 killed ideas)

### New model (current)
```
Scan → Score → Rank pool → Pick top 10 → Write venture brief → Queue build (sequential) → Review queue
```
- Nothing killed. All ideas live in idea-bank.md ranked by score
- Grill is optional (runs as interactive session to stress-test briefs)
- Human is the gate, not the grill
- Max 10 builds queued per pipeline cycle

## Artifact map

| Artifact | Path | Purpose |
|----------|------|---------|
| idea-bank.md | `~/vault/ventures/idea-bank.md` | Ranked pool of ALL scored ideas (nothing killed). Pipeline picks top 10 from here. |
| portfolio.md | `~/vault/ventures/portfolio.md` | Status tracker. "Awaiting Review" at TOP (can't miss it). Build queue, grill status, pipeline history. |
| briefs/ | `~/vault/ventures/briefs/<slug>.md` | Three-pillar venture brief per idea (Problem/Opportunity, Core Idea, Core Features). Produced by pipeline Phase 3. |
| specs/ | `~/vault/ventures/specs/` | Written specs for promoted ventures (kept from old model). |
| killed-ideas.md | `~/vault/ventures/killed-ideas.md` | Historical log (400+ lines, 181 ideas). Kept for reference, no longer written to. |
| signals/ | `~/vault/ventures/signals/` | Raw signal data from daily scans. |

## Cron jobs

| Job | ID | Schedule | Purpose |
|-----|----|---------|---------| 
| Daily Demand Signal Scan | 9493ebf6c4e2 | Every 3h (guarded once/day) | Scan Reddit/HN/PH, append raw signals to daily-scan.md |
| RequestHunt Weekly Deep Scan | a9b7d447f13e | Mon/Wed/Fri 05:00 | Multi-platform signal collection (currently broken — script path issue) |
| Pipeline + Build Cycle | 7872dbc93ab1 | 4x/day, 3-day cooldown | Score → Rank → Brief → Queue builds → Move to review |

## Sequential build chain (Phase 4)

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

## Pipeline prompt location

`cronjob action='list'` only shows truncated previews. Full prompt:
```bash
cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -m json.tool
```

## Known issues

1. **RequestHunt cron broken** — error "Script not found" even though script exists on disk. Likely path resolution issue in no_agent mode. Low priority (supplementary signal source).
2. **Idea bank entries are thin** — each idea is just a name + score + 80-char snippet. The original signal data (quotes, URLs) lives in daily-scan.md, disconnected. Venture briefs written from thin entries may hallucinate context. User flagged this as a concern (2026-07-22) but no fix implemented yet.
3. **Scoring done by builder in single pass** — no structured rubric, no independent review. Builder scores its own ideas, then decides what to build.
