# ADR-002: Design-council — stakes-led, research-backed multi-perspective design

**Status:** Accepted  
**Date:** 2026-07-12  
**Tier:** T2  
**Introduced-by:** hermes-teams-jov  
**Refined:** 2026-07-12 (during validation) — PO interaction expanded to a live intercom *interview* before the ADR (standard + high) and per-synthesis PO *review* cards (high); the async PO gate card is retired for standard. Pre-merge refinement of the same decision.  

## Context

ADR-001 made the architect a proactive design partner called by the PO before
tickets. The v2 test (board `test88-design-v2`, 2026-07-11) proved the flow
end-to-end — and exposed the failure mode this ADR addresses:

- The architect ran the **entire design solo**. The design card's tool-call
  histogram: 5 `write_file`, 0 `kanban_chains`. `design.md` (427 lines) and four
  ADRs came from one agent's reasoning, with no research and no peer critique.
- The SOUL permitted it: *"For T1 projects, do it solo — no fan-out."*
  New-project design-partner mode is untiered, so the fan-out the doctrine
  imagined for T2+ never fired.
- The intercom topic was provisioned correctly but never exercised — the
  architect had enough context to skip it. The mechanism worked; the
  *behaviour* defaulted to solo.

The operator's standing experience is that single-agent-from-memory design
output "is almost always wrong or has many issues." The v2 test confirmed it
mechanically: a design produced with zero research and zero critique. This ADR
refines ADR-001's tier rule; it does not supersede ADR-001 (design-partner mode
stands).

## Decision

Every ADR the architect records is the output of a **design-council** — a
research-backed, multi-perspective deliberation created with `kanban_chains`,
which parks the architect in dependency-wait until the council completes. The
ADR cannot be written from one agent's training memory.

The council is **stakes-led and adaptive**, not a fixed heavy ceremony:

- **Floor (every ADR).** ≥1 research card + ≥1 peer-architect perspective, run
  as parallel `kanban_chains` with no `after` — the architect is parked and
  synthesizes the ADR on resume. Never solo.
- **Stakes** (PO-declared on the design card) sets the council tier *and* the PO's role:
  - *Low* (prototype / internal / throwaway) → floor only (1 research + 1 peer), 1 round, no PO interaction.
  - *Standard* (default) → floor + a **live intercom interview** with the PO before the ADR (the async gate card is retired for standard); +1 peer on high-complexity decisions.
  - *High* (revenue / safety / brand / hard-to-reverse) → full fan-out (research + 2-3 peers + adversarial critic) + a **PO review card after each synthesis** (product fit) + a **live intercom interview** before the ADR; iterate to confidence or a 3-round ceiling.
- **Complexity** (architect-rated per decision, blast-radius instinct)
  fine-tunes peer count within the tier.
- **Confidence** (synthesis-reported H/M/L) gates iteration: not-high and a
  round remains → a critique round (targeted research + red-team → re-synth);
  ceiling hit → ADR records a *Residual risks* section and blocks `needs_input`
  for review, never silently accepted.
- The architect may escalate a single decision above the project's stake tier
  (with reason).

The outer v2 flow — PO → design card → architect → PO to-tickets — is
unchanged; this refines only the architect's internal design method. Realised
by the `design-council` skill (architect doctrine) using the `kanban_chains`
plugin exclusively — never `delegate_task` (board cards survive session
boundaries; subagents do not). ADRs follow `docs/agents/adr-convention.md`,
not `to-spec` (which writes product specs to the issue tracker — the PO's
domain). The old dimension fan-out (domain model / data layer / infra / …)
becomes a coverage checklist at decompose-time, not separate fan-out cards.

## Alternatives Considered

### Option A: Keep ADR-001's tier rule as-is (rejected)
T1 solo, T2+ fan-out. **Rejected because:** new-project design-partner mode is
untiered, so the rule's only escape hatch ("T1 solo") is the path that fires —
the exact failure the v2 test exposed.

### Option B: Tier-independent mandate — every decision, full council (rejected)
"Every ADR through a heavy council, no solo path, tier-independent."
**Rejected because:** it overcooks. At the floor it ran research + peer + a
separate PO-gate card + a separate synthesis card per decision — 4+ cards × N
decisions, 16-60 cards for a small project. The `design-council` skill's rubric
already scales by complexity, so the SOUL rule need not forbid solo or re-impose
tiering; it needs to route ADRs through a skill that scales.

### Option C: Structural only, no doctrine (rejected)
Rely on `kanban_chains` topology alone, no SOUL rule. **Rejected because:**
structure takes over only *after* the architect calls `kanban_chains`; without
a mandate the LLM can still choose solo. The call itself must be forced.

### Option D: Add a verifier gate (rejected, for now)
A verifier card rejecting ADRs missing research/council evidence. **Rejected
because:** the operator chose structural-only; the floor (architect parked
until research + perspective exist) already guarantees the evidence without a
second checker. Remains the remedy if lazy-accept is observed.

### Option E: Stakes-led adaptive council via the design-council skill (ACCEPTED)
Floor guarantee defeats solo-from-memory; stakes (PO) + complexity (architect)
scale the ceremony so low-stakes work costs ~2 cards and high-stakes gets the
full multi-agent fan-out; confidence gates iteration; the ceiling prevents
spinning. **Accepted because:** it is the minimal mechanism that satisfies
"never an unaided ADR" without overcooking trivial decisions, reuses the
existing `kanban_chains` plugin and the PO/architect ownership split, and
leaves the v2 flow intact.

## Consequences

- **Positive.** No ADR is memory-only; every decision is research-backed and
  critiqued. Council scale tracks business stakes (PO-owned) and technical
  complexity (architect-owned). High-stakes work gets the fan-out the operator
  wants; low-stakes work stays cheap.
- **Negative.** More cards and spawned sessions per design — even at the floor,
  ~2 cards per decision vs 0 solo. Design phases take longer and cost more
  tokens. Mitigated by stakes-led scaling (low-stakes stays at floor) and the
  3-round ceiling.
- **Ownership.** The PO gains a responsibility: declare project stakes on the
  design card. The architect gains the `design-council` skill and loses the
  "T1 solo" escape hatch.
- **Intercom.** The PO ↔ architect intercom (validated separately: same topic =
  same session, direction-independent) carries in-step clarification; the PO
  gate is the structural confirmation for high-stakes decisions.
- **Open.** Lazy-accept risk — the architect could call a thin council and
  declare high confidence. The floor keeps that from being *solo*, but Option D
  (verifier) is the remedy if it becomes observed. Council sizes and rubric
  thresholds are starting values, to be tuned on real runs.

## Citations

- v2 test evidence — board `test88-design-v2`, card `t_999e064a` tool-call
  histogram: "5 write_file, 0 kanban_chains" (architect solo).
- ADR-001 — "For T1 projects, do it solo — no fan-out" (the rule this refines).
- `docs/workflow-redesign-v2.md` § "The Design Team Pattern" / "Fan-out scales
  with tier" — the prior art this builds on.
- `startup/plugins/kanban_chains/` schema — "Blocks your card (kind=dependency
  → status=todo) … you auto-promote when all terminal work completes."
- intercom `compute_session_id(startup, architect, product-owner,
  habit-tracker-design)` — direction-independent (validated 2026-07-11).

## References

- v2 design doc: `docs/workflow-redesign-v2.md`
- ADR convention: `docs/agents/adr-convention.md`
- Skill: `startup/profiles/architect/skills/architecture/design-council/`
- Plugin: `startup/plugins/kanban_chains/`
- Introducing ticket: `hermes-teams-jov`
