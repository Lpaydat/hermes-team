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
  If the ask errors `target_not_connected` (VB offline), resend as a `send` with
  `spawn: true` — VB is woken to answer, and the answer arrives in YOUR session
  asynchronously (it is injected on a later turn: after spawn-sending, keep the session
  alive and check again after your next tool call; give it a few minutes before escalating).
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
- `wayfinder:architecture` — architect via the same queue: leave the ticket on the frontier
  for the dispatcher (the resolution is an ADR per `docs/agents/adr-convention.md`, cited by
  number in the resolution comment). PO stays the asker — PO NEVER answers an architecture
  question itself.
- `wayfinder:prototype` (building the artifact) — developer queue; the *reaction* to it is
  PO↔VB.

## Citation rule (anti-hallucination — hard requirement)

Every VB answer you record and every resolution comment you write MUST cite its source:

- the idea-brief bead (`hermes-teams-<id>`), or
- a prior map decision (closed ticket id), or
- the intercom exchange itself (`intercom topic <map-id>, VB reply` — quote the decisive line).

An answer neither you nor VB can source is an ESCALATION, not a guess. Asynchronously:

1. Flag the ticket: `bd tag <ticket-id> human` and add an `ESCALATE:` comment naming
   exactly what could not be sourced (the operator answers with `bd human respond
   <ticket-id>`, which comments and closes the ticket — that human answer IS the citation).
2. Ping the operator's surface: create a card on the `hermes-hq` board, `--assignee default`,
   titled `[ESCALATION] <ticket name>` with the question + map/brief pointers.
3. Move on to other frontier tickets — an escalation never blocks unrelated work.

Uncited product intent must never enter the map. When you later find an escalated ticket
closed by `bd human respond`, carry its answer to the map index citing the human's comment.

## One unit per session (upstream rule, restated because cards tempt batching)

- A **chart-the-map card**: name the destination from the idea brief, create the map bead,
  create the tickets you can specify now, wire blocking edges second-pass, sketch the fog into
  Not-yet-specified — then COMPLETE the card. Do NOT also resolve tickets.
- A **work-the-map card**: claim ONE frontier ticket (`bd update <id> --claim`), resolve it,
  record the cited resolution, graduate fog — then COMPLETE the card. One ticket, no more.

## Map completion → architecture gate (before to-tickets)

When a map's frontier empties, do NOT go straight to to-tickets. Architecture is reviewed
BEFORE tracer beads are cut, and the architect — not you — owns that verdict. You stay the
product authority; you never assign the tier or write the ADR yourself. Wire the gate in
this order — the **blocked-by edge FIRST**, so a session death mid-setup leaves a safe,
visible deadlock (to-tickets blocked) rather than a silent ungated proceed:

1. **Create the gate bead.** One bead per completed spec — its id is the gate handle
   (bead-sync closes it when the gate card is done).
2. **Block to-tickets on it FIRST.** Make the to-tickets / tracer-cutting work
   **blocked-by** the gate bead: `bd dep add <to-tickets-bead> <gate-bead>`. The
   to-tickets bead is now immediately blocked and cannot be dispatched ungated — even if
   the next step never runs.
3. **Raise the gate card.** Only now create the **architecture gate card**:
   `--assignee architect`, `--workspace dir:<venture>`, force-load `architecture-gate`
   together with the design skills (`--skill architecture-gate --skill codebase-design
   --skill domain-modeling`), and idempotency key `bead-<gate-bead>` so completion is
   durable. The body carries the map pointer + the completed spec path and instructs the
   gate to triage by blast radius, produce the tier's artifact (T0: none; T1: one ADR;
   T2: escalate — a T2 card is left **blocked**, never completed done, so the gate bead
   stays open), stamp the spec's architecture sections surgically without touching the
   product sections, and complete with the gate's completion-contract metadata.

Only when the architect completes the gate card (T0/T1) does **bead-sync** close the gate
bead and unblock to-tickets — which then proceeds and **inherits** the gate's tier + ADR
list from the stamped verdict.

The gate card is created by YOU (this doctrine), never by the engine: the engine's dispatch
skips any bead that already has a `bead-<id>` card, so a re-run never duplicates the gate.
Keep it to ONE gate card per completed spec — wire the blocked-by edge, raise the card,
then complete your own map card. PO stays the asker and product authority; the architect
owns the architecture verdict.

## Completion discipline

Complete the card with a summary naming the map and what changed (charted N tickets / resolved
<ticket name>), and stamp metadata: `{"map": "<map-bead-id>", "charted": N}` or
`{"map": "<map-bead-id>", "resolved": "<ticket-id>", "cited": "<source>"}`. Board/bead state is
the seam every observer audits — leave it queryable.
