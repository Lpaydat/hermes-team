# Milestone-Auto-Refactor Pattern

## The pattern: kanban parent/child dependency gate as a deferred trigger

The kanban board natively supports a dependency gate: a card with `parents=[A, B]`
sits in `todo` until ALL parents reach `done`, then auto-promotes to `ready`.

This is a **deferred trigger** — no new engine trigger types, no cron polling,
no `wait` nodes. The board handles it natively.

## When to use

- Wait for N sibling tickets to complete, then fire a downstream workflow
- Milestone-triggered refactor (wait for milestone's tickets → scan codebase)
- Any "all children done, then trigger X" pattern

## Implementation (milestone-auto-refactor)

### 1. Pipeline creates milestone cards after decomposition

```
decompose → milestone-plan node:
  reads ticket_ids from decompose output
  groups 2-5 tickets per milestone based on dependencies
  creates [milestone-NN] cards with parents=ticket_ids
```

The milestone-plan node is a regular `task` node (profile=product-owner). It
calls `kanban_create` for each milestone with `parents=[ticket_card_id, ...]`.

### 2. Milestone cards sit in todo, auto-promote when tickets complete

The kanban board's dependency gate handles this automatically. No engine code.
No polling. When all parent tickets reach `done`, the milestone card promotes
to `ready`.

### 3. PO completes the milestone → downstream workflow fires

The refactor-cycle workflow triggers on `title_prefix_any: ["[milestone]"]`:

```json
"trigger": {
  "source": "card_completed",
  "condition": {
    "assignee": "product-owner",
    "status": "done",
    "title_prefix_any": ["[refactor-request]", "[milestone]"]
  }
}
```

The milestone card body contains the repo path, which the scan node reads via
`${trigger.card_body}`.

## Why per-spec refactor is too granular

A typical spec produces 3-5 tickets. After 3-5 small changes, the codebase
hasn't accumulated enough structural debt for the scanner to find real
deepening opportunities. Proven in testing:
- todo-app (48 tests, clean): 0 Strong candidates
- hangman (517 lines, proper module split): 0 Strong candidates

Refactor after milestones (3-5 specs worth of code) is the sweet spot — enough
accumulated code for the scanner to find real patterns.

## Template node body (from dev-dispatch.json)

The route-milestone node:
- Reads `${nodes.route-decompose.output.ticket_count}` and `ticket_ids`
- Groups tickets by dependency analysis (parallel tickets share milestones,
  dependent tickets split across milestones)
- Creates `[milestone-NN]` cards with `parents=[ticket_ids]`
- Body includes `kanban_create` instructions and completion metadata schema

## LIVETEST RESULTS — 4 test cases, all correct (board `lt-milestone` + `lt-ms-retry`)

| Test case | Tickets | Dependency graph | Milestones created | Correct? |
|---|---|---|---|---|
| **Small** (Markdown, 3 features) | 4 | Linear chain (01→02→03→04) | 1 milestone — all 4 in "Full converter" | YES — no natural split point |
| **Medium** (Expense, 6 features) | 6 | Star (T01 center, T02-T06 parallel) | 2 — M1 CRUD (T01+T02+T03+T06), M2 Reporting (T04+T05) | YES — functional layers |
| **Large** (Project Mgmt, 10 features) | 5 | Layered (T1→(T2∥T3)→T4, T3→T5) | 3 — M1 Foundation, M2 Entity CRUD, M3 Integration | YES — architectural layers |
| **Parallel** (Converter, 4 independent) | 6 | T1→(T2∥T3∥T4∥T5)→T6 | 3 — M1 Foundation (T1), M2 Converters (T2-T5 parallel), M3 CLI (T6) | YES — foundation/body/integration |

### Milestone auto-promotion confirmed

The kanban dependency gate works correctly:
- **Markdown milestone-01**: status `ready` — all 4 parent tickets done. Board promoted it.
- **Project Mgmt milestones**: M1 running (T1 done), M2 running (T2+T3 done, promoted), M3 still todo (T4+T5 incomplete)
- **Parallel converter**: milestone-01 (Foundation) completed when T1 completed, auto-promoted, and triggered refactor-cycle

### The full chain end-to-end:

```
[ticket-01] done ─┐
[ticket-02] done ─┤→ [milestone-01] auto-promotes to ready
                   │   → PO completes → refactor-cycle fires
                   │   → scan → review → stop or refactor tickets
[ticket-03] done ─┐
[ticket-04] done ─┤→ [milestone-02] → refactor again
```

## Key lesson

Before building new engine trigger types (sibling_completion, milestone_ready),
check if the existing kanban dependency gate can express the same semantics.
The parent/child mechanism is a general-purpose "wait for N cards to complete"
primitive that works with zero engine changes.

## Pitfall: milestone node crash when out of credits

The milestone-plan node crashed twice (DeepSeek credits exhausted) — appeared as
"Agent crash x2: worker exited cleanly without calling kanban_complete." This is
NOT a template bug — the agent body is correct. Always check `hermes kanban log <id>`
for the actual error (billing/credits) before debugging the template.
