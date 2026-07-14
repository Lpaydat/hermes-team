---
name: venture-intake
description: "Use when venture-builder (or anyone) pitches a product or venture idea — over intercom (topic venture-pitch/*), in chat, or forwarded by the operator. Captures the pitch as a citable idea-brief bead, creates the venture's board and autonomous chart-the-map card, and acks the pitcher with the ids. Triggers: 'pitch', 'venture', 'new product idea', 'idea brief', 'file this as a brief', 'start the map'."
---

# Venture intake — pitch → idea brief → chart card

You are the tech company's representative receiving a founder's pitch. Your job is to turn
the conversation into durable, citable tracker state and kick off autonomous planning —
in ONE session, ending with an ack to the pitcher.

## 1. Parse the pitch against the brief schema

Required fields: gap/opportunity · target user · value hypothesis · constraints/budget ·
success criteria · pitcher's confidence notes.

If a required field is missing, ask the pitcher back ONCE on the SAME intercom topic for
the gaps. If it is still missing after that, file the brief with the absent field marked
`[not provided — escalated]` and flag the brief bead for the human (`bd human <brief-id>`),
asynchronously. Never invent a field: the brief is the venture's citable root of product
intent — an invented field poisons every downstream decision.

## 2. File the idea-brief bead (root repo tracker)

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
Pitched by <profile> over intercom, topic <venture-pitch/slug>, <date>.
Key line: \"<the pitch's decisive sentence, quoted verbatim>\""
```

The `## Source` section is mandatory — every brief cites the exchange it came from.

## 3. Create the venture board + chart card

Each venture is isolated on its own board:

```bash
export HERMES_KANBAN_HOME=/home/lpaydat/.hermes-teams/startup
hermes kanban boards create venture-<slug> --name "venture: <venture name>"
HERMES_KANBAN_BOARD=venture-<slug> hermes kanban create \
  "[chart] <venture name>: chart the wayfinding map" \
  --assignee product-owner --skill wayfinding-auto --skill wayfinder \
  --workspace dir:/home/lpaydat/.hermes-teams \
  --body "CHART-THE-MAP card (autonomous). You are product-owner, the ASKER, per the
force-loaded wayfinding-auto overlay + wayfinder skill.
IDEA BRIEF: bead <brief-id> (bd show <brief-id>). Chart from the brief; questions you
cannot answer from it become tickets or fog, never guesses.
TRACKER: beads — docs/agents/issue-tracker.md 'Wayfinding operations'. Run bd from
/home/lpaydat/.hermes-teams.
DO: name the destination; create the map epic (label wayfinder:map); create the child
tickets you can specify now (label wayfinder:<type>, --no-inherit-labels, '## Question'
bodies); wire blocking edges second-pass; sketch the fog into Not-yet-specified. Then
COMPLETE this card — chart only, resolve nothing. Stamp metadata
{\"map\": \"<map-id>\", \"charted\": N}."
```

## 4. Ack the pitcher

Reply on the same intercom topic: brief bead id, board name, chart card id — e.g.
"Brief filed: hermes-teams-XYZ. Map charting queued: board venture-<slug>, card t_...".
The founder records these in their portfolio; the ack is what closes the intake loop.

## Discipline

- Intake is one session: parse → brief → board+card → ack. Do not also chart the map here
  (the chart card does that in its own session, per one-unit-per-session).
- The human is asynchronous-only (`bd human`); never block the intake waiting for them.
- Report state, not prose: the brief id, board, and card id ARE the deliverable.
