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

## Profile SOUL.md refactoring

When refactoring a profile's SOUL.md to identity-only (via `writing-great-soul`):
**discuss the plan first, don't act immediately.** The user wants alignment on scope
and approach before changes start. The two-part pattern: (1) SOUL.md → identity-only,
(2) embedded workflows → skills (via `create-workflow`). Extract procedures to skills
BEFORE removing them from SOUL.md so the profile keeps working during transition.

For the complete profile inventory, refactor phases, and safety protocol, see
[`references/profile-refactor-audit.md`](references/profile-refactor-audit.md).

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
  → kanban_chains(dev+verifier) → merge → workflow engine auto-creates QA card → QA → done
  
Feedback loops:
  QA PASS w/ findings → files bug beads (linked to epic) → workflow engine routes to debugger
  QA FAIL → triage: bug→debugger, non-bug→tech-lead, spec→PO
  Verifier iter ≥3 → ESCALATE → tech-lead → (hard bug) → debugger
  Debugger EXIT A → fix+RCA → verifier reviews+merges → workflow engine auto-creates QA card → QA → done
  Debugger EXIT B → design flaw → ADR stub → architect gate
```

### Workflow engine phases (5)

The engine runs every minute on cron. All 5 phases run per-project:

1. **bead-sync** — kanban card status → bd bead status (closes done beads)
2. **dispatch** — `bd ready` → PO dispatch card (bugs → debugger directly via `dispatch_bug_to_debugger`)
3. **human-escal** — human-flagged beads → operator HQ card
4. **scanner** — blocked tasks → escalate via ESCALATION_CHAIN (dev/verifier/debugger/qa → tech-lead, tech-lead → PO)
5. **qa-trigger** — scans for recently-completed verifier/debugger cards whose summary mentions "merged" → creates QA re-test card automatically. Dedup via `qa-after-<card-id>`. Filters out probes, sub-reviews, and internal loop phases.

**QA trigger design lesson:** The trigger went through 4 iterations:
- v1 (git merge detection): false positives on PO spec/doc commits
- v2 (card assignee + parent-child): missed loop_engine's complex parent chains
- v3 (`"merged"` keyword): false positives ("re-open against merged master")
- v4 (regex patterns: `"merged to master"`, `"merged to main"`, `". merged "`, `"^merged "`): zero false positives, validated against 18 historical cards

The lesson: **detect the outcome in natural language summaries, not structural relationships.** The verifier writes "merged to master" when it merges — that's the ground truth. Parent-child links and assignee checks are indirect and unreliable when loop_engine creates complex card hierarchies.

See [`references/workflow-engine-phases.md`](references/workflow-engine-phases.md) for the full phase reference.

### QA timing tradeoff: per-merge vs post-all-merge

The QA trigger fires after every merge. For an N-slice epic, this runs N QA cycles — but the first N−1 test intermediate states where other slices are absent. When the user questions whether this adds value or wastes cycles, load [`references/qa-timing-failure-modes.md`](references/qa-timing-failure-modes.md). Key insight: per-merge QA is structurally blind to cross-slice interaction bugs (the absent slices' code can't be exercised), but it's the only defense that catches regressions in existing code early enough to prevent propagation. The analysis covers four scenarios (interface breaks, latent runtime bugs, multi-slice integration failures, regressions) and recommends a hybrid: lightweight per-merge QA for regression detection plus a post-all-merge integration pass for the cross-slice failure space.

## Beads vs kanban boundary

The pipeline uses two stores by design:

- **Beads** (`.beads/`, Dolt DB, git-synced) = **master plan**. Epics, feature slices, bugs, dependencies. Visible via `bd list`. Survives board resets. `bd ready` computes topological order.
- **Kanban** (per-board SQLite) = **execution plan**. Cards created dynamically by agents (tech-lead via `kanban_chains`, verifier creates QA card, debugger via `loop_engine`). Not synced — local execution state.

## Bug routing detail

Bugs filed by QA go through the workflow engine. The engine checks `issue_type == 'bug'` OR `issue_type == 'task'` with `'bug'` in labels — because bd versions may store the type as `"task"` with the word in the title/labels. Bug beads route directly to debugger via `dispatch_bug_to_debugger()`, bypassing the PO dispatch → tech-lead path. Bug beads should be `bd link`ed to the parent epic for traceability.

The ESCALATION_CHAIN covers all profiles: developer → tech-lead, verifier → tech-lead, debugger → tech-lead, qa → tech-lead, tech-lead → product-owner. Blocked cards escalate one level per scanner tick until they reach a human.

For the full decision matrix and anti-patterns, see [`references/beads-vs-kanban-artifact-policy.md`](references/beads-vs-kanban-artifact-policy.md). For the 9 bugs found via end-to-end livetest, see [`references/livetest-findings-20260729.md`](references/livetest-findings-20260729.md).
