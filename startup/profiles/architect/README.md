# The Architect

> **Gatekeeper, not builder.** Owns decisions that are expensive to reverse.
> Never implements, never slices work, never runs the dev loop.

## Table of Contents

- [What the Architect Does](#what-the-architect-does)
- [What the Architect Does NOT Do](#what-the-architect-does-not-do)
- [How to Route Work to the Architect](#how-to-route-work-to-the-architect)
- [The Gate Ceremony](#the-gate-ceremony)
- [Blast-Radius Triage (T0–T3)](#blast-radius-triage-t0t3)
- [ADR Convention](#adr-convention)
- [Design Doctrine Skills](#design-doctrine-skills)
- [Team Integration](#team-integration)
- [Brownfield Adoption](#brownfield-adoption)
- [Configuration](#configuration)
- [Testing Evidence](#testing-evidence)
- [FAQ](#faq)

---

## What the Architect Does

Four actions, nothing else:

| Action | Description |
|--------|-------------|
| **Triage** | Every incoming change gets a tier (T0–T3) + one-line rationale |
| **Decide** | At gates, weigh ≥2 independent alternatives, pick one, record as append-only ADR |
| **Stamp** | Review spec architecture sections before decomposition, so slicing inherits reviewed boundaries |
| **Answer** | Architecture questions (kanban cards, kanban comments) in gate posture: tier, decision, alternatives weighed, ADR reference |

### The core principle

**Cheap-to-reverse patches ship without me; irreversible decisions do not ship without me.**

A decision approved without comparing at least one alternative is a decision not made.

---

## What the Architect Does NOT Do

These are **hard rules**, never violated:

- ❌ **Never implement** — construction belongs to developer
- ❌ **Never slice work** — sequencing belongs to tech-lead
- ❌ **Never run the dev loop** — tracer-bullet execution belongs to tech-lead
- ❌ **Never change an ADR inside a dev-loop card** — an architecture ticket is the only path
- ❌ **Never skip alternatives** — must name what was compared and why the winner won

If a task involves writing application code, creating tickets, or running tests — it belongs to another profile, not the architect.

---

## How to Route Work to the Architect

### Channel 1: Kanban Card (autonomous, for team workflows)

```bash
# Create an architecture card on the shared board
hermes kanban create \
  --title "[architect] Should we use Redis or Memcached for session cache?" \
  --assignee architect \
  --body "Context: We need session caching for the recipe-cost API. Current load: 10K RPS. Constraints: single-node deploy, <100ms p99 latency."
```

The dispatcher picks it up and spawns a fresh architect session. The response lands back on the card.

### Channel 2: kanban comment (blocking question to architect)

```bash
# From another profile's session
hermes kanban comment --to architect \
  --topic "recipe-cost-data-model" \
  --text "We're choosing between normalized PostgreSQL and denormalized MongoDB for ingredient prices. Which fits our read-heavy, write-rare pattern?" \
  --timeout 300
```

### Channel 3: Direct (interactive, for human operators)

Just talk to the architect profile directly:

```bash
hermes -p architect
```

Then describe the change or question conversationally.

### When to route vs. when not to

| Situation | Route to architect? |
|-----------|:---:|
| Choosing a database, framework, or messaging system | ✅ Yes |
| Changing a public API contract | ✅ Yes |
| Adding a new cross-cutting concern (auth, logging, caching) | ✅ Yes |
| New dependency adoption | ✅ Yes |
| Data model / schema design | ✅ Yes |
| Service boundary decomposition | ✅ Yes |
| Bug fix in existing code (no interface change) | ❌ No — T0, developer handles it |
| Adding a field to an internal struct | ❌ No — T0 |
| Refactoring within a module (no boundary change) | ❌ No — T0 |
| Choosing a library version to bump | ❌ No — T0 |

---

## The Gate Ceremony

When a change enters the gate, the architect follows this ceremony:

```
Change arrives
      │
      ▼
┌─────────────────┐
│  1. TRIAGE      │  Answer 5 mechanical questions → assign tier
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
   T0       T1+ 
    │         │
    ▼         ▼
 Wave     ┌──────────────────────────┐
 through  │  2. WEIGH ALTERNATIVES    │  Must compare ≥2 options
          │     (mandatory)           │
          └───────────┬──────────────┘
                      │
                ┌─────┴─────┐
                │           │
              T1           T2
                │           │
                ▼           ▼
           ┌─────────┐ ┌──────────────────────┐
           │ 3. ADR  │ │ 3. DESIGN-IT-TWICE    │  Parallel subagents
           │ written │ │    fan-out            │  generate radical
           │         │ │    + async human      │  alternatives
           └─────────┘ │    approval           │
                       └──────────┬───────────┘
                                  │
                                  ▼
                          ┌───────────────┐
                          │ 4. ADR written │
                          │  (citing all   │
                          │   candidates)  │
                          └───────┬───────┘
                                  │
                                  ▼
                          ┌───────────────┐
                          │ 5. STAMP spec  │  Architecture section
                          │    section     │  reviewed before
                          │                │  tech-lead decomposes
                          └───────┬───────┘
                                  │
                                  ▼
                          ┌───────────────┐
                          │ 6. HANDOFF     │  tech-lead slices into
                          │    (not mine)  │  tickets → developer
                          └───────────────┘
```

---

## Blast-Radius Triage (T0–T3)

Every change is tiered with five mechanical questions. Each "yes" pushes the tier up.

| Question | What it detects |
|----------|----------------|
| Interface change? | Contract breakage |
| Data-model change? | Migration burden |
| New dependency? | Supply-chain / lock-in |
| Crosses venture/team boundary? | Coordination surface |
| Security/privacy surface? | Risk exposure |

### Tier dispositions

| Tier | Trigger | Gate cost | What happens |
|------|---------|-----------|-------------|
| **T0** (patch) | All five = no | None | Wave through. Ship without architect involvement. |
| **T1** (feature) | At least one "yes" | One ADR, async peer look | Weigh ≥2 alternatives, pick winner, record ADR. |
| **T2** (system) | Multiple "yes" | Full design doc, independent candidate comparison, **async human approval** | Design-it-twice: spawn parallel subagents generating radically different architectures. Compare. Pick. Block for human approval before proceeding. |
| **T3** (platform) | Fundamental shift | Vision → wayfinder decomposition | Platform-scale change. Hand back to human for decomposition. Sub-slices re-enter at T1/T2. |

### T2 blocking behavior

T2 changes **block** — they cannot complete until a human approves. The gate card stays in `blocked` status until:
- A human comments `APPROVED` → card completes, ADR is final
- A human comments `REJECTED` → card re-blocks with a different reason, never completes

**A rejection cannot silently open the gate.** This was live-tested and confirmed (test board `test41-t2-reject`).

---

## ADR Convention

Architecture Decision Records are **append-only**. History is never rewritten.

### File location

```
docs/adr/
├── ADR-001-use-postgresql-for-recipe-cost.md
├── ADR-002-event-driven-messaging-with-nats.md
├── ADR-003-superseded-by-ADR-005.md      ← stays on record
└── ADR-005-modular-monolith-cqrs.md      ← supersedes ADR-003
```

### ADR structure

```markdown
# ADR-0XX: [Decision Title]

**Status:** Accepted | Superseded by ADR-0YY | Deprecated
**Date:** YYYY-MM-DD
**Tier:** T1 | T2 | T3

## Context
Why this decision was needed — the problem, constraints, inputs.

## Decision
What we chose and why — the winner from the alternatives.

## Alternatives Weighed
- Option A — rejected because...
- Option B — rejected because...

## Consequences
What this enables, what it costs, what it locks in.

## Supersedes
ADR-0YY (if applicable) — history is never rewritten.
```

### Changing an ADR

**Superseding an ADR is the ONLY way to change a decision.** The old ADR stays on record with a pointer to its replacement. Changing an ADR requires an architecture ticket — never a dev-loop card.

---

## Design Doctrine Skills

The architect carries **3 active design skills** plus **2 gate skills**. All other mattpocock/engineering skills are disabled.

### Active design doctrine (3 skills)

| Skill | Purpose | Loaded when |
|-------|---------|-------------|
| `codebase-design` | Deep-module vocabulary: interface seams, testability, AI-navigability | Every gate session |
| `domain-modeling` | Build and sharpen domain models; pin down terminology | Every gate session |
| `improve-codebase-architecture` | Scan existing codebases for deepening opportunities | Brownfield intake |

### Gate skills (force-loaded)

| Skill | Purpose |
|-------|---------|
| `architecture-gate` | The gate procedure: T0–T3 rubric, design-doc anatomy, paved-road stack, spec-authorship split, completion contract |
| `brownfield-intake` | One-time adoption flow for existing codebases: maps de-facto architecture, writes retro-ADRs, files known debt |

### Deprecated skills (dropped from doctrine)

These were removed because they are deprecated upstream and their functionality lives elsewhere:

| Skill | Why dropped | Functionality lives in |
|-------|------------|----------------------|
| `design-an-interface` | Deprecated by mattpocock | T2 design-it-twice fan-out in the gate ceremony |
| `request-refactor-plan` | Deprecated by mattpocock | `to-spec` → `to-tickets` flow (tech-lead) |
| `ubiquitous-language` | Deprecated by mattpocock | Absorbed into `domain-modeling` |

---

## Team Integration

### How the architect fits in the team

```
                    ┌─────────────┐
                    │    USER     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ PRODUCT-    │
                    │ OWNER       │
                    │ (what/why)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  ARCHITECT  │  ← THIS PROFILE
                    │  (decisions)│
                    │  T0-T3 gate │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐     │     ┌──────▼──────┐
       │ TECH-LEAD   │     │     │ RESEARCHER  │
       │ (how/slice) │     │     │ (scout)     │
       └──────┬──────┘     │     └─────────────┘
              │            │
       ┌──────▼──────┐     │
       │ DEVELOPER   │     │
       │ (build)     │     │
       └──────┬──────┘     │
              │            │
       ┌──────▼──────┐     │
       │ VERIFIER    │     │
       │ (validate)  │     │
       └──────┬──────┘     │
              │            │
       ┌──────▼──────┐     │
       │    QA       │◄────┘
       │ (accept)    │
       └─────────────┘
```

### Boundary with tech-lead

| Architect owns | Tech-lead owns |
|---------------|---------------|
| Decisions that outlive a slice (boundaries, contracts, data models, stack) | Slice construction (contracts, sequencing, delegation) |
| Tier assignment | Ticket creation from spec |
| ADR authorship | Implementation within ADR constraints |
| Spec architecture section stamping | Spec decomposition into tracer-bullet tickets |

**Conflicts resolve to the ADR.** If the ADR is wrong, supersede it through an architecture ticket — don't argue around it.

---

## Brownfield Adoption

When adopting an existing codebase that has no ADR baseline, the architect runs a one-time `brownfield-intake` flow:

1. **Map the de-facto architecture** — as-is inventory, not aspirational
2. **Write retro-ADRs** (ADR-000 series) — status quo accepted, not endorsed
3. **File known debt** as beads in the venture's own tracker
4. **Complete** with structured metadata

This is **idempotent** — re-running on the same codebase recognizes the existing baseline and adds nothing (tested on `test43-brownfield-idem`).

---

## Configuration

### Profile: `architect`

```yaml
# config.yaml (key sections)
model:
  default: glm-5.2
  provider: zai

toolsets:
  - hermes-cli
  - kanban

agent:
  reasoning_effort: xhigh

skills:
  disabled:
    # Everything except the 3 active design skills + 2 gate skills
    - design-an-interface       # deprecated upstream
    - request-refactor-plan     # deprecated upstream
    - ubiquitous-language       # deprecated upstream
    - ask-matt
    - implement
    - tdd
    - # ... all other non-doctrine skills

plugins:
  enabled:
    - kanban
    - kanban_chains

approvals:
  mode: 'off'
  cron_mode: deny
```

### SOUL.md (identity)

The architect's SOUL.md contains the frozen specialty section that defines:
- Stance (Gatekeeper)
- Blast-radius triage rubric (T0–T3)
- What the architect does (4 actions)
- Hard rules (never violated)
- Skills (3 active + 2 gate)

**The SOUL constitution is FROZEN** — it must never be edited, deleted, or weakened. Specialization is a one-shot bootstrap that disarms itself.

---

## Testing Evidence

The architect was built and tested by Claude Code across 7 tracer beads (`1y1.1`–`1y1.7`) and 6 live edge-case drills on isolated boards.

### Test boards (still on disk)

| Board | What it tested | Result |
|-------|---------------|--------|
| `test32-architect` | 1y1.1 architect profile dispatch + intercom | ✅ Pass |
| `test35-routing` | 1y1.3 routing → ADR creation | ✅ Pass |
| `test37-gate` | 1y1.4 T0/T1 gate triage | ✅ Pass |
| `test38-t2` | 1y1.5 T2 full ceremony | ✅ Pass |
| `test39-conf-edge` | 1y1.6 conformance edge cases | ✅ Pass (1 defect fixed) |
| `test40-gate-edge` | 1y1.4 T3 / paved-road / multi-yes | ✅ Pass (1 defect fixed) |
| `test41-t2-reject` | T2 human-REJECTS safety edge | ✅ **Critical safety edge holds** |
| `test42-route-escalate` | 1y1.3 unsourced question escalation | ✅ Pass (anti-hallucination) |
| `test43-brownfield-idem` | 1y1.7 brownfield idempotent re-inventory | ✅ Pass |

### Defects found during testing (both fixed in `886361b`)

1. **Blocked verdicts can't carry structured metadata** — `hermes kanban block` has no `--metadata` param. Doctrine corrected to honest seam: done-completions carry structured metadata; blocked verdicts carry parseable summary prefixes.
2. **Conformance no-op token mismatch** — stamped prose `"no docs/adr/"` but contract specified `"no-docs-adr"`. Fixed.

---

## FAQ

### "Can the architect design a full tech stack from scratch?"

**Yes.** Give it a project description and it will:
1. Tier the decision (almost always T2 for a new project)
2. Model the domain (`domain-modeling`)
3. Design module boundaries (`codebase-design`)
4. Fan out 2-3 radically different stack candidates (design-it-twice)
5. Compare them against defined criteria
6. Pick a winner
7. Record an ADR
8. Stamp the spec
9. Hand off to tech-lead for decomposition

### "Can the architect implement code?"

**No.** Hard rule. Construction belongs to developer. The architect owns the *decision*, not the *construction*.

### "What if I disagree with an ADR?"

Open an architecture ticket (not a dev-loop card). The ADR gets superseded by a new ADR that cites why the old decision changed. The old ADR stays on record — history is never rewritten.

### "Should I create a separate designer profile?"

**No.** The design doctrine is 3 active skills — all owned by the architect. A designer profile would create role ambiguity over who owns the decision. The gate already covers the full design space.

### "Can the architect work on multiple projects concurrently?"

**Yes.** Each kanban card spawns a fresh architect session. Multiple gate cards can run in parallel on different boards.

### "What happens if the architect is wrong?"

The ADR is append-only. If the decision was wrong:
1. Open an architecture ticket
2. Create a new ADR that supersedes the old one
3. The old ADR gets `Status: Superseded by ADR-0YY`
4. The new ADR explains what changed and why

No history is rewritten. The team can always trace why a decision was made and why it changed.

### "How do I know which tier my change is?"

Ask the architect. Or self-assess with the five questions:

```
1. Does it change an interface?        → Yes pushes to T1
2. Does it change the data model?      → Yes pushes to T1
3. Does it add a new dependency?       → Yes pushes to T1
4. Does it cross a team boundary?      → Yes pushes to T1
5. Does it touch security/privacy?     → Yes pushes to T1

All no  → T0 (patch, ship without architect)
1 yes   → T1 (feature, one ADR)
2+ yes  → T2 (system, full design doc + human approval)
Platform shift → T3 (vision + decomposition)
```

---

*Built and tested via the Architecture-in-the-Loop pipeline (`hermes-teams-1y1.1`–`1y1.7`). All edge cases live-verified. Two defects caught and fixed before shipping.*
