# Foreach Subworkflow — Parallel Pipelines

## The problem

Foreach on task nodes is a barrier: N cards created, ALL must complete before the next node. This breaks pipelines where each item should flow independently.

```
WRONG (barrier):
  parse → grill (foreach, 10 cards) → build (foreach, 10 cards)
  
  grill cards: [1 done] [2 running] [3 ready] ... [10 ready]
  build can't start until ALL 10 grills finish
```

## The fix: foreach + subworkflow

Parent workflow spawns N independent child workflows. Each child runs its own pipeline — no barrier.

```
Parent:  parse (command) → spawn (foreach + subworkflow → child-template)
Child:   grill → build → handoff (sequential, independent per item)

  Child A: grill(A) → build(A) → handoff(A)
  Child B: grill(B) → build(B) → handoff(B)  ← starts independently
```

## Template structure

**Parent template** (`builder-grill-build.json`):
```json
{
  "id": "builder-grill-build",
  "nodes": [
    {"id": "parse", "type": "command", "command": "python3 parse.py"},
    {"id": "spawn", "type": "subworkflow", "workflow_ref": "builder-single",
     "foreach": "${nodes.parse.output.ideas}",
     "depends_on": ["parse"]}
  ],
  "edges": [{"from": "parse", "to": "spawn"}]
}
```

**Child template** (`builder-single.json`):
```json
{
  "id": "builder-single",
  "nodes": [
    {"id": "grill", "profile": "builder", "skill": "self-grill",
     "title_template": "Grill: ${trigger.name}",
     "body_template": "Slug: ${trigger.slug}..."},
    {"id": "build", "profile": "builder", "skill": "venture-prototype",
     "title_template": "Build: ${trigger.name}",
     "depends_on": ["grill"]},
    {"id": "handoff", "profile": "builder", "skill": "prototype-review-handoff",
     "title_template": "Review: ${trigger.name}",
     "depends_on": ["build"]}
  ],
  "edges": [
    {"from": "grill", "to": "build"},
    {"from": "build", "to": "handoff"}
  ]
}
```

## How item data flows to children

`_dispatch_foreach_subworkflow` injects item dict fields directly into child trigger context:
- If item is `{"slug": "x", "name": "Y", "score": 18}`, child context gets `trigger.slug`, `trigger.name`, `trigger.score`
- If item is a string, child gets `trigger.item`
- `item_index` always set

## Completion tracking

Parent's spawn node stores `_foreach_instances` (list of child instance IDs) in output. PHASE 1 checks if ALL children are `completed`. Parent completes only when all children complete.

## Tick ordering

Child instances are created during the parent's tick (PHASE 2 dispatch). But `load_active_instances()` already ran at the start of the tick. Children dispatch their first cards on the NEXT tick. Tests must call `tick()` twice when expecting child dispatch.

## 7 tests in test_foreach_subworkflow.py

- Basic spawn (N children)
- Independent progress (A completes while B runs — the KEY test)
- Parent completes when all children done
- Child context has item fields
- Empty list
- String items
- 3-step pipeline independence
