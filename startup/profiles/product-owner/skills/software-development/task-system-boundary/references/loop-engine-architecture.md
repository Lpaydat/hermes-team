# loop_engine — the dynamic converge-loop engine (profile-managed)

> **Source:** read directly from `startup/plugins/loop_engine/` (tools.py 3068 lines,
> schemas.py 516 lines, __init__.py, README.md, SPEC.md) + workflow engine migration docs.
> Verified against the code, not aspiration. This is the DYNAMIC complement to the
> declarative workflow engine documented in `workflow-engine-v1-architecture.md`.

## What it is

`loop_engine` is a plugin that drives iterative **converge-loop** workflows on the
durable kanban board. It decomposes a GOAL into ordered PHASES; each phase runs its
own converge-loop (discover → execute → verify). The tool is invoked **once per
promotion** of the loop-driver card; each invocation runs ONE iteration of the outer
phase-loop.

**Core principle (loop engineering):** the LLM is a black box; the loop *around* it
is engineered. The board is the external state. The engine is the loop driver.
**Termination is always deterministic** — in plugin code, never model-enforced.

**It is tool-driven, not hook-driven.** The driver reads board state on its own
re-promotion. The observer hook registered in `__init__.py` is telemetry-only
(debug log). This sidesteps the verified `recompute_ready` ordering hazard
(dependents promote BEFORE the `kanban_task_completed` hook fires).

## Relationship to the workflow engine (static-dynamic coexistence)

loop_engine is explicitly classified as **profile-managed dynamic orchestration** —
it stays OUTSIDE the declarative workflow engine:

| Aspect | Workflow Engine (declarative JSON) | loop_engine (plugin) |
|---|---|---|
| Paradigm | Static DAG of nodes/edges in JSON templates | Dynamic converge-loop driven by tool calls |
| State | Template definitions + runtime card graph | Board blackboard comments (`loop_state`) |
| Looping | No native loop primitive | Core purpose — verifier-gated converge loops |
| Topology authoring | Pre-planned at template author time | Created dynamically per-iteration by the tool |

**Coexistence pattern:** the workflow engine dispatches a parent card (e.g., to the
debugger). The profile picks it up and calls `loop_engine` internally, creating its
own sub-topology. The workflow engine waits for the parent card to reach `done`. The
two systems never interfere — loop_engine is the sole topology author on its root
subtree. Flattening loop_engine into a declarative node breaks atomic authoring,
convergence judgment, and the FAIL-loop (the declarative engine has no loop primitive).

**loop_engine cannot be a declarative workflow template node**, but CAN be triggered
indirectly: a template dispatches a card to a profile whose skill (e.g., `debug-loop`)
calls `loop_engine` as a tool.

## The tool API

**Tool name:** `loop_engine` · **Handler:** `tools.loop_engine(args, **kwargs) -> str` (JSON)
**Schema:** `schemas.LOOP_ENGINE` · **Required:** `["goal"]` + `anyOf: [execution | phases]`

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `goal` | `string \| [Claim]` | — | What the workflow accomplishes. String = bare; `[Claim]` = pre-grounded (skips discover). Derives root idempotency key. |
| `runner` | `string` | `"worker"` | Profile driving the loop + default card assignee. Resolution: `runner → worker → default`. |
| `execution` | `object` | — | Single execution card `{assignee?, title, body, skill?}`. |
| `phases` | `array` | — | Ordered phase specs `[{execution, verifier?, max_iterations?}]`. |
| `verifier` | `object` | — | Evaluate step (enables T2 mode). `{assignee?, title, body, skill?, metric_type?, battery?, dod_signals?, strict_fact_basis?, strict_dod?, artifact_required?}`. |
| `max_iterations` | `integer` | `5` | Hard iteration cap for verifier-gated loop. |
| `budget` | `integer` | `None` | Workflow-wide cost-unit budget (1 unit/iteration). |
| `no_progress_threshold` | `integer` | `2` | Escalate after N consecutive identical verdict hashes. |
| `discover` | `object` | engine-default | Phase-0 grounding `{assignee?, dod, max_iterations?}`. |
| `strict_fact_basis` | `boolean` | `false` | T9 opt-in: hard-requires `metric_type` + `evidence`. |
| `strict_dod` | `boolean` | `false` | T8 opt-in: hard-requires structured `dod_signals`. |
| `loop_id` / `root_id` | `string` | — | Durable loop handle. Echo on re-invocation for drift-immunity. |

### Module constants (tools.py)
```
MAX_PHASE_STEPS = 1               # T1 hard cap
DEFAULT_MAX_ITERATIONS = 5        # T2 verifier-gated loop cap
DEFAULT_ITERATION_COST = 1        # cost units per iteration
DEFAULT_NO_PROGRESS_THRESHOLD = 2 # consecutive identical verdicts
MAX_REEVAL_ATTEMPTS = 3           # stale/missing-verdict re-evaluations
DEFAULT_RUNNER = "worker"
RUNNER_FALLBACK = "default"
```

## Two modes

- **T1 spine (no verifier):** ONE phase, ONE iteration, execute-and-read. First
  invocation builds root + execution card, parks (status=blocked). Re-invocation
  stub-decides at hard cap 1 (status=complete / workflow_complete).
- **T2 verifier-gated converge loop (verifier present):** after execution completes,
  an independent verifier card evaluates output against the DoD, completes with a
  `dod_verdict` in `run.metadata`. Driver reads verdict on promotion and decides:
  advance / replan / escalate.

## The phase model (discover → execute → verify)

The engine is **consumer-agnostic** — no hardcoded domain concepts. The generic
phase model is discover → execute → verify per phase:

1. **Discover (phase 0, always-on):** Grounds the goal in evidence before user phases.
   Three modes: `[Claim]` goal → fast-pass (skeleton, no worker); bare string +
   `discover:{}` → dispatch grounding worker; bare string, no config → fast-pass
   skeleton (`unconfigured`).
2. **Execute:** Card parented on root, assigned to a worker profile.
3. **Verify:** Independent verifier card (parented on execution card) evaluates
   against DoD, completes with `dod_verdict` in `run.metadata`.

### The dod_verdict shape
```json
{
  "dod_met": true,
  "score": 0.85,
  "gaps": [{"dimension": "...", "issue": "..."}],
  "recommendation": "advance|replan|escalate",
  "evidence": [{"text": "...", "citations": [{"artifact_type": "test_output", "locator": "pytest -q"}]}]
}
```

## Decision logic (advance / replan / escalate)

On each re-promotion (`_reinvoke_verifier`), the engine reads the terminal's
`dod_verdict` via `latest_run` direct read, then:

**Advance** (DoD met + artifact complete):
- `dod_met=true` AND `_validate_dod_artifact()` passes → `_advance_or_complete()`
- If proxy metric with battery → dispatch battery card first (terminal gate)
- Multi-phase + non-last → `_advance_phase()` (next phase sub-graph, re-park)
- Multi-phase + last → `workflow_complete`
- Single-phase → `advance`

**Replan** (DoD not met, under caps): `_replan()` — creates fresh execution +
verifier cards (new iteration), re-parks. Completed cards can't re-run.

**Escalate** (layered exits — ALL route to sticky HITL `needs_input` block):
Order: (1) verifier `recommendation=="escalate"`, (2) `budget_remaining<=0`,
(3) `no_progress_streak>=threshold`, (4) `iteration_counter>=cap` (hard cap).
`_escalate()` does `block_task(kind="needs_input")` (sticky — recompute_ready won't
auto-promote) + `_append_event("loop_escalated", {exit, phase, iteration, human_owes})`.

**Evidence gate** (`_apply_evidence_gate`): a "done" verdict with an un-cited
material claim does NOT advance — forces `dod_met=false` + `recommendation="replan"`.
Under `strict_fact_basis`, a verdict with no `evidence` key also trips.

## The blackboard pattern (state-sharing, NOT "breadcrumbs")

There is NO "breadcrumb" concept in loop_engine. State-sharing is the **blackboard
pattern**: all loop state lives as JSON in comments on the root card (last-write-wins
per key, prefixed `[swarm:blackboard]`).

- **`loop_state`** key: `{phase_index, iteration_counter, terminal_ids,
  execution_card, verifier_card, max_iterations, exit_counters, resolved_runner,
  strict_fact_basis, ...}` — single source of truth. Driver is stateless between
  promotions.
- **`_loop_protocol_footer(root_id)`**: injected into execution + verifier card
  bodies so grandchild workers can read the shared blackboard via `kanban_show`.
- **`council:last_iteration`** / **`council:best_so_far`**: persisted by driver
  (`_persist_council_state`) so replan/converge workers read prior verdicts/scores.
- **`context_brief`**: discover worker's evidence `[Claim]`, stored for replans.
- **`loop_engine_root`**: written to the DRIVER's own blackboard so a drifted,
  loop_id-less re-invocation recovers the same root (drift-immunity backstop).

## Identity: root_id vs goal_hash

The durable identity of a loop is `root_id` (root card's task id), NOT the goal hash.
- First call: omit `loop_id` → engine mints root via goal_hash bootstrap, returns
  `root_id`.
- Re-invocation: echo `root_id` as `loop_id` → opens that exact card, reads
  `loop_state` directly (drift-immune — kills the goal-drift defect class).
- `loop_id_mismatch`: if supplied `loop_id` doesn't resolve, fires event + falls
  back to goal_hash.

## What profiles use it (consumer-agnostic)

| Profile | Consumer workflow | Notes |
|---|---|---|
| **Debugger** | `debug-loop` (reproduce → hypothesize → falsify → converge) | Canonical v2 consumer. `strict_fact_basis=True`, 3 phases, `runner="debugger"`. |
| **Architect** | `design-council` (researcher + peer fan-out → PO interview → ADR) | Profile-managed converge loop. |
| **Developer/builder** | (indirect — execution cards within loops) | Assigned via `_resolve_assignee`. |

## The 4 enable gates (install)

For `loop_engine` to reach a worker session, ALL four must be open:
1. **Plugin enabled** (in plugins config / manifest active).
2. **Global enable** (not disabled by a global flag).
3. **Profile toolset** (driving profile declares the tool / inherits plugin tools).
4. **Plugin symlink** (`startup/profiles/<profile>/plugins/loop_engine` so
   `PluginManager.discover_and_load()` finds it — the gate most easily missed).

If any gate is closed, the tool is invisible (no error, just absent). Verify via the
REAL `PluginManager.discover_and_load()` against a throwaway profile, not direct-import.
