# Refactor Workflow Planning — improve-codebase-architecture + autonomous pipeline

Researched and designed for the "tech-lead can handle project refactor workflow" task.

## The mattpocock skill: `improve-codebase-architecture`

Location: `shared-skills/mattpocock/improve-codebase-architecture/SKILL.md`

**What it does (3 phases):**
1. **Explore** — walks the codebase for friction using `codebase-design` vocabulary. Notes shallow modules, tight coupling, testability gaps. Applies the deletion test.
2. **Present candidates as HTML report** — visual before/after diagrams. Each candidate: files, problem, solution, benefits, recommendation strength (Strong / Worth exploring / Speculative).
3. **Grilling loop** — user picks a candidate → skill runs `/grilling`. Updates `CONTEXT.md` inline.

**Problem:** built for a human at a terminal (browser, interactive selection, grilling). Cannot run autonomously in a kanban card.

## The codebase-design vocabulary

From `shared-skills/mattpocock/codebase-design/SKILL.md`. Use these terms EXACTLY:

- **Module** — anything with an interface and implementation
- **Interface** — everything a caller must know (type signature + invariants + error modes + performance)
- **Depth** — behaviour per unit of interface complexity. Deep = small interface + large implementation
- **Seam** (Michael Feathers) — where you can alter behaviour without editing in that place
- **Adapter** — concrete thing that satisfies an interface at a seam
- **Leverage** — what callers get from depth
- **Locality** — what maintainers get from depth (bugs concentrate)

**Key principles:**
- Deletion test: delete the module. Complexity vanishes = pass-through. Reappears across callers = earning its keep.
- Interface is the test surface: callers and tests cross the same seam.
- One adapter = hypothetical seam. Two = real seam.

## The 11 Fowler code smells (from `code-review` skill)

Labelled heuristics, never hard violations. Repo standards override.

1. Mysterious Name  2. Duplicated Code  3. Feature Envy  4. Data Clumps
5. Primitive Obsession  6. Repeated Switches  7. Shotgun Surgery
8. Divergent Change  9. Speculative Generality  10. Message Chains  11. Middle Man

## Milestone vs Epic — when to run refactoring

**Milestone is better.** Epics are mid-flight (scope creep, merge conflicts). Milestones are natural pause points — all features landed, tests green, full picture visible. Maps to "hardening sprint" practice.

## The user's actual workflow (crystallized this session)

The user described their manual process, which maps to a clean 4-node workflow with a back-edge:

```
node1: scan (improve-codebase-architecture exploration phase)
  → node2: fan-out review per candidate (kanban_chains) + fan-in synthesis
    │     each reviewer verifies the candidate against actual code
    │     synthesis decides: continue (real findings) or stop (trivial)
    ├── stop (trivial) → done
    └── go → node3: to-tickets (decompose validated findings)
              → node4: tech-lead-execute (type: subworkflow)
                         → back-edge to node1 (scan again)
```

**Why this works with the existing engine:**
- **node4 as subworkflow** — engine blocks parent until tech-lead-execute completes, then advances. No wait node needed.
- **back-edge node4 → node1** — engine already handles back-edges (reset pass in `_tick_instance`).
- **conditional stop** — node2 synthesis outputs `{verdict: "continue"|"stop"}`, conditional edge routes.
- **kanban_chains fan-out in node2** — reviewer agent calls it as a tool, same as architect T2 ceremony.

**Stop condition:** scan produces zero "Strong" (or zero non-trivial) candidates → synthesis returns `verdict=stop` → conditional edge routes to done.

## Autonomous scan test result (PROVEN)

Tested via delegate_task on the todo-app codebase (99 lines production, 48 tests):

- **0 "Strong" findings** — correct, codebase is clean for its size
- **2 "Worth exploring"** — both real:
  - Candidate 1: load→mutate→save duplicated in every CLI handler (missing transaction module)
  - Candidate 3: 48 tests all end-to-end, none test the storage seam directly
- **2 "Speculative"** — both real but minor (lookup-by-id duplication, `list` stub)
- **Honest assessment:** "This codebase is clean for its size" — did NOT invent friction
- **Used vocabulary correctly:** module, interface, depth, seam, locality, leverage, deletion test

**Key signal:** the stop condition works. If this scan had produced zero non-trivial candidates, the workflow would stop. The scan quality is good enough to build the workflow.

**Risk noted:** the skill relies on "organic exploration" and "experiencing friction" — subjective. The reviewer horde (node2) filters false positives. On this test there were none to filter.

## What `improve-codebase-architecture` needs adapted for autonomous use

1. **Phase 1 (Explore)** — works as-is autonomously. No changes needed.
2. **Phase 2 (HTML report)** — replace with structured output: candidate list with recommendation strength. The synthesis node consumes this.
3. **Phase 3 (Grilling)** — replace with architect's `design-council` (design-it-twice fan-out, already autonomous). Or skip entirely — the refactor tickets go through tech-lead-execute which has its own verify loop.

## Status

- Scan autonomy: PROVEN (delegate_task test, honest findings)
- Workflow design: crystallized (4-node graph with back-edge + subworkflow)
- Next step: build the `refactor-cycle.json` workflow template
- Not yet built or livetested
