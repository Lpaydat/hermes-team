# Spec: Architecture in the Loop (architect profile + blast-radius gates)

Status: ready-for-agent · Owner: operator · Origin: 2026-07-11 architecture-design consultation (visual reference: "Architecture in the Loop" artifact)

## Problem Statement

The autonomous venture pipeline ships software with no owner for architecture. In the first live venture, technical decisions ("Expo/React Native", "swappable provider abstraction") were made by product-owner grilling venture-builder — the product authority, not a technical one — and the spec's implementation sections were written by PO with no technical review. Tech-lead only enters per-ticket, after the design is already cut into tracer beads, and its doctrine is tuned for delivery speed ("go straight to EXECUTE"), the wrong posture for weighing alternatives. Downstream, nothing checks that built code honors earlier design decisions: a later slice could silently violate the "swappable provider" decision and no verdict would catch it. As ventures grow past greenfield — refactors, brownfield adoption, redesigns — the missing function compounds: there is no durable record of *why* systems are shaped as they are, and no gate whose ceremony scales with how irreversible a change is.

## Solution

Mirror how big tech owns architecture — a senior function embedded in the flow, not a standing department — using the team's existing machinery. A **gateway-less `architect` profile** (the qa-profile pattern: card-spawned and intercom-spawned only) owns decisions that outlive a slice, recorded as **append-only ADRs** in each venture repo. Every piece of work is **triaged once by blast radius** into tiers T0–T3, and the ceremony scales with the tier: none for a patch, one ADR for a feature, design-it-twice candidate fan-out plus async human approval for a system, decomposition via wayfinder for a platform. An **architecture gate** sits between map completion and to-tickets; a **conformance lens** in the verifier's probe mandate catches drift from ADRs; **`wayfinder:architecture` tickets** route technical questions to the architect instead of defaulting to the founder. Refactor, brownfield, and redesign enter the same funnel: brownfield gets a one-time as-is inventory producing retro-ADRs; redesign is ADR supersession at T2+, never an edit.

## User Stories

1. As the operator, I want architecture decisions made by a technical authority with a gatekeeper posture, so that founder-grilling stops being the default answerer for engineering trade-offs.
2. As the operator, I want review ceremony proportional to blast radius, so that patches ship without friction while irreversible decisions get real scrutiny.
3. As the operator, I want every architectural decision recorded as an append-only ADR citing its inputs, so that I can audit *why* any system is shaped as it is from tracker/repo state alone.
4. As the operator, I want the architect profile to cost nothing while idle, so that the team does not gain another always-on gateway to babysit.
5. As product-owner, I want architecture-typed map tickets routed to the architect like research routes to scout, so that I stay the asker and never invent technical answers.
6. As product-owner, I want the architect to stamp the spec's architecture sections before I cut tracer beads, so that decomposition inherits reviewed boundaries instead of my improvisation.
7. As the architect, I want a narrow SOUL and curated design skills without delivery doctrine, so that my sessions never inherit "execute fast" instincts at a gate.
8. As the architect, I want a blast-radius triage rubric with mechanical questions, so that tier assignment is repeatable rather than a judgment call.
9. As the architect, I want T2 decisions produced by comparing independent design candidates, so that the first plausible design is not the only one considered.
10. As the architect, I want ADR supersession as the only way to change a decision, so that history is never rewritten and migrations are always explicit.
11. As the architect, I want a one-time brownfield inventory flow producing retro-ADRs, so that adopted codebases get a baseline the gate can reason against.
12. As tech-lead, I want slice contracts to cite the ADRs they build under, so that my planning inherits decided boundaries and I never re-litigate them per card.
13. As tech-lead, I want a crisp boundary — architect owns what outlives a slice, I own how a slice gets built — so that authority disputes are settled by the ADR, not negotiation.
14. As a developer, I want the relevant ADRs referenced in my card body, so that I build inside decided constraints without reading the whole map.
15. As the verifier, I want an architecture-conformance lens in my static probe mandate, so that drift from ADRs fails review even when no bug exists.
16. As venture-builder, I want architecture questions to stop arriving in my grilling queue, so that I answer product intent only and never guess at engineering.
17. As the qa profile, I want the spec's architecture sections testable as claims, so that acceptance probes cover structure as well as behavior.
18. As the human, I want T2+ gates to escalate to me asynchronously for approval, so that irreversible choices get my veto without blocking unrelated work.
19. As any profile, I want triage, gates, ADRs, and approvals durable as beads/cards/files, so that a crashed session never loses an architecture decision.
20. As the operator, I want refactors distinguished from redesigns mechanically (interfaces intact vs moved), so that "refactor" cards cannot smuggle architectural change past the gate.
21. As the operator, I want the whole capability provable by drills on the existing plant-care venture, so that adoption follows evidence like every prior pipeline stage.

## Implementation Decisions

- **Architect profile, gateway-less (the qa precedent).** A new profile with SOUL, config, memories, and skills directory but no systemd gateway unit; sessions spawn via kanban dispatch (`-p architect`) and the intercom offline spawner. Promotion to a full gateway is deferred until standing cadence (T3 steering) demands it.
- **SOUL posture.** Gatekeeper, not builder: weighs alternatives before approving; owns ADRs and spec architecture sections; never implements, never slices work, never runs the dev loop. Skill set: the design doctrine family (codebase design, interface design, domain modeling, architecture improvement, refactor planning, ubiquitous language) and explicitly NOT loops-engineering or delegation doctrine.
- **ADR-as-arbiter boundary.** Architect owns decisions that outlive a slice (boundaries, contracts, data models, stack, cross-cutting patterns); tech-lead owns slice construction (contracts, sequencing, delegation). Conflicts resolve to the ADR; changing an ADR requires an architecture ticket — never a dev-loop card.
- **Blast-radius triage rubric (T0–T3).** Five mechanical questions — interface change? data-model change? new dependency? crosses venture/team boundary? security/privacy surface? All no → T0; each yes pushes up. T0 patch: no design artifact. T1 feature: one ADR, async peer look. T2 system: full design doc + candidate review + async human approval. T3 platform: vision → wayfinder decomposition, sub-slices re-enter at T1/T2.
- **`wayfinder:architecture` ticket type.** Added to the engine's routing table (routes to architect, same shape as research→scout) and to the tracker mapping doc and wayfinding-auto overlay. Grilling/prototype stay PO↔VB; the map/brief skip set is unchanged.
- **Architecture gate card** between map completion and to-tickets. Force-loads the design skill set + the gate skill (which carries the triage rubric and the design-doc anatomy checklist: context, requirements/SLOs, domain and data model, data flow, interfaces/contracts, decomposition, stack, storage/consistency, security/privacy, observability, capacity/cost, failure modes, testing, rollout/migration, alternatives, risks). T2 runs design-it-twice: 2–3 independent candidate cards fanned out via kanban_chains, a synthesis pass, then an async human-approval escalation on the gate bead before to-tickets proceeds.
- **ADR convention.** Per-venture `docs/adr/` directory; one decision per file; append-only; each ADR records decision, context, alternatives, consequences, and citations (brief, map tickets, prior ADRs, human answers). Supersession links via the tracker's native supersede relation plus a Superseded-by header. Brownfield adoption starts with retro-ADRs ("status quo — accepted, not endorsed") produced by an as-is inventory card using the existing code-mapping tooling.
- **Verifier conformance lens.** The static-review probe mandate gains one lens: does the diff honor the ADRs and the spec's architecture section? Findings are severity-graded like any other; drift with no bug is still a finding.
- **Spec authorship split.** PO writes problem/solution/user stories; architect writes/stamps implementation and testing architecture sections; the gate stamps approval metadata before tracer beads are cut.
- **Paved road.** An approved-stack section in the gate skill (not a separate enforcement system): deviations are legitimate but must be justified in the ADR that introduces them.

## Testing Decisions

- **A good test asserts external behavior at the board/bead seam** — durable state transitions any observer can query (card status, stamped verdict metadata, bead labels/relations) — never doctrine prose or agent transcripts. This is the seam every prior pipeline drill used; reuse the drill pattern wholesale (fixture → synthetic seed → board-state waiters → stamped-metadata assertions).
- **Second seam: repo artifacts.** ADR files exist, are append-only across a supersession drill, and contain the required sections and citations; the spec's architecture section exists and is stamped. Asserted by file/content checks in the same drill scripts.
- **Acceptance drills:** (1) an architecture-typed map ticket routes to an architect card carrying question + map pointer, resolving with a cited ADR; (2) a gate drill per tier — a T0 passes through untouched, a T1 produces exactly one ADR, a T2 fans out candidates, synthesizes, escalates for async human approval, and blocks to-tickets until answered; (3) a conformance drill — a diff deliberately violating an ADR must FAIL verification with the drift named; (4) a supersession drill — redesign produces a superseding ADR + migration note, old ADR intact; (5) a brownfield drill — inventory card on an existing fixture repo yields retro-ADRs and debt beads.
- **Prior art:** test27–test31 drill scripts (field-integrity, routing, E2E arrows) and the planted-defect kvstore series; the conformance drill is the planted-defect pattern applied to design instead of code.

## Out of Scope

- A standing architect gateway, cron reviews, or T3 steering cadence (revisit when a real T3 exists).
- Automated enforcement of the approved stack beyond ADR justification (no linters/policy engines).
- Retrofitting ADRs onto ventures other than the drill fixtures; org-wide architecture metrics or dashboards.
- Multi-team / cross-machine architecture coordination.
- Changing the existing dev-loop, QA-swarm, or report-back machinery (the gate and lens compose with them; they do not modify them).

## Further Notes

- Everything here reuses validated machinery: card-forced skills, kanban_chains fan-out, engine label routing, async human escalation (tag + hq ping), and the citation rule. The architect profile itself is the only genuinely new object, and the qa profile proves its gateway-less shape works.
- The plant-care venture is the natural drill fixture: it has a real spec, real ADR-worthy decisions already made informally (provider abstraction, bundled dataset), and two unbuilt tracer beads' worth of history — its retro-ADR inventory doubles as the brownfield drill.
- Big-tech grounding: embedded senior ownership + document-based review scaled by blast radius (Google design docs, Amazon 6-pagers/PE review) rather than a standing architecture team; the tier rubric is the codified form of "spend review capacity proportional to irreversibility."
