---
name: project-kickoff-grill
description: "Part 1 of project kickoff — discuss architecture with the user, then adversarially grill every decision until it holds under stress. Outputs persisted grill decisions. Use when the user brings a new project idea, wants to migrate an existing system, or says 'let's build X'. MUST complete before project-kickoff-spec."
---

# Project Kickoff — Grill

You own the conversation from "the user has an idea" to "every architecture decision has been stress-tested." This is Part 1 of the project kickoff pipeline. Part 2 (`project-kickoff-spec`) cannot start until this skill's output exists.

The leading word is _adversarial_: discussion is not grilling. You find the scenario where the user's answer breaks, show them the breakage, and keep pushing until the decision holds under stress.

## Step 1: Discuss

Ask the user about the three questions that change architecture:

1. **Hardware** — what devices, what peripherals (printers, scanners), what connection types
2. **Distribution** — internal tool vs product, single-tenant vs multi-tenant
3. **Scale** — how many users/devices, expected growth

Be direct. State recommendations as decisions, not menus. This user HATES unnecessary complexity — when one path is obvious, say so and move on.

**Completion criterion:** you can state the problem, the constraints, and the target architecture in 2-3 sentences.

## Step 2: Grill (NON-NEGOTIABLE)

Load the `grilling` skill. Work through every architecture decision from Step 1.

For each decision, ask: "what happens in the worst case?" Don't accept the first answer if a stress scenario can break it.

**Stress-test every decision** against these categories (see `references/grill-stress-categories.md` for the full checklist with examples):
- Single points of failure (what if X dies?)
- Data loss (what if two devices write simultaneously?)
- Money safety (can a sync conflict corrupt a balance?)
- Compliance (tax receipts, VAT, legal record-keeping)
- Offline/degraded operation
- Physical workflow edge cases
- Inventory and stock reality
- Debt and credit workflows
- Pricing model reality

**Completion criterion:** every architecture decision has been challenged with at least one concrete failure scenario and either held or changed.

## Step 3: Persist grill output

Write grill decisions to `~/projects/<slug>/.driver/grill/decisions.md` (or `~/projects/<slug>/.context/grill/decisions.md` if `.context/` convention is used).

This file is the gate for Part 2 (`project-kickoff-spec`). Without it, Part 2 must refuse to proceed.

**Completion criterion:** grill decisions file exists with every locked decision, resolved stress scenario, and the old → new field mapping (for migrations).

## For migrations

Before grilling, pull the old domain model from source. This makes the grill 10x sharper — you can challenge "does the old model support X?" with evidence.

```bash
gh api repos/<owner>/<repo>/contents/<path>/models/product.py --jq '.content' | base64 -d
```

Record the old → new field mapping in the grill decisions file.

## What this skill does NOT do

- Does NOT write the spec (that's `project-kickoff-spec` Step 1)
- Does NOT create the architect card (that's `project-kickoff-spec` Step 2)
- Does NOT decompose into tickets (that's `project-kickoff-spec` Step 3)
- Does NOT set up project infrastructure (that's `project-kickoff-spec` Step 4)

If you find yourself about to run `to-spec` or create beads, STOP. This skill's job ends when grill decisions are persisted. Hand off to `project-kickoff-spec`.

## Failure modes

- **Skipping the grill.** The most common and most damaging shortcut. Discussion feels like enough — it isn't. Specs written from unchallenged discussion contain holes that surface during implementation, when they're 10x more expensive to fix. This happened in a real session (2026-07-26): the user caught the missing grill, and the retrofit cost more than doing it upfront.
- **Confusing discussion with grilling.** "Here are the options, which do you want?" is discussion. "You said PWA, but here's a scenario where a PWA can't access the receipt printer. What's your plan?" is grilling. Only the second produces decisions that hold up.
- **Stopping early.** 50+ questions is normal. The grill is done when you genuinely cannot find a new angle — not when you feel like you've covered the basics.

## References

- `references/grill-stress-categories.md` — 9-category stress checklist with concrete examples
- `references/migration-domain-model-extraction.md` — pulling old domain models from GitHub
