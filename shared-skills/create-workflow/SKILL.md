---
name: create-workflow
description: Authoring guide for composing skills into gated workflows — skills whose body chains other skills in sequence with checkable preconditions between them.
disable-model-invocation: true
---

A **workflow** is a skill whose body is a **composition** — it names other skills in order, with **gates** between them that block until the prior skill's output exists. A regular skill does work; a workflow orchestrates skills that do work.

This is the companion to `writing-great-skills`. That guide teaches how to write one skill well. This one teaches how to chain several.

## Three enforcement tiers

Before composing, know which tier of enforcement each gate needs. Not every dependency needs a skill — some are better enforced structurally:

1. **Card chain** — the strongest. Skills run in separate kanban cards, linked as parent→child sequences via `kanban_chains`. The dispatcher will not promote a child card until its parent completes — the gate is the board's dependency graph, not prompt text. Use when steps need fresh context windows (a multi-hour grill should not share context with a build phase).
2. **Skill gate** — medium. A workflow skill's body says "proceed to step 2 only when step 1's output exists at `<path>`." The agent loads the workflow and follows the steps in order within one session. Harder to skip than scattered prose, but the agent can still bypass by not loading the skill.
3. **Config** — coarse but absolute. `disabled_toolsets` in the profile config physically removes toolsets. Use for role boundaries ("this profile can never write code") that no gate should be needed for. Does not work for fine-grained sequencing ("load skill X before command Y").

The tier choice is the first decision. A chain that needs context isolation between steps should be card-enforced, not skill-enforced. A chain that fits in one session should be a workflow skill. A role boundary should be config-enforced, not prompt-enforced.

## When to compose

Before writing a workflow, run the **dependency test** on every proposed step pair:

> Does the next skill actually read the previous skill's output?
> If yes → real **dependency**, keep them sequenced.
> If no → independent — they don't belong in the same chain.

A workflow earns its existence only when each step depends on the previous one's output. A chain where you can remove a step without breaking the rest is not a workflow — it's a **router skill** (a list of independent skills the profile reaches for by trigger, not sequence).

Write a workflow when: 3+ skills with real dependencies between them, all in one session. For 2 skills where one gates the other, put the gate directly in the second skill's body — no workflow needed. For steps that need fresh context per step, use a **card chain** instead — the gate is the parent-child dependency, and writing a workflow skill would be leaky duplication of what the card bodies already contain.

## Gates

A **gate** is a precondition that blocks a step until a prior step's output exists. Gates are what separate a workflow from a suggestion.

Two parts:

1. **The check** — a condition the agent can verify concretely: "a grill transcript exists in this conversation," "the spec file exists at `<path>`," "the architect's design card status is done." A check must be binary — it either passes or doesn't, with no judgment call.
2. **The block** — what happens when the check fails: stop, name what's missing, load the prerequisite skill.

A gate the agent can't verify is a **phantom gate** — it looks like enforcement but the agent can't distinguish "satisfied" from "not satisfied," so it either always passes or always blocks. "Make sure you've grilled the user" is a phantom gate — the agent can't tell grilled from discussed. "A grill transcript with stress-scenario resolutions exists in this conversation" is checkable.

Write gates as **positive preconditions** — what must exist to proceed — never as **prohibitions**. "Proceed to `to-tickets` only when a spec file exists at `<path>`" states the target. "Don't run `to-tickets` without a spec" names the wrong behavior into the frame.

## Composition body

The body is a numbered chain. Each entry names the **skill** (by exact name), its **gate** (what must exist), and its **output** (what it produces that the next step needs):

```
1. Skill: grilling
   Gate: none — can start immediately
   Output: grill transcript (decisions + resolved stress scenarios)

2. Skill: to-spec
   Gate: grill transcript exists in conversation
   Output: spec published to tracker

3. Skill: to-tickets
   Gate: spec exists + architect design card done
   Output: tickets published to tracker with blocking edges
```

The body is intentionally spare. The workflow's job is sequencing and gating — the heavy lifting lives in the skills it chains. A workflow that restates the instructions of its constituent skills is **leaky**; cure it by cutting everything except skill names, gates, and outputs.

## Registry

List a workflow in the profile's SOUL.md identity section as a one-line entry — name, trigger, and the skill chain in shorthand:

```
Your workflows:
- spec-pipeline — when committing to build (grill → to-spec → architect → to-tickets)
```

The registry tells the profile what workflows it owns and when to reach for each. It carries no steps — those live in the workflow skill.

## Failure modes

- **Phantom gate** — a gate the agent can't actually check, so it never enforces. Cure: make the condition concrete and binary (file exists, transcript present, card status = done).
- **Over-chaining** — sequencing skills that don't depend on each other. Cure: the dependency test. If no data crosses the boundary, they're independent skills behind a router, not a chain.
- **Leaky workflow** — the body duplicates the content of the skills it chains. Cure: cut everything except skill names, gates, and outputs. The workflow orchestrates; it doesn't instruct.
- **Dead workflow** — a workflow that isn't listed in the profile's registry. If the profile doesn't know the workflow exists, it won't load it. Cure: every workflow gets a registry entry at creation time.
- **Wrong tier** — using a skill gate where a card chain is needed (steps need fresh context, or the gate must be structural not prompt-level), or writing a workflow skill when `kanban_chains` already enforces the sequence. Cure: apply the tier test first — if steps need context isolation or the sequence is already card-enforced, don't write a workflow skill at all.
