# Spec: Autonomous Venture Pipeline (idea → shipped, no human in the loop)

Status: ready-for-agent · Owner: operator · Origin: 2026-07-10 loops-engineering session

## Problem Statement

The operator wants to drop a single product idea into the system and have it developed to completion without shepherding it through each phase. Today every venture requires the operator to: relay the idea to the team, run `/wayfinder` (or grilling) by hand to turn fog into a plan, answer every product question personally and synchronously, kick off the development loop, and carry results back. The `venture-builder` profile exists to originate ideas — but its workflow is unpolished and nothing downstream consumes its output autonomously. Planning (wayfinder) is human-invoked by upstream design, and its human-in-the-loop ticket types have no autonomous answerer, so the pipeline stalls wherever a product judgment is needed.

## Solution

A closed loop between two agent roles with the human only at the edges:

- **venture-builder (VB)** plays the founder/innovator: finds market gaps, originates ideas, owns product intent, and **answers** product questions — the system's "user."
- **product-owner (PO)** plays the tech company's representative: receives VB's idea over intercom, files an idea brief, drives an autonomous **wayfinding map** (asker), routes each investigation ticket to the profile that can resolve it, and hands the finished destination (a spec) into the existing development loop (tech-lead → kanban_chains → developer → verifier probe swarm → merge → QA swarm).
- Product questions flow **PO → VB over intercom** (ask/reply, deterministic per-topic sessions). Research tickets go to researcher/scout; mechanical tasks to ops/developer. The real human appears only for **asynchronous escalations** (when VB/PO genuinely cannot decide) and final review — never as a blocking step.
- When the way is clear, the map's destination becomes a published spec → tracer-bullet tickets → beads → the already-validated dev loop. On completion, PO reports the outcome back to VB, closing the founder's loop.

Asker and answerer are always **different profiles in different sessions** — the separation wayfinder's design demands, achieved with agents instead of a human.

## User Stories

1. As the operator, I want to seed a single idea (or a standing direction) and have it developed to completion, so that my time is spent on judgment, not shepherding.
2. As the operator, I want every product decision the agents made recorded with its source, so that I can audit the trail and veto bad calls after the fact.
3. As the operator, I want to be pinged asynchronously only when the system genuinely cannot decide, so that autonomy never silently substitutes for my values.
4. As venture-builder, I want to pitch an idea to the product-owner over intercom, so that a venture starts from a conversation, not a manual ticket.
5. As venture-builder, I want product questions from planning routed to me with the context of my original pitch, so that my answers stay consistent with the idea's intent.
6. As venture-builder, I want a completion report when the venture ships, so that I can judge market fit and originate follow-on ideas.
7. As product-owner, I want every accepted pitch captured as an idea brief on the tracker, so that planning has a durable, citable source of product intent.
8. As product-owner, I want to chart a wayfinding map autonomously from the brief, so that fuzzy ideas become routed, dependency-ordered investigation tickets without a human running a slash command.
9. As product-owner, I want each map ticket typed (research / prototype / grilling / task), so that the dispatcher can route it to the profile equipped to resolve it.
10. As product-owner, I want to ask venture-builder grilling questions over intercom and record the answers as ticket resolutions, so that decisions accumulate on the map, not in a chat log.
11. As product-owner, I want any answer I cannot source from the brief or a prior decision to force an escalation instead of a guess, so that hallucinated product intent cannot enter the map.
12. As a researcher/scout, I want research tickets dispatched to me as ordinary kanban cards, so that AFK investigation flows through the queue I already work.
13. As the tech-lead, I want the finished destination delivered as a spec plus tracer-bullet beads, so that the development loop starts from the same contract quality the loop drills validated.
14. As a developer, I want venture work to arrive as ordinary contract-bearing cards, so that nothing about my loop changes.
15. As the verifier, I want venture work verified through my normal probe-swarm doctrine, so that autonomy adds no new merge path.
16. As the qa profile, I want a QA card after merge like any other project, so that ventures get the same adversarial acceptance as internal work.
17. As the ops profile, I want the whole pipeline observable as board/bead state, so that a stalled venture is diagnosable from the tracker alone.
18. As the product-owner, I want to report shipped outcomes back to venture-builder with evidence, so that the founder loop closes with facts, not claims.
19. As the operator, I want concurrent ventures isolated (per-project boards/worktrees), so that two ideas in flight cannot corrupt each other.
20. As any profile, I want the map, tickets, and decisions to survive crashes and restarts, so that a venture never depends on any single session staying alive.
21. As the operator, I want to optionally run `/wayfinder` myself on a map, so that manual and autonomous planning interoperate on the same artifact.
22. As the product-owner, I want charting and ticket resolution capped at one unit of work per session, so that context stays small and every step lands as durable state.

## Implementation Decisions

- **Role wiring (the core decision):** PO is the *asker* (drives the map); VB is the *answerer* (product intent). Never the same profile for both — this substitutes wayfinder's human-in-the-loop with a two-agent exchange while preserving its independence property. The real human is an escalation target, not a participant.
- **Wayfinder runs autonomously via card-forced skill loading.** The platform force-loads a card's `skills` into the spawned worker; the upstream skill's `disable-model-invocation` flag is inert in this platform (verified against platform source). A "chart the map" card assigned to PO with the wayfinder skill starts planning with no slash command.
- **A thin overlay skill (`wayfinding-auto`) wraps the upstream wayfinder skill** rather than editing it (upstream stays sync-safe). The overlay adds: the PO-asks/VB-answers wiring, the escalation policy, and the tracker mapping below. Upstream's invariants stay binding: one ticket per session; decisions-not-deliverables; fog-of-war discipline; concurrent sessions expected.
- **Beads is the wayfinder tracker.** Map = a bead (epic) labeled as a wayfinder map; tickets = child beads labeled by type; blocking = native bead dependencies; the frontier (open ∧ unblocked ∧ unclaimed) is exactly the tracker's ready query; claiming = assignment. The existing beads-watchdog/dispatch cron flows frontier tickets to kanban cards with no new machinery.
- **Ticket routing by type:** research → researcher/scout; task → ops/developer; grilling and prototype-reaction → PO↔VB over intercom (PO poses the question from the ticket, VB answers in the founder role; the resolution comment cites the exchange).
- **Citation rule (anti-hallucination):** every VB answer and PO resolution must cite its source — the idea brief, a prior map decision, or the intercom exchange itself. An answer nobody can source forces an escalation (human-flagged bead / needs-input block / intercom ping to the operator) — asynchronous; other frontier tickets keep flowing while it waits.
- **Intercom is the conversation transport** (existing shared broker): ask/reply with timeouts, per-topic deterministic sessions so parallel ventures never mix context, offline queueing. The idea pitch, grilling exchanges, and the final report-back all ride it.
- **Idea brief schema (bead body):** gap/opportunity, target user, value hypothesis, constraints/budget, success criteria, VB's confidence notes. The brief is the citable root of product intent for the venture.
- **Handoff at map completion:** destination artifact = a spec in the repo's spec convention, published to the tracker; then decomposition into tracer-bullet beads (existing to-spec/to-tickets conventions); then the existing validated loop (planner → chains → generator → probe-swarm verifier → merge → QA swarm). No new execution machinery.
- **Report-back:** on venture completion (QA verdict), PO sends VB an intercom summary with evidence pointers (verdicts, board links); VB records the outcome against its original thesis.
- **Isolation:** each venture gets its own project board + worktree/repo per the existing per-project board convention.

## Testing Decisions

- **A good test asserts external behavior at the board/bead seam** — durable state transitions any observer can query — never doctrine internals or agent prose. This is the highest existing seam and the one every drill in the validation campaign used.
- **Primary seam — kanban/beads state machine.** The acceptance drill: inject a synthetic VB pitch → assert idea-brief bead appears (with citable fields) → chart card runs → map bead + typed child beads exist with correct dependencies → frontier tickets dispatch to the right profiles → a grilling ticket resolves with a cited VB answer → destination spec bead appears → dev-loop chain runs to stamped PASS verdicts → report-back message lands. Every arrow is a queryable state assertion.
- **Second seam — intercom broker protocol** (existing suite + round-trip script): ask/reply delivery, per-topic session determinism, offline queue drain.
- **Escalation path test:** a grilling ticket whose answer cannot be sourced must produce a human-flagged escalation and must NOT resolve with an uncited answer.
- **Prior art:** the fix-loop drills (planted-defect kvstore series) established the drill pattern — fixture project, synthetic seed, board-state waiters, stamped-verdict assertions; reuse it wholesale.

## Out of Scope

- Intercom broker durability/supervision (separate spec: intercom-durability).
- Terse agent-to-agent reporting style (separate spec: terse-comms).
- Multi-team/cross-machine routing; budget and spend governance; production deployment/hosting of shipped ventures; human-facing dashboards; VB's market-research quality itself (this spec wires the pipeline, not the founder's judgment).
- Editing the upstream wayfinder skill (overlay only).

## Further Notes

- Everything downstream of the map is already built and field-validated this session: chains-native delegation (kanban_chains v3 with idempotent recovery), the probe-swarm verifier doctrine (v6) with stamped verdicts, fix-loop and QA-swarm behavior — proven across six live drills including a two-iteration FAIL→fix→re-verify cycle.
- The wayfinder→beads fit is native, not adapted: its "frontier" concept and the tracker's ready-query are the same thing; claim-by-assignment likewise. The overlay is role wiring plus vocabulary, not machinery.
- VB↔PO intercom channel was verified live end-to-end during this session (ask/reply round-trip with deterministic topic session).
