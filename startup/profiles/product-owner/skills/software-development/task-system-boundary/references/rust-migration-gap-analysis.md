# Rust Migration Gap Analysis — ngin daemon + nginbot-api + beads vs Hermes

**Date:** 2026-08-05
**Sources:** 3 parallel subagents reading actual source code across 4 repos

## The three systems and what each solves

```
                    GRAPH FORMAT          EXECUTION ENGINE         TASK TRACKER
                    ─────────────          ────────────────         ───────────
nginbot-api (TS)    ✅ BEST               ❌ synchronous only      ❌ none
Hermes engine (Py)  ⚠️ simpler            ✅ async, triggers       ⚠️ kanban (SQLite)
ngin daemon (Rust)  ❌ flat steps[]       ⚠️ task runner only      ✅ beads (Dolt)
```

## nginbot-api graph engine — what it has (better than Hermes)

- **Source directives**: `store:field`, `node:Id.output`, `input:name`, `#` (previous node) — declarative data wiring
- **Composite edges (fan-in barriers)**: target waits for multiple sources from different nodes
- **Expression engine**: full `expr-eval` (arithmetic, boolean, functions, `_` previous, `_item` iteration)
- **Conditional maps**: edge condition true → iterate array → create next step per item (dynamic fan-out)
- **GraphSchemaManager**: 7 validators (topology, edge, node, source, parameter, resource, defaults) with Tarjan SCC + CyclePolicy
- **Content-hash versioning**: xxhash of schema params → deterministic version
- **GraphQL API**: first-class CRUD for graphs, runs, steps
- **Type-safe node system**: TypeScript discriminated unions, compile-time checking
- **Run history DAG**: `{stepId: {in: [], out: []}}` tracks exact execution graph

## ngin daemon — what it has (better than Hermes)

- **Real PID tracking**: `libc::kill(pid, 0)` for liveness, `waitpid(WNOHANG)` for zombie reaping
- **Startup recovery**: pre-tick pass resets orphaned runs from previous crash
- **Atomic 4-step transitions**: update state → emit event → bd.comment → bd.set_dispatch_state
- **Circuit breaker**: consecutive_failures ≥ max → gave_up (terminal)
- **Ownership guard**: verifies issue being mutated matches run's assigned issue
- **Hallucination gate**: verifies created child cards actually exist in beads
- **Dry-run mode**: DryRunGuard previews every action without mutation
- **Graceful shutdown**: drain_running_dispatches marks running→interrupted
- **Review-loop breaker**: reject_count/gate_failures threshold breaks bounce loops
- **Assignee-change debounce**: cross-tick memory prevents dispatching just-changed issues
- **Trait-based testability**: BdCli, PidChecker, ProcessSpawner, Phase all mockable

## The 15 gaps ngin needs to close to replace Hermes workflow engine

### CRITICAL (Priority 1)
1. **Graph DAG execution engine** — ngin spawns one process per issue; needs to become a graph walker with per-node state tracking
2. **Conditional edges (AND/OR)** — unconditional incoming = AND, conditional = OR
3. **Template variable resolution** — `${nodes.X.output.Y}` → context dict per instance
4. **Back-edge loops** — Tarjan SCC at load, reset pass, iteration counters, max_iterations caps
5. **Triggers** — card_completed/bead_ready, completion scanner, condition matcher, dedup
6. **Subworkflow nodes** — child instance creation, parent blocking, cross-instance output reads
7. **Foreach fan-out** — list iteration, N card creation, aggregation

### IMPORTANT (Priority 2)
8. Command/wait node types (synchronous shell, poll condition)
9. JSON Schema output validation (principle-based verify depends on this)
10. Dead-branch skip propagation
11. Completion fence (re-read board truth before declaring complete)
12. Stateless/derived phase from board truth each tick

### NICE-TO-HAVE (Priority 3)
13. Zombie guard
14. Garbage collection
15. Optimistic concurrency / state blob versioning

## The 8 gaps beads has vs Hermes kanban

### CRITICAL (must build new subsystems)
1. **No task_runs / per-attempt retry tracking** — outcome/error/summary/PID per attempt
2. **No typed block semantics / loop-breaker** — dependency vs needs_input vs capability vs transient
3. **No claim/heartbeat/liveness** — claim_lock, claim_expires, worker_pid, heartbeat, stale reclamation
4. **No attachments** — on-disk blobs + metadata
5. **No gateway notification subscriptions** — push to Telegram/Discord on events
6. **No workspace management** — scratch/worktree/dir, workspace_path injection
7. **No worker-config injection** — skills/model/reasoning/goal_mode per-task
8. **No max_runtime_seconds / timeout enforcement**

### MODERATE (workable with conventions, lossy)
9. Status model mismatch (9 Hermes statuses vs 7 beads)
10. Board isolation model differs (per-board SQLite vs single Dolt DB)
11. No idempotency_key dedup
12. No session_id linking
13. No build_worker_context (structured handoff for retries)
14. No consecutive_failures circuit breaker
15. No lifecycle hooks

### Where beads is STRICTLY BETTER
- Version history / time-travel (Dolt commits)
- Typed multi-relationship dependencies (blocks/tracks/related/parent-child)
- Federation (cross-workspace sync)
- Branches (parallel work streams)
- Distributed sync (Dolt remotes, push/pull)

## Recommended architecture

```
nginbot-api graph format  →  graph specification language (source directives, composite edges, validators)
         +
ngin daemon (Rust)        →  execution runtime + NEW workflow module (graph walker on top of existing tick loop)
         +  
beads (bd)                →  issue tracker + NEW dispatch layer (runs, claim, heartbeat, workspace — built on top)
```

**Key principle:** Do NOT replace ngin's existing 8-phase tick loop. Add a workflow-engine layer ON TOP of it. Each workflow node dispatches as an ngin "run" — inheriting crash recovery, PID tracking, circuit breaker. The workflow engine decides WHAT to dispatch; ngin's existing phases handle HOW.

**Flow definition upgrade:** Extend `.ngin/flows/*.json` from `{steps: []}` to `{nodes: [], edges: [], trigger: {...}}`. Backward compat: if only `steps` present, treat as legacy single-process flow.

**New tables needed:** `workflow_instances` (instance_id, workflow_id, state blob, version), `trigger_keys` (dedup), `trigger_watermark` (last-scanned).

**Estimated effort:** ~3-4 focused engineering cycles. Graph walker + condition engine + trigger system is the bulk. ngin's existing reliability infrastructure is a significant head start.

## Hermes agent runtime stays

The daemon dispatches to Hermes gateways (not pi-coding-agent). Future plan: build a Rust-native agent runtime to replace both pi and Hermes.
