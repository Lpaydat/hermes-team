# Builder Pipeline Analysis

> Source: `~/.hermes-teams/startup/profiles/builder/` — SOUL.md, config.yaml,
> skills (project-promotion, prototype-iteration, self-grill, grill-rpc-ops,
> venture-prototype, prototype-review-handoff, prototype-verification),
> cron/jobs.json, scripts (queue-builds.sh, pipeline-guard.sh, scan-guard.sh).

## The 6-stage workflow

```
Stage 1: DISCOVERY (cron, no agent)
  scan-guard.sh + scan-requesthunt.sh → signals/daily-scan.md

Stage 2: INTAKE (cron 4x/day, agent)
  pipeline-guard.sh → guard check
  Phase 1: ingest signals
  Phase 2: score /25
  Phase 3: write 13-section dossier
  Phase 3.5: fact-verify (delegate subagent)
  Phase 4: update portfolio + idea-bank

Stage 3: QUEUE (cron every 6h, zero-token script)
  queue-builds.sh:
    1. Read idea-bank.md, sort by score, skip built/grilling
    2. Top 10 (Door D ideas always first)
    3. For each: create TWO cards:
       Card A: "Grill: <name>" → builder (self-grill skill)
       Card B: "Build: <name>" → builder (venture-prototype skill)
         parent=Card A (waits for grill to complete)

Stage 4: GRILL (kanban card, builder session)
  Read dossier → draft venture brief → launch PO via grill-rpc
  PO asks questions → builder answers as FOUNDER
  20+ Q&A per branch, 3-5 locked decisions per branch
  Output: ~/projects/<slug>/context/<branch>.md files

Stage 5: BUILD (kanban card, builder session)
  Read grill decisions → POC gate → pick prototype type
  loop_engine (2 phases): build + README, each with verify gate
  Write review handoff (portfolio entry + kanban comment)

Stage 6: USER REVIEW (interactive — human)
  Triage: EXECUTION (rebuild) | DESIGN (re-grill) | NEW IDEA | PROMOTE | SHELVE
  Promote → project-promotion skill → dispatch to PO (NOT tech-lead)
```

## Engine feature mapping

| Builder stage | Current mechanism | Engine feature | Template shape |
|---------------|------------------|----------------|----------------|
| Stage 1 (discovery) | Cron script (scan-guard.sh) | `type: "command"` node | Runs scan, captures signals |
| Stage 2 (intake) | Cron + agent prompt | `type: "task"` node (builder profile) | Agent runs scoring + dossier + verify |
| Stage 3 (queue) | Cron script (queue-builds.sh) | `type: "foreach"` over scored ideas | Creates grill+build card pairs via `card_mode: "chain"` |
| Stage 4 (grill) | Kanban card (builder, self-grill skill) | `type: "task"` node (stays as skill) | Skill behavior, not orchestration |
| Stage 5 (build) | Kanban card (builder, venture-prototype skill) | `type: "task"` node (stays as skill) | Skill behavior, not orchestration |
| Stage 6 (review) | Interactive human | NOT templatable | Human gate |

## Key observations

1. **Stages 1-3 are orchestration** — cron scripts that create cards. These are
   direct engine migration targets: `command` nodes for scripts, `foreach` for
   queue, `chain` mode for grill+build pairs.

2. **Stages 4-5 are agent behavior** — skills that run inside cards. These stay
   as skills. The engine creates the cards; the skills define what happens inside.

3. **The grill→build parent-child dependency** is exactly what `card_mode: "chain"`
   models: create a parent card (grill) and a child card (build) linked via
   `--parent`. The child auto-promotes when the parent completes.

4. **queue-builds.sh is the clearest migration target**: it reads a data source,
   sorts, and creates kanban cards with parent-child links. That's a `foreach`
   node with `card_mode: "chain"` and a `command` node to read the idea-bank.
