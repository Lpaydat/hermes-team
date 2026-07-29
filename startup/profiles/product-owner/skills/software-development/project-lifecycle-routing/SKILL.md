---
name: project-lifecycle-routing
description: "Routing map for the production pipeline — which skill to load for each project lifecycle transition. Use when a project changes state (promotion, kickoff, feature addition, dispatch) and the right skill is ambiguous."
disable-model-invocation: true
---

# Project Lifecycle Routing

A project moves through lifecycle stages. Each stage has a skill that owns the process. This skill is the index that prevents improvisation at transition points.

## The routing map

| Trigger | Stage | Skill to load | What it does |
|---------|-------|---------------|--------------|
| User says "promote this" / "ship it" | Promotion | `project-promotion` | Creates project structure, board, bd epic. Dispatches to PO. |
| User brings a new project idea | New project | `project-kickoff` | Routes to grill → spec → architect → to-tickets |
| Feature work on existing project | Planning | `dev-planning` | Discuss → to-spec → architect → to-tickets |
| Workflow engine creates dispatch card | Dispatch | `dev-dispatch` | Creates tech-lead cards from ready beads |
| Project needs technical decisions | Design | Architect design card | design-council → ADRs → PO reads before to-tickets |

## The critical transition: promotion → planning

When `project-promotion` completes, it dispatches a card to PO saying "You own: beads tickets, dependencies." This is a trigger to load `dev-planning` — NOT a signal to hand-write beads.

**The failure mode:** PO reads "create beads tickets" in the promotion card, skips `dev-planning`, and runs `bd create` directly. This produces horizontal layer slices instead of tracer bullets, skips the user approval gate in `to-tickets`, and bypasses the architect design step entirely.

**The fix:** After promotion, the project is now "existing." The PO's skill index routes "planning feature work for an existing project" to `dev-planning`. Load it. `dev-planning` reaches `to-tickets`, which owns the tracer-bullet decomposition and the user approval gate.

## The architect gate

If the project involves ANY technical decisions (stack, data model, boundaries, dependencies), the PO creates an architect design card BEFORE running `to-tickets`. The architect runs `design-council`, produces ADRs, and `to-tickets` cites them.

Sequence: grill → spec → **architect** → to-tickets → dispatch → tech-lead → developer ↔ verifier → merge → QA → done

**⚠ Deadlock:** PO must NOT `kanban_link` the architect design card as a child of the PO's own task — this creates a circular dependency (PO blocks on architect via dependency, architect card stuck in `todo` because parent PO card is still `running`). Use `kanban_block(kind="dependency")` only.

## Pitfall: coverage gaps in the skill index

A skill index is only useful if it covers every situation the agent encounters. If a workflow exists that triggers bead creation but the index has no matching trigger, the agent improvises. Audit the index when:
- A new workflow is added
- A project transitions to a stage not covered by an existing entry
- An agent bypasses a skill (the trigger condition didn't match)

## Complexity posture (user preference)

The user HATES unnecessary complexity. When discussing the pipeline or
proposing changes, default to fewer moving parts. Argue for adding a
component only when its value is concrete and the alternative is worse.
See `references/pipeline-complexity-analysis.md` for the full audit of
the beads+kanban dual system (14 counted parts → 6 irreducible, per-scale
verdict, and the technique for evaluating any system's complexity). For
the *external* benchmark — how GitHub, Jira, Linear, GitLab, and military
OODA each handle plan-vs-execute, and what their failure modes teach us —
see `references/dual-system-industry-comparison.md`.

## Full pipeline reference

```
User → PO → (grill → spec → architect → to-tickets → approval)
  → beads → workflow engine → dev-dispatch → tech-lead
  → kanban_chains(dev+verifier) → merge → verifier creates QA card → QA → done
  
Feedback loops:
  QA PASS w/ findings → files bug beads (linked to epic) → workflow engine routes to debugger
  QA FAIL → triage: bug→debugger, non-bug→tech-lead, spec→PO
  Verifier iter ≥3 → ESCALATE → tech-lead → (hard bug) → debugger
  Debugger EXIT A → fix+RCA → back to QA re-test
  Debugger EXIT B → design flaw → ADR stub → architect gate
```

## Beads vs kanban boundary

The pipeline uses two stores by design:

- **Beads** (`.beads/`, Dolt DB, git-synced) = **master plan**. Epics, feature slices, bugs, dependencies. Visible via `bd list`. Survives board resets. `bd ready` computes topological order.
- **Kanban** (per-board SQLite) = **execution plan**. Cards created dynamically by agents (tech-lead via `kanban_chains`, verifier creates QA card, debugger via `loop_engine`). Not synced — local execution state.

Bugs filed by QA go through the workflow engine which routes `issue_type=bug` to debugger (not tech-lead). Bug beads should be `bd link`ed to the parent epic for traceability.

For the full decision matrix and anti-patterns, see [`references/beads-vs-kanban-artifact-policy.md`](references/beads-vs-kanban-artifact-policy.md). For the 6 bugs found via end-to-end livetest, see [`references/livetest-findings-20260729.md`](references/livetest-findings-20260729.md).
