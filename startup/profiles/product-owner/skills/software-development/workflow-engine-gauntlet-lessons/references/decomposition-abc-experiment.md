# Decomposition A/B/C Experiment — Session Record

## Question
How should the plan phase decompose a spec? One-shot (A), loop_engine
convergence to atomic leaves (B), or critic-collaborated revision (C)?

## The three versions

| Version | Template | Plan-phase mechanism | Distinctive metadata |
|---------|----------|---------------------|---------------------|
| A | tech-lead-execute.json | to-tickets → kanban_chains (one-shot, current) | task_count, sizing_summary |
| B | tech-lead-execute-b.json | to-tickets → loop_engine converge (execution: break oversized tasks; verifier: atomicity check; advance/replan/escalate, max_iterations 5) → dispatch LEAF tasks | decomposition_iterations |
| C | tech-lead-execute-c.json | to-tickets → delegate_task clean-context critic subagent (5 fixed questions) → revise → kanban_chains | critic_findings, critic_revisions |

## Atomicity definition (B's convergence condition)
A task is atomic when: (a) a junior dev can complete it in one sitting,
(b) it has clear testable acceptance criteria, (c) it can be verified
independently, (d) it is not two tasks disguised as one.

## C's critic questions (self-grill pattern)
1. Does every spec requirement have at least one task covering it? Gaps?
2. Are any tasks too big for a junior dev in one sitting? Which?
3. Are any tasks two tasks disguised as one? Which?
4. Is the task count reasonable for spec complexity (~1 task per 50 lines)?
5. Are the acceptance criteria testable? Which aren't?

User's open concern about C: clean context may make the critic ignorant of
what it reviews. Mitigation tried: pass spec body + proposed task list as
the critic's full context.

## Parallel setup (trigger-prefix isolation — lesson #9)

- 3 templates, triggers: `[spec-a]` / `[spec-b]` / `[spec-c]` title prefixes
- 3 specs, each seeded on 3 boards with prefixed titles + IDENTICAL bodies
- Spec card IDs unique per board (spec-a1, spec-b1, spec-c1) — all-`spec-1`
  collides on trigger_key dedup (only the first board fires)
- 9 boards total: ab-decom-a1..c3, all dispatched in tick 2

## Test specs (medium complexity, multi-component — chosen to expose
## decomposition differences)
1. Markdown Table Generator CLI (9 requirements: CSV parsing, alignment
   flags incl. column-specific, escaping, errors)
2. JSON Diff Tool (9 requirements: two output formats, nested/array/type
   diff, ignore keys, exit codes)
3. Unit Converter Library (10 requirements: 4 categories, auto-detect,
   batch, pretty print, errors)

## Phase-scoped testing (user direction)
"we may only test the decomposition part, not the full workflow."

Stop condition: all plan cards created their chains (dev cards exist OR plan
card done/blocked/todo). Measure decomposition only:
- task count (over/under)
- chain structure (tree depth, serial vs parallel)
- AC quality / dependency correctness
- B: decomposition_iterations; C: critic_findings + critic_revisions
- time-to-decompose

Then kill the run. Dev→verify→close adds hours and answers nothing about
planning quality. Cuts gauntlet cost 70%+ for planning-phase questions.

## Status
Experiment dispatched (9 boards live). Results analysis pending — see the
board-quality-audit skill for the 5-dimension scoring protocol when
analyzing.
