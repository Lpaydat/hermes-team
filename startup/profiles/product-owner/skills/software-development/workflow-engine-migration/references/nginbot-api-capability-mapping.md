# nginbot-api Capability Mapping

> Verified 2026-08-05 against Hermes `model.py` + 4 production templates (`tech-lead-execute`, `qa-gate`, `debugger-exit`, `dev-dispatch`) and nginbot-api source (`types/types.ts`, `types/schema.ts`, `GraphSchemaManager.ts`, `outgoingEdges.ts`, `ExpressionProcessor.ts`, `factory.ts`, `nodes/task/task.ts`, `resource/types/schema.ts`, `db/enums.ts`, `lib/constants.ts`, `stringExtractors.ts`).

## Summary

| # | Hermes Feature | nginbot-api | Verdict |
|---|---|---|---|
| 1 | Node `profile` (assignee) | `resourceKeys.AGENT` + `node.resources` | **YES** |
| 2 | `body_template` `${nodes.X.output.Y}` | TASK `description` `{param}` | **PARTIAL** |
| 3 | Input/output JSON Schema | `inputSchema` / `outputSchema` | **YES** |
| 4 | AND/OR conditional edges | `edges.conditions` + expr-eval | **PARTIAL** |
| 5 | Back-edges + `max_iterations` | `CyclePolicy` (maxLength, no per-edge cap) | **PARTIAL** |
| 6 | `foreach` | Conditional `map` (iterate array → steps) | **PARTIAL** |
| 7 | Triggers (`card_completed`/`bead_ready`) | *(none)* | **NO** |
| 8 | `type:subworkflow` | `GRAPH` node (subgraph) | **YES** |
| 9 | `type:command` / `type:wait` | *(none)* | **NO** |
| 10 | `title_prefix` trigger isolation | *(none)* | **NO** |

## Per-feature detail

### (1) Node profiles → YES

Hermes `node.profile = "verifier"` → register an AGENT resource (`ResourceType.AGENT`, `db/enums.ts`), add the key to `node.resources: Set<ResourceKey>`, and the graph-level `resources` map. `NodeFactory.createNode()` (`factory.ts` L36) resolves AGENT keys → `BaseAgent[]` via `getResourceNames('AGENT', ...)`. `TaskNode` (`task.ts` L99) picks `agents[0]` to execute (multi-agent is TODO). Difference: nginbot treats agent as a runtime-resolved resource pointer; Hermes bakes the string into the card. Functionally equivalent.

### (2) Body templates → PARTIAL

**Syntax gap:** Hermes uses `${var}`, nginbot uses `{var}` (single braces, extracted by `extractTemplateParams` regex `/{([^{}]+)}/g` in `stringExtractors.ts`).

**Scoping gap (the real issue):** nginbot TASK `description` params must be declared in `inputSchema` with a `source` binding (`INodeInputSchema`, types.ts L99-107):
- `"node:<nodeId>.<field>"` (SOURCE_NODE_OUTPUT = `"node"`, constants.ts L9)
- `"input:<field>"` (SOURCE_INPUT = `"input"`, constants.ts L10)
- `"store:<field>"` (SOURCE_STORE = `"store"`, constants.ts L11)

You cannot write `{nodes.plan.output.task_count}` inline — declare `{ task_count: { source: "node:plan.task_count" } }` and reference `{task_count}` in the description. Hermes allows arbitrary inline `${nodes.X.output.Y.Z}` dot-paths.

**No trigger context:** `${trigger.*}` has no native equivalent (no trigger concept — see #7). Would need to be passed as graph `inputSchema` at instantiation.

**Transform required:** (a) `${x}` → `{x}`, (b) hoist every referenced variable into a declared inputSchema property with a source binding.

### (3) JSON Schemas → YES

Both use standard JSON Schema. nginbot's `INodeInputSchema` is a superset (adds `source`/`target` fields for data binding). `outputSchema` is equivalent. nginbot auto-injects `_raw` string property into output schemas (`TaskNode.formatOutputSchema`, task.ts L144).

### (4) Conditional edges → PARTIAL

**Hermes grammar** (`evaluate_condition`, model.py L657): `clause (OR clause)*`, `atom (AND atom)*`, `${var} <op> <value>`. Operators: `==`, `!=`, `exists`, `is empty`, `<`, `<=`, `>`, `>=`. No parentheses. AND binds tighter than OR.

**nginbot:** `ConditionalRoute.condition: Expression` evaluated via **expr-eval** (`outgoingEdges.ts` L174: `this.parser.parse(condition).evaluate(input)`). Supports `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, ternary, parentheses. Variables are bare identifiers resolved against `ExpressionScope`.

| Hermes op | expr-eval | Works? |
|---|---|---|
| `${x} == 'PASS'` | `x == 'PASS'` | ✅ |
| `${x} != 'PASS'` | `x != 'PASS'` | ✅ |
| `A OR B` | `A \|\| B` | ✅ |
| `A AND B` | `A && B` | ✅ |
| `${x} < 3` | `x < 3` | ✅ |
| `${x} exists` | *(none)* | ❌ |
| `${x} is empty` | *(none)* | ❌ |

**Gap:** `exists`/`is empty` truthiness operators have no expr-eval equivalent. Used in production (`tech-lead-execute.json` L202: `"${nodes.plan.output.plan_complete} exists"`). Workaround: coerce to boolean and test truthiness, but fails for falsy-but-present values (0, ""). Needs custom expr-eval function or pre-evaluation rewrite.

**Variable scoping:** Hermes `${nodes.X.output.Y}` is inline path. expr-eval needs flat identifiers in `ExpressionScope` — paths must be flattened and injected.

### (5) Back-edges + max_iterations → PARTIAL

**Hermes:** `annotate_back_edges()` (model.py L171) detects via Tarjan SCC + DFS discovery order. `max_iterations` caps execution count per back-edge. Validation (`_validate_template_graph`, L316) requires every cycle to have ≥1 capped edge.

**nginbot:** `CyclePolicy` (schema.ts L141): `allowDirect` (default false), `allowConditional` (default true), `strictMode` (default false), `maxLength` (default 10 — cycle LENGTH in nodes, NOT execution count).

**Critical gap:** `maxLength` caps structural cycle length (node count), not runtime fire count. No per-edge iteration counter exists in `outgoingEdges.ts`. A 3-node cycle with maxLength=10 could loop infinitely. Hermes `max_iterations: 10` means "retry the fix loop at most 10 times" — a runtime execution cap. Needs: (a) per-edge `maxIterations` on `ConditionalRoute`, (b) runtime iteration tracking in execution state, (c) conditional short-circuit on cap exceed.

### (6) Foreach → PARTIAL

**Hermes:** `Node.foreach` — node property, iterates a list, creates one card/subworkflow per item. `${item.field}` dot-path on items. Example: `builder-grill-build.json` spawns one subworkflow per idea.

**nginbot:** `ConditionalMap` (types.ts L116) — edge property, not node property. `map.source` specifies which node's output array to iterate. `outgoingEdges.ts` `conditionalSteps()` (L184-211): reads array from state via `sourceExtractor`, iterates, creates `FunctionNode` per item with `injectedParams: {_item: item}`, pushes `NextStepQueue` per item.

**Gap:** Item dot-path access unverified — `_item` injected as `ExprValue`, `extractTemplateParams` extracts bare `{param}` names (no dot-path resolution on items). Structural difference: Hermes foreach is node-level fan-out; nginbot map is edge-level fan-out (source → conditional edge with map → target per item).

### (7) Triggers → NO (BLOCKER)

**Hermes:** Every production template has `trigger.source: "card_completed"` with condition dict. Engine subscribes to kanban events, starts workflow instance on match. This is the ONLY entry point for reactive templates.

**nginbot:** No trigger concept. Graphs have `START` system node, launched explicitly via API. No event subscription, no external source integration, no condition-based instantiation, no webhook listener.

**Needed:** Full trigger subsystem: event listener layer, condition evaluator (assignee/status/metadata/title-prefix filtering), graph instantiation pipeline (trigger payload → inputSchema), trigger-to-graph registry. **Without this, zero production templates can run.**

### (8) Subworkflow → YES

Hermes `type: "subworkflow"` + `workflow_ref` → nginbot `GRAPH` node type with `arguments: { graphId, graphVersion }`. Parent receives output via `RunCallback`. Clean structural mapping. nginbot is richer (versioned subgraphs).

### (9) Command/Wait nodes → NO

**Hermes:** `type: "command"` runs shell, captures stdout as output. `type: "wait"` polls a condition each tick. Command nodes used in 3/4 production templates (routing junctions: check-merge in qa-gate, entry in dev-dispatch, check-verdict in debugger-exit).

**nginbot:** Node types are `SYSTEM | FUNCTION | TASK | GRAPH` only (types.ts L56). No shell execution, no polling/waiting. FUNCTION nodes run expr-eval `storeUpdater` expressions (pure state mutation).

**Workaround for command:** wrap each script as a TOOL resource, invoke via TASK node. Loses declarative inline-command ergonomics. **Wait:** no workaround — needs new node type or polling edge.

### (10) Title prefix isolation → NO

**Hermes:** `title_prefix: "[spec]"`, `title_not_prefix: "[probe]"` — string prefix matching for event routing isolation. Critical for loop safety (QA workflow's own `[qa]` output cards don't re-trigger QA).

**nginbot:** No trigger concept → no prefix matching. expr-eval also lacks `startsWith`. Needed: once triggers exist (#7), condition evaluator must support `startsWith`/prefix and negative-prefix exclusion.

## Gap severity (highest impact first)

1. **Triggers (#7)** — BLOCKER. Zero templates run without event subsystem.
2. **Command/Wait nodes (#9)** — 3/4 templates depend on command nodes for routing.
3. **Title prefix isolation (#10)** — loop safety, blocked by #7.
4. **Back-edge iteration caps (#5)** — retry-loop pattern needs per-edge maxIterations.
5. **Condition exists/is empty (#4)** — needs custom expr-eval extension.
6. **Body template scoping (#2)** — mechanical transform but verbose.
7. **Foreach item fields (#6)** — fan-out works, dot-paths need verification.
8. **Profiles (#1), Schemas (#3), Subworkflows (#8)** — NO GAP.
