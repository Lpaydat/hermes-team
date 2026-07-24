# E2E Test #2 — AI Pen Testing Service

**Date:** 2026-07-24
**Card:** t_6db568d5
**Idea:** AI Pen Testing Service (18/25)
**Result:** PASS — all components working

## What was tested

New workflow with updated skills: self-grill (per-branch output + validation gate), venture-prototype (POC gate, type selection, README template), loop_engine enabled.

## Timing

- 05:30 — Card created, dispatcher claimed
- 05:31 — Builder launched PO with timeout 600 (fix applied and working)
- 05:36 — Grill state initialized, 6 branches created by PO
- 05:46 — Card blocked (builder called kanban_block during grill — same old issue)
- 05:57 — Grill branches persisted to ~/projects/
- 06:08 — Card completed

## Component results

| Component | Result | Notes |
|---|---|---|
| Grill persisted to ~/projects/<slug>/context/ | PASS | 13 files, 6 branches, 24 locked decisions |
| Validation script | PASS | 23 checks, 0 failures |
| Prototype type correct | PASS | HTML (web dashboard — correct for SaaS) |
| Prototype built | PASS | index.html |
| README exists | PASS | Full 9-section structure, 8 specific "How to Review" steps |
| Grill decisions in README | PASS | 12-decision summary table with PO challenges |
| Portfolio updated | PASS | Rich entry with correct ~/projects/ path |
| Card completed | PASS | done at 06:08 |
| No files in ~/vault/ | PASS | All artifacts in ~/projects/ |
| loop_engine used | NOT USED | Builder did one-shot build (acceptable for simple HTML) |

## Issues found

1. **Duplicate grill files** — builder created both `build.md` AND `build-vs-wrap-&-technical-moat.md` (short + long names). 6 branches → 12 files instead of 6. Cosmetic.
2. **Card blocked during grill** — same issue as E2E #1. Builder self-healed via CLI. The NEVER-block instruction in self-grill doesn't override the system prompt's kanban task protocol.
3. **context/ folder was named grill/ initially** — renamed to context/ mid-session per user direction.

## What the new workflow fixed vs E2E #1

| Problem from E2E #1 | Fixed? |
|---|---|
| Grill output lost to /tmp/ | YES — persisted to ~/projects/context/ |
| 3/10 had no grill docs | YES — validation gate enforces output |
| Inconsistent naming | PARTIAL — short+long names, but content is there |
| No READMEs (8/10 missing) | YES — full README with all 9 sections |
| Wrong location (~/vault/) | YES — everything in ~/projects/ |
