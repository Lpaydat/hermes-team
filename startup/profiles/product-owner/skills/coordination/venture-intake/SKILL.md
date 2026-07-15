---
name: venture-intake
description: "Use when venture-builder (or anyone) pitches a product or venture idea — over intercom (topic venture-pitch/*), in chat, or forwarded by the operator. Captures the pitch as a citable idea-brief bead, GRILLS the pitcher (VB) to confidence, pinning the venture's shared language into the context_graph (term nodes + ADRs), then creates the venture's board and autonomous chart-the-map card, and acks the pitcher with the ids. Triggers: 'pitch', 'venture', 'new product idea', 'idea brief', 'file this as a brief', 'start the map'."
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

## 3. Grill to confidence in the context_graph — drives the wrapped skill

You (PO) are the GRILLER; venture-builder is the user-rep (the GRILLEE) — it answers
decisions over the SAME intercom topic.

Force-load `grill-with-docs` (grilling + domain-modeling) + `decision-tree-grill`.
`decision-tree-grill` WRAPS the official `grilling` skill — it owns the graph store
(term nodes replace CONTEXT.md), the MANDATORY stateless recovery, and the objective
done-check; `grilling` owns the interview mechanics (seed-one-question, walk-each-
branch, fork-as-answers-reshape). Drive the grill's decision tree **in the
context_graph** (the `context_graph` toolset) to completion IN THIS SESSION. The tree
lives in the shared graph DB — **not beads, not CONTEXT.md**. The interview mechanics
are `grilling`'s; do NOT re-implement them here — defer to the two loaded skills.

### 3a. Recover the tree FIRST (mandatory stateless recovery)

The FIRST action of this step is the recovery sequence from `decision-tree-grill`:
`graph_pull('<slug>')` → filter to `type=root` → `graph_tree(root)` → `graph_frontier()`.
If recovery returns no `type=root` node, seed the root (`graph_add_node node_type=root`,
title = venture name; content = brief-bead-id + pitch topic; topics=['<slug>']) and let
`grilling` pose the entry question. Rootless `graph_tree`/`graph_stats` are forbidden.

### 3b. Grill (defer the mechanics to grilling + the substrate)

Run the interview per `grilling`: it walks the frontier one question at a time,
resolving `fact` by lookup and `decision` by posing to VB over the intercom (recorded
as `graph_resolve_node content='VB: <answer>'`), forking new branches as answers
reshape the tree. `decision-tree-grill` stores each resolution; `domain-modeling` pins
each clarified term as a `graph_add_node node_type=term` (content = VB-approved
definition, tagged with the topics it spans) — **term nodes replace the CONTEXT.md
glossary**. Tag every node with ALL topics it touches (multi-topic). The grill is
uncapped; a test run may cap it externally (turn budget / monitor threshold), never in
the skill. Viability doubts → a new `decision` node to VB; never moot-close.

### 3c. Complete (the substrate's three-part done-check)

`decision-tree-grill` fires `GRILL COMPLETE` only when ALL THREE hold: (1)
`graph_frontier()` empty, (2) every `decision` resolved with a `VB:` answer, (3) **≥1
`term` node exists** (language pinned). Only then `graph_resolve_node(root,
content='GRILL COMPLETE: <slug>')` + send `GRILL COMPLETE` over the grill intercom
topic (venture-builder is WAITING on this signal). Stamp the brief bead with the root
node id (`graph_tree(root)` is the deliverable). If (1) holds but (2)/(3) don't, the
grill was fake-completed — re-open + resolve properly before signalling.

**Hard rules:** NEVER moot-close a decision (VB owns decisions). Viability doubts → new
`decision` node to VB. ≥1 `term` node is mandatory before root resolve.

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
SHARED LANGUAGE: context_graph — graph_pull('<slug>') returns the venture's pinned term nodes
(type=term, content=VB-approved definition) + resolved decisions from the grill (step 3). ADRs
under docs/ventures/<slug>/docs/adr/. Chart from BOTH — the brief is intent, the graph's term
nodes are the vocabulary every ticket + the map's Notes inherit. Questions you cannot answer
from either become tickets or fog, never guesses.
TRACKER: beads — docs/agents/issue-tracker.md 'Wayfinding operations'. Run bd from
/home/lpaydat/.hermes-teams.
DO: name the destination; create the map epic (label wayfinder:map); create the child
tickets you can specify now (label wayfinder:<type>, --no-inherit-labels, '## Question'
bodies); wire blocking edges second-pass; sketch the fog into Not-yet-specified. Then
COMPLETE this card — chart only, resolve nothing. Stamp metadata
{\"map\": \"<map-id>\", \"charted\": N}."
```

## 5. Ack the pitcher

Reply on the same intercom topic: brief bead id, grill root node id + term count, board name,
chart card id — e.g. "Brief filed: hermes-teams-XYZ. Grill complete: graph root gn-…, N terms
pinned (graph_pull('<slug>')). Map charting queued: board venture-<slug>, card t_...".
The founder records these in their portfolio; the ack is what closes the intake loop.

## Discipline

- Intake is one session: parse → brief → grill-to-confidence → board+card → ack. The grill
  loop runs multiple passes WITHIN this session over intercom; do not also chart the map here
  (the chart card does that in its own session, per one-unit-per-session).
- The human is asynchronous-only (`bd human`); never block the intake waiting for them. The
  grill is uncapped — it runs until the substrate's objective done-check passes (frontier
  empty + every decision `VB:`-answered + ≥1 term). If a test run needs a bound, impose it
  externally (turn budget / monitor threshold), never as a baked pass/turn cap. "Confidence"
  is that graph state, not a self-reported 0–1 score.
- Report state, not prose: the brief id, grill root node id + term count
  (`graph_pull('<slug>')`), board, and card id ARE the deliverable — there is no CONTEXT.md
  path (terms are graph `term` nodes).
- `term` nodes (context_graph) are a glossary only — pure vocabulary, no implementation/spec.
  ADRs are sparing: only hard-to-reverse, surprising-without-context, real-trade-off decisions.
