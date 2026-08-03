# loop_engine plugin — how the converge loop works (code-referenced map)

This file captures the architecture of the `loop_engine` plugin
(`~/.hermes-teams/startup/plugins/loop_engine/`) so an agent designing
loop-driven workflows understands what the plugin already owns and does NOT
reimplement in a template or in ad-hoc card choreography.

Files: `__init__.py` (registration), `tools.py` (the engine, ~3000 lines),
`schemas.py` (tool schema + Claim/Citation dataclasses).

## Architecture: tool-driven, not hook-driven

`__init__.py:25` registers a `kanban_task_completed` hook, but it is
**telemetry-only** (debug log). The engine re-reads board state on each
promotion of the driver card. This sidesteps the `recompute_ready` ordering
hazard (dependents promote *before* the completion hook fires). The driver is
**stateless between promotions**; all state lives in `loop_state` on the root
card's blackboard.

## Sub-graph creation (`_first_invocation`, `tools.py:1866`)

1. Root card via `create_task` with idempotency key `loop:{driver}:{sha1(goal)[:10]}`
   — the shared blackboard. **Completed first** so children are `ready`.
2. Execution card (`_create_execution_card`, `tools.py:1200`): `parents=[root_id]`.
3. Verifier card (`_create_verifier_card`, `tools.py:1230`): **parented on the
   execution card** (`parents=[exec_id]`) — load-bearing: verifier is `ready`
   only after exec completes, and `build_worker_context` injects exec output.
4. Driver dependency-parks on the **terminal** (the verifier card).
   Topology: `root → execution → verifier ← (driver parked on verifier)`.

T1 spine (no verifier) parks on the execution card directly (hard cap 1).
Cards carry intent-stable idempotency keys
(`loop:{driver}:phase{N}:iter{I}:{role}`, `_card_idempotency_key:302`) so a
crash-replay dedups instead of creating duplicate phase cards.

## Phases

Two modes selected by whether a verifier is supplied:
- **T1 spine** (no verifier): one phase, one execution card, hard cap 1,
  stub-decide on re-invocation (`_reinvoke_t1`, `tools.py:2454`).
- **T2 verifier-gated converge loop** (verifier supplied): per-phase converge
  loops with `max_iterations` cap (`DEFAULT_MAX_ITERATIONS = 5`, `tools.py:87`).

Multi-phase (`phases` array): ordered list; each phase runs its own execution +
optional verifier + its own DoD. `_advance_phase` (`tools.py:2916`) creates the
next phase's sub-graph.

discover phase-0 (SPEC §2, always-on): a grounding worker runs before user
phases. Fast-passes (skeleton card, no worker) when goal arrives as cited
`[Claim]` array ("skipped") or no `discover:` block configured
("unconfigured") — `_fast_pass_discover_card` (`tools.py:2121`).

## Iteration counting (`iteration_counter` in `loop_state`)

- T2 first invocation seeds `iteration_counter: 1` (`tools.py:2042`) — the first
  exec+verifier pair IS iteration 1. T1 seeds 0.
- `_replan` (`tools.py:3014`): `next_iter = iteration_counter + 1`, persisted,
  fresh exec+verifier cards minted at the new iteration.
- `_advance_phase` (`tools.py:2916`): resets counter to 1 (T2) / 0 (T1).
- `_reevaluate` (`tools.py:1463`): does NOT advance the counter — bounded
  separately by `MAX_REEVAL_ATTEMPTS = 3` (`tools.py:105`).

## Decision tree (`_reinvoke_verifier`, `tools.py:2531`)

```
pre-checks:
  terminal not done         → repark existing (no phantom verdict)
  no structured verdict     → _reevaluate (bounded → stale_verdict escalate)
  un-cited material claim   → evidence gate forces dod_met=false

IF dod_met AND artifact_complete (no latent_defect):
    proxy+battery phase     → dispatch battery card (terminal gate)
    ELSE                    → _advance_or_complete
        multi-phase, non-last → _advance_phase (next phase sub-graph)
        multi-phase, last     → workflow_complete
        single-phase          → advance

ELSE (DoD not met):
    recommendation=escalate   → _escalate("verifier_escalate")
    budget_remaining <= 0     → _escalate("budget_exhausted")
    no_progress_streak >= N   → _escalate("no_progress")
    iteration_counter >= cap  → _escalate("hard_cap")
    ELSE                      → _replan (fresh cards, iter+1, repark)
```

**Critical:** the engine no longer trusts `recommendation="advance"` to override
a failed DoD (`tools.py:2602`). It requires `dod_met AND artifact_complete`.
Only `recommendation="escalate"` is honored from the recommendation field.

## Layered exits / HITL (`_escalate`, `tools.py:1589`)

ALL exits route to a sticky HITL block — termination is **deterministic**
(plugin code, not model-enforced; SPEC §"Termination is safety-critical,
therefore deterministic"). `_escalate` performs:
1. `block_task(kind="needs_input")` — sticky (`recompute_ready` will NOT
   auto-promote; spans multi-hour waits; `unblock_task` is the only resume).
2. `_append_event("loop_escalated", payload)` naming exactly what the human owes
   (`_human_owes`, `tools.py:1560`): exit reason, phase, iteration, gaps/budget/cap.

Exit reasons: `hard_cap`, `budget_exhausted`, `no_progress`,
`verifier_escalate`, `stale_verdict`.

## Debugger-specific exits (no-seam, blocked-hitl)

"no-seam" and "blocked-hitl" are **debugger-level terms**, NOT plugin terms
(zero matches in the plugin dir). They are realized via loop_engine:

- **no-seam / exit-B (design flaw):** the falsify verifier sets
  `recommendation: "escalate"` with `no-correct-seam` / `root-cause-spans-boundary`
  in gaps → `_reinvoke_verifier` hits `recommendation == "escalate"` first
  → `_escalate`. The debugger THEN writes RCA + ADR stub and routes to the
  architect gate (`verdict = "escalated-design"`).
- **blocked-hitl:** maps directly to the sticky HITL block. The debugger
  augments: tags bead `human`, writes `ESCALATE:` comment, mints
  `bead-human-<bug-id>`, leaves blocked. `verdict = "blocked-hitl"`,
  no `done` completion.

See `profiles/debugger/skills/software-development/debug-loop/SKILL.md` for the
phase→DoD→assignee→verifier mapping and `scripts/drive_loop.py` for a concrete
invocation.

## loop_engine vs JSON-edge converge loops

The workflow engine has two ways to run an iterative dev→verifier loop:

| Concern | JSON-edge loop (template edges) | `loop_engine` plugin |
|---|---|---|
| State | per-node iteration counter + archived cards | `loop_state` JSON on root-card blackboard (durable across sessions) |
| Termination | `max_iterations` on a cycle edge | hard cap + budget + no-progress + stale-verdict, all → sticky HITL |
| Verifier verdict | node `output.schema` validation | `dod_verdict` in `run.metadata` |
| Phase sequencing | explicit edges + `depends_on` | engine-internal: root→exec→verifier sub-graph, multi-phase advance |
| Crash recovery | engine resets target on back-edge | idempotency keys dedup cards on re-drive |

**Rule of thumb:** if the loop is *converge-on-a-DoD with independent
verification* (bug fixes, diagnosis, design-council, any falsify-first
workflow), **drive `loop_engine`** — it already owns the loop machinery. A
JSON-edge loop is appropriate for simpler stateless retry (build→review→ship)
without a persistent blackboard or a DoD-gated verifier.
