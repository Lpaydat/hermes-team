# Workflow Graph Model — declarative node/edge design

The successor design to the 696-line `workflow-engine.py` cron: a **declarative graph model** (node types, edge types, conditions, entry/exit) that compiles *down to* the proven kanban primitives. Designed 2026-07-31. Full deliverables: `workflow-graph-model.md` (design spec) and `workflow-graph-schema.json` (Draft 2020-12 JSON Schema) — both validated with 31 checks (6 positive, 6 negative, conditional validation).

## Core principle: the graph is a declarative layer over the board

Every node materializes as kanban card(s). Every sequential/parallel-join edge becomes a parent-child dependency. The board's `recompute_ready` is the execution engine — it promotes cards when parents complete. The graph model does NOT replace the board; it replaces the imperative cron logic that decides *which* cards to create and *when*.

## Primitive mapping table (the key bridge)

| Graph node type | Creates | Compiles to | Replaces cron phase |
|----------------|---------|-------------|---------------------|
| `task` | 1 card | `kanban_create` | dispatch card creation |
| `fan-out` (branches) | N chains + root | `kanban_chains` | (tech-lead kanban_chains) |
| `fan-out` (foreach) | 1 card per item | loop + `kanban_create` per item | `phase_dispatch` |
| `fan-in` | 1 synthesis card | `kanban_create(parents=[all_terminals])` | (kanban_chains `after`) |
| `branch` | 0 cards (routing only) | runtime condition eval | dispatch routing logic |
| `loop` | root + exec + verify per iteration | `loop_engine` | (dev↔verifier cycle) |
| `gate` | 0 cards (sync only) | poll condition | (human review gates) |
| `emit` | 0 cards (side effect) | bd/kanban API call | `phase_bead_sync`, `phase_qa_trigger` |

## Seven node types

1. **`task`** — single-profile execution. One card, one assignee, one skill. Compiles to `kanban_create`. Implicit `next` field creates a parent→child edge.
2. **`fan-out`** — parallel split. Two modes:
   - `branches` (static): explicit list of branch chains. Maps directly to `kanban_chains(chains=[], blackboard, after=[])`.
   - `foreach` (dynamic): iterates a data source (`bd_ready`, `bd_list`, static list), one card per item. Maps to the cron dispatch loop. Dedup via `idempotency_key="bead-{{item.id}}"`.
3. **`fan-in`** — synthesis/join barrier. Waits for all branches, runs one card. Maps to `kanban_chains` `after` tail. The board dependency graph enforces the barrier.
4. **`branch`** — conditional routing. Evaluates a condition, routes to one downstream node. Creates no card — pure routing. Replaces cron `if/elif/else` (bug→debugger, wayfinder→scout, etc.).
5. **`loop`** — converge iterate. Execute → verify → decide. Maps to `loop_engine`. Layered exits: DoD met / hard cap / budget / no-progress.
6. **`gate`** — checkpoint/sync barrier. No execution; blocks until a condition is met (e.g., human approval = card status done).
7. **`emit`** — side-effect terminal. Produces an effect (bd_update, bd_close, create_card, log) without running a profile.

## Four edge types

| Type | Semantics | Board mapping |
|------|-----------|---------------|
| `sequential` | B starts after A completes | `kanban_create(B, parents=[A.card_id])` |
| `conditional` | B starts after A completes *and* condition true | Engine evaluates at runtime; creates B only if true |
| `parallel-split` | A creates N independent branches; each runs concurrently | N cards, same parent context |
| `parallel-join` | B starts only after ALL branches complete | `kanban_create(B, parents=[all_branch_terminals])` |

Most edges are **implicit** (via `next` fields). Explicit edges needed only for parallel-split/parallel-join/conditional when not expressed via node fields.

## Conditions (JSONLogic-inspired, must be deterministic)

Structured predicates — no model judgment. Operators: `==`, `!=`, `in`, `not_in`, `contains`, `not_contains`, `exists`, `not_exists`, `matches` (regex), `gt`, `lt`, `gte`, `lte`. Combinators: `all` (AND), `any` (OR), `not` (NOT).

Grounded in real cron logic:
- Bug routing: `{"field": "issue_type", "op": "==", "value": "bug"}`
- Skip gt:slot: `{"field": "labels", "op": "not_contains", "value": "gt:slot"}`
- QA trigger: `{"field": "summary", "op": "matches", "value": "merged to (master|main)"}`

## Key design answers

### How does foreach work (one card per bead)?
A `fan-out` node in `mode: "foreach"` queries a data source on each engine tick. For each item, it materializes a card from the `template`, substituting `{{item.*}}` variables. Dedup via `idempotency_key: "bead-{{item.id}}"` — if a non-archived card with that key exists, skip. New beads on later ticks are picked up on re-evaluation. This is exactly `phase_dispatch` made declarative.

### How does a loop node know when to stop?
Four layered exits, checked deterministically in engine code (not model judgment):
1. **DoD met** — verifier returns `dod_verdict.dod_met == true` → converge
2. **Hard cap** — `max_iterations` reached → exhaust
3. **Budget** — cumulative cost exceeds `budget` → exhaust
4. **No-progress** — verdict byte-identical across `no_progress_threshold` iterations → exhaust

This maps directly to `loop_engine`'s DECISION logic. Termination is deterministic because caps live in plugin code, not prompts.

### How do fan-out/fan-in map to kanban_chains?
- **Static fan-out** (`branches`) → `kanban_chains` direct call: `branches[].steps[]` = `chains`, `blackboard` = `blackboard`, fan-in `next` = `after` tail.
- **Dynamic fan-out** (`foreach`) → does NOT map to `kanban_chains` (requires pre-planned topology). Maps to cron-style loop: iterate source, `kanban_create` per item.
- **Fan-in** → board dependency barrier: card with `parents=[all_branch_terminals]`. `recompute_ready` enforces the join.

## Trigger types (entry points)

- `bd_ready` — poll bd ready every N seconds (replaces cron main loop). Requires `project` path.
- `card_completed` — fire when a card completes matching assignee + summary regex (replaces qa-trigger).
- `manual` — human or agent starts it.
- `webhook` — future.

## Schema invariants (validated)

The JSON Schema (`workflow-graph-schema.json`, Draft 2020-12) enforces:
- Nodes are a map keyed by ID — the map KEY is the canonical node ID (an `id` field inside the object is optional/redundant). No node subtype requires `id`.
- Discriminator on `type` selects the node schema via `oneOf`.
- `bd_ready` triggers require `project` (conditional validation via `allOf` + `if/then`).
- `fan-out` in `foreach` mode requires `source` + `template`; in `branches` mode requires `branches`.
- `loop` requires `goal`, `execute`, `verify` (with `dod`), `max_iterations`, `on_converge`, `on_exhaust`.
- Conditions are recursive (`oneOf`: simple predicate | `all` | `any` | `not`).

The proxy-metric-without-battery rule (from `loop_engine` v2) is a **runtime check**, not schema-enforced — consistent with the existing engine design where `metric_type` enforcement lives in plugin code, not JSON Schema.
