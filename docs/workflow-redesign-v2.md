# Workflow Redesign: Architecture-in-the-Loop v2

> Refined from v1 (gatekeeper model). The architect is a proactive design
> partner called by PO, not a reactive gate downstream. No new profiles,
> no planning phase — just one clean insertion point between spec and
> tickets, using kanban for handoff and intercom for live collaboration.

## The Problem with v1

v1 positioned the architect as a **reactive gatekeeper** between map
completion and ticket creation:

1. **PO writes the entire spec alone** — including technical architecture
   sections — without technical expertise.
2. **The architect stamps after the fact** — the design is already done;
   the gate is just a yes/no, not a creative contribution.
3. **Tech-lead inherits a fait accompli** — can't challenge boundaries
   that were never technically reviewed, only decompose what's given.
4. **The design is single-threaded** — one non-technical agent makes all
   architecture decisions with no peer review or alternative exploration.

## The Refined Workflow (v2)

Simple, PO-owned, one insertion point:

```
User/VB ←grilling→ PO
                │
                ▼
         PO runs to-spec → product spec (problem, users, metrics, scope)
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

### What each profile does

| Profile | Phase 1: Ideation | Phase 2: Design | Phase 3: Decomposition | Phase 4: Execution |
|---------|-------------------|-----------------|------------------------|-------------------|
| **PO** | Grills user/VB. Runs `to-spec`. Creates architect card. | Answers architect questions via intercom. | Reads design output. Runs `to-tickets`. Creates beads + dependencies. Dispatches. | Monitors progress. |
| **Architect** | — | Picks up card. Runs design (kanban_chains fan-out). Intercoms PO. Completes card with design doc + ADRs. | — | Answers architecture questions (kanban/intercom). |
| **Tech-lead** | — | — | — | Receives stamped tickets. Sequences. Delegates to developer. |
| **Developer** | — | — | — | Builds. |
| **Verifier** | — | — | — | Probes + conformance lens (checks against ADRs). |
| **QA** | — | — | — | Acceptance. |

**Key: PO owns the flow.** The architect is a design service PO calls,
not a co-author PO negotiates with. No planning phase — PO cuts tickets
after design, same as today, just with better input.

### What stays the same

- PO still owns `to-spec` and `to-tickets`
- PO still creates beads and dependencies
- Tech-lead still sequences and delegates
- The dev loop (developer → verifier → qa) is unchanged
- The T0-T3 gate ceremony still applies for **incremental changes** to
  existing systems (after initial build)


## How PO and Architect Communicate

### The card is the shared workspace

The kanban card is the primary coordination surface. PO creates it with
full context; architect reads it, works, and completes it.

**Card body template (PO creates this):**

```yaml
title: "[design] Recipe Cost SaaS — technical design"
assignee: architect
body: |
  ## Spec
  docs/specs/recipe-cost.md

  ## Context (from grilling user/VB)
  - User is a restaurant owner, non-technical
  - Needs <5s cost calculation per recipe
  - Budget: <$500/mo total hosting + APIs
  - Timeline: 3-month MVP
  - User strongly prefers PostgreSQL (prior experience)
  - Price data: user wants API first, manual fallback acceptable

  ## Intercom topic
  recipe-cost-design

  ## Open technical questions (PO couldn't answer)
  - Scraper vs API for ingredient prices?
  - How to handle price volatility (daily changes)?
  - Caching strategy for price lookups?
```

The card body is **self-contained** — the architect can start working
without reading the full grilling transcript. But if it needs more
detail, it can intercom PO (see below).

### Intercom for live collaboration

The architect uses intercom to ask PO questions during the design phase.
No session IDs needed — the **topic** field is the session key.

**How intercom session targeting works:**

Intercom computes a deterministic session ID from the topic:

```
session_id = intercom-{team}-{profile_A}-{profile_B}-{topic}-{hash8}
```

- `team` = `startup`
- `profile_A` and `profile_B` sorted alphabetically (direction-independent)
- `topic` = the string from the card body (e.g., `"recipe-cost-design"`)
- `hash8` = first 8 hex chars of MD5

**Same topic = same session = accumulated context.** The PO that
responds is the same PO that has the project context, even if PO's
session died and was respawned by the offline spawner.

**Two delivery paths:**
1. **Online** (PO has a live session): message injected into PO's current
   session via `pre_llm_call` hook — full project context available.
2. **Offline** (PO has no session): broker spawns a PO session via
   `hermes -p product-owner chat -q "<msg>" -Q --pass-session-id` and
   **resumes the same session** on subsequent messages to the same topic.

**Always use the qualified form** `startup/product-owner` — bare names
can route to the wrong team under the degraded identity issue.

**Example — architect asks PO a question:**

```python
intercom ask(
    to="startup/product-owner",
    topic="recipe-cost-design",       # from card body
    text="Your brief says <$500/mo. Does that include the price API subscription? "
         "If separate, what's the API budget?",
    timeout=300
)
```

### When to use which channel

| Situation | Channel |
|-----------|---------|
| Handoff (brief → design) | Kanban card body |
| Design output (ADRs, design doc) | Kanban card completion metadata |
| "I'm blocked, need PO's input" | Intercom ask (blocking, topic-based) |
| FYI (design ready, review please) | Intercom send (fire-and-forget) |
| Iterative Q&A during design | Intercom (topic = accumulated session) |
| Durable decision record | Kanban comment + ADR file |


## The Design Team Pattern

### Why not one agent?

One agent can't give full depth to every design dimension in a single
context window. The operator's requirement: the design phase should work
as a **design team**, each dimension getting focused attention.

### How it works: kanban_chains fan-out

The architect uses `kanban_chains` to create parallel design cards on
the board. Each card is a real tracked task — durable, observable, with
its own workspace. **NOT `delegate_task` subagents** (fragile:
background-only, unreliable self-reports, don't survive session
boundaries).

| Design dimension | Card focus | Output |
|-----------------|------------|--------|
| **Domain model** | Entities, relationships, bounded contexts | Domain model doc |
| **System architecture** | Module boundaries, service decomposition | Architecture diagram + contracts |
| **Data layer** | Schema, storage strategy, migration plan | Data model + storage ADR |
| **Infrastructure** | Hosting, scaling, CI/CD, observability | Infra ADR |
| **Security & risk** | Auth model, threat surface, failure modes | Security ADR + risk register |
| **API design** | Public contracts, versioning, error model | API specification |

### The fan-out flow

```
Architect receives card from PO (with spec + context)
         │
         ├──▶ kanban_chains: parallel design cards
         │    ├── [design] Domain model      (assignee: architect)
         │    ├── [design] System architecture(assignee: architect)
         │    ├── [design] Data layer         (assignee: architect)
         │    ├── [design] Infrastructure     (assignee: architect)
         │    ├── [design] Security & risk    (assignee: architect)
         │    └── [design] API design         (assignee: architect)
         │
         ├──▶ After all complete: synthesis card
         │    (architect reviews all outputs, resolves conflicts,
         │     produces unified design doc + ADR series)
         │
         └──▶ Complete original card:
              summary = design doc path + ADR series
              metadata = {design_doc, adrs, tech_stack, data_model}
```

Each design card runs in a **fresh architect session** — isolated
context, focused on one dimension. The synthesis card merges them into
a coherent whole, resolving cross-dimension conflicts (e.g., the data
layer choice affects the API design).

### Fan-out scales with tier

| Tier | Fan-out |
|------|---------|
| T1 (feature) | Solo design — no fan-out, architect does it in one session |
| T2 (system) | Full fan-out — all dimensions get dedicated cards |
| T3 (platform) | Fan-out + wayfinder decomposition |


## Who Owns Which Matt Pocock Skills

| Skill | v2 owner | Phase | What it does |
|-------|----------|-------|-------------|
| `to-spec` | **PO** | Phase 1 + 3 | Synthesizes conversation into a spec. PO runs it after grilling to create the brief, and after architect completes to merge design into the final spec. |
| `to-tickets` | **PO** | Phase 3 | Breaks spec into tracer-bullet tickets. PO runs it after receiving the architect's design output. Stays with PO — it has full context. |
| `codebase-design` | **Architect** | Phase 2 | Deep-module vocabulary for boundary design |
| `domain-modeling` | **Architect** | Phase 2 | Domain entity/relationship modeling |
| `improve-codebase-architecture` | **Architect** | Phase 2 | Existing codebase deepening scan (brownfield) |
| `architecture-gate` | **Architect** | Phase 2 + incremental | Triage rubric + design-doc anatomy + paved-road stack |
| `grilling` | **PO** | Phase 1 | Structured interview to surface requirements |

**Key: `to-tickets` stays with PO.** It does NOT move to tech-lead. PO
has the full context (spec + design + grilling findings) and is the
right profile to decide slice boundaries and dependencies.


## Profile Assessment

### No new profiles. No renames.

| Candidate | Verdict | Reasoning |
|-----------|---------|-----------|
| **planner** | ❌ No | Planning is PO's job. PO cuts tickets after design — same as today, just with better input. |
| **designer** | ❌ No | Design is the architect's job, executed via kanban_chains fan-out. |
| **rename architect** | ❌ No | "Architect" is standard industry term. No ambiguity. |
| **rename PO** | ❌ No | "Product-Owner" is correct — owns the product flow end-to-end. |

The fix is the workflow insertion point and intercom communication, not
the org chart.


## What Changes (concretely)

### 1. PO learns to call the architect

PO's SOUL.md gains:

- "After writing the spec via `to-spec`, if the project involves
  technical decisions (stack, data model, boundaries, dependencies),
  create a kanban card for the architect with the spec link, context
  summary, and an intercom topic."
- "Include any technical questions you couldn't answer during grilling."
- "Do NOT write the spec's implementation/architecture sections yourself
  — the architect will produce those as design output."

PO keeps:

- Full ownership of `to-spec`, `to-tickets`, bead/dependency creation
- Full ownership of dispatch and monitoring
- Full ownership of the product flow

### 2. Architect gains design-partner mode

Architect's SOUL.md gains:

- "When you receive a design card from PO, run the full design phase:
  domain model, stack selection, data model, boundaries, risks, ADRs."
- "Use kanban_chains for the design fan-out (T2+ projects). Each design
  dimension gets its own card."
- "Use intercom to ask PO questions during design. Use the topic from
  the card body — same topic = same session = accumulated context."
- "Complete the card with design doc path + ADR series."

Architect keeps:

- All hard rules (never implement, never slice, never run dev loop)
- ADR convention (append-only, supersession)
- T0-T3 triage rubric (for incremental changes on existing systems)
- Conformance stamping

### 3. The workflow order

```
v1 (current):
  PO → spec (alone) → to-tickets → tech-lead → developer

v2 (refined):
  PO → spec → architect card (design) → PO reads design
       → to-tickets (with design input) → tech-lead → developer
```


## Comparison: v1 vs v2

| Dimension | v1 (gatekeeper) | v2 (design partner) |
|-----------|----------------|---------------------|
| When architect enters | Between map and to-tickets | Between spec and to-tickets |
| Who writes architecture | PO (alone) | Architect (via design fan-out) |
| Who cuts tickets | PO | PO (unchanged — with design input) |
| How they communicate | Card body only (one-way) | Card body + intercom (two-way, topic-based) |
| Design depth | One stamp (yes/no) | Full design phase with alternatives |
| Single-threaded? | Yes | No — kanban_chains parallel fan-out |
| New profiles needed | No | No |
| Planning phase needed | No | No — deferred to future iteration |


## Brownfield and Incremental Changes

### Brownfield adoption

Runs BEFORE the design phase. The architect maps the existing
architecture (retro-ADRs via `brownfield-intake`), THEN the design phase
works within those constraints (or supersedes them via ADR).

### Incremental changes (after initial build)

The T0-T3 gate ceremony applies:

1. Change arrives (kanban card or intercom ask)
2. Architect triages: 5 mechanical questions → tier
3. T0: wave through (no architect involvement)
4. T1: weigh alternatives, write ADR
5. T2: design-it-twice fan-out + async human approval
6. T3: vision → wayfinder decomposition
7. Record ADR, stamp, handoff

The gate is for **incremental** changes, not for initial project design.


## Open Questions (deferred)

1. **Planning phase**: Deferred. Once v2 design partner flow is proven,
   we may add a collaborative planning step (PO + architect co-author
   milestones and slice boundaries). Not needed now.

2. **Venture-builder role**: VB currently does ideation + research + spec
   + build orchestration. In v2, VB narrows to ideation + research +
   business model. Refine later.

3. **Gate skill update**: The gate skill needs a "design phase" preamble
   for new projects. Refine when implementing.

4. **Tech-lead ADR citation**: Tech-lead should cite ADRs in slice
   contracts. Refine when implementing.


## Decision Needed

This is a T2 change to the team's workflow architecture. It modifies:

- Architect SOUL.md (add design-partner mode + intercom doctrine)
- PO SOUL.md (add "call architect before tickets" + intercom topic)
- The workflow order (one insertion point between spec and tickets)

Before implementing, this should be recorded as an ADR and the operator
should approve.
