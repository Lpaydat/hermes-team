# Stateless Graph Redesign — the langgraph shift

> **Date:** 2026-08-02. **Branch:** `feat/workflow-dispatch`.
> **Status:** DESIGN APPROVED — implementation pending.

## The problem this fixes

The engine assigned a **monotonic status** to each node
(pending→dispatched→{done,failed,skipped}). This is MORE restrictive than the
kanban cards it sits on top of (which cycle: done→todo, running→blocked→ready).
That mismatch is why loops don't work — a DONE node is frozen, back-edges
(review FAIL → dev fix) have no effect. `dev-review-loop.json` already proved
this dead-ends after one iteration.

The user's question that unlocked it: *"should we make the node status mimic
what hermes kanban has?"* → then *"do node need status? or should we use the
langgraph approach where each run has its own state and we will run that state
against the workflow graph to see what to do next instead?"*

The answer: **the graph should be stateless; the run carries all state.**

## The new model

- **Graph** (workflow template): pure routing logic — nodes, edges, conditions.
  Stateless. Unchanged from current model.py.
- **RunState** (per instance): one JSON blob holding trigger_context +
  per-node data (card_id, card_status, output, iteration). Replaces both
  `node_states` table and the status enum.
- **Tick** = graph walk: sync card statuses from board → walk graph against
  state → dispatch what's needed → check exit conditions → save state.

No node status field at all. A node runs when the graph says it should, based
on what's in state — not because it's marked "pending."

## What we keep (unchanged)

- model.py graph definitions (Workflow/Node/Edge/Trigger)
- store.py (template loading)
- kanban_adapter.py (board interface)
- Triggers (card_completed, bead_ready, manual)
- Output schema validation (hard validation of card metadata)
- Engine event log
- All 11 existing templates (DAGs = subset of cyclic traversal)

## What we rip out

- `NodeStatus` enum, `NodeState` dataclass, `node_states` table
- All status-transition logic: PHASE 1 completion marking, PHASE 1b regression
  detection, zombie guards, monotonic dispatch guard
- COALESCE UPSERT for node states (no node_states table)

## What changes

- **Iteration-aware idempotency**: `wf:<instance>:<node>:iter<N>` so each loop
  iteration gets a fresh card.
- **Completion model**: exit nodes (leaf nodes, or explicit `exit_condition`)
  reached done/failed, not "all nodes frozen."
- **Condition engine**: `evaluate_condition` upgraded for `AND`/`OR` +
  numeric comparison (`>= 3` for iteration caps on back-edges).

## Design doc

Full spec at `startup/scripts/workflow_engine/DESIGN-stateless-graph.md` (in
the worktree on branch `feat/workflow-dispatch`).

## Backwards compatibility

All existing templates are DAGs (no loops). DAG traversal is a subset of cyclic
traversal. Existing templates work unchanged. The existing test suite must pass
with identical EXTERNAL behavior (cards created, outputs read, triggers fire) —
only the internal state representation changes.

## The migration sequence it enables

With loops native, the engine can express real construction workflows
(dev↔verifier iteration). The goal-bounded decomposition becomes:

1. **dispatch** — bead_ready → PO card → creates tech-lead card
2. **construction** — tech-lead/dev/verifier with dev↔verifier loop (NOW POSSIBLE)
3. **qa** — DONE (qa-loop.json, verifier PASS → QA card)
4. **bug-router** — bug bead_ready → debugger card

Plus infrastructure: human-escalation, board-scanner.
