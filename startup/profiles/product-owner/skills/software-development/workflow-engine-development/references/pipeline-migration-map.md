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

## Key Design Constraints

1. One PO dispatch card at a time — needs guard
2. Bug routing bypasses PO — goes directly to debugger
3. Wayfinder routing by label — different labels → different profiles
4. Sequential dispatch — beads process one at a time
5. Merge serialization — verifier holds merge slot
