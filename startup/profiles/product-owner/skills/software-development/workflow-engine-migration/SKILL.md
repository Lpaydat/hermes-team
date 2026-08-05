---
name: workflow-engine-migration
description: "Evaluate whether an external graph/workflow engine can express Hermes workflow template features, and map Hermes template capabilities to a target engine's schema. Use when migrating templates to another engine, comparing engine expressiveness, or answering 'can engine X do feature Y from Hermes templates'. Knows the per-feature mapping methodology and the specific verdicts for nginbot-api (verified 2026-08-05)."
triggers:
  - migrate workflow templates
  - nginbot-api
  - graph schema mapping
  - engine expressiveness
  - can nginbot express
  - port hermes templates
  - workflow engine compatibility
  - capability mapping
---

# Workflow Engine Migration

Evaluate whether a target graph/workflow engine can express Hermes workflow template features. Provides a systematic per-feature mapping methodology plus known verdicts for specific target engines.

## When to load

- "Can nginbot-api / LangGraph / Temporal / <engine> express Hermes template feature X?"
- Migrating Hermes workflow templates to another execution engine
- Comparing engine expressiveness for a template design decision
- "Port these templates to <engine>"

## Methodology: the 10-point capability audit

For any target engine, evaluate each Hermes template feature against the target's native primitives. The 10 features that cover the full Hermes template surface:

1. **Node profiles/assignees** — how does the target bind agents to nodes?
2. **Body templates** — does the target support variable interpolation in node/task descriptions? What syntax (`${var}` vs `{var}`)? Inline paths or declared input bindings?
3. **Input/output schemas** — does the target validate node I/O against JSON Schema?
4. **Conditional edges (AND/OR)** — what condition operators exist? Can every Hermes operator (`==`, `!=`, `exists`, `is empty`, `<`, `<=`, `>`, `>=`) be expressed?
5. **Back-edges + iteration caps** — does the target support cycles? Does it cap execution count (runtime fire count), not just structural cycle length?
6. **Foreach / fan-out** — can a node iterate over a runtime list and create one sub-execution per item? Can item fields be interpolated?
7. **Triggers** — does the target support event-driven instantiation (card_completed, bead_ready)? This is the entry point for all reactive Hermes templates.
8. **Subworkflow nodes** — can a node embed/suspend on a child subgraph?
9. **Command/wait nodes** — can the target run arbitrary shell commands as nodes? Poll a condition until true?
10. **Trigger prefix isolation** — can the target filter events by string prefix matching (for loop safety)?

For each, give a verdict: **YES** (directly expressible), **PARTIAL** (expressible with transform/workaround), **NO** (gap — needs new engine feature).

## Known target verdicts

### nginbot-api (verified 2026-08-05)

Full per-feature analysis with code references: [`references/nginbot-api-capability-mapping.md`](references/nginbot-api-capability-mapping.md)

| # | Feature | Verdict | Key gap/constraint |
|---|---|---|---|
| 1 | Node profiles | **YES** | Maps to `resourceKeys.AGENT` + `node.resources`. `NodeFactory` resolves to `BaseAgent[]`. |
| 2 | Body templates | **PARTIAL** | `${var}` → `{var}`; every var must be a declared `inputSchema` property with `source` binding — no inline ad-hoc refs. |
| 3 | JSON Schemas | **YES** | Both standard JSON Schema. nginbot input schema is a superset (adds `source`). |
| 4 | Conditional edges | **PARTIAL** | expr-eval handles `==`/`!=`/`&&`/`||`/`<`/`>`. **Cannot express `exists` or `is empty`** truthiness operators. |
| 5 | Back-edges + max_iterations | **PARTIAL** | `CyclePolicy.maxLength` caps cycle LENGTH (node count), NOT runtime fire count. No per-edge iteration counter. |
| 6 | Foreach | **PARTIAL** | `ConditionalMap` does array fan-out, but it's an edge property not node property. Item dot-paths unverified. |
| 7 | Triggers | **NO** | No event subsystem. **BLOCKER — zero production templates can run.** |
| 8 | Subworkflow | **YES** | `GRAPH` node with `graphId`/`graphVersion`. Clean mapping via `RunCallback`. |
| 9 | Command/wait nodes | **NO** | Only SYSTEM/FUNCTION/TASK/GRAPH. Command used in 3/4 templates for routing. Workaround: TOOL resources. |
| 10 | Title prefix isolation | **NO** | No triggers → no prefix matching. expr-eval also lacks `startsWith`. |

**Gap severity ranking:** Triggers (#7) is the single blocker. Command nodes (#9) affect 3/4 templates. Back-edge caps (#5) affect the retry-loop pattern. The rest are mechanical transforms.

### Adding a new target

When evaluating a new target engine, create a `references/<engine-name>-capability-mapping.md` file using the same 10-point structure. Verify against the engine's actual source code, not its docs — read the type definitions, the condition evaluator, and the node factory. Add a row to the Known Verdicts table above.

## Key source files to read

### Hermes template model
- `~/.hermes-teams/startup/scripts/workflow_engine/model.py` — `Node`, `Edge`, `Trigger` dataclasses, `evaluate_condition()` grammar, `annotate_back_edges()`, `_validate_template_graph()`.
- `~/.hermes-teams/startup/scripts/workflow_engine/templates/*.json` — production templates.

### nginbot-api graph types
- `src/features/graph/types/types.ts` — `NodeType`, `INodeSchema`, `ConditionalRoute`, `ConditionalMap`, `NodeArgsMap`.
- `src/features/graph/types/schema.ts` — `CyclePolicy`, `ManagerState`.
- `src/features/graph/services/graph/schema/GraphSchemaManager.ts` — graph construction/validation API.
- `src/features/graph/services/graph/outgoingEdges.ts` — conditional edge evaluation (expr-eval), map iteration.
- `src/features/graph/services/nodes/factory.ts` — AGENT resource resolution.
- `src/features/graph/services/nodes/task/task.ts` — TASK node, description interpolation.
- `src/features/common/utils/stringExtractors.ts` — `{param}` extraction regex.
- `src/features/resource/types/schema.ts` — resource schema.
- `src/db/enums.ts` — `ResourceType.AGENT`.
- `src/lib/constants.ts` — `SOURCE_NODE_OUTPUT`, `SOURCE_INPUT`, `SOURCE_STORE`.

## Pitfalls

- **Don't trust engine docs for expressiveness claims.** Read the actual condition evaluator and node factory source. nginbot's docs don't mention that `exists`/`is empty` are unsupported — only reading `outgoingEdges.ts` reveals it uses expr-eval which lacks those operators.
- **Cycle length ≠ iteration count.** Many engines cap cycle *structure* (max nodes in cycle) but not *execution count* (how many times the cycle fires at runtime). These are fundamentally different termination guarantees. Always check whether the cap is structural or runtime.
- **Inline paths vs declared bindings.** Hermes allows arbitrary `${nodes.X.output.Y.Z}` inline. Many engines (nginbot included) require declared input bindings with explicit source mappings. This isn't just a syntax change — it's a scoping model difference that requires hoisting every variable into a schema property.
- **Triggers are the hardest gap.** If the target engine has no event-driven instantiation, the entire reactive template class (all `card_completed`/`bead_ready` templates) cannot migrate without building a trigger subsystem. This is usually the blocking gap.
- **Command nodes are silently load-bearing.** Routing junctions in Hermes templates are often `type: "command"` nodes (shell scripts that return routing decisions). If the target has no shell-execution node, these junctions need rearchitecting, not just re-platforming.
