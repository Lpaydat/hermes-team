# E2E Test #2 — AI Pen Testing Service

**Date:** 2026-07-24
**Card:** t_6db568d5
**Idea:** AI Pen Testing Service (18/25)
**Result:** PASS (structural) but FAIL (grill authenticity — discovered post-hoc)

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
| Grill persisted to ~/projects/<slug>/context/ | PASS | 13 files, 6 branches |
| Validation script (structural) | PASS | 23 checks, 0 failures (at the time) |
| Prototype type correct | PASS | HTML (web dashboard — correct for SaaS) |
| Prototype built | PASS | index.html |
| README exists | PASS | Full 9-section structure, 8 specific "How to Review" steps |
| Grill decisions in README | PASS | 12-decision summary table with PO challenges |
| Portfolio updated | PASS | Rich entry with correct ~/projects/ path |
| Card completed | PASS | done at 06:08 |
| No files in ~/vault/ | PASS | All artifacts in ~/projects/ |
| **Grill authenticity (post-hoc)** | **FAIL** | **Builder self-played both roles. PO session DB shows 0 `<Q>` tags.** |
| loop_engine used | NOT USED | Builder did one-shot build |

## Critical discovery (post-hoc): Builder self-played the grill

The grill output looked structurally correct (12 decisions, 6 branches, 10-14KB files) but was **fabricated**. PO session DB analysis revealed:

- PO session (20260724_053111_823fc4) has 56 messages but **0 `<Q>` tags**
- PO messages show identity confusion: "I jumped ahead and asked a question as PO, but I'm the builder"
- PO session ends with: "I'll run the full grill across all 6 branches. I'm the builder playing both roles"
- Builder wrote all branches in bulk via `execute_code` (not through the RPC loop)

### Root cause: HERMES_KANBAN_TASK environment variable leaks to PO subprocess

The builder runs inside a kanban task with `HERMES_KANBAN_TASK=t_6db568d5` set. When the builder calls `terminal("hermes -p product-owner --cli ...")`, the PO subprocess inherits this env var. PO then:
1. Sees `HERMES_KANBAN_TASK`, loads the kanban task protocol
2. Calls `kanban_show`, reads the task body
3. Thinks IT is the task worker (builder)
4. Loads self-grill skill (which was symlinked into PO's skills dir)
5. Writes both roles itself

### Fix applied

1. `env -u HERMES_KANBAN_*` in grill-rpc-ops before launching PO
2. Removed self-grill symlink from PO's skills dir
3. Added check 6 to validate-grill-output.sh: queries PO state.db for real `<Q>` tags (requires 5+)
4. Rewrote grill-rpc skill: identity anchor, "50+ questions", removed "8 branches" / "20+" limits
5. Added "NEVER self-play" section to self-grill SKILL.md

## Updated validation now catches this

After the fix, `validate-grill-output.sh ai-pen-testing-service` correctly FAILS:
```
✗ PO session 20260724_053111_823fc4 only asked 0 questions with <Q> tags
  (expected 5+). Builder may have self-played the grill instead of using real PO.
```
