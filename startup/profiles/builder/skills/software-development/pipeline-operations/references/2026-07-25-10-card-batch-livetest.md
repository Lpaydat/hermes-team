# 10-Card Batch Livetest (2026-07-25)

Fresh board `e2e-livetest`, 10 ideas, 3 concurrent, 2-card split (grill + build).

## Setup
- Board: `e2e-livetest` (created fresh, isolated from hermes-hq)
- Ideas: 10 unbuilt ideas from idea-bank.md, scores 15-17/25
- Pattern: 2-card chain per idea (grill parent → build child), 20 cards total
- Concurrency: max_in_progress_per_profile=3 (3 grill cards running simultaneously)

## Results (6/10 pairs completed at time of analysis)

| # | Idea | Grill Dec | Branches | Prototype | Size | Verify | Runtime | Time |
|---|------|-----------|----------|-----------|------|--------|---------|------|
| 1 | SMB Cross-Platform Data Sync | 82 | 6 | HTML | 37KB | 97/97 | YES | ~50min |
| 2 | AI Coding Flow-State Tool | 54 | 2 | CLI | 37KB | 51/51 | YES | ~90min |
| 3 | Agency Reporting Data Aggregation | 50 | 5 | HTML | 53KB | 70/70 | N/A (HTML) | ~10min |
| 4 | How Are You Hiring Engineers | 28 | 5 | HTML | 50KB | 44/44 | YES | ~60min |
| 5 | AI Always-Adds-Code Fixer | 105 | 5 | CLI | ~37KB | — | — | ~80min |
| 6 | AI Agent Management Burden | 72 | 5+ | CLI | — | — | — | ~120min |

4 more pairs in progress or queued at time of analysis.

## What worked

1. **Verify template update validated at scale.** 3/4 HTML+CLI builds include runtime execution checks (subprocess-run, exit 0 assertion). The 4th (HTML-only) correctly has no runtime check. The template update from earlier in the session is being followed by autonomous workers.

2. **2-card pipeline architecture handles deep grills.** Grills producing 50-105 decisions ran to completion (some after timeout reclamations). The parent-child dependency auto-promoted build cards correctly when grills finished.

3. **Fresh-board testing pattern.** Creating a dedicated `e2e-livetest` board kept test cards isolated. The dispatcher picks up cards from any board for the builder profile.

4. **Deep grill recovery works.** Two grills (AI Tool Spend Dashboard, AI Always-Adds-Code Fixer) hit the 200-iteration limit on run 1, got reclaimed, and run 2 recovered state from /tmp and resumed. The system self-healed.

## Deep grill stalls (NEW operational pattern)

One grill (AI Tool Spend Dashboard, t_4214b605) stalled for 4+ hours on run 12:
- 54 decisions locked, no growth for 2+ hours
- Worker at 0.1% CPU with only a `sleep` child process (no `hermes --resume` or `timeout` child)
- No active PO RPC turn — the worker is in a sleep/wait loop, not thinking

**Detection signal:** `pstree -p <worker_pid>` shows `bash→sleep` but NO `timeout→hermes --resume` chain. This means the worker finished its last turn and is sleeping before retrying, but never actually re-engages PO. Combined with 0 decision growth for 1+ hour = stalled.

**Differentiation from normal PO wait:** During a normal PO RPC turn, the process tree shows `timeout → hermes --resume` (the answer.sh subprocess waiting for PO's response). A stalled worker shows only `bash → sleep` — no active PO communication.

**Impact:** The stalled grill blocks a concurrency slot indefinitely. The dispatcher's stale timeout (default 4h) eventually reclaims it, but that's a long wait.

**Mitigation (for observer):** If you detect this pattern (sleep-only children + 0 decision growth for 1+ hour), report it to the user. Do NOT kill the worker without explicit direction. The dispatcher reclaim will eventually give it a fresh session.

## Config changes made during this test

1. `max_turns: 200` → `max_turns: 2000` in profile config (root cause of iteration budget exhaustion)
2. `base_url: ''` removed from profile config (root cause of cron credential failures)
3. `DEEPSEEK_API_KEY` commented out in `.env` (root cause of unwanted provider fallback)
4. `fallback_providers` (deepseek) commented out in profile config
5. answer.sh patched: 4-field → 5-field read for _state.md count update (root cause of count stuck at 0)
6. Gateway restarted to pick up all config changes
7. venture-prototype verify-script-template.md updated: added Category 5 (runtime execution) and Category 4 (environment/import checks)

## Final results (8/10 pairs completed, 2 grills still running at session end)

| # | Idea | Grill Dec | Branches | Prototype | Verify | Runtime |
|---|------|-----------|----------|-----------|--------|---------|
| 1 | SMB Cross-Platform Data Sync | 82 | 6 | HTML 37KB | 97/97 | YES |
| 2 | AI Coding Flow-State Tool | 54 | 2 | CLI 37KB | 51/51 | YES |
| 3 | Agency Reporting Data Aggregation | 50 | 5 | HTML 53KB | 70/70 | N/A (HTML) |
| 4 | How Are You Hiring Engineers | 28 | 5 | HTML 50KB | 44/44 | YES |
| 5 | AI Always-Adds-Code Fixer | 105 | 5 | CLI ~37KB | pass | YES |
| 6 | AI Agent Management Burden | 37 | 2 | CLI | pass | YES |
| 7 | AI Tool Spend Management Dashboard | 55 | 6 | HTML 39KB | pass | — |
| 8 | Code-Reading-First IDE | 116 | 4 | CLI 3 files | pass | — |
| 9 | The Log is the Agent | 117+ | — | — | — | (grill still running) |
| 10 | AI-Powered Internal Tool Builder | 84+ | — | — | — | (grill still running) |

## Deep-grill time budget problem (CRITICAL operational insight)

Code-Reading-First IDE produced **116 decisions** across 4 branches and took **14+ hours** to complete. The Log is the Agent reached **117 decisions** and was still running at session end (~14 hours in). These are the deepest grills ever produced.

**Math:** glm-5.2 takes 2-3 min per PO turn. A 116-decision grill with 4 branches needs ~60 Q&A turns minimum (PO asks follow-ups, not every turn locks a decision). At 2.5 min/turn average = 150 min = 2.5 hours just for Q&A. But with answer.sh processing, state persistence, validation checks, and the builder's own reasoning between turns, each turn actually takes 5-10 min. So 60 turns × 7 min = 420 min = 7 hours. With timeout reclamations adding overhead, a 116-decision grill takes 10-14 hours.

**Impact on batch pipeline:** With 3 concurrent slots and 10 ideas, if 3 ideas each produce 100+ decision grills, the batch takes 14+ hours. The remaining 7 ideas can't start until slots free. This makes the daily pipeline impractical for complex ideas.

**Root cause:** The grill system has no decision cap. PO keeps asking questions as long as it finds design holes. For complex ideas (IDE, event-sourcing architecture, multi-stakeholder platforms), the design space is vast and PO correctly probes deeply — but the depth is impractical for a daily pipeline.

**Recommended fix:** Add a `MAX_DECISIONS_PER_BRANCH` (default 15-20) and `MAX_TOTAL_DECISIONS` (default 50) to the grill scripts. When a branch hits the cap, PO is instructed to wrap up with a final synthesis question. This caps any grill at ~50 decisions × 7 min/turn = ~6 hours worst case, with most grills finishing in 2-3 hours.

## Key metrics (updated with final data)

- **Grill depth range:** 28-117 decisions (4x variance)
- **Grill time range:** 10 min to 14+ hours (correlates strongly with decision count)
- **Build time range:** 7-13 min (consistent, independent of grill depth)
- **Timeout reclamations:** 4/10 grills needed at least one reclaim (all were deep: 55-116 decisions)
- **Stalled workers:** 1/10 early in the run (sleep-only children pattern)
- **Deep grill threshold:** grills above ~60 decisions consistently took 5+ hours; above 100 decisions consistently took 10+ hours
