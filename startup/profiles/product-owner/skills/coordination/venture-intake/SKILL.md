---
name: venture-intake
description: "Use when venture-builder (or anyone) pitches a product or venture idea — over intercom (topic venture-pitch/*), in chat, or forwarded by the operator. Captures the pitch as a citable idea-brief bead, GRILLS the pitcher (VB) to confidence to pin the venture's shared language (CONTEXT.md + ADRs), then creates the venture's board and autonomous chart-the-map card, and acks the pitcher with the ids. Triggers: 'pitch', 'venture', 'new product idea', 'idea brief', 'file this as a brief', 'start the map'."
---

# Venture intake — pitch → idea brief → grill-to-confidence → chart card

You are the tech company's representative receiving a founder's pitch. Your job is to turn
the conversation into durable, citable tracker state PLUS a pinned shared language, and kick
off autonomous planning — in ONE session, ending with an ack to the pitcher.

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

## 3. Seed + resolve the decision tree (in-session, max 4 initial nodes)

You (PO) are the GRILLER; venture-builder is the user-rep (the GRILLEE) — it answers
decisions over the SAME intercom topic.

Force-load `grill-with-docs` (grilling + domain-modeling). Drive the grill's decision tree
in beads to completion IN THIS SESSION:

### 3a. Seed (max 4 initial nodes)

`bd create` the root bead (label `decision-tree`, `dt:root`; body = venture name + brief-id).
Seed ONLY the **3-4 most critical** decisions/facts the venture faces — NOT every possible
question. **Max 4 initial child nodes** (beyond root). Fewer nodes = faster grill = fits the
session turn budget = consistent completion. `bd dep <node> --blocks <root>` for each.

### 3b. Resolve (walk the frontier)

Walk the frontier (`bd ready -l decision-tree`): resolve `dt:fact` (lookup) + `dt:decision`
(pose to VB over intercom, record `bd comment "VB: <answer>"`, close). Dynamic branching:
if an answer surfaces a new sub-decision, fork (create child bead) — but keep the frontier
**≤4 open nodes at any time** (fork sparingly). `domain-modeling` writes CONTEXT.md
(`docs/ventures/<slug>/CONTEXT.md`) as terms resolve.

### 3c. Complete

When no open `dt:fact`/`dt:decision` remain (frontier empty): verify CONTEXT.md exists (create
it NOW if not — write the glossary from resolved terms). Close the root. Stamp the brief with
the root id + CONTEXT.md path.

**Hard rules:** NEVER moot-close a decision (VB owns decisions). Viability doubts → new
dt:decision to VB. CONTEXT.md is mandatory before root close.

## 4. Create the venture board + chart card

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
IDEA BRIEF: bead <brief-id> (bd show <brief-id>).
SHARED LANGUAGE: docs/ventures/<slug>/CONTEXT.md (pinned in step 3, confidence <0.X>) +
ADRs under docs/ventures/<slug>/docs/adr/. Chart from BOTH — the brief is intent, CONTEXT.md
is the vocabulary every ticket + the map's Notes inherit. Questions you cannot answer from
either become tickets or fog, never guesses.
TRACKER: beads — docs/agents/issue-tracker.md 'Wayfinding operations'. Run bd from
/home/lpaydat/.hermes-teams.
DO: name the destination; create the map epic (label wayfinder:map); create the child
tickets you can specify now (label wayfinder:<type>, --no-inherit-labels, '## Question'
bodies); wire blocking edges second-pass; sketch the fog into Not-yet-specified. Then
COMPLETE this card — chart only, resolve nothing. Stamp metadata
{\"map\": \"<map-id>\", \"charted\": N}."
```

## 5. Ack the pitcher

Reply on the same intercom topic: brief bead id, confidence + CONTEXT.md path, board name,
chart card id — e.g. "Brief filed: hermes-teams-XYZ. Language pinned to 0.9x at
docs/ventures/<slug>/CONTEXT.md. Map charting queued: board venture-<slug>, card t_...".
The founder records these in their portfolio; the ack is what closes the intake loop.

## Discipline

- Intake is one session: parse → brief → grill-to-confidence → board+card → ack. The grill
  loop runs multiple passes WITHIN this session over intercom; do not also chart the map here
  (the chart card does that in its own session, per one-unit-per-session).
- The human is asynchronous-only (`bd human`); never block the intake waiting for them. The
  5-pass cap means you never grill indefinitely — if confidence won't reach 0.95, flag the
  gaps and proceed.
- Report state, not prose: the brief id, confidence, CONTEXT.md path, board, and card id ARE
  the deliverable.
- `CONTEXT.md` is a glossary only — pure vocabulary, no implementation/spec. ADRs are
  sparing: only hard-to-reverse, surprising-without-context, real-trade-off decisions.
