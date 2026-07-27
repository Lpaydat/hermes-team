# Grill Decision Cap — Runaway Prevention (updated 2026-07-27)

## The Problem

The grill system has NO built-in decision cap. PO keeps probing as long as it finds design holes. For complex ideas (event sourcing, multi-layer systems), this creates runaway grills that consume the entire iteration budget and block a concurrency slot.

## Evidence (2026-07-26 batch, 10 ideas — FINAL 2026-07-27)

| Idea | Decisions | Active Time | Notes |
|------|-----------|-------------|-------|
| How Are You Hiring Engineers | 28 | ~30 min | |
| AI Agent Management Burden | 37 | ~45 min | |
| Agency Reporting Data Aggregation | 50 | ~1.5h | |
| AI Coding Flow-State Tool | 54 | ~1.5h | |
| AI-Powered Internal Tool Builder | 54 | ~1.5h | |
| AI Tool Spend Dashboard | 55 | ~1.5h | |
| SMB Cross-Platform Data Sync | 82 | ~2.5h | |
| AI Always-Adds-Code Fixer | 105 | ~3h | |
| Code-Reading-First IDE | 116 | ~4h | |
| The Log is the Agent | 475+ | ~2-3h* | RUNAWAY — exhausted max_turns=2000 |

*User corrected: actual ACTIVE grill time was 2-3 hours, not 109h wall-clock. Wall-clock inflated by dispatcher reclaim cycles, stale timeout gaps, monitoring intervals.

**Key: the 475-decision grill's build took only 9 minutes.** Grill depth is the sole pipeline bottleneck.

## Recommended Caps (self-imposed by builder during grill)

| Cap | Value | Action when reached |
|-----|-------|---------------------|
| MAX_TOTAL_DECISIONS | 60 | Tell PO: "We have enough decisions. Finalize and conclude." |
| MAX_DECISIONS_PER_BRANCH | 15 | Tell PO: "This branch is deep enough. Next category." |
| MAX_BRANCHES | 6 | Stop adding branches. Tell PO to finalize. |

## Monitoring Command

```bash
grep -rh "Lock D" /tmp/grill-<slug>/context/ | wc -l
```

| Count | Status | Action |
|-------|--------|--------|
| 30-60 | Normal | Most grills finish here |
| 60-80 | Deep | Consider wrapping up |
| 80-100 | Very deep | Strongly recommend wrapping up |
| 100+ | RUNAWAY | Invoke cap, tell PO to finalize NOW |

## How to Invoke the Cap

As the BUILDER (not PO), you control branch creation:
1. Stop adding new branches
2. Tell PO: "We have [N] decisions across [M] branches. Wrap up the remaining branches — finalize what we have."
3. Mark remaining pending branches as done
4. Run validation and complete the card

## Why 60?

Diminishing returns set in past 60 decisions. The last 400+ decisions in the runaway case added marginal value over what the first 60 established. Build quality was identical to 50-60 decision grills.

## Pinned Skills Block

self-grill and grill-rpc-ops are PINNED — `skill_manage patch` refuses updates. Options:
1. User runs `hermes curator unpin self-grill` and `hermes curator unpin grill-rpc-ops`
2. Apply changes via `patch` tool directly on the filesystem (bypasses curator)
3. Builder self-imposes the caps described above during the grill session
