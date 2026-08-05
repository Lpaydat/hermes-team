# Graph/Workflow Schema Format Comparison

Reference knowledge from analyzing the **nginbot-api** `IGraphSchema` format (a TypeScript/Kysely graph engine) against the **Hermes** workflow template JSON format (Python dataclass-based). Use when comparing workflow formats, considering migration between them, or designing a unified schema.

## The two formats at a glance

| Aspect | Hermes template | nginbot-api IGraphSchema |
|---|---|---|
**Origin** | `startup/scripts/workflow_engine/model.py` | `nginbot-api/src/features/graph/types/types.ts`
**Language** | Python dataclasses → JSON | TypeScript types → JSONB
**Nodes** | Array `[{id, profile, skill, body_template, ...}]` | Object map `{ id: {id, type, inputSchema, ...} }`
**Edges** | Flat array `[{from, to, condition, max_iterations}]` — first-class topology view | Embedded per-node `node.edges.direct` / `node.edges.conditions` — scattered
**State** | Stateless nodes; output is the only contract | `storeSchema` + `storeUpdater` expressions — shared mutable state across nodes
**Data flow** | `${nodes.X.output.field}` template strings (loose) | `inputSchema.properties.field.source = "node:X"` (typed, validated)
**Profiles** | `profile` + `skill` per node (inline, dispatch-ready) | `resources` Set referencing a resource registry
**Triggers** | First-class `trigger: {source, condition}` | None (programmatic invocation)
**Iteration caps** | `max_iterations` per edge (load-time validated) | `cyclePolicy` graph-wide (allowDirect, allowConditional, maxLength)
**Sub-workflows** | `type: "subworkflow"` + `workflow_ref` | `type: "GRAPH"` node + `{graphId, graphVersion}`
**Validation depth** | Reachability, exit-node, back-edge caps | Schema, resource, parameter, topology, source, edge, graph topology
**Typing** | JSON Schema on outputs only | JSON Schema on inputs, outputs, store, AND resources

## nginbot-api IGraphSchema structure (9 top-level fields)

```
id                    string        — unique graph id
dataSchemaVersion     "20240904"    — format version constant (validated on import)
version               string        — xxhash64 of sorted input+output params (I/O contract hash)
supportMultipleEdges  boolean       — allow >1 edge A→B (each becomes separate queue entry)
storeSchema           JsonSchema    — shared mutable state shape (graph-wide memory)
inputSchema           object        — graph input payload shape (supports `source` overrides)
outputSchema          object        — graph output shape (supports `source` e.g. "node:build")
compositeEdges         object        — fan-in: { targetId: { sourceIds: [...] } }
nodes                 object map    — all nodes keyed by id (includes __start__, __end__)
resources             object map    — { resourceKey: {id, version, type, name, inputSchema} }
```

### Node types (4)

| Type | arguments | outputSchema | Purpose |
|---|---|---|---|
`SYSTEM` | none | JsonSchema | Virtual `__start__`/`__end__` nodes
`FUNCTION` | `{storeUpdater: {expr}}` | undefined | Pure state mutation (fan-in sink nodes must be FUNCTION)
`TASK` | `{description, expectedOutput?}` | JsonSchema | Agent-executed task (templates support `{var}` subst)
`GRAPH` | `{graphId, graphVersion}` | JsonSchema | Sub-graph invocation (blocks until child completes)

### Conditional routing (more powerful than Hermes)

```json
"edges": {
  "conditions": {
    "route_by_verdict": [
      { "target": "ship", "condition": "${verdict} == 'PASS'" },
      { "target": "fix", "condition": "${verdict} == 'FAIL'",
        "map": { "source": "verify", "storeUpdater": { "fix_count": "fix_count + 1" } } }
    ]
  }
}
```

The `map` field allows **state mutation on a conditional route** — Hermes conditions can only route, not mutate state.

## Persistence model (nginbot-api)

Single `Graph` table, composite PK `(id, version)`, full schema as JSONB `schema` column.
Graphs are **immutable and version-addressed** — no UPDATE, only new versions.
Execution tracked by: `Run` (instance) → `GraphState` (snapshots) → `StepState` (per-node) → `NextStep` (dispatch queue).

Tables:
- `Graph` (id, version, inputSchema, schema) — the schema itself, JSONB
- `Run` (id, graphId, graphVersion, history, createdBy) — execution instances
- `GraphState` (id, runId, caller, graphId, graphVersion, nodeId, stepId, prevStepId, resources, steps, history, input, output, store) — runtime state snapshots
- `StepState` (id, runId, graphId, graphVersion, nodeId, input, output, error) — per-node execution records
- `NextStep` (id, runId, source, target, stateId, status) — the dispatch queue (status: AVAILABLE/REUSABLE/EXHAUSTED)

## Versioning approach

```typescript
// graph.ts — version = hash of I/O contract only (not internal wiring)
inputParams  = sorted [{name, type}] from inputSchema.properties
outputParams = sorted [{name, type}] from outputSchema.properties
version = xxhash64(JSON.stringify(inputParams) + JSON.stringify(outputParams))
```

Two graphs with same inputs/outputs but different internal wiring get the **same version**.
This is deliberate: the version is a caller-compatibility contract, not a content hash.

Separate utility `generateVersionFromObject` (SHA-1, `object-hash`) with prefix system (`g-`, `ag-`, `tl-`) is used by the Resource model.

## Readability vs expressiveness verdict

- **Hermes is more readable** for humans: flat node list, flat edge array, inline profile/skill, `${var}` templating.
- **nginbot-api is more expressive/rigorous**: typed dataflow, shared mutable state, deep validation, resource registry, version-addressed immutability, conditional route mapping. But verbose (~2x the lines for equivalent workflow).

## Unified schema proposal (8 additions to nginbot-api base)

To support Hermes-style async dispatch on top of IGraphSchema:

1. **`dispatch.trigger`** — top-level `{source, condition}` (card_completed, bead_ready, manual, cron, webhook)
2. **`dispatch.idempotencyKey`** — dedup for workflow instances
3. **`dispatch.entryNodes` / `dispatch.exitCondition`** — explicit graph entry/exit
4. **`node.profile` + `node.skill`** — maps TASK nodes to agent profiles/skills for card creation
5. **`node.cardMode`** — template/delegate/chain dispatch semantics
6. **`node.foreach`** — list iteration (creates N parallel cards)
7. **`TaskArgs.bodyTemplate` / `TaskArgs.titleTemplate`** — kanban card body/title generation
8. **`ConditionalRoute.maxIterations`** — per-edge iteration cap (finer than `cyclePolicy.maxLength`)

The `dispatch` block is cleanly separated — engines that don't need async dispatch can ignore it and execute the graph synchronously.

## File locations in source repos

**nginbot-api** (`~/workspace/personal/ngin-bot/nginbot-api/src/features/graph/`):
- Types: `types/types.ts` (IGraphSchema L198, INodeSchema L231), `types/schema.ts` (managers)
- Validation: `types/validation.ts`, `services/graph/schema/validators/`
- Serialization: `services/graph/schema/managers/SchemaSerializer.ts`
- Persistence: `repositories/graph.repo.ts`, `db/types.ts` (Graph table L27)
- Versioning: `services/graph/graph.ts` L673 (generateVersion, xxhash)
- Constants: `lib/constants.ts` (START="__start__", END="__end__", DATA_SCHEMA_VERSION="20240904")
- Resources: `features/resource/types/schema.ts`

**Hermes** (`startup/scripts/workflow_engine/`):
- Model: `model.py` (Workflow, Node, Edge, Trigger dataclasses)
- Templates: `templates/*.json`

Full detailed analysis with complete JSON examples and the full proposed JSON Schema is in the session artifact: `~/.hermes-teams/nginbot-graph-schema-analysis.md`
