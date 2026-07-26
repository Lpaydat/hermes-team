# Parallel 2-Card Test Results (2026-07-24)

> 3 parallel grill→build pairs tested the v3 architecture (parallel pairs, no cross-idea chaining). All 3 completed end-to-end. 3 bugs found (1 critical, 2 minor). All bugs documented with root causes and fixes.

## Test setup

3 ideas without existing kanban cards, deployed as parallel pairs:

| Pair | Idea | Score | Grill Card | Build Card | Dossier pre-existed? |
|------|------|-------|------------|------------|----------------------|
| 1 | ChatGPT Ads Tooling First-Mover | 20/25 | t_59816a1b | t_c4a8ad44 | YES |
| 2 | Solo Founder Customer Onboarding | 16/25 | t_d859b00c | t_9d820367 | NO |
| 3 | SMB Cross-Platform Data Sync | 16/25 | t_afd2e9d3 | t_60d866c9 | NO |

Pairs 2-3 had no dossiers — the grill card's first job was to create one via delegate_task research subagents.

## Results

| Pair | Grill | Build | Prototype | Verify | README | Cards needed |
|------|-------|-------|-----------|--------|--------|--------------|
| 1 | 5 branches, 15 decisions | 7 min | 1014 lines, 43KB | 15/15 PASS | 9 sections | 2 (clean) |
| 2 | 5 branches, 69 locked lines | ~30 min | 1457 lines, 55KB | 5/5 PASS | 9 sections | 3 (+1 re-grill) |
| 3 | 3 branches, 56 locked lines | ~5 min | 980 lines, 33KB | 5/5 PASS | 9 sections | 3 (+1 re-grill) |

Total: 8 cards (expected 6, +2 recovery). All prototypes verified.

## What worked

1. **Parallel execution** — pairs 2 and 3 grilled simultaneously (pids 115478 + 115479). No cross-idea blocking.
2. **Verify scripts** — all 3 build cards produced verify scripts that parse decisions from context/ and exit 0.
3. **Build gate caught missing grills** — pairs 2 and 3 both blocked correctly when grill hadn't run. Build cards refused to invent specs (venture-prototype skill instruction worked).
4. **Self-healing** — when premature completion struck, the build card created its own re-grill task (pair 2), or the observer created one (pair 3). Both re-grills completed and builds proceeded.

## Bugs found

### Bug 1: delegate_task subagents complete parent card prematurely (CRITICAL)

**Impact:** 2/3 pairs required recovery cards, adding ~45 min each.

**Root cause:** The grill card delegates dossier creation to a research subagent via `delegate_task`. The subagent inherits the full kanban toolset and calls `kanban_complete` on the parent grill card after finishing its research — before the grill runs.

**Detection:** Build card checks `context/` directory, finds it empty (no grill decisions), runs `validate-grill-output.sh` → FAIL, blocks with evidence.

**Fix applied:** Added `enabled_toolsets` restriction warning to venture-prototype and self-grill skills. Leaf subagents should get `["web", "file", "terminal"]` — never `"kanban"`.

**Future enforcement:** Consider adding `enabled_toolsets` parameter to the grill card body template in queue-builds.sh.

### Bug 2: Build cards stuck blocked after parents complete (MINOR)

**Impact:** Pair 3's build card (t_60d866c9) stayed blocked after both parents completed. Required manual `kanban_unblock`.

**Root cause:** The `needs_input` block kind is designed for human-gated tasks, not dependency-gated tasks. The dispatcher doesn't auto-promote `needs_input` blocked cards even when all parents are done.

**Fix:** Use `kanban_unblock` manually when monitoring. Or use `kind=dependency` instead of `kind=needs_input` when blocking for missing prerequisites.

### Bug 3: Race condition on context/ directory (MINOR)

**Impact:** Build card checks context/ before grill worker finishes writing files.

**Root cause:** The build card spawns and checks `context/` before the grill worker has written any files. The build card correctly blocks (context/ empty), but then the grill completes and the build stays blocked (bug 2).

**Fix:** This is a timing issue that self-heals if the re-grill task is created and the build card is unblocked. No code fix needed — just awareness when monitoring.

## Verify script quality gap

All 3 verify scripts passed, but they were shallow (5-15 checks each vs RouteOpt's 48). The builder does the minimum to pass. The verify-script-template.md was rewritten to enforce a 20-check minimum with 4 categories (structural, decision-content, README, build-rules).
