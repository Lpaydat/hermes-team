# v0.4 Branch-Based E2E Test — Full Results (2026-07-21)

## Test: "too-late-to-code" CLI — complete grill

**Idea**: A CLI tool that tells you if it's too late to start a new coding project tonight.

**Result**: COMPLETE. All 8 branches grilled through. 20 questions asked. 22 decisions locked. PO declared grill complete.

## Branch completion (in order)

| Branch | Decisions | Questions | Key outcomes |
|--------|-----------|-----------|-------------|
| product | 5 (D1-D5) | 6 | CLI command, JSON config, single-sentence verdict, sleep as cost metric, deliberate user action |
| user | 3 (D6-D8) | 4 | Personal tool, pre-commitment+reflection mechanism, no teeth/no memory |
| mechanism | 4 (D9-D12) | 4 | 3-state graduated verdict, effective sleep target formula, config schema, tomorrow-only selection |
| data | 0 (merged) | 0 | Data inputs covered by mechanism branch |
| edges | 2 (D13-D14) | 2 | Floor at 20:00, 4 edge cases (no config/past bedtime/invalid times/no meetings) |
| output | 2 (D15-D16) | 2 | Single line plain text, 5 output states |
| deployment | 2 (D17-D18) | 2 | Manual CLI invocation, pip/script in PATH |
| constraints | 4 (D19-D22) | 2 | Read-only, clock+config only, Linux/XDG, Python stdlib only |

## What worked

- **Branch system prevented re-asking**: Across 20 questions spanning 8 branches, PO never re-asked a resolved question. The `[GRILL STATE]` prefix showing "Questions already asked" per branch was effective.
- **PO transitioned branches naturally**: When orchestrator said "branch done, move to X", PO adapted immediately and started asking questions in the new category.
- **PO found real inconsistencies**: Caught D9 (3 inputs) vs D10 (formula only used 2 inputs). Caught prep-time gap in effective sleep target formula. Caught unfalsifiability of the tool's value proposition.
- **PO pushed to genuine depth**: Asked about mechanism of behavioral change, escape hatch design, cost currency, and observable success signals.
- **`<Q>` tag extraction**: ~50% compliance. stderr fallback handled the rest without information loss.
- **Q&A logging**: All 20 exchanges logged to branch files with incrementing Q numbers and timestamps.

## What didn't work

- **`<LOCK>` tags**: 0% compliance. PO never used them across any test session. Orchestrator locked all 22 decisions manually.
- **`<DONE>` for early surrender**: PO used `<DONE>` to escape after Q1 in one test run. Anti-surrender prompt reduced this but tag compliance for legitimate completion was unreliable.
- **_state.md auto-update**: Orchestrator maintained decision counts manually. The `sed`-based auto-update was removed as fragile.

## Design lesson: orchestrator owns structure, PO owns grilling

The fundamental insight from 4 E2E tests (v0.2, v0.3-graph, v0.4-test1, v0.4-test2):

PO (glm-5.2) is excellent at grilling — finding gaps, pushing depth, catching inconsistencies. It is terrible at structured output — tags, file protocols, decision logging. The system works when:
- PO does what it's good at: ask probing questions in natural prose
- The orchestrator does what PO can't: extract questions, lock decisions, manage state, track branches

This is a feature, not a bug. The branch system is designed around this asymmetry.
