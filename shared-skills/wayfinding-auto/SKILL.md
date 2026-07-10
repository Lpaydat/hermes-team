---
name: wayfinding-auto
description: Autonomous-venture overlay for the wayfinder skill — product-owner drives the map as asker, venture-builder answers product questions over intercom, every resolution cites its source. Force-loaded via a card's skills field together with wayfinder; never invoked by slash command.
---

# Wayfinding — autonomous overlay (PO asks, VB answers)

You are running wayfinder WITHOUT a human in the loop. This overlay wires the two-agent
substitute for wayfinder's human. It NEVER replaces the upstream skill: read and obey the
`wayfinder` skill (force-loaded alongside this one) and the tracker mapping in
`docs/agents/issue-tracker.md` ("Wayfinding operations" — beads). Upstream invariants stay
binding: plan-don't-do, one unit of work per session, fog-of-war discipline, refer by name,
decisions-not-deliverables, concurrent sessions expected.

## Role wiring (never violate)

- **product-owner (you, normally) = the asker.** You drive the map: chart it, choose frontier
  tickets, pose questions, record resolutions. You NEVER answer a product question yourself.
- **venture-builder = the answerer.** VB owns product intent (the founder). Product questions
  go to VB over intercom: the `intercom` tool, `ask` action, `to: venture-builder`,
  `topic: <map bead id>` — the per-topic deterministic session keeps parallel ventures from
  mixing context. Include the idea-brief bead id and the ticket's Question in the ask.
- **Asker and answerer are different profiles in different sessions — always.** If you find
  yourself both posing and answering a question, stop: that is the self-answering failure
  wayfinder forbids.
- **The human is an escalation target, not a participant.** Never wait synchronously on a
  human; never treat operator silence as an answer.

## Ticket routing by type

- `wayfinder:grilling` and prototype-reaction — PO↔VB over intercom (above).
- `wayfinder:research` — researcher/scout via the normal dispatch queue: leave the ticket on
  the frontier for the dispatcher; do not resolve it yourself in a grilling session.
- `wayfinder:task` — ops/developer via the same queue.
- `wayfinder:prototype` (building the artifact) — developer queue; the *reaction* to it is
  PO↔VB.

## Citation rule (anti-hallucination — hard requirement)

Every VB answer you record and every resolution comment you write MUST cite its source:

- the idea-brief bead (`hermes-teams-<id>`), or
- a prior map decision (closed ticket id), or
- the intercom exchange itself (`intercom topic <map-id>, VB reply` — quote the decisive line).

An answer neither you nor VB can source is an ESCALATION, not a guess:
flag the ticket for the human asynchronously (`bd human <ticket-id>` — or block the bead
`needs-input` with an `ESCALATE:` comment naming what could not be sourced), then move on to
other frontier tickets. Uncited product intent must never enter the map.

## One unit per session (upstream rule, restated because cards tempt batching)

- A **chart-the-map card**: name the destination from the idea brief, create the map bead,
  create the tickets you can specify now, wire blocking edges second-pass, sketch the fog into
  Not-yet-specified — then COMPLETE the card. Do NOT also resolve tickets.
- A **work-the-map card**: claim ONE frontier ticket (`bd update <id> --claim`), resolve it,
  record the cited resolution, graduate fog — then COMPLETE the card. One ticket, no more.

## Completion discipline

Complete the card with a summary naming the map and what changed (charted N tickets / resolved
<ticket name>), and stamp metadata: `{"map": "<map-bead-id>", "charted": N}` or
`{"map": "<map-bead-id>", "resolved": "<ticket-id>", "cited": "<source>"}`. Board/bead state is
the seam every observer audits — leave it queryable.
