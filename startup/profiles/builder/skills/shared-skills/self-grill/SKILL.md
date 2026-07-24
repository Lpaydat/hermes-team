---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. Branches are created dynamically as the grill reveals what design categories matter for THIS specific idea — no hardcoded list. PO identifies what needs interrogation, you add branches, the grill progresses.

> **Pipeline context** — grill happens in Stage 3 (builder sessions). See [`references/pipeline-context.md`](references/pipeline-context.md).
>
> **Web evidence** — for gathering quotes/URLs/competitor data for dossiers, see [`references/web-evidence-gathering.md`](references/web-evidence-gathering.md).
>
> **Fact-verification** — dossiers must be independently verified before grilling. See [`references/fact-verification.md`](references/fact-verification.md).

## Discovery (prerequisite)

Before launching the grill, produce a **venture brief** from the dossier. A raw idea fed to PO wastes the first 3-5 turns extracting "what problem are you solving?" — that's discovery the builder should do beforehand.

The brief has three pillars:

1. **Problem / Opportunity** — Why does this need to exist? What pain or gap? Who has this problem (specific, not "everyone")? What they do today instead?
2. **Core Idea** — One-sentence pitch. The core mechanism or insight that makes your approach solve the problem better. Not features — the *insight*.
3. **Core Features** — 3-7 irreducible capabilities, each traceable to a pain point. If a feature doesn't map to a problem, it's scope creep.

The brief is a **strawman**, not settled scope. The pillars are **iterative** — tighten in loops until consistent (a feature that doesn't solve the stated problem sends you back to pillar 1 or 2). When launching PO, state: "this list is incomplete by definition; one of your jobs is to find the gaps, not just audit what's here." PO grills *both* the features *and* the list's completeness.

Use the [venture brief template](references/venture-brief-template.md). Check `~/vault/ventures/ideas/` for an existing dossier before drafting.

## Workflow

```
1. Draft venture brief (3 pillars) from the dossier
2. Set up grill state (see grill-rpc-ops for scripts)
3. Launch PO with the brief, not a raw idea
4. PO asks questions → first few reveal what categories matter
5. Ask PO: "What 3-5 design categories does this idea need?"
6. Create branches from PO's answer
7. Grill through each branch — ANSWER AS FOUNDER with conviction
8. Add new branches if the grill surfaces new categories
9. Done when no pending or active branches remain
10. Persist grill output to ~/projects/<slug>/context/ (see below)
```

**Answer as founder:** you have conviction. The dossier is your evidence. Don't hedge, don't fold — if PO pushes on a weakness, defend with evidence or fix it honestly. "This is hard" is not a fatal flaw.

## Grill depth (LESSON LEARNED)

A prior version of this skill (mattpocock `grilling`, 855 bytes, 7 lines) produced 50+ question grills naturally. Our RPC/branch machinery produced only 12 decisions across 6 branches — too shallow. The lesson: **complexity kills grill depth.** The RPC scripts, branch files, and state management got in the way of relentless questioning.

What made the simple version work:
- **One question at a time, WAIT for the answer.** No batching, no multi-branch jumping.
- **Walk the decision tree.** Each answer unlocks the next question — follow the dependency chain.
- **Provide a recommended answer.** Stake a position, let the founder push back. Dialogue, not interrogation.
- **Push past easy answers.** 20+ questions per branch is normal. Don't stop at 2 decisions per branch — dig until the decision is genuinely locked, not just "good enough."

Target: 3-5 locked decisions per branch, 20+ Q&A per branch. If you have fewer, the grill is too shallow.

## NEVER block the kanban card during self-grill

You are the founder. PO's questions are for YOU to answer, not a human gate.
Do NOT call `kanban_block`. Do NOT set the card to `needs_input`.
Answer immediately and continue the grill.
Blocking causes the dispatcher to reclaim the card after ~1h stale timeout,
wasting a full reclaim cycle and fragmenting grill state across sessions.
The card stays `running` from grill start to completion.

## Grill output: per-branch files (REQUIRED)

The grill produces **one file per branch**, not a single giant file. A long grill (100+ Q&A) in one file is unmanageable. Per-branch files keep each design area self-contained.

### Structure

```
~/projects/<slug>/context/
├── _state.md                  ← branch table + active branch
├── <branch-slug>.md           ← one file per branch
├── <branch-slug>.md
└── ...
```

Each branch file has:
- `## Decisions` — locked decisions from this branch
- `## Questions asked` — Q&A log for this branch

### Persistence (CRITICAL)

The grill scripts write to `/tmp/grill-<slug>/context/` during the session. That directory is ephemeral — it dies when the workspace is cleaned up.

**Before completing the card**, copy the grill state to the project directory:

```bash
mkdir -p ~/projects/<slug>/context/
cp /tmp/grill-<slug>/context/*.md ~/projects/<slug>/context/
```

Completion criterion: every branch file exists in `~/projects/<slug>/context/`. Verify with `ls ~/projects/<slug>/context/*.md | wc -l` — the count must match the number of branches in `_state.md`.

**Before completing the card**, run the validation script:

```bash
bash ~/.hermes-teams/shared-skills/self-grill/scripts/validate-grill-output.sh <slug>
```

Exit 0 = pass (safe to complete). Exit 1 = fail (fix the issue before completing). Do NOT call `kanban_complete` until the script passes.

If this step is skipped, the grill decisions are lost. The venture-prototype skill (loaded after the grill) reads from this directory to build the prototype.

## RPC mechanics

All grill RPC operations — setup, PO launch, answer pattern, branch management, decision locking, timeout handling, done criteria, and model quirks — live in **`grill-rpc-ops`**. Load it (`skill_view grill-rpc-ops`) when running a grill session. That skill is the single source of truth for the mechanics; this skill owns the workflow and the founder role.

## Dossier delegation pattern

When building dossiers at scale, delegate research to subagents via `delegate_task` with `role='leaf'`. Dispatch in batches of 3 (parallel). If a subagent hits the tool-call limit before writing the file, the content is preserved in the delegation summary — extract and write locally.

Check `delegation.max_iterations` in `~/.hermes-teams/startup/config.yaml` before dispatching. A rich 13-section dossier with web research needs 80-150 tool calls. If the budget is low, extract from the delegation summary as fallback.
