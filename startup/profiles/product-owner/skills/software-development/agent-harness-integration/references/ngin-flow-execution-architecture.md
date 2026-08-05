# ngin Flow Execution Architecture — daemon↔worker boundary

The daemon and the worker split flow execution across a hard boundary.
Understanding this split is essential before any steps[]→graph migration.

## The hard boundary: daemon is a dumb pipe, worker is the smart executor

| Layer | Codebase | Role |
|-------|----------|------|
| **Daemon** (Rust) | `daemon/src/` (spawn.rs, flow.rs, auto_resume.rs) | Claim → spawn → monitor → resume. Treats `steps` as **opaque JSON** (`Vec<Value>`). Never inspects step contents. |
| **Worker** (TypeScript) | `.pi/git/.../pi-subagents/src/runs/` (subagent-runner.ts, flow-runner.ts, flow-execution.ts) | Iterates `steps[]`, handles match/when/loop/subflow, threads `{previous}`, checkpoints, parallel groups, tree visualization. |

The daemon does NOT iterate steps. It does NOT know what a "step" is.
`FlowConfig.steps` is `Vec<Value>` — untyped JSON blob passed through verbatim.

## Data contract: SubagentRunConfig

**Daemon side** (`spawn.rs:17-38`):
```rust
pub struct SubagentRunConfig {
    pub id: String,
    pub cwd: String,
    pub result_path: String,
    pub async_dir: String,
    pub placeholder: String,       // issue title + description + 30 most recent comments
    pub flow: FlowConfig,
}

pub struct FlowConfig {
    pub steps: Vec<Value>,              // OPAQUE — daemon never inspects contents
    #[serde(default)] pub agents: Value,
    #[serde(default = "default_max_depth")] pub max_subagent_depth: u32,  // default 3
    #[serde(default)] pub skills: Vec<String>,  // merged: flow skills + issue skills
    #[serde(skip_serializing_if = "Option::is_none")] pub resume_state: Option<Value>,
}
```

Serialized to temp file (`/tmp/ngin-spawn/<run_id>.json`), passed as argv[2]
to `subagent-runner`. The runner reads it, deletes the temp file, and dispatches.

**Worker side** (`subagent-runner.ts:52-89`): same struct, typed as
`SubagentRunConfig` with `config.flow` carrying `steps, agents, maxSubagentDepth,
skills, resumeState`. Dispatches to `runFlowSubagent()` (if `config.flow` set)
or `runSubagent()` (sequential chain).

## Step variants (FlowStep union — worker side only)

```typescript
type FlowStep =
  | SequentialStep   // {agent: "builder", task: "...", output?, reads?}
  | ParallelStep     // {parallel: [{agent, task}, ...]}
  | MatchStep        // {match: {field, cases: {...}, default: [...]}}
  | WhenStep         // {when: [{condition, then: [...]}], else: [...]}
  | LoopStep         // {loop: {while?|foreach?|retry?, max, steps: [...]}}
  | SubFlowStep;     // {subflow: {steps: [...], input?, output?, previous?}}
```

The daemon reads only: `steps` (as array), `agents`, `skills`, `maxSubagentDepth`.
Everything else passes through as opaque JSON.

## Step execution (entirely worker-side)

Main loop in `flow-execution.ts:971`:
```typescript
for (let stepIndex = startStepIndex; stepIndex < flowSteps.length; stepIndex++) {
    const step = flowSteps[stepIndex]!;
    // dispatch: runParallelStep | executeMatchStep | executeWhenStep |
    //           runWhileLoop | runForeachLoop | runRetryLoop |
    //           executeSubFlowStep | runSequentialStep
}
```

The worker threads `{previous}` (output of step N becomes input of step N+1)
as an in-memory variable. It resolves templates, validates sandboxes, manages
working-tree stash/restore, builds a flow tree for visualization, and writes
checkpoints after each step boundary.

## Step failure behavior

**Sequential step fails** (`flow-execution.ts:1500-1515`):
- `r.exitCode !== 0` → loop breaks immediately
- Returns `{isError: true}` → worker writes `result.json` with `exitCode: 1`
- Worker process exits → daemon classifies the exit

**Parallel step fails** (`subagent-runner.ts:201`):
- `if (result.anyHardFailure) break;` — any task failure stops the whole run

**Daemon side:** sees process exit, classifies it. Crash (non-zero exit,
non-blocked status) increments `consecutive_failures` and triggers auto-resume
(Phase 3) if under the failure limit.

## Dual checkpoint model (critical gap)

### A. Worker-side: `.resume-state.json` (file-based, full state)

Written by `checkpointWriter.writeCheckpoint()` after every step boundary
(`flow-execution.ts:910-928`). Contains: `stepIndex`, `prev` (the {previous}
string), `globalTaskIndex`, `results[]`, `subFlowDepth`, `stepResumeData?`
(loop iteration state), `parallelStepState?`.

Resume restores state (`flow-execution.ts:948-962`):
```typescript
const startStepIndex = params.resumeState?.stepIndex ?? 0;
if (params.resumeState) {
    prev = params.resumeState.prev;
    globalTaskIndex.value = params.resumeState.globalTaskIndex;
    for (const sr of params.resumeState.results) { results.push({...}); }
}
// Loop starts at startStepIndex instead of 0
```

### B. Daemon-side: `flow_checkpoints` SQLite table (subset)

Schema (`001_pi_subagents.sql:45-56`):
```sql
CREATE TABLE flow_checkpoints (
    run_id                  TEXT PRIMARY KEY,
    flow_definition_hash    TEXT NOT NULL,
    step_index              INTEGER NOT NULL,
    prev                    TEXT,
    global_task_index       INTEGER NOT NULL,
    sub_flow_depth          INTEGER DEFAULT 0,
    results_json            TEXT,
    step_resume_data_json   TEXT,
    written_at              INTEGER NOT NULL
);
```

The daemon reads it in `build_resume_state()` (`spawn.rs:386-412`) to populate
`FlowConfig.resume_state`. **BUT it only reads 3 fields** (`step_index,
global_task_index, step_resume_data_json`) — it does NOT read `prev` or
`results_json`. The worker's `FlowResumeState` expects `prev` and `results`
for full restore. **This is a gap:** daemon-side checkpoint is incomplete
relative to what `executeFlow` needs for a full resume.

## Steps[] → graph migration analysis

### A flat steps[] IS already a linear chain

`steps: [A, B, C]` maps mechanically to:
```yaml
nodes:
  A: {agent: builder, task: "..."}
  B: {agent: tester, task: "..."}
  C: {agent: deployer, task: "..."}
edges:
  - {from: A, to: B}
  - {from: B, to: C}
```

Conversion: `steps[i] → node_i`, implicit `i → i+1` ordering → explicit edges.

### A graph format ALREADY EXISTS in pi-subagents

`graph-serializer.ts` parses `.graph.yaml` files with `{nodes: {...},
edges: [...]}`. The `GraphConfig` type carries `nodes` (object) and `edges`
(array). Flow migration goes TO this format, not a new one.

### What does NOT map cleanly

Control-flow step types within `steps[]` produce runtime-resolved edges,
not static topology:
- `{match: {...}}` — conditional branching
- `{when: [...]}` — multi-branch conditionals
- `{loop: {while/foreach/retry}}` — iteration (dynamic edges, runtime-determined)
- `{subflow: {steps: [...]}}` — nested graphs
- `{parallel: [...]}` — fan-out/fan-in

A static nodes+edges graph cannot represent `while(condition)` or
`match(field)` without either keeping control-flow as special node kinds
(match-node, loop-node), or making edges conditional (edge predicates —
which re-invents step types as edge metadata).

### The core question: who owns step sequencing?

- **Current:** Worker owns it (single process, in-memory `prev` threading,
  tight loop, ~700 lines of control-flow logic in `executeFlow`).
- **Graph-in-worker (low risk):** Worker still owns it, reads different input
  format. `FlowConfig` changes from `steps: Vec<Value>` to
  `graph: {nodes, edges}`. Worker needs graph-aware entry point
  (topological sort → execute). Preserves all current capabilities.
- **Graph-in-daemon (high risk):** Daemon becomes orchestrator, spawns one
  process per node. Loses in-memory data threading (must pass `{previous}`
  via files/env). Loses control-flow primitives (must reimplement
  match/when/loop/subflow). Must reimplement template resolution, sandbox
  validation, working-tree stash/restore, parallel coordination, tree
  visualization, checkpointing.

## Key source files

- **Daemon flow registry:** `daemon/src/flow.rs` — scans `.ngin/flows/*.json`,
  maps `flow:<name>` route → file path
- **Daemon spawn:** `daemon/src/spawn.rs` — `SubagentRunConfig`, `FlowConfig`,
  `build_flow_config()`, `build_resume_state()`, `write_run_config()`
- **Daemon auto-resume:** `daemon/src/auto_resume.rs` — Phase 3, reads
  `flow_checkpoints.step_index`, creates child run with `parent_run_id`
- **Worker entry:** `.pi/git/.../pi-subagents/src/runs/background/subagent-runner.ts`
  — reads config, dispatches to `runFlowSubagent` or `runSubagent`
- **Worker flow runner:** `.pi/git/.../pi-subagents/src/runs/background/flow-runner.ts`
  — `runFlowSubagent()`, writes status/result, calls `executeFlow()`
- **Worker executor:** `.pi/git/.../pi-subagents/src/runs/foreground/flow-execution.ts`
  — `executeFlow()`, main step loop, checkpoints, match/when/loop dispatch,
  tree building, stash/restore
- **Flow types:** `.pi/git/.../pi-subagents/src/shared/flow-types.ts` —
  `FlowStep` union, `FlowResumeState`, `LoopResumeData`, `ParallelStepState`
- **Graph serializer:** `.pi/git/.../pi-subagents/src/agents/graph-serializer.ts`
  — existing `.graph.yaml` parser (`{nodes, edges}` format)
- **Checkpoint schema:** `db/migrations/001_pi_subagents.sql` —
  `flow_checkpoints` + `flow_definitions` + `run_steps` tables
