# 2-Card Pipeline Architecture (grill → build, parallel pairs)

> **Status: IMPLEMENTED + DEPLOYED FOR TESTING (2026-07-24).** Commits `461fdcf7` (2-card split) + `ae20dea8` (parallel pairs). queue-builds.sh creates 2 cards per idea (Grill + Build) with no cross-idea chaining.

## Why split into 2 cards

The 1-card-per-idea pipeline has ONE card that does everything: dossier + grill + build + README + portfolio. The builder reaches the build step 2+ hours into the session, context window full of grill Q&A, and self-assesses the build as "simple enough" to skip loop_engine. This happened on EVERY prototype in EVERY E2E test (Batch 1: 10/10, Batch 2: 5/5). Text instructions ("loop_engine is MANDATORY") do not enforce — the builder ignores text it disagrees with.

The 2-card split solves this structurally:

1. **Fresh context for build** — a dedicated build card starts with an empty context window focused solely on building with loop_engine. The card body IS the loop_engine spec, not a buried instruction among 5 steps.
2. **Single-purpose cards are proven to work** — the rebuild card t_0e3bc9ed (RouteOpt rebuild) ran clean in 8 min because it had ONE job. The builder followed instructions precisely.
3. **Grill failures don't waste build time** — if the grill is shallow or kills the idea, only the grill card is wasted
4. **Context bloat eliminated** — grill RPC state and prototype code are in separate sessions

## The split

```
GRILL CARD (Card A, no parent):
  reads dossier → grills with PO → outputs context/*.md → validates → completes
  Loads: self-grill + grill-rpc-ops
  Output: ~/projects/<slug>/context/*.md + .context/grill/decisions.md + .context/dossier.md
  Does NOT build prototype

BUILD CARD (Card B, child of grill card, auto-promotes when grill completes):
  reads context/*.md → loads venture-prototype skill
  → POC gate → picks type → builds with loop_engine → README → portfolio
  Loads: venture-prototype
  Output: ~/projects/<slug>/prototype/ + ~/projects/<slug>/README.md
  Does NOT re-grill
```

## Parallel pairs (no cross-idea chaining)

Each idea is an INDEPENDENT grill→build pair. No sequential chaining between ideas.

```
idea1-Grill → idea1-Build   ↘
idea2-Grill → idea2-Build   → all run concurrently (capped by max_in_progress_per_profile=3)
idea3-Grill → idea3-Build   ↗
```

The founder explicitly requested parallel over sequential: "I don't really want each prototype to chain in sequential but parallel separately." Each grill card has no parent (ready immediately). Each build card has its own grill card as parent. The dispatcher's `max_in_progress_per_profile` controls concurrency.

## queue-builds.sh implementation

The script (lines 117-200) creates 2 `hermes kanban create` calls per idea:

1. **Grill card** — no parent (ready immediately for dispatcher pickup)
2. **Build card** — `--parent "$GRILL_ID"` (waits for grill to complete)

No `PREV_ID` variable — each idea is self-contained. The `PREV_ID` cross-idea linking was removed in commit `ae20dea8`.

The grill card body explicitly says "Do NOT build the prototype — that is the next card." The build card body says "This card's ONLY job is to build with loop_engine. Do not skip it."

## Evolution

1. **v1 (original):** 1 card per idea, sequential chain. Builder skipped loop_engine on all 15 prototypes.
2. **v2 (commit 461fdcf7):** 2 cards per idea, sequential chain across ideas. Architecturally correct but unnecessary serialization between independent ideas.
3. **v3 (commit ae20dea8, current):** 2 cards per idea, parallel pairs. Each idea independent. Dispatcher controls concurrency.

## Test deployment (2026-07-24)

**Deployed:** 3 parallel pairs for testing the v3 architecture:

| Pair | Idea | Score | Grill Card | Build Card | Has Dossier? |
|------|------|-------|------------|------------|--------------|
| 1 | ChatGPT Ads Tooling First-Mover | 20/25 | t_59816a1b | t_c4a8ad44 | YES |
| 2 | Solo Founder Customer Onboarding | 16/25 | t_d859b00c | t_9d820367 | NO (grill card creates it) |
| 3 | SMB Cross-Platform Data Sync | 16/25 | t_afd2e9d3 | t_60d866c9 | NO (grill card creates it) |

Pair 1 was created by queue-builds.sh. Pairs 2-3 were created manually via `kanban_create` because the dedup check in queue-builds.sh blocked them (false positive substring matches from old completed cards — see dedup pitfall in pipeline-operations SKILL.md).

**Test results (2026-07-24 23:40):**

| Pair | Idea | Grill | Build | Prototype | Verify | README |
|------|------|-------|-------|-----------|--------|--------|
| 1 | ChatGPT Ads (20/25) | DONE (5 branches, 15 decisions) | DONE | 1014 lines, 43KB | 15/15 PASS | 9 sections |
| 2 | Solo Founder Onboarding (16/25) | DONE (re-grill: 5 branches, 20 decisions) | DONE | 1452 lines, 55KB | 5/5 PASS | 9 sections |
| 3 | SMB Data Sync (16/25) | DONE (3 branches, 28 decisions) | DONE | ~700 lines, 33KB | 5/5 PASS | 9 sections |

All 3 pairs completed end-to-end. All used verify scripts. All passed.

**What the 2-card pattern validated:**
1. Parallel execution worked — pairs 2 and 3 grilled simultaneously, no cross-idea blocking.
2. Build cards started fresh with only the build job — all 3 used verify scripts.
3. The build gate caught missing grills — pairs 2 and 3 blocked correctly when the grill hadn't run yet. Build cards refused to invent specs. This is the #1 win of the 2-card split: the build card checks `context/` exists and has decisions before building.

**Bugs found during the parallel test:**

1. **delegate_task subagents call kanban_complete prematurely (NEW BUG).** The grill card dispatches a research subagent via `delegate_task` to create the dossier. The subagent inherits the kanban toolset and calls `kanban_complete` on the parent grill card before the grill runs. This happened on BOTH pairs 2 and 3. Root cause: leaf subagents have access to kanban tools. Fix needed: restrict leaf subagent toolsets in delegate_task (remove kanban tools from leaves), or add a guard in the grill card body saying "do NOT use delegate_task for steps that could complete the card."

2. **Build cards stay blocked after parents complete.** When a build card blocks with `kind=needs_input` and then the parent (or re-grill task) completes, the auto-promote to `ready` does NOT always fire. Required manual `kanban_unblock`. This is a dispatcher limitation — blocked cards with `needs_input` kind don't auto-promote even when dependencies resolve.

3. **Race condition on context/ directory.** The build card checked `context/` before the grill worker finished writing to it. The grill was still running when the build card first checked, found it empty, and blocked. Timing: the original grill worker (pid 115479) was still grilling when the build card spawned and checked. The build card correctly blocked, then the grill completed and a re-grill task verified the decisions were there. The build needed manual `kanban_unblock` to proceed.

**Self-healing observed:** When the premature-completion bug struck, the build card created its own re-grill task (t_97f83869 for pair 2), which ran the full grill successfully. For pair 3, the observer created the re-grill task manually. Both re-grills completed and the builds proceeded.

## Known limitation: queue-builds.sh dedup blocks fresh ideas

The dedup check uses substring matching: `if '$slug' in (title + body).lower()`. This causes false positives when a slug fragment appears in any existing card. Example: `ai-smb-bookkeeping` slug is blocked because a card body mentions "smb-bookkeeping" in passing. This prevented queue-builds.sh from creating cards for ideas that share keywords with already-completed work.

**Workaround:** Create pairs manually via `kanban_create` tool (Python API handles multiline bodies correctly). This is also faster for targeted testing — you control exactly which ideas enter the pipeline.
