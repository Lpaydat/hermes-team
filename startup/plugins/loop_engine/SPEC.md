# loop_engine — dynamic-workflow / loop-engineering plugin (spec)

> **Status:** DRAFT spec (v1 = engine only). A **generic loop-engineering engine** — drives any iterative converge-loop workflow on the durable kanban board. Composes with `kanban_chains` (execute) + `verifier` (evaluate); modifies neither. **Consumer-agnostic:** example consumers include debugging (the debugger profile), design (`design-council`), research, and UX/UI — each supplies its own phases/DoD; the engine has no domain-specific concepts.
> **Branch:** `design/debugging-workflow` (worktree). Implementation gets its own branch (shared plugin infra).
> **Date:** 2026-07-13.

---

## Problem Statement

Hermes orchestrators that need an **iterative converge-loop** — reproduce → hypothesise → fix → falsify (debugging), diverge → critique → synthesize → evaluate (design), search → read → synthesize (research) — have no shared engine. `kanban_chains` is **static**: the caller pre-plans the entire topology at call-time, builds the DAG atomically, parks, and is re-dispatched once. "Dynamism" today is re-implemented ad hoc by each orchestrator skill as *adapt-between-dispatches*, with no consistent definition-of-done contract, no independent evaluator wiring, no layered termination, and no durable per-iteration state.

The cost: every loop-bearing skill reinvents the same scaffolding, drifts on termination semantics, and cannot prove convergence. The user (an orchestrator profile author) wants to express a workflow as **a goal decomposed into phases, each phase a converge-loop with a definition-of-done and a stop condition**, executed on the durable kanban board by a shared, trustworthy engine — not hand-rolled per skill.

## Solution

A new **`loop_engine` plugin** (a tool plus optional observer hooks — the first plugin to register both) that drives **loop-engineering-style workflows** on the existing kanban board. The engine is the *engineered loop around a model black box*; the board is the *external state*; `kanban_chains` is the *execute* step; the `verifier` profile is the *evaluator*.

A workflow = a **goal** decomposed into ordered **phases** (subgoals). Each phase runs an inner converge-loop:

1. **Define** the phase definition-of-done (DoD) + optional stop condition.
2. **Plan** the iteration's execution (model judgment).
3. **Execute** via `kanban_chains` (fan-out to worker profiles).
4. **Collect + evaluate** — an independent `verifier` card checks the phase output against the DoD, returns a structured verdict in `run.metadata`.
5. **Decide** — DoD met → phase complete → next phase. Stop condition / hard cap / budget / no-progress → **escalate to human** (sticky blocked card). Otherwise → **replan** (repeat 2–5).

The whole thing is **durable by construction**: the loop-driver is itself a claimed card; all loop state lives on the board (blackboard comments + task edges + run metadata); the model is stateless between iterations. A crash or session boundary is recovered by re-reading board state on the next promotion.

**Composition, not modification:** the engine calls `kanban_chains` for execute, dispatches a `verifier` card for evaluate, and uses the board for state. `kanban_chains` stays the clean static-topology primitive. No changes to `kanban_db`, the dispatcher, or `kanban_chains`.

## User Stories

1. As an **orchestrator-profile author**, I want a shared loop engine, so that I do not reinvent converge-loop scaffolding per skill.
2. As an orchestrator, I want to **author a workflow as a goal + phases**, so that the engine drives the phasing for me.
3. As an orchestrator, I want each **phase to declare a definition-of-done**, so that convergence is a checkable condition, not a vibe.
4. As an orchestrator, I want each phase to declare an **optional stop condition**, so that a dead-end escalates instead of looping forever.
5. As an orchestrator, I want the stop condition **removable** (run-non-stop until goal), so that I can force exhaustive convergence when I accept the cost.
6. As an orchestrator, I want the engine to **plan each iteration**, so that replanning adapts to the results of the prior iteration.
7. As an orchestrator, I want execution to **fan out via `kanban_chains`**, so that phase work is durable, observable, and role-pure across profiles.
8. As an orchestrator, I want the **verifier to evaluate the DoD independently**, so that convergence is not self-graded.
9. As an orchestrator, I want the verifier's **verdict to flow back to the driver**, so that the decide step has the evidence.
10. As an orchestrator, I want **DoD-met to advance the next phase** automatically, so that the workflow progresses without my intervention.
11. As an orchestrator, I want **non-convergence to replan**, so that the loop iterates toward the DoD.
12. As an orchestrator, I want a **hard iteration cap per phase**, so that no phase loops forever even in non-stop mode.
13. As an orchestrator, I want a **token/time budget per workflow**, so that runaway spend is bounded.
14. As an orchestrator, I want **no-progress detection**, so that a loop circling a dead end breaks early.
15. As an orchestrator, I want **escalation to route to a human as a sticky blocked card**, so that HITL is observable, async, and survives sessions.
16. As a **deployer**, I want the **loop-driver's profile to be configurable per workflow**, so that the debugger profile drives debugging workflows, the architect drives design, etc.
17. As a deployer, I want a **fallback profile** (`worker` / `default`) when no specific profile is set, so that a workflow runs out of the box without a dedicated runner profile.
18. As an orchestrator, I want the loop to **survive a crash / session boundary**, so that a long workflow resumes from board state, not from scratch.
19. As an orchestrator, I want **re-drive to be idempotent**, so that a reclaimed or re-dispatched driver does not duplicate phase work or corrupt topology.
20. As an orchestrator, I want the **current phase, iteration, DoD, and exit counters to be observable on the board**, so that I (and observers) can see loop progress.
21. As a **human operator**, I want escalation to name **exactly what input or decision I owe**, so that I can unblock precisely.
22. As a human operator, I want to **unblock an escalated workflow** so that it resumes the loop.
23. As a **verifier**, I want a **defined DoD-verdict schema**, so that I return a structured, machine-readable judgment.
24. As a verifier, I want to **write my verdict to `run.metadata`**, so that the driver receives it without a custom channel.
25. As an **observer/auditor**, I want a **durable event trail** of phase transitions, replans, and escalations, so that I can reconstruct what the loop did.
26. As an orchestrator, I want the engine to **respect the ~60s dispatcher tick**, so that I understand per-iteration latency and can choose board-round-trips vs in-session loops deliberately.
27. As an orchestrator, I want the engine to **compose with `kanban_chains` rather than duplicate it**, so that topology authoring, atomic parent-linking, and dependency-parking stay in one place.
28. As an **implementer agent**, I want this spec to be **trackable as a single ready item**, so that I can build the engine in isolation before any consumer.

## Implementation Decisions

### Shape
- **New plugin `loop_engine`** under the plugins tree. Provides **one control tool** (invoked by the loop-driver each promotion) plus **optional observer hooks** (telemetry/audit). This is the first plugin to register both a tool and hooks; `PluginContext` supports it.
- The **loop-driver is a claimed card** on the board. The tool runs in the driver's worker process, resolves its own card id and run id from the worker environment, opens a board connection, and drives **one iteration** of the outer phase-loop per invocation.
- **Runner assignment:** the loop-driver card's `assignee` is set from the workflow goal/config. Unset → fallback profile (`worker`, then `default`). The dispatcher spawns the driver like any card.

### State (the board is the single source of truth)
- A **root card** per workflow (idempotency key `loop:{driver_card}:{salt}`).
- **Loop state** lives in blackboard comments on the root (last-write-wins per key, the `kanban_chains` pattern):
  ```
  loop_state = {
    phase_index, phase_plan,
    iteration_counter,
    dod_checklist: [...],
    exit_counters: {hard_cap, budget_remaining, no_progress_streak},
    terminal_ids: [...]
  }
  ```
- **Recovery on re-invocation** = re-read the blackboard + task edges (the `kanban_chains` recovery pattern). The driver is stateless between promotions.

### Phase decomposition = topology authoring
- For the current phase, create the phase's execution sub-graph via `create_task` with `parents=[root]` (atomic edge insertion in the same write-txn as the row — no orphan window).
- Each execution unit is a card carrying `assignee`, `skills`, `workspace_kind`, `priority`, `max_retries`, `max_runtime_seconds` — mapping layered exits onto board-native caps.

### Execute step
- **Call `kanban_chains`** to build + park the phase's execution chain (reuse its atomic linking, idempotent recovery, dependency-parking). Then the driver **dependency-parks itself**: `link_tasks` + `block_task(kind="dependency")`, which routes the driver to `todo` and lets `recompute_ready` promote it when **all** phase terminals are `done` (the fan-in barrier). Then return; the worker session ends; the dispatcher re-spawns the driver on the next tick when promoted.

### Evaluate step
- Dispatch a **verifier card** as a terminal parent of the driver. The verifier evaluates the phase output against the DoD and completes with a structured verdict in `run.metadata`:
  ```
  dod_verdict = {
    dod_met: bool,
    score: number,                 // 0..1, optional
    gaps: [{ dimension, issue }],  // concrete, checkable
    recommendation: "advance" | "replan" | "escalate"
  }
  ```
- `build_worker_context` injects the parent verifier's `run.metadata` into the driver as an `_metadata_:` line (4 KB cap). The driver reads `dod_met` / `recommendation` to decide.

### Decide + layered exits
- **DoD met** (verifier `dod_met=true` / `recommendation="advance"`) → mark phase complete in `loop_state`, create the next phase's sub-graph, dependency-park, return.
- **Replan** (`dod_met=false`, under caps) → increment `iteration_counter`, re-plan, re-execute.
- **Escalate** (stop condition fired, OR hard cap hit, OR budget exhausted, OR no-progress streak ≥ threshold) → `block_task(kind="needs_input")` (sticky; `recompute_ready` will not auto-promote), emit an event naming exactly what the human owes. Human unblocks → loop resumes.
- **Caps map onto board primitives:** hard cap → per-phase `iteration_counter` vs `MAX_PHASE_STEPS`; budget → cumulative token/time accounting in `loop_state` + per-card `max_runtime_seconds`; no-progress → state-hash unchanged across N iterations. The board's own circuit breaker (`max_retries`, `consecutive_failures`) is a backstop, not the primary loop guard.

### Termination is safety-critical, therefore deterministic
- The caps, budget, and no-progress checks live in **plugin code** (the tool handler), not in a model-followed skill protocol. Loop engineering's core tenet: the model is a black box; the loop *around* it is engineered. Termination logic must not depend on the model remembering to stop.

### Constraints respected (verified against the substrate)
- **Dependency-park does not trip `block_recurrences`**: the `kind="dependency"` branch of `block_task` routes to `todo` and returns before the recurrence counter runs. Re-parking the driver every iteration is safe. (The recurrence guard catches only truly-blocked same-cause re-blocks: `needs_input`/`capability`/`transient`.)
- **The verifier `run.metadata` path is confirmed end-to-end:** `kanban_complete(metadata=...)` stores a free-form dict on the closing run; `build_worker_context` surfaces parent `run.metadata` to the child driver. (The architecture gate already stamps structured completion metadata this way — existence proof.)
- **The engine is tool-driven, not hook-driven**, so it is unaffected by the verified ordering hazard (`recompute_ready` promotes dependents *before* the `kanban_task_completed` hook fires). The driver reads board state on its own promotion, not via a hook. Hooks are observer-only telemetry.
- **Idempotency is a pre-check (no unique index)** — the engine designs for **idempotent re-drive** (re-reading board state, dedup by intent) and does not rely on idempotency keys for mutual exclusion. The salt is chosen for recover-vs-rebuild semantics, not locking.
- **~60s tick latency is accepted** for v1 (board round-trips at phase + iteration boundaries). A tight in-session inner loop via the `pre_verify` nudge hook is explicitly deferred.

## Testing Decisions

- **One seam: board-level integration.** Drive a minimal workflow against a temporary board, assert **external board behavior only** — no internal state-machine mocks.
- A **stub verifier** returns a deterministic DoD verdict (configurable per test: advance / replan / escalate). No real LLM in the loop.
- Assertions cover: phase advance (phase N terminal `done` → driver promoted → phase N+1 cards created); dependency-park re-park across iterations without `block_recurrences` trip; verifier `run.metadata` DoD verdict arriving in the driver's `_metadata_:` line; each layered exit tripping correctly (DoD-met → advance; hard cap / budget / no-progress → sticky `needs_input` escalation); runner `assignee` respected and fallback applied when unset.
- **Prior art:** the `kanban_chains` plugin's own pytest suite (temp-board integration pattern) and the design-council `dc-val-*` validation boards.
- **What makes a good test here:** it would pass if the board state + metadata flow are correct regardless of how the engine's internals are refactored. It would fail if dependency-parking, fan-in promotion, or the verdict path regressed.

## Out of Scope (v1)

- The **debugging workflow** itself (the debugger profile + debug-loop skill). It will be the first *consumer* of the engine, in a later spec.
- The **UX/UI workflow**.
- **Hook-driven acceleration** (worker-side hooks that grow topology mid-phase; the `pre_verify` in-session inner loop).
- **Nested / re-entrant sub-loops** (a loop-engine phase that is itself a loop-driver) — idempotency salts and blackboard keys would collide; deferred.
- **Cancellation / cascade-block** of an in-flight subtree (no native "cancel children" primitive today).
- **`auto_decompose` interaction hardening** (the dispatcher may decompose cards; v1 assumes the engine is the sole topology author on its root subtree, or that auto-decompose is off for the workflow board).
- **Observability UI / dashboard** for loop progress (events are emitted; a viewer is later).
- **Loop-wide wall-clock budget** as a first-class primitive (v1 accounts budget in `loop_state` across re-dispatches; a native primitive is later).

## Further Notes

- **Durability by construction.** Loop engineering's "external state" = the hermes kanban board. The model is the fixed black box in the middle; the engine is the loop around it; the board holds the state. HITL escalation is a sticky blocked card, which spans multi-hour waits natively. This is why the design resolves the ephemeral-vs-durable tension without sandbox/VM machinery.
- **Concept sources:** loop engineering (Steinberger / Osmani, June 2026), the Karpathy loop (generator → evaluator → feedback → terminate on quality-threshold or max-iterations), and the canonical agent-loop pseudocode (`init_state → for step in MAX_STEPS: reason → execute → compact → verifier.passes? success : no_progress/budget? escalate`). Termination is "the single most common — and most expensive — mistake"; layered exits are non-negotiable even in non-stop mode.
- **Verified showstoppers (both cleared against real code):** (1) `block_recurrences` does not count `kind="dependency"` parks; (2) the verifier → driver `run.metadata` path is confirmed end-to-end (store + surface).
- **Relationship to the debugger spec:** the engine is the foundation; the debugger's debug-loop (reproduce → hypothesise/fix → falsify → converge, each a phase) becomes the engine's first consumer. Build the engine first, then the debugging loop on top.
- **Honest residual risks** (to address in the implementation plan, not this spec): partial-topology corruption if the driver crashes mid-phase-authoring (mitigated by atomic `create_task(parents=)` per card + idempotent re-drive reconciliation); silent optimistic-lock drop if a verifier/driver run is reclaimed mid-verdict (the engine must detect a dropped completion and re-evaluate); compound tick latency across a multi-handoff iteration (acceptable for v1, optimization later); `auto_decompose` potentially mutating engine-authored topology (assume sole-author or board-disabled for v1).
