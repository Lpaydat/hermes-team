# Dev-Dispatch Workflow Template Design

The dev-dispatch workflow is the first production template built on the stateless
engine. This document captures its design decisions and patterns reusable for
other routing workflows.

## Shape: Command-junction routing diamond

```
TRIGGER: card_completed (assignee=product-owner, status=done, title_prefix=[spec])
│
├── entry (command, synchronous — no card)
│   ├── edge: entry→route-bug       condition: ${trigger.type} == 'bug'
│   ├── edge: entry→route-scout     condition: ${trigger.type} == 'research'
│   ├── edge: entry→route-ops       condition: ${trigger.type} == 'ops'
│   ├── edge: entry→route-architect condition: ${trigger.type} == 'architecture'
│   └── edge: entry→route-tech-lead condition: ${trigger.type} != 'bug' AND ...
│
└── One route fires, others SKIPPED (dead-branch propagation)
```

## Why command-type entry?

A command node runs synchronously (echo) and completes in the same tick. No
kanban card is created for it. This means:
- Routing fires on the SAME tick as the trigger (1 tick instead of 3)
- No wasted PO card that just says "noop"
- The engine's `_update_blob_after_dispatch` sets `done: True` immediately

## Trigger condition keys

The `_matches_trigger` function supports:
- `assignee`: exact match on card assignee
- `status`: exact match on card status
- `metadata.<field>`: match on metadata key
- `title_prefix`: card title starts with this
- `title_not_prefix` / `title_not_prefix2`: card title does NOT start with this

## Trigger context fields

When a trigger fires, the context includes:
- `trigger.card_id`: the triggering card's ID
- `trigger.board`: the board name
- `trigger.assignee`: the triggering card's assignee
- `trigger.title`: the triggering card's title (added after body resolution bug)
- `trigger.<metadata-field>`: all metadata fields spread flat

## Edge-case test coverage

The test suite (`test_dev_dispatch.py`) covers 18 cases across 6 categories:
1. Basic routing (5 tests — one per route type)
2. Trigger filtering (3 tests — wrong assignee, status, title prefix)
3. Idempotency (1 test — no double-trigger across ticks)
4. Missing metadata (2 tests — empty + null metadata → defaults to tech-lead)
5. Multiple specs (1 test — two specs trigger two instances)
6. Entry/completion/validation (6 tests — archived card, entry no card, dead-branch
   skip, workflow completion, schema validation, body template resolution)

## Pattern for new routing workflows

1. Define trigger condition (what card completion event starts the workflow)
2. Create a command-type entry node as the routing junction
3. One conditional edge per route, condition on `trigger.<field>`
4. Default route uses `!=` on all specific types
5. Dead-branch skip propagation handles the non-matching routes automatically
6. Test all route types + trigger filtering + idempotency + missing metadata
