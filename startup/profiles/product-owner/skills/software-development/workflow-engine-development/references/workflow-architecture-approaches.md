# Workflow Architecture — mega vs distributed vs goal-bounded

> **Date:** 2026-08-02. Researched via 6 parallel subagents analyzing the
> actual engine code + 4 industry domains. This is the decision reference for
> how to decompose the dev pipeline into workflow templates.

## The three approaches considered

| Approach | Shape | Verdict |
|----------|-------|---------|
| **A — Mega** | One workflow template, ALL agents as nodes, all handoffs are edges | REJECTED. Engine is DAG, no loops → dev↔verifier iteration unexpressible. Blocked agent freezes entire chain. "Single graph" collapses at fan-out (foreach subworkflow). The empty dev-pipeline.json proved it stalled. |
| **B — Per-agent** | Each agent owns small workflow(s), handoffs via card_completed triggers | Natural fit (qa-loop.json proves it), BUT: iteration counting lives nowhere across trigger boundaries, debugging a 6-workflow chain needs manual SQLite, self-trigger guard bug (hyphenated IDs). |
| **C — Goal-bounded** | Multiple goal workflows, several agents cooperate per workflow via edges, composed via card handoffs | CHOSEN. Matches incremental migration principle. Best failure isolation + visibility. Edges where cooperation is real, triggers at goal boundaries. |

## Why C won (grounded in code + industry research)

1. **Industry consensus**: BPMN (Camunda), data orchestration (Airflow/Temporal),
   Saga pattern, multi-agent frameworks (LangGraph/CrewAI) ALL converge on
   hybrid: orchestrate within bounded contexts, choreograph across boundaries.
2. **9 handoffs mapped**: 6 favor distributed (B/C), 2 tie, 1 favors A (but
   that loop already runs agent-managed in production).
3. **Engine already does the hybrid** in production: edges inside feature
   instances (PO→architect, verifier→QA), triggers for cross-instance routing
   (dispatch, bug routing), opaque subworkflows for agent-managed loops.
4. C is a formalization of what already works.

## The goal decomposition

```
#1 PLANNING    (PO + Architect)     — interactive, human-gated. Stays as skills.
#2 DISPATCH    (PO)                 — bead_ready → tech-lead card. MIGRATE FIRST.
#3 CONSTRUCTION (TL + Dev + Ver)    — opaque (kanban_chains/loop_engine). Unless
                                       stateless-graph redesign lands, then expressible.
#4 QA          (QA)                 — DONE (qa-loop.json).
#5 BUG-FIX     (Debugger + Ver)     — bead_ready (type=bug) → debugger card.
#6 HUMAN-ESCAL (operator)           — human label → HQ card.
#7 SCANNER     (escalation)         — blocked card → escalation card.
```

## The decision rule (from industry research)

```
WITHIN a bounded context  → explicit-edge orchestration (one workflow)
ACROSS domain boundaries   → card_completed triggers (choreography)
PARALLELISM / LOOPS        → subworkflow / kanban_chains (child workflows)
DYNAMIC / EMERGENT         → agent autonomy (loop_engine)
```

## The blocker for C (empirically verified)

C self-blocks TODAY: the self-trigger guard (runtime.py:1783-1800) suppresses
card_completed triggers on cards from edge-declaring workflows. Every goal
workflow in C uses edges internally → cross-workflow handoffs die.

Two fixes (both already anticipated in MIGRATION-PLAN but not implemented):
1. `idempotency_key_template` on terminal nodes (non-`wf:` key escapes guard)
2. Fix the hyphenated-ID parsing bug in the guard heuristic

## Key user correction (style)

When the user says "create scaffolding," they mean a MINIMAL empty structure
(empty nodes + edges arrays), NOT detailed templates with body_templates and
engine_gap annotations. The first attempt (4 detailed templates) was deleted;
the correct scaffold was a single empty `dev-pipeline.json`. **Start minimal,
fill in bit by bit through discussion.**
