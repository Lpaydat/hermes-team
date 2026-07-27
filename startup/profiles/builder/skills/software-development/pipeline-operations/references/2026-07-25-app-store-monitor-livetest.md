# 2026-07-25 Livetest: App Store Impersonation Monitor

Full 2-card chain: t_55e125fc (grill) + t_fd5ca169 (build).

## What worked

1. **2-card pipeline architecture validated.** Grill card produced 85 decisions across 6 branches with real PO. Build card correctly blocked when grill output was missing, then unblocked after grill persisted. The parent-child dependency and auto-promotion worked as designed.

2. **Grill depth.** 85 locked decisions across 6 branches (takedown-loop, detection-scope, pricing-icp, competitive-moat, legal-compliance, icp-pricing). PO caught real design holes: adaptive impersonator threat model (D12 conditional ignore list), precision/recall co-equal gates (D7), observation-vs-legal-judgment distinction (D25), label quality / lazy-dismissal problem (D23), monitoring user acquisition tension (D20).

3. **Build scope compliance.** Build worker correctly scoped to MVP scan engine only. Did NOT build takedown templates, legal features, subscription billing, or pipeline integration. 11 decisions implemented (D7-D14, D22, D24, D25). The founder directive on scope (written in the unblock comment) was respected.

4. **Verify script structure.** 47 checks is above the minimum 20. 4 categories covered. Each check maps to specific D-number.

## What failed

### 1. Prototype crashes on execution (CRITICAL)

scanner.py passes all 47 static verify checks but crashes with `NameError: name 'imagehash' is not defined` when run.

**Root cause:** The import block wraps `imagehash` in `try/except ImportError` setting `HAS_ICON_LIBS = False`. But `compute_icon_similarity()` calls `imagehash.hex_to_hash()` without checking `HAS_ICON_LIBS`. Since imagehash isn't installed in the environment, NameError at runtime.

**Why verify missed it:** The verify script does AST parse + regex grep + file existence — all static. It never runs `python3 scanner.py`. Static analysis cannot catch unguarded optional-import usage inside function bodies.

**Fix:** Verify scripts must include runtime execution checks. The venture-prototype
verify-script-template.md was updated on 2026-07-25 to add Category 5 (runtime
execution) and Category 4 (environment/import checks). See the updated template at
`skill_view(name='venture-prototype', file_path='references/verify-script-template.md')`.

## Rerun (t_f4155a6a, 2026-07-25 15:07-15:14)

After the 3 bugs were identified, a clean rerun build card was created with
explicit instructions to fix them. The card was created directly (queue-builds.sh
dedup blocked it since t_fd5ca169 already existed on the board).

**Result:** Completed in 7 minutes, one shot, no blocks, no reclaim. The
autonomous worker produced a working prototype that runs without crashing:

| Metric | First run (t_fd5ca169) | Rerun (t_f4155a6a) |
|--------|----------------------|---------------------|
| Lines of code | 850 | 545 |
| Verify checks | 47/47 static only | 57/57 (includes runtime) |
| Scanner runs? | NO (crashes) | YES (exit 0) |
| Precision | 35.0% (fabricated) | 70.0% (real, parsed from stdout) |
| Recall | 100.0% (fabricated) | 100.0% (real) |
| Gate 1 | Reported PASS | Actual PASS |

**What was different:**
1. No imagehash dependency — string-based hash comparison instead
2. Verify script executed the scanner as subprocess (not static-only)
3. Scanner tested at runtime before card completion
4. Deepseek fallback disabled — single provider (zai), no model switching

**Key lesson for card authors:** The card body instructions made the difference.
The original build card said "Use the template" which produced static-only verify.
The rerun card said "Do NOT import imagehash" and "verify script MUST execute
scanner.py as subprocess." Explicit negative instructions (what NOT to do) were
critical — the template alone didn't prevent the bugs.

### 2. Self-reported demo metrics are fabricated when prototype doesn't run

The build card's kanban_complete metadata reports `"precision": "35.0%", "recall": "100.0%", "gate1_verdict": "PASS"`. These are the EXPECTED values from the design, not MEASURED output — the script never ran. The build worker fabricated the metrics from the simulated data's `is_impersonator` labels without executing the evaluation code.

**Pattern:** When a prototype self-reports quality metrics (precision, recall, accuracy, pass rate), always run the prototype and verify those numbers appear in real stdout. If they don't, they're fabricated from the design spec.

### 3. Grill card iteration budget exhaustion (run 30)

The first run of the grill card (run 30) hit the 50/50 iteration budget and completed after writing only the research report. It never launched PO or produced any grill decisions. The card was marked `done` with `outcome: completed` despite missing the grill entirely.

**Why:** 3 parallel research subagents consumed ~40+ iterations of the budget. The grill RPC loop (20+ Q&A rounds with PO, each taking 60-200s) needed another 40+ iterations. Total exceeded the 50-iteration cap.

**Impact:** The build card spawned, found empty `context/`, and correctly blocked (`needs_input`). The grill had to be completed in a continuation session.

**Mitigation:** The grill card body should explicitly say "delegate research first, then use remaining iterations for the grill." If research subagents eat the budget, the dispatcher's reclaim gives a fresh session. The 2-card split helps here — the grill card's only job is dossier + grill, not build.

### 4. PO kanban tool leakage

The PO session (running env-isolated with `env -u HERMES_KANBAN_*`) accessed the kanban board directly: unblocked the build card, wrote comments as "worker" including a founder directive on scope, and reported the grill as complete.

**Why env isolation isn't enough:** It removes task context so PO doesn't think it's the worker. But the `kanban_*` tools are still in PO's toolset. PO can call them on any task ID it discovers from the `[GRILL STATE]` prefix or the builder's answers.

**Mitigation:** Instruct PO in the launch prompt to not touch kanban. Verify product-owner profile doesn't have `kanban` toolset. Avoid mentioning task IDs in grill answers.

## Key decisions locked

Three pre-committed kill criteria:
1. Detection precision >= 35% AND recall >= 70%
2. Takedown success >= 40% within 14 days
3. Subscription retention >= 5% free-to-paid conversion

MVP scope: Apple App Store + Google Play only. Search-result monitoring (top 50), not full catalog crawl. Weighted scoring with developer mismatch as multiplier. Conditional ignore list for adaptive impersonators.

## Lessons for future sessions

1. **Always run the prototype during verification.** Static-only verify scripts are a false confidence generator. See `prototype-verification` skill.
2. **Research subagents can eat the grill card's iteration budget.** Delegate research, but monitor iteration count. If approaching the limit, the grill must take priority.
3. **PO oversteps its role when it has kanban tools.** Add explicit "do not touch kanban" to the PO launch prompt.
4. **The 2-card split is the right architecture.** It isolated the grill (85 decisions, deep) from the build (fast, scoped). The build card's block-unblock cycle worked correctly.
