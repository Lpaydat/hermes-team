# Design Phase — Proactive Architecture for New Projects

> v2 redesign (2026-07-11, simplified by operator). The architect enters
> at the design phase as a **design service PO calls**, not a co-author
> PO negotiates with. PO owns the full flow.
>
> When `architecture-gate` is unpinned, move this reference there —
> it is architect doctrine, not curator-administration doctrine.

## The corrected flow (operator's version)

```
User/VB ←grilling→ PO
                │
                ▼
         PO runs to-spec → product spec
                │
                ▼
         PO creates architect kanban card
         (card body = spec link + context summary + intercom topic)
                │
                ▼
         ARCHITECT picks up card
         ├── reads spec + context
         ├── runs design (kanban_chains fan-out — the design team)
         ├── intercoms PO when needs input (topic from card body)
         └── completes card with design doc + ADRs
                │
                ▼
         PO reads design output
                │
                ▼
         PO runs to-tickets (spec + design → slices, beads, dependencies)
                │
                ▼
         Normal workflow: tech-lead → developer → verifier → qa
```

**Key: PO owns the flow.** The architect is a design service PO calls.
No planning phase. No co-authoring. PO cuts tickets after design, same
as today, just with better input.

## What PO passes to the architect (card body)

The card body is **self-contained** — the architect can start working
without reading the full grilling transcript.

```yaml
title: "[design] <project> — technical design"
assignee: architect
body: |
  ## Spec
  docs/specs/<project>.md

  ## Context (from grilling user/VB)
  - <key finding 1>
  - <key finding 2>
  - <constraints discovered>

  ## Intercom topic
  <project-slug>-design

  ## Open technical questions (PO couldn't answer)
  - <question 1>
  - <question 2>
```

## How architect and PO communicate during design

### Intercom topic-based session targeting (NO session IDs needed)

Intercom computes a **deterministic session ID** from the topic:

```
session_id = intercom-{team}-{profile_A}-{profile_B}-{topic}-{hash8}
```

- `team` = `startup`
- `profile_A` and `profile_B` sorted alphabetically (direction-independent)
- `topic` = the string from the card body
- `hash8` = first 8 hex chars of MD5

**Same topic = same session = accumulated context.** The PO that
responds is the same PO with project context, even if PO's session
died and was respawned by the offline spawner.

**Always use qualified form** `startup/product-owner` — bare names can
route to the wrong team under the degraded identity issue.

### Two delivery paths

1. **Online** (PO has live session): message injected via `pre_llm_call`
   hook into PO's current session — full project context available.
2. **Offline** (PO no session): broker spawns PO session via
   `hermes -p product-owner chat -q "<msg>" -Q --pass-session-id` and
   **resumes the same session** on subsequent messages to same topic.

### When to use which channel

| Situation | Channel |
|-----------|---------|
| Handoff (brief → design) | Kanban card body |
| Design output (ADRs, design doc) | Kanban card completion metadata |
| "I'm blocked, need PO's input" | Intercom ask (blocking, topic-based) |
| FYI (design ready) | Intercom send (fire-and-forget) |
| Iterative Q&A during design | Intercom (topic = accumulated session) |
| Durable decision record | Kanban comment + ADR file |

### Example

```python
# Architect asks PO a blocking question during design
intercom ask(
    to="startup/product-owner",
    topic="recipe-cost-design",       # from card body
    text="Your brief says <$500/mo. Does that include the price API subscription?",
    timeout=300
)
```

## The design team fan-out (kanban_chains, NOT subagents)

**NEVER use `delegate_task` / subagents.** They are fragile:
background-only, unreliable self-reports, don't survive session
boundaries. Always use `kanban_chains` — durable board cards,
observable, each with its own workspace.

### Why kanban_chains over delegate_task

| kanban_chains | delegate_task |
|---------------|---------------|
| Durable board cards | Background-only, ephemeral |
| Observable by any profile | Black box until completion |
| Survives session disconnects | Lost if parent session closes |
| Dispatcher resumable | No resume |
| Verifiable from board state | Unreliable self-report |
| Real workspace per card | No workspace isolation |

### Fan-out scaling by tier

| Tier | Fan-out | Rationale |
|------|---------|-----------|
| T1 | Solo design (no fan-out) | Small blast radius, one pass suffices |
| T2 | Full 6-dimension fan-out | Wide blast radius, needs parallel depth |
| T3 | Fan-out + wayfinder decomposition | Platform-scale, needs decomposition first |

### T2 fan-out dimensions

| Dimension | Card focus | Output |
|-----------|------------|--------|
| Domain model | Entities, relationships, bounded contexts | Domain model doc |
| System architecture | Module boundaries, service decomposition | Architecture diagram + contracts |
| Data layer | Schema, storage strategy, migration plan | Data model + storage ADR |
| Infrastructure | Hosting, scaling, CI/CD, observability | Infra ADR |
| Security & risk | Auth model, threat surface, failure modes | Security ADR + risk register |
| API design | Public contracts, versioning, error model | API specification |

After all dimensions complete, a synthesis card merges them into a
unified design doc + ADR series, resolving cross-dimension conflicts.

## Skill ownership in v2

| Skill | Owner | Phase |
|-------|-------|-------|
| `to-spec` | PO | Ideation (brief) + after design (final spec merge) |
| `to-tickets` | PO | Decomposition (stays with PO — full context) |
| `grilling` | PO | Ideation |
| `codebase-design` | Architect | Design |
| `domain-modeling` | Architect | Design |
| `architecture-gate` | Architect | Design + incremental gate |

**`to-tickets` does NOT move to tech-lead.** PO has full context.

## What was removed from v1 (and why)

| v1 concept | Status | Why |
|------------|--------|-----|
| Co-authoring / planning phase | ❌ Removed | Operator: too complex, PO owns flow |
| `to-tickets` on tech-lead | ❌ Removed | PO has full context, should cut tickets |
| Reactive gate as primary function | → Secondary | Gate is for incremental changes only |
| Architecture sections written by PO | → Architect | PO isn't technical; architect owns design |

## Big-tech grounding

| Company | Pattern |
|---------|---------|
| Google | Design doc by TL/Sr Eng → peer review → implementation plan |
| Amazon | 6-pager by Sr Eng/Principal → senior review → decomposition |
| Meta | RFC by Staff Eng → peer review → task breakdown |
| Stripe | Design doc by Staff+ Eng → cross-team review → sequencing |

Consistent: design is authored by technical authority, reviewed, THEN
handed to planning. Not done by the product authority alone.
