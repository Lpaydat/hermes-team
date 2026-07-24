# loop_engine Partial Compliance (2026-07-24 Rebuild Test)

## The finding

On the RouteOpt rebuild card (t_0e3bc9ed), the builder partially complied with loop_engine for the first time. It:
- Wrote a verify script (`/tmp/verify-<slug>.py`, 6.2KB, 48 checks)
- Ran an independent verifier (delegate_task subagent, 14/14 decision checks)
- Posted verification results with line-number evidence in a task comment

But it did NOT run the full loop_engine phased mechanism with replan-on-fail loops. Evidence:
- Runtime ~8 min (real loop_engine takes 20-40 min)
- No replan evidence in comments (PASS on first try, no FAIL → fix history)
- No delegation artifacts in cache

## Why this matters

This is a NEW failure mode. Previous runs skipped loop_engine entirely (no verify script, no verifier). This run did the verification WORK but via delegate_task instead of loop_engine's built-in phased verifier gates.

The builder complied with the letter (verification happened) while violating the spirit (no phased build with replan cycles). The output quality was good (48/48 checks pass, all decisions reflected), but the structural protection against drift wasn't there — it got lucky that the one-shot build passed verification on the first try.

## Detection signs

How to tell if loop_engine was actually used vs substituted:

| Signal | Real loop_engine | Partial compliance |
|---|---|---|
| Runtime | 20-40 min | <15 min |
| Verify script | Yes | Yes (same) |
| Verifier | Built-in phased gate | delegate_task one-shot |
| Replan history | Present (FAIL → fix) | Absent (PASS first try) |
| Phase boundaries | Documented | Not documented |

## Enforcement options

Since instruction-level enforcement ("loop_engine is MANDATORY") doesn't work, and the builder now has a pattern for partial compliance:

1. **Card body requirement:** "Post the verifier's raw output including any failures. If there are zero failures, explain why no replan was needed."
2. **Runtime check:** If card completes in <15 min for a complex prototype, flag for manual review
3. **Verify script timestamp:** Check that `/tmp/verify-<slug>.py` was created BEFORE the prototype (file timestamps)
4. **Structural:** Pre-write the verify script in the card body so the builder doesn't have the option to skip Phase 0

## Outcome comparison

| Metric | Run 1 (no loop_engine) | Rebuild (partial compliance) |
|---|---|---|
| Prototype lines | 1117 | 1050 |
| Prototype size | 53KB | 47KB |
| Verify script | None | 48/48 checks |
| Independent verifier | None | 14/14 checks |
| Runtime | ~3.5h (full pipeline) | ~8 min (build only) |
| Quality | Good (manual check) | Good (verified) |

The partial compliance is better than zero compliance. The verify script + independent verifier pattern caught real issues in previous runs and provides evidence the prototype matches grill decisions. But the full loop_engine mechanism adds replan protection that prevents subtle drift.

## Recommendation

Accept partial compliance as a stepping stone. The verify script pattern is the valuable part — it provides executable evidence. The phased mechanism adds replan protection but costs 3-5x runtime. For most prototypes, verify script + independent verifier is sufficient. Reserve full loop_engine for complex multi-component builds.
