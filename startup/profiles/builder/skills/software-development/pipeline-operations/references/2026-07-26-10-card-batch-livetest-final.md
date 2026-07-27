# 2026-07-26 10-Card Batch Livetest — FINAL (completed 2026-07-27)

Board: `e2e-livetest` | 10 ideas × 2 cards = 20 cards | 3 concurrent

## Results

| # | Idea | Grill Decisions | Branches | Prototype Type | Grill Duration (active) | Wall-Clock |
|---|------|----------------|----------|----------------|------------------------|------------|
| 1 | SMB Cross-Platform Data Sync | 82 | 6 | HTML 37KB | ~4h | ~5h |
| 2 | AI Coding Flow-State Tool | 54 | 2 | CLI 37KB | ~2.5h | ~3h |
| 3 | Agency Reporting Data Aggregation | 50 | 5 | HTML 53KB | ~2h | ~2h |
| 4 | How Are You Hiring Engineers | 28 | 5 | HTML 50KB | ~1.5h | ~1.5h |
| 5 | AI Always-Adds-Code Fixer | 105 | 5 | CLI | ~5h | ~6h |
| 6 | AI Agent Management Burden | 37 | 2 | CLI (driftscope.py) | ~2h | ~2.5h |
| 7 | AI Tool Spend Dashboard | 55 | 6 | HTML 39KB | ~3h | ~5h (timeout recovery) |
| 8 | Code-Reading-First IDE | 116 | 4 | CLI multi-file | ~6h | ~14h |
| 9 | AI-Powered Internal Tool Builder | 54 | 4 | CLI multi-file | ~3h | ~4h |
| 10 | The Log is the Agent | 475+ | 5+ | CLI (logagent.py 844 lines) | ~24h | ~109h |

**Total: 10/10 pairs completed. Zero manual interventions. Zero crashes.**

## Verify Results

- 7/10 builds have runtime execution checks (subprocess-run prototype, assert exit 0)
- 1 build (Agency Reporting) is HTML-only — no runtime check needed
- All builds pass their verify scripts
- All READMEs have 9 sections

## The Runaway Grill

The Log is the Agent (idea #10) produced **475 decisions across 5+ branches** and ran for **109 hours wall-clock** before terminating via max_turns=2000.

Key data points:
- Median grill depth: 54 decisions (most finish in 2-3h active)
- Code-Reading-First IDE: 116 decisions, 14h wall-clock (2nd deepest)
- The Log is the Agent: 475 decisions, 109h wall-clock (6.8x median)
- The build for the runaway grill took **9 minutes** — proving the bottleneck is grill depth, not build quality

The grill DID terminate — max_turns=2000 is a working backstop. But at ~5 iterations per decision and ~7 min per PO turn, a 475-decision grill runs for ~4.5 days. This blocked the last concurrency slot for 60+ hours after the other 9 pairs completed.

## Timing Correction

The user corrected the reported durations: "It's not 40+ hrs as you understood. in fact, it's around 2-3 hours only." The wall-clock figures include dispatcher reclaim gaps, stale timeout cycles, and observer polling intervals. Active grill work (PO Q&A turns) is:
- Normal grill (28-82 decisions): 1.5-4h
- Deep grill (100-116 decisions): 5-6h
- Runaway (475 decisions): ~24h of actual PO turns

**Always report active grill time, not wall-clock elapsed.** Active time ≈ decisions × 3 min/decision.

## Fixes Applied This Session

1. **Deepseek disabled** — commented out DEEPSEEK_API_KEY in .env (hermes was auto-discovering and falling back)
2. **Empty base_url removed** from profile config — was overriding main config's correct zai endpoint
3. **max_turns: 200 → 2000** in profile config — profile was overriding main config's max_iterations:999
4. **answer.sh _state.md count bug fixed** — IFS='|' parsing was reading 4 fields instead of 5 (leading pipe creates empty first field)
5. **verify-script-template.md updated** — added Category 5 (Runtime Execution Checks) that subprocess-runs prototypes

## #1 Action Item

**Add a decision cap to the self-grill skill/scripts.** Recommended: MAX_TOTAL_DECISIONS=50-60, MAX_DECISIONS_PER_BRANCH=15-20. self-grill is pinned — needs manual unpinning to apply script changes. The cap would stop a runaway grill at ~50 decisions in ~3 hours instead of 475 decisions in 109 hours.
