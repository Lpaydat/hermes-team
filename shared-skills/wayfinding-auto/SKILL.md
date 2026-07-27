---
name: wayfinding-auto
description: Autonomous overlay for wayfinder — PO drives the map as asker, VB answers product questions over intercom, every resolution cites its source. Force-loaded by wayfinding cards alongside wayfinder.
disable-model-invocation: true
---

# Wayfinding — autonomous overlay (PO asks, VB answers)

This overlay runs wayfinder with no human in the loop — the two-agent substitute for that human.
The `wayfinder` skill (force-loaded alongside) and `docs/agents/issue-tracker.md` own the
invariants; this file adds the asker/answerer wiring, the citation rule, and the gate handoff.

## Role wiring

- **product-owner (you) = the asker.** Drive the map: chart it, choose frontier tickets, pose
  questions, record resolutions. Product answers come from VB, not from you.
- **venture-builder = the answerer.** VB owns product intent (the founder). Route product
  questions over intercom — `intercom`, `ask`, `to: venture-builder`, `topic: <map bead id>`
  (per-topic session keeps parallel ventures from mixing context); include the idea-brief bead
  id and the ticket's Question.
- **VB offline → spawn.** On `target_not_connected`, resend as `send` with `spawn: true`; the
  reply is injected in your session on a later turn (stay alive, re-check after your next tool
  call, allow a few minutes before escalating).
- **Two sessions, never one.** Posing and answering in one session is the self-answering
  failure wayfinder forbids — route the question to VB instead.
- **Humans are escalation targets.** Route asynchronously; operator silence is not an answer.

## Ticket routing by type

- `wayfinder:grilling`, prototype-reaction — PO↔VB over intercom (above).
- `wayfinder:research` / `:task` — researcher/scout, ops/developer via the dispatch queue;
  leave on the frontier.
- `wayfinder:architecture` — architect via the same queue; leave on the frontier (resolution
  is an ADR per `docs/agents/adr-convention.md`, cited by number). You stay the asker.
- `wayfinder:prototype` (building it) — developer queue; the *reaction* to it is PO↔VB.

## Citation rule (anti-hallucination — hard requirement)

Cite a source for every VB answer and resolution comment: the idea-brief bead
(`hermes-teams-<id>`), a prior map decision (closed ticket id), or the intercom exchange
(`intercom topic <map-id>, VB reply` — quote the decisive line).

An unsourced answer is an ESCALATION, not a guess: flag it (`bd tag <ticket-id> human` + an
`ESCALATE:` comment naming the gap — the operator's `bd human respond <ticket-id>` closes it,
and that human reply IS the citation), ping the operator (card on `hermes-hq`,
`--assignee default`, `[ESCALATION] <ticket name>` + map/brief pointers), then move on — an
escalation does not block other tickets. Cite every product intent before it enters the map;
when an escalated ticket is later closed by `bd human respond`, carry its answer to the map
index citing the human's comment.

## One unit per session — the card shapes

- **chart-the-map card**: name the destination from the idea brief, create the map bead, create
  the tickets you can specify now, wire blocking edges second-pass, sketch the fog into
  Not-yet-specified — then COMPLETE. Resolve tickets on a separate work-the-map card.
- **work-the-map card**: claim ONE frontier ticket (`bd update <id> --claim`), resolve it,
  record the cited resolution, graduate fog — then COMPLETE. One ticket per card.

## Map completion → architecture gate

When a map's frontier empties, route through the architecture gate BEFORE to-tickets — the
architect owns the architecture verdict; you stay the product authority. Wire the **blocked-by
edge first** so a session death mid-setup leaves a safe, visible deadlock (to-tickets blocked)
rather than an ungated proceed. Full procedure: see `architecture-gate.md`.

## Completion discipline

Complete the card with a summary naming the map and what changed (charted N tickets /
resolved <ticket name>), and stamp metadata `{"map": "<map-bead-id>", "charted": N}` or
`{"map": "<map-bead-id>", "resolved": "<ticket-id>", "cited": "<source>"}`.
