# Orchestration vs Choreography — Decision Rules for This Engine

> Condensed from industry research (BPMN/Camunda, Airflow/Dagster/Temporal, Saga
> pattern, multi-agent frameworks). The full research with all citations lives at
> `orchestration-vs-choreography-research.md` in the session workspace; this file
> is the distilled decision rules a template author needs.

## The core question

When building a workflow, you have three routing mechanisms. Which do you use?

| Mechanism | What it is | Industry analog |
|-----------|-----------|-----------------|
| **Explicit edges** in one workflow | Nodes + edges in a single JSON template. Engine advances nodes in order, resolves conditions. | Temporal Workflow, Camunda BPMN process, Airflow DAG |
| **card_completed trigger** | A card completing on any board starts a NEW workflow instance. Decoupled. | Airflow ExternalTaskSensor / Saga choreography |
| **subworkflow node** | A node spawns a CHILD workflow instance, blocks until it completes. | Temporal Child Workflow |

## The universal industry consensus: hybrid, not either/or

Every established system arrives at the same answer — **orchestrate within bounded contexts, choreograph across boundaries**:

- **Camunda/Zeebe** (BPMN): "When you are facing domain coupling between your services orchestration is the way to go." Event-driven choreography only for messages that "leave the context of the current domain."
- **Airflow**: explicit task dependencies WITHIN a DAG; cross-DAG via sensors/triggers (acknowledged as "more complex" — the weak point).
- **Dagster**: eliminates cross-DAG entirely via declarative asset dependencies (single logical graph).
- **Temporal**: parent workflow → child workflows. Single-orchestrator bias; events only at boundaries.
- **Saga pattern** (Richardson): orchestration for complex sagas (many steps, conditional logic); choreography for simple 2-3 service flows.
- **LangGraph/CrewAI/AutoGen**: all default to supervisor/orchestrator for multi-agent reliability; swarm/choreography reserved for emergent behavior.

## Decision rules for this engine

```
WITHIN a pipeline (one bounded context, 3+ sequential agents)?
    → EXPLICIT EDGES (one workflow template)
    → Visibility, execution-order guarantee, conditional routing, debugging
    → Industry: Camunda domain coupling, Temporal single workflow

CROSSING domain boundaries (different pipeline, different team)?
    → card_completed TRIGGER (choreography)
    → Loose coupling, independent evolution, fire-and-forget
    → Industry: Camunda cross-domain events, Saga choreography

PARALLELISM or LOOPS within one agent's scope?
    → subworkflow NODE + kanban_chains (child workflow pattern)
    → Isolation, independent retry, dynamic fan-out, parent awaits completion
    → Industry: Temporal Child Workflows

DYNAMIC/EMERGENT flow (agent decides next steps at runtime)?
    → Agent orchestrates internally (loop_engine, kanban_create)
    → Engine node completes when agent calls kanban_complete
    → Industry: AutoGen/CrewAI agent autonomy within delegated scope
```

## Two anti-patterns to avoid

**Mega-DAG** (one giant workflow for everything): unmaintainable, every change
risks the whole flow, can't accommodate dynamic agent-internal work. *The system
already avoids this correctly* via `kanban_chains` and child cards.

**Trigger soup** (every handoff is a `card_completed` trigger): pure choreography.
With 12 agents, tracing becomes a nightmare. Camunda: "so called event-chains can
easily occur… typically not visible and hence troubleshooting gets even trickier."

## The threshold rule (from Saga literature)

Richardson's heuristic: orchestrate when you have **4+ participants** or
**conditional logic** (branching on outputs). For 2-3 linear, independent steps,
choreography is fine. Most real dev pipelines (grill→build→review→ship) have
both — so they should be explicit-edge workflows, not independent trigger chains.

## What this validates in the current design

The engine's existing architecture is already the correct hybrid:
- Explicit edges (orchestration) for within-pipeline routing ✓
- card_completed triggers (choreography) for cross-pipeline composition ✓
- subworkflow nodes (child workflows) for loops/parallelism ✓
- Self-trigger prevention prevents trigger loops from engine-created cards ✓
- Engine is unaware of dynamic child cards — `kanban_complete` is the sole signal ✓

The research confirms: **don't simplify to one mechanism.** The power is in
choosing the right one at each boundary.
