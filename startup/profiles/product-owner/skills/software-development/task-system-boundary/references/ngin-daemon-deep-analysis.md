# ngin Daemon — Deep Capability Map & Hermes Gap Analysis

Deep codebase analysis (2026-08-05) of `~/workspace/ngin/daemon/src/` (26 .rs files),
`~/workspace/ngin/ngin-db/src/` (13 .rs files), and all 7 SQL migrations, compared against
the Hermes workflow engine (`scripts/workflow_engine/` — model.py, runtime.py, store.py).
The full 29KB analysis document lives at `~/workspace/ngin-vs-hermes-gap-analysis.md`;
this reference captures the durable knowledge for future sessions.

## The 8-Phase Tick Loop (order 7→1→2→3→4→8→5→6)

| Phase | Module | Responsibility |
|-------|--------|----------------|
| 7 exit_classify | `exit_classify.rs` | Reap completed PIDs (`waitpid WNOHANG`), classify via beads status + exit code matrix (block/success/protocol-violation/crash) |
| 1 reclaim | `reclaim.rs` | Expired claims (`claim_expires < now`); alive PID → reclaim, dead PID → defer to P2 |
| 2 crash_detect | `crash_detect.rs` | Dead PIDs in `running` state; reap exit code, classify |
| 3 auto_resume | `auto_resume.rs` | New run rows (parent_run_id chain) for crashed/blocked/timed_out/reclaimed/spawn_failed; inherits failures+role; reads flow_checkpoints for resume |
| 4 dep_promote | `dep_promote.rs` | `bd ready` + auto-unblock blocked issues whose deps all resolved (closed or gave_up) |
| 8 triage | `triage.rs` | Claim unrouted issues (no assignee, no route) for `flow:triage`; schedule-gated |
| 5 claim | `claim.rs` | Dispatch brain: dual-read (assignee→AgentRegistry primary, metadata.route→FlowRegistry fallback); parked surfacing; review-loop breaker; assignee-change debounce |
| 6 spawn | `spawn.rs` | Build SubagentRunConfig JSON, spawn subagent-runner process, record PID+claim_expires |

## Database Schema (6 migrations, PRAGMA user_version, WAL mode)

- **`runs`** — per-dispatch: run_id, parent_run_id, pid, claim_expires, exit_code, outcome, metadata, issue_id
- **`runs_ngin`** — dispatch extension: dispatch_state, consecutive_failures, route, role, spawned_at, claimed_at
- **`events`** — append-only audit log (run_id, event_type, payload, created_at)
- **`flow_checkpoints`** — resume state (step_index, global_task_index, step_resume_data_json)
- **`daemon_state`** — KV store (last_triage_at, force_triage, parked_issues, claim_assignee_memory)
- **`dispatch_metrics`** — counters (heartbeat_stalls, resume_attempts, breaker_trips)
- **`run_checklist`** — hard gate on success (pending items block close)

## State Machine (4-step atomic transition via state_machine.rs)

UPDATE runs_ngin → INSERT event → bd.comment → bd.set_dispatch_state.
Terminal: success, gave_up, blocked. Resumable: crashed, blocked, timed_out, reclaimed, spawn_failed.

## Reliability Features (ngin's strengths over Hermes)

- **PID tracking** — libc::kill(pid,0) liveness + waitpid reaping. Hermes has NO process-level tracking.
- **Startup recovery** — pre-tick scan resets orphaned claimed/running runs.
- **Ownership guard** — verifies target issue matches run's assigned issue before bd mutations.
- **Circuit breaker** — consecutive_failures ≥ max → gave_up (distinct from review-loop breaker).
- **Idempotency** — `run-<run_id>-step-<idx>-<slug>` keys prevent duplicate children on retry.
- **Hallucination gate** — verifies created_cards IDs exist in beads; freezes orphan children.
- **Dry-run mode** — DryRunGuard previews all actions without mutation.
- **Review-loop breaker** — reject_count/gate_failures ≥ threshold parks bouncing issues.
- **Assignee-change debounce** — cross-tick memory skips just-changed assignees.

## The 15 Gaps (what ngin needs to replace Hermes)

### Critical (P1 — the workflow-engine layer)
1. **Graph DAG execution** — ngin spawns ONE process per issue (flat steps[]); Hermes walks a node+edge graph dispatching each node independently. Must add workflow_instances + node_states tables + per-tick graph walk.
2. **Conditional edges (AND/OR)** — unconditional incoming = AND, conditional = OR. ngin has no edge model.
3. **Template variables + data flow** — `${nodes.X.output.Y}` resolution, context dict, output schemas.
4. **Back-edge loops** — Tarjan SCC detection, reset pass, iteration counters, max_iterations caps.
5. **Triggers** — card_completed/bead_ready sources, completion scanner, dedup, self-trigger guard.
6. **Subworkflow composition** — child instance creation, parent blocking, cross-instance output reads.
7. **Foreach fan-out** — list iteration, N cards, aggregation on all-complete.

### Important (P2)
8. Node types (command=synchronous shell, wait=poll condition)
9. JSON Schema output validation on node completion
10. Dead-branch skip propagation
11. Completion fence (re-read exit node board truth)
12. Stateless/derived phase (derive from beads status each tick, not persisted monotonic)

### Nice-to-have (P3)
13. Zombie guard (reactivated completed instances)
14. Garbage collection (old instances/events)
15. Optimistic concurrency (versioned state blob for multi-daemon)

## Architecture Recommendation

Do NOT replace ngin's 8-phase tick loop. ADD a workflow-engine layer on top:
- New `workflow.rs` module — the graph walker. Each node dispatches as an ngin run, inheriting crash recovery, PID tracking, circuit breaker.
- Extend `.ngin/flows/*.json` from `{steps:[]}` to `{nodes:[], edges:[], trigger:{...}}` — backward compatible (steps-only = legacy single-process).
- New tables: workflow_instances, trigger_keys, trigger_watermark.
- ngin's existing reliability infra is a significant head start over building from scratch.

## Conceptual Model Difference (the key insight)

ngin is a **task runner** (one issue = one process; worker internally sequences steps).
Hermes is a **workflow engine** (one workflow = many coordinated cards with dependencies, conditions, data flow).
To replace Hermes, ngin must become the graph walker — but it can reuse its excellent per-task reliability for each node's execution.
