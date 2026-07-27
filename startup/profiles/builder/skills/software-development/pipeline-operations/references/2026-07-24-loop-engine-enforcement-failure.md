# loop_engine Enforcement Failure (2026-07-24 E2E Batch 2)

## Finding

The venture-prototype skill says "loop_engine is MANDATORY" in bold caps. The builder has skipped it on EVERY prototype in EVERY E2E test run:
- Batch 1 (2026-07-24, 10 cards): all built directly, no loop_engine
- Batch 2 (2026-07-24, 5 cards): all built directly, no loop_engine
- RouteOpt rebuild card (t_0e3bc9ed) explicitly said "loop_engine MANDATORY — the previous run skipped it and that is why we are rebuilding" — still at risk

## Root Cause

The builder reasons: "I can build this HTML in one shot, why phase it?" This is rational self-assessment — a single-file HTML dashboard IS simple enough to build in one shot. But the value of loop_engine isn't in the BUILD step. It's in the VERIFIER GATE: a separate agent session checks the prototype against the grill decisions. That independent check catches drift, missing decisions, and incomplete READMEs.

The "MANDATORY" instruction in the skill is necessary but insufficient. The builder reads it, self-assesses as exempt, and skips. Instruction-level enforcement does not work for this class of shortcut.

## What Does NOT Work

1. Saying "MANDATORY" in the skill body — builder self-assesses exemption
2. Adding a pitfall entry "Skipping loop_engine" — already there, still skipped
3. Putting "do NOT self-assess as simple enough to skip" — already there, still skipped

## What MIGHT Work (untested)

1. **Verify script pre-written in card body** — put the exact `/tmp/verify-<slug>.py` path in the kanban card so Phase 0 (write verify script) is already done. The builder can't skip to build without having a verify script.
2. **Rebuild cards with explicit failure reason** — "the previous run skipped loop_engine and that is why we are rebuilding" gives the builder context on why it can't skip.
3. **Post-completion audit** — after the card completes, check if loop_engine was used (look for delegation/verifier sessions in state.db). If skipped, flag for manual review instead of auto-accepting.
4. **Structural coupling** — make the verify script a hard dependency of kanban_complete (the card can't complete until verify passes). This requires pipeline-level enforcement, not skill-level.

## E2E Batch 2 Results (RouteOpt)

Despite skipping loop_engine, the RouteOpt prototype was actually good quality:
- 53KB single-file HTML, 1117 lines, all 10 quality checks pass
- 4 tabs, ROI calculator, traffic-light budget, counterfactual methodology
- 65 grill decisions across 4 branches reflected in the prototype

But the prototype was built from `.context/grill/decisions.md` (a summary file) rather than reading every branch file independently. The verifier gate would have caught any decisions missed.

## UPDATE: Two-card split + verify template RESOLVED this (2026-07-25 Batch 3)

The structural fix worked. Splitting the pipeline into separate grill and build cards, plus rewriting the verify-script-template.md to enforce 4 categories with minimum 20 checks, produced:

| Batch | Verify checks (avg) | Recovery cards | Grill decisions (avg) |
|---|---|---|---|
| Batch 1 (single card) | 48 (RouteOpt only) | N/A | 65 (RouteOpt only) |
| Batch 2 (2-card, old template) | 8.3 | 2 | 21 |
| **Batch 3 (2-card, new template)** | **56** | **0** | **53** |

Key changes that fixed it:
1. **Two-card split** — build card isolates loop_engine in a fresh session where it's the ONLY job
2. **Verify-script-template.md rewritten** — 4 categories (structural, decision-content, README, build-rules), minimum 20 checks, with ~15 automatic checks built into the template
3. **Card body includes "MINIMUM 20 checks" + template path** — explicit instruction that the builder followed

The original recommendation below is now superseded. The structural coupling was achieved through card design + template, not through a completion gate script.
