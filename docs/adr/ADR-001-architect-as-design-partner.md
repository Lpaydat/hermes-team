# ADR-001: Architect as proactive design partner (workflow v2)

**Status:** Accepted  
**Date:** 2026-07-11  
**Tier:** T2  

## Context

The v1 workflow positioned the architect as a reactive gatekeeper between
map completion and ticket creation. In practice this meant:

1. PO wrote the entire spec alone — including technical architecture
   sections — without technical expertise.
2. The architect stamped after the fact — the design was already done;
   the gate was just a yes/no, not a creative contribution.
3. Tech-lead inherited a fait accompli — couldn't challenge boundaries
   that were never technically reviewed.
4. The design was single-threaded — one non-technical agent made all
   architecture decisions.

The operator's original mental model was different: the architect should
be part of the planning team, working with PO during design, not waiting
at a gate downstream.

## Decision

Insert the architect as a **proactive design partner** between PO's spec
creation and PO's ticket decomposition. PO owns the flow:

```
PO grills user/VB → to-spec → architect card (design) → PO reads design → to-tickets
```

The architect:
- Receives a design card from PO with spec link, context summary, and
  intercom topic
- Runs the full design phase (domain model, stack, data model, boundaries,
  risks, ADRs) using kanban_chains fan-out for T2+ projects
- Uses intercom to ask PO questions during design (topic from card body;
  same topic = same session = accumulated context)
- Completes the card with design doc path + ADR series

PO then reads the design output and runs to-tickets with design input.
No planning phase (deferred to future iteration). No new profiles.

## Alternatives Weighed

### Option A: Reactive gatekeeper (v1, rejected)
Keep architect as a gate between map and to-tickets.  
**Rejected because:** PO still makes all technical decisions alone. The
gate is a stamp, not a creative contribution. Doesn't match the
operator's mental model or big-tech patterns.

### Option B: Co-author model (earlier v2 draft, rejected)
PO and architect co-author the spec together, with a collaborative
planning phase.  
**Rejected because:** Over-engineered. Creates coordination overhead.
PO loses ownership of the flow. The operator preferred a simpler model:
PO calls architect as a design service, not negotiates with a co-author.

### Option C: Dedicated planner profile (rejected)
Create a new "planner" profile that sits between PO and tech-lead.  
**Rejected because:** Ownership ambiguity. Who owns the plan — PO or
planner? Creates a new role boundary that doesn't exist in big tech
(planning is co-authored, not delegated to a separate role).

### Option D: Dedicated designer profile (rejected)
Create a new "designer" profile separate from architect.  
**Rejected because:** Design decisions ARE architecture decisions.
Splitting them across two profiles creates authority conflicts. The
architect owns decisions; design is how it expresses that ownership.

### Option E: PO-owned design service (v2, ACCEPTED)
PO calls the architect as a design service before cutting tickets.
Architect runs design autonomously (with kanban_chains fan-out), uses
intercom to ask PO questions. PO reads the design output and cuts tickets
with full context.  
**Accepted because:** Simplest change, preserves PO ownership, matches
the operator's mental model, uses existing infrastructure (kanban +
intercom), no new profiles.

## Consequences

**Enables:**
- Technical decisions made by a technical authority before tickets are cut
- Parallel design depth via kanban_chains fan-out
- PO retains full ownership of the product flow
- Two-way communication via intercom (topic-based session targeting)

**Costs:**
- One extra step in the workflow (design card before to-tickets)
- Architect SOUL.md must carry both design-partner and gatekeeper modes
- PO SOUL.md must learn when to call the architect

**Locks in:**
- PO owns to-spec and to-tickets (does not move to tech-lead or architect)
- Architect never implements or slices tickets (hard rule unchanged)
- kanban_chains (not delegate_task) for design fan-out
- Intercom topic-based session targeting for PO ↔ architect communication

## Supersedes

None (first ADR for this workflow).

## References

- v2 design doc: `docs/workflow-redesign-v2.md`
- v1 spec: `docs/specs/architecture-in-the-loop.md`
- Intercom durability spec: `docs/specs/intercom-durability.md`
- Big-tech grounding: Google design docs, Amazon 6-pagers, Meta RFCs
