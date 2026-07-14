# Validation Reference — Skills and Techniques

Deep reference for the Validate phase. Load when setting up validation for a task or debugging validation quality.

## Matt Pocock's `code-review` skill — two-axis review

(Renamed from `review` in the skills v1.1 update.) Upstream it runs two parallel sub-agents, deliberately separate so one axis can't mask the other. **In Hermes**, the verifier's chains static worker runs BOTH axes itself sequentially inside its own card session — in-session sub-agents (`delegate_task`) are fragile here, and the axis separation is preserved by reporting under separate headings:

### Standards axis
Does the code follow the repo's documented coding standards?
- Sources: `CODING_STANDARDS.md`, `CONTRIBUTING.md`, or equivalent
- Always carries the **Fowler smell baseline** (from _Refactoring_ ch.3), even when a repo documents nothing:
  - Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Repeated Switches, Shotgun Surgery, Divergent Change, Speculative Generality, Message Chains, Middle Man, Refused Bequest
- Repo standards override the baseline; baseline smells are always judgement calls

### Spec axis
Does the code faithfully implement the originating issue/PRD?
- Checks: (a) requirements missing or partial, (b) scope creep — behavior not asked for, (c) requirements that look implemented but are wrong
- Quotes the spec line for each finding

### Aggregation
Reports under `## Standards` and `## Spec` headings separately. Does NOT merge or rerank — the separation is the point.

## `requesting-code-review` (obra/superpowers) — NOT for the kanban loop

Historical/harness-direct-era tooling: dispatches a code reviewer sub-agent with precisely crafted context — never your session's history. In the kanban-native loop the tech-lead never dispatches reviewers (the `verifier` profile owns validation; Phase 4 forbids you from running any of this yourself). Kept for reference only.

1. Get git SHAs: `BASE_SHA=$(git rev-parse HEAD~1)`, `HEAD_SHA=$(git rev-parse HEAD)`
2. Dispatch reviewer sub-agent with: description, plan/requirements, base SHA, head SHA
3. Act on feedback: fix Critical immediately, fix Important before proceeding, note Minor for later, push back if wrong (with reasoning)

## Subjective scoring (Karpathy VI)

For UI/design work. Four axes, weighted:

| Axis | What it measures |
|------|-----------------|
| **Design** | Visual hierarchy, spacing, typography, color |
| **Originality** | Does it feel fresh or derivative? |
| **Craft** | Attention to detail, polish, edge cases |
| **Functionality** | Does it actually work well? |

Score 0-1 per axis. Calibrate: tell the evaluator 3 reference sites that are good and 3 that are slop before scoring. Output: number + paragraph explaining the gap. Threshold: any axis < 0.7 flags for iteration.

The model won't invent taste; it converges toward the taste you described. The whole game is writing the rubric carefully enough that converging toward it is what you actually wanted.

## Per-epic comprehensive validation

After all tasks in an epic pass individual validation:

- **`improve-codebase-architecture`**: Explore sub-agent walks the codebase for friction — shallow modules, coupling, untested code. Produces HTML report with before/after visuals. Uses deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality).
- **`ponytail-audit`**: Repo-wide scan for over-engineering. Tags: `delete:` (dead code), `stdlib:` (hand-rolled thing the stdlib ships), `native:` (dependency doing what platform does), `yagni:` (abstraction with one implementation), `shrink:` (same logic, fewer lines). Ranked biggest cut first.
- **`ponytail` cleanup**: YAGNI enforcement on new code. Forces the laziest solution that actually works.

## CodeGraph validation tools (one-shot mode)

```bash
# Blast-radius: what does this change affect?
codegraph-server --graph-only --workspace /project \
  --run-tool codegraph_pr_context \
  --tool-args '{"baseBranch":"main","format":"markdown"}'

# Test-gap detection
codegraph-server --graph-only --workspace /project \
  --run-tool codegraph_find_untested

# Stale documentation
codegraph-server --graph-only --workspace /project \
  --run-tool codegraph_find_stale_docs
```
