# Graph-Backed Grill E2E Test — 2026-07-21

## Setup
Tested self-grill v0.3.0 (graph-backed state, `<Q>`/`<LOCK>`/`<DONE>` tag extraction).
PO: glm-5.2 via zai provider. Idea: "A CLI tool that tells you if it's too late to start a new coding project tonight."

## What worked
- graph_state.py: all commands functional (init, lock, status, done, is-done, export)
- [STATE] injection: answer.sh prepended `[STATE: EMPTY]` before each answer
- Fallback: when PO didn't use `<Q>` tags, raw output went to stderr correctly
- Done detection: `<DONE>` in PO output triggered graph root resolution
- 19/19 unit tests pass (graph_state.py + tag extraction)

## What failed

### PO (glm-5.2) ignores ALL structured tags
- Launch output: no `<Q>` tags, plain markdown question
- Turn 1 (answer.sh): PO didn't use `<Q>` or `<LOCK>` tags, wrote plain markdown
- Turn 2: builder injected `<LOCK>` tags in answer text + reminder to use tags. PO still ignored them.
- Turn 3: same — plain markdown, no tags
- Conclusion: tag-based protocol requires a model that follows output format instructions. glm-5.2 doesn't.

### answer.sh LOCK extraction design flaw
- answer.sh extracts `<LOCK>` tags only from PO's output (RAW_OUTPUT), not from the builder's answer
- Even when builder wrote `<LOCK>` tags in the answer, they never reached the graph
- Fix options: (A) extract from both answer + output, (B) builder locks manually

### Early surrender (first attempt)
- PO wrote `<DONE>` after Q1 in the first attempt
- Second attempt with stronger anti-surrender prompt ("NEVER write <DONE> until 8 categories locked") worked — PO didn't surrender early
- But tag compliance didn't improve even with the stronger prompt

### Provider latency
- Launch took 11 minutes (zai congestion)
- First grill session (2026-07-21 GitHub sentence) averaged 60-200s per turn
- This session: one turn took >10 min before being killed

## Decisions for next iteration
1. Builder should lock decisions manually via `graph_state.py lock` — don't rely on PO for structured output
2. answer.sh should extract `<LOCK>` from BOTH the answer text AND PO output
3. Consider switching PO to deepseek-v4-flash for tag compliance
4. The `<Q>` extraction fallback (stderr) works reliably as a backup
