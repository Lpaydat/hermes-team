---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. Branches are created dynamically as the grill reveals what design categories matter for THIS specific idea — no hardcoded list. PO identifies what needs interrogation, you add branches, the grill progresses.

> **Pipeline context** — the grill happens in Stage 3 (builder sessions), NOT in the pipeline cron. See [`references/pipeline-context.md`](references/pipeline-context.md) for the 4-stage architecture, artifact paths, and cron job details.
>
> **Web evidence** — for gathering real quotes/URLs/competitor data for dossiers, see [`references/web-evidence-gathering.md`](references/web-evidence-gathering.md).
>
> **Fact-verification** — dossiers must be independently verified before grilling. See [`references/fact-verification.md`](references/fact-verification.md).

## Discovery (prerequisite — do NOT skip)

Before launching the grill, produce a **venture brief** from the dossier. A raw idea fed to PO wastes the first 3-5 turns extracting "what problem are you solving?" — that's discovery work the builder should do beforehand.

The brief has three pillars:

1. **Problem / Opportunity** — Why does this need to exist? What pain or gap? Who has this problem (specific, not "everyone")? What do they do today instead?
2. **Core Idea** — One-sentence pitch. The core mechanism or insight that makes your approach solve the problem better. Not features — the *insight*.
3. **Core Features** — 3-7 irreducible capabilities, each traceable to a pain point. If a feature doesn't map to a problem, it's scope creep.

**The brief is a strawman**, not settled scope. When launching PO, state: "this list is incomplete by definition; one of your jobs is to find the gaps, not just audit what's here." The PO grills *both* the features *and* the list's completeness.

The pillars are **iterative** — tighten in loops until consistent (a feature that doesn't solve the stated problem sends you back to pillar 1 or 2).

### Venture brief template

```
## 1. Problem / Opportunity
- The pain or gap: <>
- Who has this problem: <specific, nameable group>
- What they do today instead: <>
- Source of this signal: <>

## 2. Core Idea
- One-sentence pitch: <>
- Core mechanism / insight: <>

## 3. Core Features (3-7 — each must trace back to a pain point in Section 1)
| # | Feature | Maps to pain point | Why it's core |
|---|---------|-------------------|---------------|
| 1 |         |                   |               |
```

Check `~/vault/ventures/ideas/` for an existing dossier before drafting — the idea may already have a full 13-section analysis.

## How it works

```
1. Draft venture brief (3 pillars) from the dossier
2. Set up empty grill state (no branches)
3. Launch PO with the brief, not a raw idea
4. PO asks questions → first few reveal what categories matter
5. Ask PO: "What 3-5 design categories does this idea need?"
6. Create branches from PO's answer
7. Grill through each branch — ANSWER AS FOUNDER with conviction
8. Add new branches if the grill surfaces new categories
9. Done when no pending or active branches remain
```

**Answer as founder:** you have conviction. The dossier is your evidence. You don't hedge, don't fold — if PO pushes on a weakness, defend with evidence or fix it honestly. "This is hard" is not a fatal flaw.

## NEVER block the kanban card during self-grill

You are the founder. PO's questions are for YOU to answer, not a human gate.
Do NOT call `kanban_block`. Do NOT set the card to `needs_input`.
Answer PO's question immediately and continue the grill.
Blocking the card causes the dispatcher to reclaim it after ~1h stale timeout,
wasting a full reclaim cycle and fragmenting grill state across sessions.
The card stays in `running` from grill start to prototype completion.

## Pitfall: never make the grill optional

The grill was briefly made "optional" in the build-queue model to speed up pipeline throughput. The user explicitly corrected this: **"why grill optional? make it as required step."** The grill is REQUIRED for every idea, in both the automated pipeline and interactive builds. Making it optional is a regression — do not repeat this mistake. The user wants every idea stress-tested before building, even if it slows throughput.

## RPC mechanics

All grill RPC operations — setup, PO launch, answer pattern, branch management, decision locking, timeout handling, done criteria, and model quirks — live in **`grill-rpc-ops`**. Load it (`skill_view grill-rpc-ops`) when running a grill session. That skill is the single source of truth for the mechanics; this skill owns the workflow and the founder role.

## Dossier delegation pattern

When building dossiers at scale, delegate research to subagents via `delegate_task` with `role='leaf'`. Dispatch in batches of 3 (parallel). If a subagent hits the tool-call limit before writing the file, the content is preserved in the delegation summary at `~/.hermes-teams/startup/profiles/builder/cache/delegation/subagent-summary-*.txt` — extract and write locally.

**Batch pattern (tested 2026-07-23, 9 dossiers in 3 batches):** dispatch 3 subagents at once with `delegate_task(tasks=[...])`. Each gets the idea name, template path, output path, and existing signal data. Most write the file directly; ~1 in 3 exhausts the iteration budget and needs summary extraction.

**Budget awareness:** check `delegation.max_iterations` in `~/.hermes-teams/startup/config.yaml` before dispatching. A rich 13-section dossier with web research needs 80-150 tool calls (search + fetch + write). If the budget is low (e.g., 50), the subagent will exhaust it before writing the file. The content survives in the summary — extract and write locally as fallback.

## Known issues

1. **skill_manage symlink quirk** — `skill_manage(action='patch')` and `action='write_file'` fail with "not found." Use `skill_manage(action='create')` to overwrite the full SKILL.md content. This is the only action that reliably resolves symlinked skills.
2. **Config changes don't apply mid-session** — `delegation.max_iterations` is cached at startup. Raised to 999 on disk but requires engine restart. If subagents hit limits, extract from the delegation summary file.
