# Stage 5 — Report

Disclosed detail for the Report stage. Reached from [SKILL.md](../SKILL.md).

Deliver the ranked digest to the gate (the human). Cadence: **every 3 days, top 3
survivors.**

## Digest format

```text
# Venture Digest — [Date]

## Ranked Survivors (Top 3)

### #1: [Idea name] — Score: [X/25]
**One-liner:** [What it is in one sentence]
**Problem:** [The pain, with evidence quote]
**Riskiest assumption:** [The hypothesis]
**Experiment:** [What we'll test and how]
**Kill metric:** [The threshold]
**My recommendation:** [Why this is #1 — be opinionated]
**Spec:** [link to full project spec]

### #2: ...

### #3: ...

## Killed This Cycle
- [Idea] — Killed because: [one-line reason]
- ...

## Needs Your Input
- [Any HITL blockers or hard calls]
```

The gate reviews, picks which graduate to building, and provides feedback. Approved products
enter the build-and-iterate loop (see "The build loop" in [SKILL.md](../SKILL.md)).

## Product Review ping format

Use this when a build is ready for the gate to test:

```text
# Product Ready for Review — [Idea name]

**What it is:** [One-liner — the product, not the problem]
**Live URL / repo / artifact:** [Where to interact with it]

## What I built (this iteration)
[What's working right now — be specific about what the gate can actually do/test]

## What changed since last review
[Bullet list — only if this is iteration 2+]

## What I need you to test
[The specific hypothesis this build tests. What signal am I looking for?]

## Known gaps / intentionally out of scope
[What's NOT built yet and why — keep scope honest]

## My ask
[Specific: "test the onboarding flow and tell me if the value prop is clear within 30
seconds" — make the ask concrete so the gate doesn't have to guess.]
```

## The gate is a VC/board/advisor

Bring the built product. They test, they give feedback, you iterate. Every product review
ping carries a live URL / repo / artifact path so the gate can always find it.
