# Parallel 2-Card Fix Validation (2026-07-25)

> Livetest 2: tested the 3 fixes from livetest 1 (verify template, subagent toolset restriction, blocked→ready workaround). 3 new parallel pairs. All completed. Fixes validated.

## Test setup

3 fresh ideas (no dossier, no card), deployed as parallel pairs with the new fixes applied:

| Pair | Idea | Score | Grill Card | Build Card |
|------|------|-------|------------|------------|
| 1 | Agency Reporting Data Aggregation | 16/25 | t_45fd9b75 | t_3db2e307 |
| 2 | Pre-Flight Repo Security Scan | 15/25 | t_18582480 | t_54434f6b |
| 3 | Subscription Cancellation SaaS Rescue | 15/25 | t_be163074 | t_5104a625 |

Card bodies included: `CRITICAL: pass enabled_toolsets=["web","file","terminal"]` and `MINIMUM 20 checks` + template reference.

## Results — fixes validated

| Fix tested | Livetest 1 result | Livetest 2 result | Status |
|---|---|---|---|
| Verify script depth | 5 checks (shallow) | 48-70 checks (deep) | **FIXED** |
| Subagent premature completion | 2/3 pairs broke | 1/3 auto-completed but builder recovered in-session | **IMPROVED** |
| blocked→ready auto-promotion | Stuck, manual unblock | Same — still needs manual unblock | **KNOWN LIMITATION** |

## Verify script improvement (the headline result)

| Pair | Verify checks | Previous batch equivalent |
|---|---|---|
| Agency Reporting | **70/70 PASS** | would have been ~5 |
| Repo Security Scan | **50/50 PASS** | would have been ~5 |
| Sub Cancellation | **48/48 PASS** | would have been ~5 |

The new verify-script-template.md (4 categories: structural, decision-content, README, build-rules) produced 10x deeper verification. The template's built-in checks (DOCTYPE, JS braces, dark theme, zero deps, simulated data label, README sections, specific How-to-Review steps) give the builder ~15 free checks. Adding 5+ decision-specific checks gets to the 20 minimum naturally.

## Subagent toolset restriction

The `enabled_toolsets` warning in the card body was followed by builders — they used `["web","file","terminal"]` for research subagents. However, pair 1's grill card was still auto-completed by a subagent. The difference from livetest 1: the builder continued working in the same session AFTER the auto-completion and completed the full grill (26 decisions, 5 branches, validation PASS). The build card then blocked on a race condition (checked context/ before grill finished writing), requiring manual `kanban_unblock`.

**Lesson:** The card-body warning helps but doesn't fully prevent auto-completion. The real fix is the `enabled_toolsets` parameter on delegate_task itself (enforced by the tool, not the prompt). Until that's implemented, the card-body warning is the best defense.

## Race condition pattern (recurring)

The race condition from livetest 1 recurred on pair 1:
1. Grill card auto-completes (subagent)
2. Build card spawns, checks context/ — finds it empty
3. Build card blocks (correct behavior)
4. Grill worker (still alive in same session) finishes grill, writes to context/
5. Build card stays blocked (needs_input doesn't auto-promote)
6. Manual `kanban_unblock` required

**Monitoring pattern:** When checking a batch, look for `blocked` build cards whose parent grill cards are `done`. If context/ has decision files, just `kanban_unblock` the build card.

## Parallel execution confirmed

All 3 grills ran simultaneously (pids 232879, 232880, 232881 — all started within seconds of each other). Total wall time: ~75 min for 3 complete grill→build pairs. The parallel pattern is working as designed.

## What still needs fixing

1. **delegate_task `enabled_toolsets` enforcement** — the parameter exists on delegate_task but the builder doesn't always pass it. The card-body warning helps but a tool-level default would be better.
2. **blocked→ready auto-promotion for race-condition recoveries** — still requires manual intervention. The dispatcher should check if context/ files exist when a build card blocks on missing grill, and auto-promote if they do.
3. **Browser testing** — still not happening. Verify scripts check structural presence of elements but not functional behavior (onclick handlers, tab switching).
