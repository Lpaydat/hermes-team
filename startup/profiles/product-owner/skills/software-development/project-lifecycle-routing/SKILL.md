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
| Workflow engine creates dispatch card | Dispatch | `dev-dispatch` | Routes [spec]/[ticket-] card completions by type → architect→setup→decompose→milestone |
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

## The exploration gap (known limitation)

The planning flow documented here goes straight from spec to single-approach architecture. Nobody explores **"of the fundamentally different approaches, which is the right one?"** between the grill (which validates the problem) and the architect (which optimizes the implementation). The architect's `design-council` already weighs alternatives — but *within one approach space*, not *across* approaches. It cannot question the spec it was handed.

This is a recognized structural gap, not a design choice. R&D belongs between spec and architect — PO-owned, like the grill, fanning out to existing builder/researcher/scout profiles. Triggered by novelty/risk/approach-uncertainty (NOT every feature — skip for low-stakes CRUD). It produces an exploration dossier (landscape map + approach tree + spike results + recommendation) that feeds the architect's design card, the same way grill decisions feed `project-kickoff-spec`.

Full analysis (the gap, where R&D sits, profile-vs-skill verdict, what it produces, YC/venture-builder parallel, proposed `exploration-gate` skill spec): see [`references/pipeline-exploration-gap.md`](references/pipeline-exploration-gap.md). For the Karpathy autoresearch pattern (autonomous keep-or-discard experiment loop) and its implications for parallel spike prototyping: see [`references/autoresearch-pattern.md`](references/autoresearch-pattern.md).

## Resuming a project after workflow engine changes

When resuming a project where the workflow engine has changed since the last planning session, the existing manual plan artifacts (TICKETS.md, IMPLEMENTATION-PLAN.md) are STALE — the workflow's decompose phase regenerates the plan fresh. Don't try to reconcile old plans with the new engine.

**Procedure (proven 2026-08-08, ngin project):**
1. Back up everything: `git add -A && git commit`, then `git tag backup-<date>` AND `git branch backup/<name>` — both needed (tag for immutability, branch for easy checkout)
2. Delete manual plan artifacts (TICKETS.md, IMPLEMENTATION-PLAN.md) — only SPEC + ADRs + CONTEXT.md survive
3. Clean repo: `git worktree remove --force` all worktrees (branches survive in git), `rm -rf target/` (build cache, regenerable), `git branch | grep -v main | xargs git branch -D` (stale ticket branches)
4. Verify clean state compiles (`cargo test` or equivalent)
5. Feed the spec into the workflow engine

**Key insight:** The user corrected the PO's instinct to "continue from existing plan." When the workflow engine changes, the plan it generates will differ. Starting fresh (keeping code, discarding manual plans) is cleaner than reconciling stale plans against an evolved engine.

**Beads schema migration gate:** If `bd init` reports "refusing to auto-apply N pending schema migrations (v42 -> v53)" and ALL writes are blocked, the remote's Dolt DB is behind. bd refuses to auto-migrate because two clones migrating independently forks the schema unrecoverably (#4259). When the beads DB has no live data (0 open issues): (1) `git push origin --delete refs/dolt/data`, (2) `rm -rf .beads/`, (3) `bd init --non-interactive`. The key: `bd init` WITHOUT deleting the remote ref re-bootstraps from the stale remote and hits the same gate. This is an operator action — the test failure it causes is environmental, not a code defect.

## E2E workflow test-first

When the workflow engine templates or code changed since the last successful
e2e run, test the FULL pipeline on a small project BEFORE feeding a large
spec into it. A bug at any node (trigger → architect → setup → decompose →
milestone → tech-lead-execute → merge-verify) silently breaks downstream.

See [`references/e2e-workflow-test-methodology.md`](references/e2e-workflow-test-methodology.md)
for the proven procedure (fresh board + small Rust CLI spec + verify each node fires).

## Full pipeline reference

```
User → PO → (grill → spec → [spec] card completes)
  → dev-dispatch trigger fires → routes by type:
      bug → debugger
      research → scout
      ops → ops
      tickets → PO parses pre-made tickets (route-tickets)
      default → architect (stamp spec) → setup (scaffold configs) → decompose (loop_engine + to-tickets) → milestones ([milestone-NN] cards)
  → [ticket-NN] card completes → tech-lead-execute trigger fires
      plan (loop_engine: dev phases + verifier phases) → verify (adversarial behavior tests) → fix↔re-verify (max 10) → close (merge to master) → merge-verify
  → [milestone-NN] card completes (all parent tickets done) → milestone-gate fires
      QA (receive→build→functional/journeys/security/explore→verdict) → IF PASS → refactor (scan→review→decompose) → IF FAIL → route-bug

Feedback loops:
  Verifier FAIL → fix node → re-verify loop
  Verifier ESCALATE → close node handles escalation
  Debugger debug-fix subworkflow → test_failure → debugger → verifier
```

**Note:** qa-gate.json and refactor-cycle.json were DISABLED (2026-08-08) and unified into milestone-gate.json. The old templates had two trigger bugs (prefix mismatch + self-trigger suppression blocking cross-workflow triggers). One unified graph = one trigger condition, structural edge routing. See `loop-engine-convergence-patterns` Pattern 18.

### Workflow engine architecture (current — stateless graph engine)

The OLD imperative cron engine (`startup/scripts/workflow-engine.py`, 5 phases) is **SUPERSEDED**. The current engine is the **stateless graph engine** at `startup/scripts/workflow_engine/` (`model.py` + `runtime.py` + `store.py`). It runs on a 1-minute cron tick.

**Tick pipeline (per instance, 3 passes + triggers):**
```
GC          → cleanup old instances/keys/watermarks (7-day retention)
SYNC        → read card status from board → update node states (stateless derivation)
RESET       → back-edge resets (increment iteration if < maxIterations), dead-branch skip propagation
ACTIVATE+DISPATCH → evaluate activation (AND/OR edges, fan-in barrier), dispatch ready nodes
TRIGGERS    → scan completed cards matching trigger conditions, create new instances
```

**16 production templates** live in `startup/scripts/workflow_engine/templates/`. Key workflows:
- `dev-dispatch` — routing junction: spec/ticket card completes → routes to architect→setup→decompose→milestone (default), or to debugger/scout/ops (by type), or to route-tickets (pre-made ticket parsing)
- `tech-lead-execute` — per-ticket execution loop: plan (loop_engine with dev+verifier phases) → verify → fix↔re-verify (max 10 iters) → close (merge) → merge-verify
- `milestone-gate` — triggered by [milestone-NN] card completion: QA swarm (sizing-adaptive) → refactor scan → review → decompose. Unified qa-gate + refactor-cycle (2026-08-08)
- `debug-fix` — subworkflow for test_failure → debugger → verifier

**Node types:** task (agent execution), command (synchronous shell), wait (poll condition), subworkflow (child instance), foreach (fan-out).

**Loop_engine plugin** (`startup/plugins/loop_engine/`): tool-driven convergence engine. Caller invokes it with phases (execution+verifier pairs), it handles card creation internally, dependency-parks the calling card until all phases converge. Installed on PO, tech-lead, architect, debugger, builder profiles.

For the engine internals (tick ordering, state model, guard rails, trigger system), see `references/runtime-execution-model.md` in the `workflow-engine-development` skill. For the OLD imperative phase reference (historical context only), see [`references/workflow-engine-phases.md`](references/workflow-engine-phases.md).

### Builder pipeline artifact contract (grill → build → promotion)

The builder runs a 2-card pipeline per idea (grill card → build card). The PO inherits the output at promotion. For what each stage produces, what the next reads, validation gates, and the known `.context/` validation gap, see [`references/grill-build-handoff-contract.md`](references/grill-build-handoff-contract.md). Key takeaway: `validate-grill-output.sh` checks `context/` (no dot) but NOT `.context/` (dotted) — verify the secondary outputs exist before promotion, and derive them from the primary output if missing.

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
