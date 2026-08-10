# Refactor Cycle Livetest — 3 Codebases

Tested the `refactor-cycle.json` template against 3 codebases on board `refactor-test`. Both the STOP path (clean codebase → no tickets) and CONTINUE path (messy codebase → tickets created) were proven.

## Test 1: todo-app (clean) — STOP path

- **Codebase:** 642 lines (99 production, 382 tests), 4 modules (models/storage/cli/__main__)
- **Trigger:** `[refactor-request] Post-milestone cleanup: todo-app`
- **Scan result:** `codebase_clean: true`, 0 Strong, 0 Worth exploring, 2 Speculative
  - Scanner correctly identified that load→mutate→save duplication fails deletion test (would be a shallow pass-through at this scale)
- **Review verdict:** `stop` — independently verified by reading all 162 source lines
- **Decompose:** skipped (dead-branch — review verdict=stop, conditional edge to decompose didn't fire)
- **Workflow:** completed with zero tickets created
- **Wall clock:** ~10 minutes (scan 5min + review 5min)

## Test 2: hangman (clean) — STOP path

- **Codebase:** 517 lines, 11 files, 6 source modules (game/display/cli/wordlist/__init__/__main__)
- **Trigger:** `[refactor-request] Post-milestone cleanup: hangman`
- **Scan result:** `codebase_clean: true`, 0 Strong, 0 Worth exploring, 2 Speculative
  - Scanner noted all modules are "appropriately deep — game.py is a deep state machine"
- **Review verdict:** `stop` — independently verified
- **Workflow:** completed with zero tickets created

## Test 3: messy-refactor-test (deliberately bad) — CONTINUE path

- **Codebase:** 116 lines, 1 god module (app.py — all logic in one file: model + storage + CLI + shallow wrappers), 4 tests
- **Deliberately planted problems:** god module (no separation), 3 shallow wrapper functions (get_store_path/get_todos/put_todos), duplicated load→mutate→save lifecycle in every handler, tests that bypass interfaces
- **Trigger:** `[refactor-request] Cleanup: messy all-in-one todo app`
- **Scan result:** `codebase_clean: false`, **2 Strong candidates**
  - C1: no repository module — storage scattered, no atomicity, duplicated lifecycle
  - C2: no command/service layer — each handler fuses orchestration + business rule + print
- **Review:** fanned out 2 reviewer cards via kanban_chains (one per candidate)
  - Each reviewer read the actual code and confirmed the friction is real
  - Both validated as Strong
  - Verdict: `continue`
  - REFACTOR.md written to repo root
- **Decompose:** created 2 refactor tickets:
  - `[ticket-refactor-01] C1: extract TodoRepository (storage layer)` — running
  - `[ticket-refactor-02] C2: extract service layer` — ready (depends on 01)
- **Tickets fired tech-lead-execute** via `[ticket-` prefix trigger match
- **Wall clock:** ~20 minutes (scan 2min + review fan-out 10min + decompose 5min)

## What was proven

| Path | Trigger | Scan | Review | Decompose | Tickets |
|------|---------|------|--------|-----------|---------|
| STOP (clean) | todo-app | 0 Strong | verdict=stop | skipped | 0 |
| STOP (clean) | hangman | 0 Strong | verdict=stop | skipped | 0 |
| CONTINUE (messy) | messy-test | 2 Strong | verdict=continue | fired | 2 |

## Key findings

1. **The autonomous scan is honest.** On clean codebases it correctly says "clean" and doesn't invent friction. On the messy codebase it found exactly the problems that were planted. No false positives, no false negatives across 3 tests.

2. **The stop condition works.** When review returns `verdict=stop`, the conditional edge to decompose doesn't fire, decompose is dead-branch skipped, and the workflow completes. Zero tickets created.

3. **The kanban_chains fan-out in review works.** The verifier card created one chain per candidate, each with a reviewer that checked the candidate against real code. Both reviewers confirmed validity and provided file:line evidence.

4. **Refactor tickets trigger the existing pipeline unchanged.** `[ticket-refactor-NN]` matches tech-lead-execute's `[ticket-` prefix. No template changes needed to tech-lead-execute.

5. **REFACTOR.md persists between passes.** The scan node reads it on subsequent triggers ("these candidates were already identified — mark addressed items as done"). This enables the repeat-until-clean loop at the trigger level.
