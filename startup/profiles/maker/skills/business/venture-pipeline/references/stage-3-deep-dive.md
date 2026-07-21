# Stage 3 — Deep dive

Disclosed detail for the Deep Dive stage. Reached from [SKILL.md](../SKILL.md).

For each survivor, build the full analysis. This is where Lean Startup methodology takes
over — load `lean-startup` as your operating system.

## Tool for deep validation

- **`startup-validator`** — Comprehensive market validation via web search: TAM/SAM/SOM
  sizing, competitive landscape (Porter's Five Forces), problem-solution fit assessment, and
  market positioning analysis. Includes research templates and a market analyzer script. Use
  for the evidence-heavy validation that separates a real opportunity from a vibe.

## Deliverables for each survivor

1. **Lean Canvas** — the one-page business model (see `templates/lean-canvas.md`).
2. **Assumption map** — all assumptions, scored by Impact × Uncertainty.
3. **Riskiest assumption** — the one that kills the idea if false. Test it first.
4. **Experiment design** — the cheapest test for that assumption. **Funnel math must close
   before the experiment is committed** (see "Experiment funnel math must close" below).
5. **"Why now" defense** — a clear, defensible timing argument.
6. **Monetization path** — how this makes money (subscription, one-time, usage, marketplace
   take rate, etc.).
7. **Competitive landscape** — **verified**, not recalled (see "Competitive landscape must be
   verified" below).

## Competitive landscape must be verified — not recalled

The competitive landscape deliverable is where the cheap, silent kills happen. Recalling a
comp set from memory produces two recurring failure modes, both of which have killed ideas
post-build in this pipeline:

1. **Conflation / hallucinated competitor names.** Adjacent-sounding products get swapped
   (e.g. "Fireflies" (a meeting notetaker) cited as an incident tool when "FireHydrant" was
   meant). This silently invalidates the landscape.
2. **Missing the bundled-free incumbents.** Asserting "no tool covers X" when one of the
   majors (PagerDuty, Opsgenie, incident.io, FireHydrant, Rootly, etc.) already ships X as a
   bundled, often free, feature — the gap collapses without any demand-side work needed.

**Rule:** the comp set is built from a verified feature audit against live product/pricing
pages, not from memory. For each named competitor: open its site, confirm (a) it exists with
that name, (b) what category it actually belongs to, and (c) whether its current feature set
covers the thesis feature. Pay special attention to **bundled analytics / reporting /
insights** tabs — these are where incumbents quietly absorb a thesis for free. If a named
competitor already ships the thesis feature (even bundled, even free), that is a kill axis on
its own and must be surfaced explicitly before the idea moves to design spec.

`startup-validator`'s competitive-landscape research templates can do the breadth pass; the
feature audit against live product pages is still required by hand.

## Experiment funnel math must close

An experiment design is not just "we'll do X and look for Y." It is a conversion funnel:
input actions → stage conversions → target signal. If the funnel math does not compound to
the target signal at realistic conversion rates, the experiment is **structurally
underpowered** and will produce noise, not signal — an inconclusive result that is just a
slower kill, not a pass.

**The failure mode this exists to prevent.** In grill grilllive22 (ReplyDeck, 2026-07), a
validation experiment was committed with targets — "100–150 community conversations → 15
waitlist + 3 serious-intent in 3 weeks" — that were round-number wishes, not the output of a
model. At realistic community-seeding benchmarks (15–25% conversation-to-visit, 10–20%
visit-to-waitlist, 10–15% waitlist-to-intent), the compound rate (~0.15–0.75%
conversation-to-intent) would have required 400–2,000 authentic conversations to hit 3
serious-intent — roughly an order of magnitude beyond what a solo human proxy can produce in
3 weeks. The experiment could not have reached a clean signal regardless of product quality.
The target signal, if met, would have been statistical noise; if missed, inconclusive. Both
outcomes waste pipeline capacity.

**Rule: state the funnel before committing the experiment.**

1. **Name each stage** of the funnel (e.g., outreach → landing-page visit → waitlist →
   serious-intent).
2. **State the assumed conversion rate at each stage** and the benchmark it rests on (cite
   the source — SaaS community-led-growth benchmarks, cold outreach benchmarks, etc.). Do not
   pick round numbers that feel right.
3. **Multiply through.** Does the compound rate hit the target signal from the planned input
   volume?
4. **Calibrate input volume to achievable capacity.** A solo human proxy's realistic
   authentic-engagement capacity (e.g., 5–15 genuine conversations/day/community across a
   handful of communities) is the binding constraint. If the required input volume exceeds
   achievable capacity, the experiment cannot produce a signal in the time budget.

**Pre-experiment kill criterion.** If the funnel math does not close — the target signal
requires more input than capacity allows, at realistic conversion rates — that is a
pre-experiment kill criterion on the experiment *design*, not a reason to run it anyway.
Either (a) resource the experiment properly (more capacity, more time), (b) pick a different
validation instrument with achievable math, or (c) accept that the venture cannot be
validated at solo-dev scale and surface that to the gate.

## Kill at deep dive if

- No defensible "why now" — the timing window doesn't hold up under scrutiny.
- No viable monetization path — can't articulate how revenue works.
- Riskiest assumption is unfalsifiable — you can't design an experiment to test it.
- The problem is too niche — market is too small to sustain a venture.
- The problem is too broad — no focus, no ICP, "everyone" is not a customer.
- **A named competitor already ships the thesis feature** (verified against its live product
  page), especially as a bundled/free feature — the wedge has already been absorbed.
