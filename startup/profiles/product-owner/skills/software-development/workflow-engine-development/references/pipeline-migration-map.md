# Pipeline Migration Map — 8-Profile Team Diagnosis

> Generated 2026-07-31 from 8 parallel subagent diagnoses (3,735 lines of analysis).
> Source: all SOUL.md, config.yaml, skills, and old cron across all profiles.

## The Pipeline at a Glance

```
User → PO → Architect (design) → PO (tickets) → Tech-Lead (plan)
  → Developer (code) ↔ Verifier (review/merge)
  → QA (test running artifact)
  → Debugger (bugs: reproduce → fix → falsify → converge)
```

## Profile Roles Summary

| Profile | Role | Writes Code? | Trigger | Key Output |
|---------|------|-------------|---------|------------|
| product-owner | Single front door — owns WHAT | No | User, cron dispatch, beads | PRD, beads, dispatch cards, gates |
| architect | Design partner + gatekeeper | No | PO design card | Design doc, ADRs, T0-T3 triage |
| tech-lead | Autonomous planner — owns HOW | No | PO dispatch card, beads | Contracts, dev+verifier cards, merges |
| developer | Code generator via harness | Yes | Tech-lead card via kanban_chains | Commits, tests, structured metadata |
| verifier | Adversarial reviewer + merge gate | No | Tech-lead card via kanban_chains | Verdict (PASS/FAIL/ESCALATE), merge |
| debugger | Diagnosis orchestrator | No | QA bug beads, verifier ambiguous FAIL | Root cause, post-mortem, fix dispatch |
| qa | Last gate — test running artifact | No | Verifier PASS + merge | Test results, bug beads, verdict |
| ops | Platform + environment manager | No | Cron | System health, backups |
| scout | Breadth-first research scanner | No | Cron 8x/day | Research items for researcher |

## Handoffs (9 total)

1. **PO → Architect**: design card + PRD → design doc + ADRs
2. **PO → Tech-Lead**: `[auto]` dispatch card via dev-dispatch → tech-lead reads bead, creates dev+verifier cards
3. **Tech-Lead → Developer**: kanban_chains coding card → commit + metadata
4. **Tech-Lead → Verifier**: kanban_chains review card → verdict + merge
5. **Verifier → QA** (on PASS): card_completed trigger → QA test report + bugs
6. **Verifier → Developer** (on FAIL): fix card → fixed code
7. **QA → Debugger** (bugs found): bd create --type=bug → beads → auto-routed
8. **Debugger → Developer** (fix): loop_engine converge → fixed code
9. **Debugger → Verifier** (re-verify): verifier card → verdict

## Escalation Chain

```
developer  → tech-lead
verifier   → tech-lead
debugger   → tech-lead
qa         → tech-lead
tech-lead  → product-owner    ← terminal automated node
product-owner → HUMAN_REQUIRED (no higher profile)
```

## Cron Phases and Migration Status

| Phase | What it does | Migrated? |
|-------|-------------|-----------|
| qa-trigger | Verifier PASS → QA card | **YES** (qa-loop.json) |
| bead-sync | kanban status → bd status | No |
| dispatch | bd ready → PO dispatch card | No |
| human-escal | human beads → HQ card | No |
| scanner | blocked → escalate | No |

## Ready-to-Migrate Tasks (priority order)

1. **Bug routing** — `card_completed` trigger when QA files bugs (type=bug)
2. **Bead dispatch** — `bead_ready` trigger when beads become ready
3. **Scanner escalation** — blocked card detection + escalation chain
4. **Human escalation** — human-flagged beads → HQ card
5. **Bead sync** — dedicated sync tick (not workflow)

## Stays Manual (Human Gate)

- Gate decisions (architect approval)
- Dispatch approval (user must approve before dispatch)
- Promotion handoff (prototype → production)

## Dynamic Workflows (Profile-Managed)

- **Tech-lead**: `kanban_chains` for parent→children dev+verifier. Parent goes `blocked`.
- **Debugger**: `loop_engine` converge (reproduce→fix→falsify→converge). Parent stays `blocked`.
- **QA**: `kanban_chains` for medium/large sessions (fan-out + synthesizer).
- Engine watches only parent card status. Internal trees are invisible.

## Builder Workflow (Complete Pipeline)

The builder is a self-contained venture pipeline that mirrors the production
pipeline for prototype work. Understanding it is essential for writing engine
templates that cover the full team.

```
STAGE 1: DISCOVERY (cron-driven)
  Demand Signal Scan (every 3h) → signals/daily-scan.md
  RequestHunt Deep Scan (M/W/F 5am) → signals

STAGE 2: IDEA INTAKE (cron 4x/day, agent-driven)
  pipeline-guard.sh → skip if <3 days
  Phase 1: INGEST signals
  Phase 2: SCORE /25 (Pain, Freq, WTP, Comp, WhyNow)
  Phase 3: DOSSIER — full 13-section writeup
  Phase 3.5: VERIFY — delegate fact-check subagent
  Phase 4: UPDATE portfolio.md + idea-bank.md

STAGE 3: QUEUE BUILDS (cron every 6h, zero-token script)
  queue-builds.sh:
    1. Read idea-bank.md, sort by score
    2. Top 10 (Door D always first)
    3. For each: create TWO kanban cards
       Card A: "Grill: <name>" → builder (self-grill with PO via RPC)
       Card B: "Build: <name>" → builder, parent=Card A (chain mode)

STAGE 4: GRILL (kanban card, builder session)
  Grill: <name> card
    1. Read dossier from ~/vault/ventures/ideas/<slug>.md
    2. Draft venture brief (3 pillars: Problem, Core Idea, Core Features)
    3. Launch PO via grill-rpc (env -u HERMES_KANBAN_* — critical isolation)
    4. PO identifies design categories → builder creates branches dynamically
    5. Grill each branch: 20+ Q&A, 3-5 locked decisions per branch
    6. Validate: bash validate-grill-output.sh
  OUTPUT: ~/projects/<slug>/context/ (per-branch decision files)
  COMPLETES → child Build card auto-promotes via parent-child dependency

STAGE 5: BUILD (kanban card, builder session)
  Build: <name> card
    1. Read grill decisions from ~/projects/<slug>/context/
    2. POC GATE: test riskiest assumption (technical risk → POC first)
    3. Pick prototype type (HTML demo / API+dashboard)
    4. Write verify script at /tmp/verify-<slug>.py
    5. loop_engine (2 phases: build prototype, write README — each with verify gate)
    6. Write review handoff (portfolio.md "Awaiting Review" + kanban comment)
  OUTPUT: ~/projects/<slug>/prototype/ + ~/projects/<slug>/README.md

STAGE 6: USER REVIEW (interactive — human reviews prototype)
  User reviews → 5 feedback paths (triaged by prototype-iteration skill):
    EXECUTION → "Fix X" → rebuild directly (no grill)
    DESIGN → "Wrong audience" → re-grill specific change → rebuild
    NEW IDEA → "Different product" → Door D intake → full pipeline
    PROMOTE → "Ship it" → project-promotion → dispatch to PO (NOT tech-lead)
    SHELVE → "Not now" → mark in portfolio.md
```

**Engine migration candidates from builder:**
- `queue-builds.sh` → `foreach` node iterating over scored ideas, creating grill+build card pairs via `card_mode: "chain"`
- The grill→build parent-child dependency → explicit edge with no condition (sequential)
- `project-promotion` dispatch → trigger (user "Ship it") or edge to PO

**Key constraint:** the builder's grill session launches PO as a subagent via
file-based RPC (`env -u HERMES_KANBAN_*`). This is NOT the same as the engine
dispatching a card to PO — it's a synchronous RPC within a single builder card.
The engine should NOT try to model this as two nodes; it stays inside one
builder card (the engine sees `blocked` while the grill runs).

## Migration Planning Lesson: Prescribe, Don't Describe

When the user asks you to diagnose the pipeline for migration, **the goal is to
write the replacement templates, not describe what exists.** The user's
frustration when 11 subagents produced descriptive output:

> *what a waste. what you inform subagents to research? why all of them got only so fucking shit result?*

**The wrong question:** "Read all profile files and describe what each profile does."
This produced 3,735 lines of analysis concluding "4 profiles need zero migration
because they just receive cards." That's describing the problem, not solving it.

**The right question:** "Write the full dev-pipeline.json that replaces the old
cron end-to-end. Output working templates, not analysis."

The "receives cards" conclusion is backwards — **the engine exists to CREATE the
cards those profiles receive.** Every "receives cards" profile IS a migration
target. The user caught this instantly.
