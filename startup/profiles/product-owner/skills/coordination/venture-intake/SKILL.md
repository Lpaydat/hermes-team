---
name: venture-intake
description: "Use when a kanban [intake] card assigned to product-owner (skill venture-intake) arrives — venture-builder filed a venture brief in the card body. PO parses the brief, files the idea-brief bead, grills VB over intercom using the NATIVE grill-with-docs skill (PO initiates, VB answers), then queues the chart card. Triggered by the intake card via the dispatcher."
---

# Venture intake — intake card → idea brief → grill → chart card → ack

Triggered by a **kanban intake card**: venture-builder creates `[intake] <venture>` (assigned
product-owner, skill venture-intake) with the venture brief + a `Grill topic: venture-pitch/<slug>`
line in the card body; the dispatcher spawns PO to run this skill.

## 1. Parse the brief from the kanban card body

The venture brief lives in the **intake card body** — gap/opportunity · target user · value
hypothesis · constraints/budget · success criteria · confidence notes. The same body carries the
`Grill topic: venture-pitch/<slug>` line (used in step 3). Read the card body and parse the brief.

For any missing field, mark it `[not provided — escalated]` in the filed brief and flag the
human (`bd human <brief-id>`). Quote the brief verbatim — every field traces to the card body.

## 2. File the idea-brief bead

Run bd from the team repo root (`cd /home/lpaydat/.hermes-teams`):

```bash
bd create --title="idea brief: <venture name>" --type=task --labels=venture:brief \
  --description="## Idea brief
- Gap/opportunity: ...
- Target user: ...
- Value hypothesis: ...
- Constraints/budget: ...
- Success criteria: ...
- Confidence notes: ...

## Source
Intake card <card-id> on board <board>, filed by venture-builder, <date>.
Grill topic: venture-pitch/<slug>. Key line: \"<the brief's decisive sentence, quoted verbatim>\""
```

The `## Source` section is mandatory — every brief cites the intake card it came from.

## 3. Grill VB to confidence — NATIVE grill-with-docs + intercom (nothing else)

You (PO) are the **griller/interviewer**; venture-builder is the **user (grillee)**. Treat VB as
the user — the grill runs until VB confirms shared understanding.

**Force-load `grill-with-docs`** (the official interview: `grilling` + `domain-modeling`) and
follow it EXACTLY. It drives the whole interview:
- ask **one question at a time**; wait for VB's answer before the next;
- **follow up VB's answer** — drill the sub-questions his answer opens (that is the depth-first
  walk down each branch). Do NOT jump to a different aspect after each answer; stay on the branch
  until it's resolved;
- look up facts yourself (don't ask VB what you can find); put each *decision* to VB and wait;
- cover every aspect; record decisions + terms in grill-with-docs' native docs (CONTEXT.md /
  glossary / ADRs) as the skill prescribes;
- stop only when VB confirms shared understanding (grilling: "Do not enact the plan until I
  confirm we have reached a shared understanding" — VB is the "I").

Read the grill topic `venture-pitch/<slug>` from the intake card body and reuse it for the whole
conversation.

**Pose each grill question to VB over intercom** — `intercom` tool, `to: venture-builder`,
`topic: venture-pitch/<slug>`, action `ask` (blocking). VB is offline (its intake card completed);
your `ask` resumes VB's session so it answers with memory intact across questions. If `ask` errors
`target_not_connected`, resend as `send` with `spawn: true`. VB answers on the same topic.

That is the entire grill: **`grill-with-docs` + intercom.** No graph, no custom storage skill, no
mechanical completion gate. The conversation drives the questions; CONTEXT.md records them. When
VB confirms shared understanding, go to step 4.

## 4. Create the venture board + chart card

Each venture is isolated on its own board:

```bash
export HERMES_KANBAN_HOME=/home/lpaydat/.hermes-teams/startup
hermes kanban boards create venture-<slug> --name "venture: <venture name>"
HERMES_KANBAN_BOARD=venture-<slug> hermes kanban create \
  "[chart] <venture name>: chart the wayfinding map" \
  --assignee product-owner --skill wayfinding-auto --skill wayfinder \
  --workspace dir:/home/lpaydat/.hermes-teams \
  --body "CHART-THE-MAP card (autonomous). IDEA BRIEF: bd show <brief-id>. GRILL OUTPUT: the
CONTEXT.md + glossary the grill produced (decisions + pinned terms). ADRs under
docs/ventures/<slug>/docs/adr/. Run wayfinding-auto + wayfinder; chart only. COMPLETE when done."
```

## 5. Ack the pitcher

Reply on the same intercom topic: brief bead id, where the grill output lives (CONTEXT.md path),
board name, chart card id — e.g. "Brief filed: hermes-teams-XYZ. Grill complete — decisions +
terms in <CONTEXT.md path>. Map charting queued: board venture-<slug>, card t_...". The ack
closes the intake loop.

## Discipline

- "Confidence" = shared understanding per `grill-with-docs`, **confirmed by VB** — not a
  self-reported score, not a mechanical gate.
- PO initiates the grill over intercom; VB answers. Never wait for VB to pitch — the brief
  already arrived as the intake card.
- The conversation drives question order (follow up answers = depth). Do NOT consult any graph
  or backlog to pick the next question.
- Report state, not prose: the brief id, CONTEXT.md path, board, and chart card id.
