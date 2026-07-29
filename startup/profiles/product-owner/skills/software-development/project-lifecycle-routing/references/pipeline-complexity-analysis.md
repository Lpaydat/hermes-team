# Pipeline Complexity Analysis — Beads + Kanban Dual System

When the user asks to simplify the pipeline, cut complexity, or evaluate
whether the dual system (beads + kanban) is worth it, use this analysis.
It was produced from a full audit of the real system (not theory) on
2026-07-29.

## User's standing principle

> The user HATES unnecessary complexity. Be ruthless about cutting it.
> If the dual system adds more overhead than value, say so.

This shapes the default posture for all pipeline design discussions:
prefer fewer moving parts. Argue for adding complexity only when the
value is concrete and the alternative is worse.

## Counted moving parts (14 total)

| # | Component | Role |
|---|-----------|------|
| 1 | Beads DB (`.beads/`, Dolt + JSONL) | Master plan: epics, deps, `bd ready` |
| 2 | Kanban boards (SQLite per-project) | Execution: dispatcher, worktrees, retries |
| 3 | `active-projects.json` | Registry mapping projects → boards (gatekeeper) |
| 4 | Workflow engine cron (537 LOC Python) | Every-minute poll. 4 phases |
| 5 | Bead-sync phase | Kanban card status → beads status |
| 6 | Dispatch phase | `bd ready` → PO card / direct route |
| 7 | Human-escalation phase | Human-flagged beads → HQ card |
| 8 | Scanner phase | Blocked cards → escalation chain |
| 9 | Idempotency keys (`bead-<id>`) | Cross-system dedup |
| 10 | Hygiene watchdog cron (4h) | Stale/orphan detection in beads |
| 11 | Weekly sprint report cron | Project health briefing |
| 12 | `dev-dispatch` skill | PO → tech-lead cards |
| 13 | Wayfinder routing (3 route tables) | Label-based specialist routing |
| 14 | `.pi/workflow-gates.json` | Threshold tracking (unused — nulls) |

## The three elimination scenarios

### (1) Kanban-only — eliminates 6/14

Keep: boards, dispatcher, scanner, weekly report.
Lose: dependency-driven dispatch readiness (`bd ready` = topological
sort), git-tracked version-controlled plan, the master-plan abstraction.

### (2) Beads-only — eliminates 7/14

Keep: beads DB, `bd` CLI, hygiene watchdog, weekly report.
Lose: **the execution runtime entirely**. Beads has no dispatcher, no
worktree allocation, no retry counters, no skill injection. `bd ready`
tells you what to do but nothing spawns the agent to do it.

### (3) Irreducible minimum with both — 6 parts (down from 14)

Keep: beads DB, kanban boards, one dispatch trigger (30-line cron, not
537), one sync mechanism (lifecycle hook, not polling), project
registry, weekly report (optional).

Cut: human-escalation phase, wayfinder routing, hygiene cron,
workflow-gates.json, scanner escalation chain, and shrink the engine.

## Is the workflow engine cron necessary?

**No — not in its current form.** It is a 537-line polling bridge that
exists because beads and kanban lack event hooks into each other.

| Cron function | Event-driven replacement |
|--------------|--------------------------|
| Dispatch (bead→card) | `bd` post-ready hook, or PO runs `bd ready` at session start |
| Sync (card→bead) | Kanban completion hook → `bd close <bead-id>` |
| Scanner | Kanban's built-in `blocked` + `needs_input` already surfaces to operator |
| Human escalation | `bd tag <id> human` creates HQ card at tag-time, not via poll |

## Verdict by scale

| Scale | Recommendation |
|-------|---------------|
| Single project, solo | **Kanban-only.** No need for dependency-graph master plan. Use parent/child for sequencing. |
| 6+ projects with agents | **Keep both, cut engine to ~50 lines.** Dual value is real at scale, but 537-line engine is over-engineered. |
| User hates complexity above all | **Kanban-only is the minimum viable system.** The cost of maintaining the bridge exceeds the value for small projects. |

## The irreducible truth

The dual system's sole unique value is **dependency-driven readiness**
(`bd ready` = topological sort of what can be worked on now). If you
don't need automated dependency resolution, you don't need beads.
Kanban parent/child links are sufficient for manual sequencing.

## Analysis technique (reusable)

When asked to evaluate any system's complexity:

1. **Count every moving part** from real files/config, not theory
2. **Scenario A-only** — what dies, what's lost
3. **Scenario B-only** — what dies, what's lost
4. **Irreducible minimum** — what cannot be cut if both stay
5. **Bridge necessity** — is the connecting mechanism a poll or an event?
6. **Verdict by scale** — small vs large project tradeoffs
