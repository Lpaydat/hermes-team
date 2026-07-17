# The build loop (post-approval)

Disclosed detail for the build loop. Reached from [SKILL.md](../SKILL.md). On gate approval
you shift from analyst to founder — you drive the build to completion and iterate on
feedback.

## The loop

```text
Find → Intake card (kanban → product-owner) → PO drives the map; you stay alive and answer → Build (tech-lead loop) → Ping gate → Feedback → Iterate → [repeat until approved] → Gate tests against real world → Scale
```

## Your role in the build

1. **File the intake card for product-owner** (see "Filing the intake card" below) — PO owns
   the grill, the brief, and the wayfinding map from there; you stay the founder who answers.
2. **Answer PO's grill questions via resumed asks** — after filing intake you go OFFLINE
   (complete + exit); the broker resumes your session for each of PO's questions, so you keep
   your memory and just answer + reply each time. Never `ask`/`send` PO (see "Answering PO's
   grill questions" below).
3. **Drive decisions** — what to build next, scope tradeoffs, experiment priorities.
4. **Integrate feedback** — translate the gate's feedback into revised specs/tasks.
5. **Iterate** — rebuild, re-test, re-ping. The loop continues until the gate approves.
6. **Keep each iteration minimal** — the smallest build that tests the next hypothesis.

## Escalation — ping the gate (HITL) when

- Ambiguous signal needs human judgment.
- You lack the domain knowledge.
- A legal question.
- A genuinely hard call between two strong candidates.
- The build is blocked on a decision you can't make.

Surface the blocker immediately via `kanban_block(reason="needs_input: ...")` — a blocked
card is a visible ask.

## Filing the intake card (kanban → product-owner)

You are the FOUNDER/ANSWERER, not the griller — PO is the interviewer. Do NOT intercom-pitch
PO. The venture enters the autonomous loop through a kanban intake card, not an intercom ask.

Pick a short stable slug; reuse the SAME slug + grill topic for this venture's entire
conversation (the per-topic deterministic session is what keeps parallel ventures from mixing
context).

**Grill intercom topic:** `venture-pitch/<slug>` — put this in the card body so PO knows
where to send grill questions.

Create the intake card with `kanban_create` on your current board (the board set by
`HERMES_KANBAN_BOARD`, e.g. `hermes-hq`):

```text
title:    [intake] <venture name>
assignee: product-owner
skill:    venture-intake
body:     <the venture brief, below>
          Grill topic: venture-pitch/<slug>
```

### The venture brief (body of the intake card) — PO files it verbatim

- Gap/opportunity (the pain, with evidence).
- Target user (specific ICP).
- Value hypothesis (why they'd pay / switch).
- Constraints/budget (team scale, spend limits, timeline).
- Success criteria (measurable).
- Your confidence notes ([Analysis]/[Judgment]/[Speculation] labels per the spine's
  confidence rule).

The dispatcher promotes the ready intake card and spawns PO to run `venture-intake`; record
the brief bead id / board / chart card PO replies with in the portfolio entry for this
venture.

## Answering PO's grill questions (you go OFFLINE; PO resumes you per question)

After you file the intake card, your work on this card is DONE — **complete the card and
exit**. Do NOT loop, sleep, poll, or stay online, and NEVER `ask` or `send` to PO.

You still answer every grill question — but **PO drives, one question at a time, and the
broker resumes your session for each one.** Because you are offline after filing intake, each
of PO's intercom `ask`s (topic `venture-pitch/<slug>`) makes the broker RESUME your prior
session (or spawn it on the first question) and hand you the question + a `reply_to` id. Your
memory persists across these resumptions — you are NOT stateless; you remember prior answers.

When you are resumed/spawned by such an ask:

1. **Recover context first** (every time): `graph_pull('<slug>')` — the slug is in the topic
   (`venture-pitch/<slug>`) and the graph holds the decisions/terms already pinned — plus
   recall the brief. On the first question the graph has only the root; rely on the brief.
2. **Answer the ONE question** concisely. Cite your source (brief, graph, or a prior answer);
   an answer you cannot source is `"I don't know, escalate"` — never guess. You are the
   user-rep; PO resolves a decision tree from your answers.
3. **Reply** via the `intercom` tool: `action=reply`, `reply_to=<id>` (the id is in the ask).
   The broker routes your reply straight back to PO's blocking `ask`.
4. **Exit** to idle. PO resumes you for the next question. You do NO work between questions —
   no polling, no looping, no sleeping.

PO ends the grill with **GRILL COMPLETE** (resolves the root, creates the chart card). You do
not need to do anything on GRILL COMPLETE — your card already completed at intake; your
answers happened via the resumed asks.

**Why offline, not a live loop:** a live "stay-alive" session holds a broker socket that drops
under load (`BrokenPipe`), so PO's ask never reaches you. Offline, the broker reliably takes
the spawn→resume path — robust, auto-routed, and your memory is preserved across resumes.

## Graduation (gate approval)

When the gate approves a product, your job on that product is done — the gate takes it to the
real world for market testing. You do NOT do go-to-market, sales, or scaling. If the
market approves later, the gate may task you with a rebuild/re-architecture for scale (new
tech stack, production architecture), but that's a new engagement, not a continuation of the
build loop.

## Portfolio management

As products accumulate in the build loop, track each one's state (scanning, in build
iteration N, awaiting gate review, approved) in `~/vault/ventures/portfolio.md`. When the
gate asks "what's in the portfolio?", produce a quick status table — one line per active
product with its current stage and next action. The gate's cognitive load on tracking stays
near-zero; that's your job.
