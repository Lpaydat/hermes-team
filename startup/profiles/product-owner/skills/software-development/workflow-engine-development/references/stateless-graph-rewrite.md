# Stateless Graph Engine Rewrite — Design Decision

> Decision date: 2026-08-02. Branch: `feat/workflow-dispatch`.
> Design doc: `DESIGN-stateless-graph.md` (in engine package).
> 5 review reports: `REVIEW-stateless-graph-*.md`.

## The problem

The engine assigned a **monotonic status** to each node
(pending→dispatched→{done,failed,skipped}). This is MORE restrictive than the
kanban cards it sits on (which cycle: done→todo, running→blocked→ready). The
mismatch is why loops don't work — a DONE node is frozen, back-edges have no
effect, and the dev↔verifier iteration loop is unexpressible.

`dev-review-loop.json` is the proof: it unrolls the loop once
(build→review→fix→re-review→ship) but a second FAIL dead-ends (no back-edge,
re-review is terminal).

## The fix: stateless graph, stateful run (LangGraph model)

The graph (workflow template) is **pure routing logic**. The instance (run)
carries ALL mutable state. Each tick, the engine walks the graph against the
current state to decide what to do — no node-status field, no status
transitions to fight.

```
State: { trigger: {...}, nodes: { build: {card_id, output, iteration}, review: {...} } }
Graph: pure routing rules (deps + conditions evaluated against state)
Tick:  (graph, state) → actions
```

Loops become natural graph traversal. Review FAIL → graph evaluates edges →
build should run → bump iteration, create fresh card. No frozen status.

## The 4 design blockers (from 5-subagent review)

Before implementation, these must be resolved:

1. **STATE BLOB NON-ATOMICITY (CRITICAL).** The single JSON blob loses
   atomicity — current per-row UPSERT with COALESCE is atomic; blob is
   SELECT→mutate→UPDATE = lost update window. Fix: optimistic versioning
   (`WHERE version = ?` on save) OR keep per-node rows minus the enum. The
   design doc must state which strategy is chosen.

2. **COMPLETION MODEL NON-EQUIVALENCE (CRITICAL).** Exit-node completion ≠
   all-terminal completion when SKIPPED nodes exist. A conditional diamond
   (review→ship on PASS, review→fix on FAIL) produces a SKIPPED exit node.
   Fix: terminal-for-exit = {done, failed, skipped}. Plus reachability rules
   for disconnected components.

3. **SELF-TRIGGER GUARD SURVIVES BY LUCK (P0).** The iteration suffix
   `:iter{N}` is appended after the node ID, so the instance-segment parse
   happens to work. But the heuristic parser also has a pre-existing bug:
   workflow IDs ≤3 chars cause the UUID to be misidentified as the parent
   workflow ID → infinite trigger loops. Fix: replace heuristic parse with
   deterministic `split("_")` bounded by `wf_` prefix and trailing UUID. Add
   a table-driven test covering all 6 key shapes.

4. **DB MIGRATION DESTROYS ACTIVE INSTANCES (HIGH).** `ALTER TABLE + DROP
   TABLE node_states` with no backfill = active instances lose all state.
   Fix: backfill in Python (read node_states → build JSON blob → UPDATE row).
   Stop cron during cutover. DB backup before DROP.

## The 3 spec gaps (must be written before coding)

5. **GRAPH WALK ALGORITHM UNDEFINED.** The AND/OR edge semantics (unconditional
   = convergence/AND, conditional = diamond/OR), the SKIP propagation (dead
   branches), and the activation rule must be written explicitly.

6. **BACK-EDGE DETECTION UNDEFINED.** "Reset when back-edge fires" needs a
   definition: a cycle-closing edge, detected via Tarjan SCC at template load
   time. Annotate `Edge.is_back_edge`. Reject back-edges without iteration
   caps at load time.

7. **FOREACH + SUBWORKFLOW + 3 CARD MODES NOT MENTIONED.** The design's single
   "DISPATCH" step must absorb 8 dispatch shapes (task/foreach-task/foreach-
   command/foreach-subworkflow/command/wait/subworkflow ×3 card modes) and 4
   completion paths. ~850 lines of dispatch topology is orthogonal to the
   status model and must be ported verbatim.

## Revised scope

The original ~1300 line estimate was naive. Honest accounting:
- ~850 lines of dispatch/validation/card-mode logic must be ported verbatim
- ~300 lines of new walk/sync/trim logic is additive
- Runtime GROWS (~1700 lines), not shrinks
- Tests: 317 existing, 57 node_states queries across 10 files need rewriting

**Total estimate: ~2400-2900 lines** (vs ~1300 claimed).

## What stays unchanged

- model.py graph definitions (Workflow/Node/Edge/Trigger)
- store.py (template loading)
- kanban_adapter.py (board interface)
- Triggers (card_completed, bead_ready, manual)
- Output schema validation
- Engine event log
- All 11 existing templates (DAGs are a subset of the new model)

## The NodeStatus deprecation shim

Removing NodeStatus breaks 3 test modules at import time (118+ tests). Keep
NodeStatus as a deprecated alias shim for one release cycle — re-export from
the new state strings. Makes the cutover bisectable.
