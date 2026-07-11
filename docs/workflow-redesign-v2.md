# Workflow Redesign: Architecture-in-the-Loop v2

> Refined from v1 (gatekeeper model) based on big-tech patterns and the
> operator's original mental model: the architect is a proactive design
> partner, not a reactive gate.

## The Problem with v1

v1 positioned the architect as a **reactive gatekeeper** between map
completion and ticket creation. In practice this means:

1. **PO writes the entire spec alone** — including technical architecture
   sections (stack, data model, API contracts) — without technical expertise.
2. **The architect stamps after the fact** — the design is already done;
   the gate is just a yes/no, not a creative contribution.
3. **Tech-lead inherits a fait accompli** — can't challenge boundaries
   that were never technically reviewed, only decompose what's given.
4. **The design is single-threaded** — one agent (PO, who isn't technical)
   makes all architecture decisions with no peer review or alternative
   exploration.

## How Big Tech Actually Does It

| Company | Design doc author | Design reviewers | Planning |
|---------|------------------|-----------------|----------|
| Google | Tech Lead / Sr Engineer | Peers + Staff+ engineers | Same TL writes implementation plan |
| Amazon | Sr Engineer / Principal | Senior team review | TL decomposes after approval |
| Meta | Staff Engineer | RFC review by peers+senior | TL sequences after RFC merged |
| Stripe | Staff+ Engineer | Cross-team review | EM sequences after design approved |

**Pattern**: Design is authored by a technical authority, reviewed by
peers, THEN handed to planning. Design and planning are sequential phases
with a clear handoff, not a single step done by one person.

## The Refined Workflow (v2)

### Phase 1: Ideation — WHAT and WHY

**Lead**: Product-Owner  
**Collaborator**: User or Venture-Builder  
**Output**: Brief/PRD

PO grills the user/VB about the problem space. The output is a product
brief — NOT a technical spec. It covers:

- What problem are we solving?
- Who are the users?
- What does success look like (metrics)?
- What are the hard constraints (budget, timeline, compliance)?
- What's the rough scope (MVP vs full vision)?

PO does NOT write architecture, stack, or data model sections. That's
the architect's job.

### Phase 2: Design — HOW

**Lead**: Architect  
**Input**: Brief/PRD from PO  
**Output**: Technical design doc + ADRs

The architect receives the brief and runs the design phase. This is
proactive, not reactive. The architect:

1. **Models the domain** (entities, relationships, bounded contexts)
2. **Designs module boundaries** (deep modules, shallow seams, contracts)
3. **Selects the tech stack** (weighing ≥2 alternatives, recording ADRs)
4. **Designs the data model** (schema, storage, migration posture)
5. **Identifies cross-cutting concerns** (auth, observability, error handling)
6. **Maps data flow** (request lifecycle, async flows, integration points)
7. **Identifies risks** (failure modes, scalability ceilings, security surface)

Critically, **the architect works as a design team, not a solo agent**
(see "Design Team Pattern" below).

### Phase 3: Planning — WHEN and WHAT ORDER

**Lead**: Product-Owner + Architect (co-authors)  
**Output**: Stamped spec (product + architecture + milestones)

PO and architect collaborate to produce the complete spec:

| PO contributes | Architect contributes |
|---------------|----------------------|
| Milestones (MVP → V1 → V2) | Slice boundaries (what can ship independently) |
| Ship cadence (when to release) | Dependency ordering (what blocks what) |
| Scope cuts (what to defer) | Risk sequencing (de-risk first) |
| User value ordering | Build-vs-buy decisions |
| Success metrics per milestone | Technical acceptance criteria per slice |

The spec is "stamped" when both PO and architect agree on the plan.
This stamp is the handoff to tech-lead.

### Phase 4: Decomposition — TICKETS

**Lead**: Tech-lead  
**Input**: Stamped spec (with architecture section + ADRs)  
**Output**: Tracer-bullet tickets, each citing relevant ADRs

Tech-lead reads the stamped spec and decomposes it into implementation
tickets. Each ticket cites the ADRs it builds under, so the developer
knows the decided constraints without reading the whole spec.

Tech-lead does NOT re-litigate architecture decisions. If tech-lead
disagrees with an ADR, it opens an architecture ticket — it doesn't
override the decision in a dev-loop card.

### Phase 5: Execution — BUILD + VERIFY + ACCEPT

Same as current:

```
tech-lead (sequence) → developer (build) → verifier (probe) → qa (accept)
```

No changes to the execution phase.

### Phase 6: Incremental Changes (the gate ceremony)

For changes to an existing system AFTER initial build, the T0-T3
gate ceremony still applies. A new feature, refactor, or dependency
addition goes through triage → alternatives → ADR → stamp.

The gate is for **incremental** changes, not for initial project design.


## The Design Team Pattern

### Why not one agent?

The operator's requirement: the design phase should work as a **design
team**, not rely on a single agent. This matches big-tech reality —
design docs are authored by one engineer but reviewed and shaped by
multiple perspectives.

### How the team works

The architect orchestrates a parallel design fan-out using
`kanban_chains` or `delegate_task`. Each design dimension gets its own
focused subagent:

| Design dimension | Subagent focus | Output |
|-----------------|---------------|--------|
| **Domain model** | Entities, relationships, bounded contexts, ubiquitous language | Domain model doc |
| **System architecture** | Module boundaries, service decomposition, communication patterns | Architecture diagram + boundary contracts |
| **Data layer** | Schema design, storage strategy, migration plan, query patterns | Data model + storage ADR |
| **Infrastructure** | Hosting, scaling, CI/CD, observability, deployment strategy | Infra ADR |
| **Security & risk** | Auth model, threat surface, compliance, failure modes | Security ADR + risk register |
| **API design** | Public contracts, versioning, error model, rate limiting | API specification |

### The fan-out flow

```
Architect receives brief from PO
         │
         ├──▶ kanban_chains: parallel design cards
         │    ├── [design] Domain model (assignee: architect)
         │    ├── [design] System architecture (assignee: architect)
         │    ├── [design] Data layer (assignee: architect)
         │    ├── [design] Infrastructure (assignee: architect)
         │    ├── [design] Security & risk (assignee: architect)
         │    └── [design] API design (assignee: architect)
         │
         ├──▶ After all complete: synthesis card
         │    (architect reviews all outputs, resolves conflicts,
         │     produces unified design doc + ADR series)
         │
         └──▶ Stamped architecture section → co-author spec with PO
```

Each design card runs in a fresh architect session — isolated context,
focused on one dimension. The synthesis card merges them into a coherent
whole, resolving cross-dimension conflicts (e.g., the data layer choice
affects the API design).

### Why this is better than solo design

| Solo architect | Design team |
|---------------|-------------|
| One context window, limited depth per dimension | Each dimension gets full context depth |
| Sequential exploration (slow) | Parallel exploration (fast) |
| Single perspective bias | Multiple independent perspectives |
| Alternatives explored mentally | Alternatives explored per-dimension, in parallel |
| Risk of missing a dimension | Structured checklist ensures coverage |


## Profile Assessment

### Current profiles — keep as-is

| Profile | Current role | v2 role | Change needed |
|---------|-------------|---------|---------------|
| **product-owner** | Ideation + spec + tickets + dispatch | Ideation + co-author plan + dispatch | Remove technical spec authoring; add "route to architect" |
| **architect** | Reactive gatekeeper | Proactive design partner + incremental gate | Expand SOUL.md; add design fan-out doctrine |
| **tech-lead** | Decompose + execute | Decompose + execute (unchanged) | None — already correct |
| **developer** | Build | Build (unchanged) | None |
| **verifier** | Probe + verify | Probe + verify + conformance lens (unchanged) | None |
| **qa** | Acceptance | Acceptance (unchanged) | None |

### Do we need new profiles?

| Candidate | Verdict | Reasoning |
|-----------|---------|-----------|
| **planner** | ❌ No | Planning is co-authored by PO + architect, not a separate role. Adding a profile creates ownership ambiguity. |
| **designer** | ❌ No | Design is the architect's core job, executed via fan-out subagents. A separate profile can't own decisions the architect must own. |
| **tech-architect** vs **architect** | ❌ No rename | "Architect" is the standard industry term and matches the spec. No ambiguity. |

**No new profiles needed. No renames needed.** The fix is to the
workflow and identity prompts, not to the org chart.


## What Changes

### 1. Product-Owner SOUL.md

Add to PO's identity:

- "Route the brief to the architect for technical design BEFORE writing
  the spec's implementation sections."
- "Co-author the spec with the architect: PO owns product sections
  (problem, users, metrics, milestones), architect owns architecture
  sections (stack, data model, boundaries, risks)."
- "Do NOT make technical trade-off decisions. If a technical question
  arises during ideation, tag it `wayfinder:architecture` and route to
  the architect."

Remove from PO's identity:

- Writing implementation/architecture sections of specs (this moves to
  architect)

### 2. Architect SOUL.md

Add to architect's identity:

- "Proactive design partner: when you receive a brief from PO, you run
  the full design phase — domain model, stack selection, data model,
  boundaries, risks, ADRs — using the design team fan-out pattern."
- "Co-author the spec with PO: you write the architecture sections, PO
  writes the product sections."
- "The T0-T3 gate ceremony applies to incremental changes on existing
  systems, not to initial project design (which is the design phase
  above)."

Keep:

- All hard rules (never implement, never slice, never run dev loop)
- ADR convention (append-only, supersession)
- T0-T3 triage rubric (for incremental changes)
- Conformance stamping

### 3. The workflow order

```
v1 (current):
  PO → spec (alone) → gate → tech-lead → tickets → developer

v2 (refined):
  PO → brief → architect (design team fan-out) → design doc + ADRs
       → PO + architect co-author stamped spec
       → tech-lead → tickets → developer
       → [incremental changes go through T0-T3 gate]
```


## Comparison: v1 vs v2

| Dimension | v1 (gatekeeper) | v2 (design partner) |
|-----------|----------------|---------------------|
| When architect enters | Between map and to-tickets | Between ideation and planning |
| Who writes architecture sections | PO (alone) | Architect (with fan-out team) |
| Who plans milestones | PO (alone) | PO + architect (co-authors) |
| Design depth | One stamp (yes/no) | Full design phase with alternatives |
| Single-threaded? | Yes — one agent stamps | No — parallel design fan-out |
| Big-tech alignment | Weak (no design phase) | Strong (design doc → review → plan) |
| Gate ceremony | Primary function | Secondary (incremental changes only) |


## Open Questions

1. **Should the design fan-out always run, or only for T2+ projects?**
   Small projects (T1) might not need a 6-way fan-out — a single design
   pass might suffice. Recommendation: fan-out scales with tier. T1 =
   solo design, T2 = full fan-out, T3 = fan-out + wayfinder decomposition.

2. **Should venture-builder be in the design phase?**
   VB currently does ideation + research + spec + build orchestration.
   In v2, VB's role narrows: ideation + research + business model, then
   hands to PO for the product brief. VB does NOT participate in design
   (that's architect's job) or planning (that's PO + architect).

3. **How does brownfield fit?**
   Brownfield intake runs BEFORE the design phase. The architect maps
   the existing architecture (retro-ADRs), THEN the design phase works
   within those constraints (or supersedes them via ADR).

4. **Does the gate skill need updating?**
   Yes — the gate skill currently assumes all changes come through the
   map → gate → to-tickets path. It needs a "design phase" preamble for
   new projects that runs the fan-out before the gate stamp.


## Decision Needed

This is a T2 change to the team's architecture. It modifies:

- Two profile identities (PO + architect SOUL.md)
- The workflow order (where architect enters)
- The spec authorship split
- The gate skill (add design phase)

Before implementing, this should be recorded as an ADR and the operator
should approve.
