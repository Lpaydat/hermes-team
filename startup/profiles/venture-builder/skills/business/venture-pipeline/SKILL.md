---
name: venture-pipeline
description: The venture loop — scan demand signals, kill-gate the weak, spec and build survivors, iterate until the gate signs off.
disable-model-invocation: true
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [venture, pipeline, opportunity-scanning, idea-scoring, project-spec, kill-gate]
    related_skills: [lean-startup, requesthunt, review-mining, startup-validator, mvp-scoping, team-delegation]
---

# Venture Pipeline — the kill-gate system

Find real human problems, run them through a kill-gate pipeline, and — for survivors the
gate approves — **build the actual MVP/POC**, not just a paper spec. Volume + evidence-based
filtering is the analysis strategy; tight iteration is the build strategy. A kill is a
conclusion the evidence forces — not a default or a cost-saver; default to refining the
venture and resolving open branches, and kill only when a load-bearing premise is refuted
and every pivot has been weighed.

## Two gate interactions — keep them distinct

1. **The Digest** (every 3 days, top 3 survivors) — the gate picks which ideas graduate to
   building. Output: ranked specs + recommendations.
2. **The Product Review** (on demand, when a build is ready) — the gate tests the built
   product and gives feedback. Output: the live MVP/POC plus what changed since last review.

A portfolio of products runs the loop in parallel — expected. The gate shifts toward
test/review as the portfolio grows; your job stays find/build/iterate.

## The pipeline — 5 stages

Each stage ends on a checkable criterion. The heavy detail behind each (rubrics, formats,
tool pointers) is disclosed to its reference file — load it when you run that stage.

### 1. Scan
Ingest demand-side signals — complaints, unmet needs, willingness-to-pay evidence,
underserved niches. Capture everything; filter nothing yet.
Detail: [`references/stage-1-scan.md`](references/stage-1-scan.md).
**Done:** a raw list of candidate signals, each with source URL and quote.

### 2. Filter & rank — kill 90%
Score every signal on five dimensions; kill what doesn't pass the bar.
Detail: [`references/stage-2-filter.md`](references/stage-2-filter.md).
**Done:** a survivor shortlist (~10% of raw signals) with scores and rationale; every cut
idea has a one-line kill reason.

### 3. Deep dive
For each survivor, build the full analysis. Lean Startup is the operating system here —
load `lean-startup`; reach for `startup-validator` on evidence-heavy validation.
Detail: [`references/stage-3-deep-dive.md`](references/stage-3-deep-dive.md).
**Done:** each survivor carries a lean canvas, assumption map, riskiest assumption,
experiment design, "why now" defense, and monetization path.

### 4. Design spec
Author the build-ready spec for survivors that pass deep dive. Reach for `mvp-scoping` for
the scope cut; use `templates/project-spec.md`.
Detail: [`references/stage-4-spec.md`](references/stage-4-spec.md).
**Done:** spec carrying problem, ICP, riskiest assumption, lean-canvas summary, experiment
type, tech stack, kill metric, and pivot/kill criteria — every claim labeled.

### 5. Report
Deliver the ranked digest to the gate (every 3 days, top 3 survivors).
Detail: [`references/stage-5-report.md`](references/stage-5-report.md).
**Done:** ranked digest with recommendations; killed ideas carry one-line reasons; the gate
picks what graduates to building.

## The build loop (post-approval)

On gate approval you shift from analyst to founder — you drive the build, not just hand off
a spec. Detail (intake card, wait-and-answer loop, escalation, portfolio) in
[`references/build-loop.md`](references/build-loop.md).

```text
Find → Intake card (kanban → product-owner) → PO drives the map; you stay alive and answer → Build (tech-lead loop) → Ping gate → Feedback → Iterate → [repeat until approved] → Gate tests against real world
```

Each iteration is the minimum to test the next hypothesis. Surface blockers to the gate
immediately via `kanban_block(reason="needs_input: ...")` — a blocked card is a visible ask.

**Answer PO's grill questions via resumed asks — load-bearing.** You are the founder/answerer;
PO is the interviewer — never `ask` or `send` PO anything. File a kanban intake card
(`[intake] <venture>`, assignee `product-owner`, skill `venture-intake`, body = the venture
brief + grill topic `venture-pitch/<slug>`), then **complete the card and go offline**. PO
drives: each of PO's intercom `ask`s on `venture-pitch/<slug>` makes the broker RESUME your
session (spawn on the first question) and hand you the question + a `reply_to` id — your memory
persists across resumptions, so you are not stateless. Recover (`graph_pull('<slug>')` +
brief), answer the one question (cite source; unsourced = "I don't know, escalate", never a
guess), reply via `intercom action=reply reply_to=<id>`, then exit to idle. No looping, no
polling, no staying online — being offline is what lets the broker resume you reliably. Full
detail in [`references/build-loop.md`](references/build-loop.md).

On gate approval, your job on that product is done — the gate takes it to real-world market
testing. A rebuild-at-scale is a new engagement, not a continuation.

## Confidence & honesty — every claim labeled

Calibrate the gate's trust by labeling every claim you make:

- **[Analysis]** — derived from data/signal evidence.
- **[Judgment]** — reasoned inference from experience/heuristics.
- **[Speculation]** — explicit guess, no strong evidence.

Kill what the evidence kills — even ideas you like. Scope each spec to a validation-sized
experiment. After approval, bring the gate the built product itself — a live URL/repo/
artifact path in every review ping.
