# Workflow Building Blocks

Three systems for orchestrating work. Each owns a different region of the dynamic spectrum. Choose by how much you know at design time vs how much the agent must decide at runtime.

## The decision

```
Do you know the exact structure at template author time?
  │
  ├── YES → Declarative workflow engine (JSON template)
  │         Static routing graph. Nodes, edges, conditions.
  │         No loops. No dynamic fan-out.
  │
  ├── YES, but the profile should build the children at runtime
  │         → Workflow template dispatches a parent card.
  │           Profile calls kanban_chains inside the card.
  │
  └── NO — need iteration until a condition is met
            → Workflow template dispatches a parent card.
              Profile calls loop_engine inside the card.
```

## Block 1: Declarative workflow engine (JSON templates)

**What:** A stateless routing-graph compiler. Templates declare nodes (cards), edges (routing), and conditions (branching). The engine ticks every minute, advancing nodes when their dependencies complete.

**Owns:** Static routing — trigger fires → check condition → dispatch card → wait → advance. Predictable, pre-planned, no loops.

**Template node types:** task (card), command (shell script), subworkflow (child instance), wait (poll condition), foreach (fan-out over list).

**File location:** `startup/scripts/workflow_engine/templates/*.json`

**When to use:** When the flow is predictable at design time. QA trigger → check-merge → plan → test → verdict. Dispatch → route → tech-lead. All static routing.

## Block 2: kanban_chains (static topology primitive)

**What:** A single tool that atomically builds N parallel chains + optional fan-in tail on the kanban board, then parks the caller until all terminal cards complete. Re-dispatched exactly once, automatically, when terminals hit done.

**Owns:** Pre-planned parallel execution. The caller knows the exact DAG at call time — which profiles, how many chains, what sequence.

**API:**
```
kanban_chains(
  goal: str,                    # what the matrix accomplishes
  chains: [[step, step, ...], # N parallel chains, each a sequence
           [step, step, ...]],
  after: [step, step, ...],    # optional sequential fan-in tail
  blackboard: {image_tag, container_port, base_port, env_facts, spec_path},
  idempotency_key: str         # dedup root card
)

# Each step: {assignee, title, body, skill?, workspace_path?, priority?}
```

**How it works:**
1. Creates root card (blackboard anchor), completes immediately.
2. For each chain: creates steps sequentially (step[0]→root, step[n]→step[n-1]).
3. If `after`: creates fan-in tail (after[0] parented on ALL chain terminals).
4. Links caller as child of terminal card(s).
5. Blocks caller (kind=dependency). Auto-promotes when terminals complete.

**Profiles:** All 13 profiles (advisor, architect, base, builder, debugger, developer, ops, product-owner, qa, researcher, scout, tech-lead, verifier).

**When to use:** When a profile card needs to fan out children dynamically — e.g., tech-lead card spawns developer + verifier pair. The workflow engine dispatches the parent card; the profile calls kanban_chains inside it.

## Block 3: loop_engine (dynamic converge-loop)

**What:** Drives iterative converge-loops. Decomposes a goal into ordered phases, each running discover → execute → verify. Verifier gates advancement. Iterates until DoD met or hard cap reached.

**Owns:** Dynamic iteration — retry until a condition is met, with replan, escalation, and cost budgets. The agent doesn't know how many iterations it will take.

**API:**
```
loop_engine(
  goal: str | [Claim],          # what to accomplish; array = pre-grounded
  runner: str,                  # profile driving the loop
  phases: [{                    # ordered phase specs
    execution: {assignee, title, body, skill?},
    verifier: {assignee, title, body, metric_type?, dod_signals?},
    max_iterations: int         # hard cap per phase
  }],
  execution: {assignee, title, body, skill?},  # single-phase shortcut
  verifier: {assignee, title, body, ...},       # global verifier
  max_iterations: int,          # global cap (default 5)
  budget: int,                  # cost-unit budget
  no_progress_threshold: int,   # escalate after N identical verdicts (default 2)
  discover: {assignee, dod, max_iterations},    # phase-0 grounding
  strict_fact_basis: bool,      # require evidence in verdicts
  strict_dod: bool,             # require structured dod_signals
  loop_id: str                  # durable handle for drift-immunity
)
```

**Decision logic (per iteration):**
- **Advance:** DoD met + artifact valid → next phase or complete.
- **Replan:** DoD not met, under caps → fresh execution + verifier cards.
- **Escalate:** budget exhausted, no progress, or hard cap → sticky HITL block.

**Profiles:** architect, builder, debugger (the three with loop_engine enabled).

**When to use:** When work needs iteration until quality bar is met — debugging (reproduce→fix→converge), architecture (research→interview→ADR), building (prototype→verify→iterate).

## How they compose: static-dynamic coexistence

The three systems don't compete — they layer:

```
Workflow template (static routing)
  └── dispatches parent card to profile
        └── profile calls kanban_chains (static fan-out)
        │     └── developer card + verifier card (parallel pair)
        │
        └── profile calls loop_engine (dynamic iteration)
              └── execution card → verifier card → replan? → loop
```

**The boundary:** The workflow engine observes the PARENT card's status only. It doesn't track children created by kanban_chains or loop_engine. The parent card completes when the profile's internal work is done. The workflow engine then advances to the next node.

**What this means for templates:** A workflow node assigned to tech-lead can fan out developer+verifier pairs via kanban_chains. A node assigned to debugger can iterate via loop_engine. The template just says "dispatch card, wait for done" — the profile decides how to accomplish it.

## Enforcement hierarchy (which block enforces what)

```
Output schema (workflow engine)    → Card fails validation, retries. ENFORCED.
kanban_chains parent linking       → Child can't promote until parent done. ENFORCED.
loop_engine DoD gate               → Can't advance until verifier says DoD met. ENFORCED.
Body template text                  → Agent may or may not follow. NOT enforced.
```

All three systems enforce structurally. Body text doesn't. This is the principle: tool-level enforcement > prompting.
