# Architecture Decision: Goal-Bounded Workflows (Approach C)

> Decision date: 2026-08-02. Validated via 6 parallel research subagents
> analyzing engine code, pipeline handoffs, and industry patterns. See:
> `dev-pipeline-handoff-mapping.md` (9 handoffs × 2 approaches),
> `orchestration-vs-choreography.md` (industry decision rules),
> `engine-pitfalls.md` § "Cross-workflow trigger guard" (composition blocker).

## The decision

The dev pipeline migration uses **goal-bounded workflows** (Approach C):
multiple agents cooperate inside one workflow with a clear objective, composed
via card handoffs between workflows.

NOT a single mega-workflow (Approach A — no loops, single point of failure,
collapses into black boxes anyway). NOT per-agent micro-workflows (Approach B —
trigger soup, no pipeline visibility, iteration counting across instances).

## Goal decomposition

| Workflow | Agents inside | Goal | Entry trigger | Exit |
|----------|--------------|------|---------------|------|
| planning | PO + Architect | spec + design + tickets | manual / user request | beads created → `bead_ready` fires construction |
| construction | tech-lead (+ developer + verifier as opaque subtree) | merged feature | `bead_ready` | verifier PASS card → qa-loop trigger |
| qa | QA | verified artifact | card_completed (verifier PASS) | bug bead → `bead_ready` fires bug-fix |
| bug-fix | debugger (+ developer + verifier as opaque subtree) | proven fix | bug `bead_ready` | merge card → QA re-verify trigger |

≈12 internal edges, ≈7 external triggers. Compare: Approach A ≈20 edges in one
graph (no loops, mega-template), Approach B ≈27 triggers (no pipeline shape).

## The C-opaque shape (design rule)

**Orchestration-heavy goals** (construction inner loop, bug-fix): opaque
orchestrator node + thin engine edges for the single-pass tail. The orchestrator
(tech-lead via kanban_chains, debugger via loop_engine) manages its own card
tree internally; the engine sees one node, completes it when `kanban_complete`
fires.

**Cooperation-heavy but judgment-light junctions** (planning diamond, PASS/FAIL
routing): flattened engine nodes with explicit edges + schema validation.

This is honest about what the engine can do (static routing, schema validation,
visibility, condition-based dispatch) and what it can't (loops, convergence).

## Prerequisites (Phase 0 — not yet implemented)

1. **`idempotency_key_template` on terminal nodes** — gives handoff cards a
   non-`wf:` key so they escape the self-trigger guard. Currently 0 hits in
   engine code. THIS IS THE #1 BLOCKER.
2. **Fix the hyphenated-ID parsing bug** in the self-trigger guard
   (runtime.py:1788-1796). Use structured lookup, not string heuristic.
3. `label_not` / `type_not` trigger conditions (dispatch filtering)
4. `card_blocked` trigger source (scanner migration)
5. `target_board` node field (human-escalation to hermes-hq)

## The "static-dynamic coexistence" pattern (unchanged)

The three orchestrators (architect design-council, tech-lead kanban_chains,
debugger loop_engine) stay as opaque nodes. C does NOT flatten them into engine
nodes. Flattening would: break atomic authoring, fight convergence judgment, and
hit the no-loop constraint. The engine's job is the static skeleton; the
orchestrators own the dynamic internals.

## What Approach A gets wrong (do not revisit)

- Engine is a DAG — node status is monotonic (PENDING→DISPATCHED→terminal), no
  code path resets it. The dev↔verifier loop is unexpressible.
- `dev-review-loop.json` is a prior attempt — unrolls the loop once, second FAIL
  dead-ends (no back-edge). This is a proven limitation, not theoretical.
- One blocked agent freezes the entire downstream chain. No escalation mechanism.
- The "single graph" fiction collapses at fan-out (foreach subworkflow = separate
  templates anyway).
- Evidence it stalled: `dev-pipeline.json` was created as an empty mega-template
  and stayed empty. Renamed or replaced by goal-bounded templates.

## What Approach B gets wrong (do not revisit)

- Iteration counting lives nowhere — no single workflow tracks "iteration 2 of 3"
  across trigger boundaries.
- Debugging a broken 6-workflow chain requires manual SQLite queries across two
  DBs. No unified trace.
- ~27 trigger surfaces for the full pipeline — too many places for the
  documented trigger footguns (1h lookback, LIMIT 200, non-atomic dedup).
- The self-trigger guard bug (hyphenated IDs) makes trigger chains unreliable.
