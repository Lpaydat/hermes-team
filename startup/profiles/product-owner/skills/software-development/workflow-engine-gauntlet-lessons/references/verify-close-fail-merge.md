# verify FAIL→close false merge — design remedies

Session-specific detail backing lesson #13 of `workflow-engine-gauntlet-lessons`.
The condensed rule lives in the SKILL.md; this file carries the three concrete
designs + ready-to-adapt edge JSON.

## Failure (recap)

`tech-lead-execute.json` edge `{"from":"verify","to":"close"}` is unconditional.
Verifier stamps `verdict=FAIL`, creates fix cards via `kanban_create` in its body,
then `kanban_complete`s. close fires immediately (no verdict guard), stamps
`verdict=merged`, instance exits "successfully" with an unfixed Critical finding.
The fix cards finish later, orphaned.

Two independent root causes:
1. No `condition` on verify→close (engine dispatches on source-done, not verdict).
2. Fix cards live outside the graph (kanban_create in body = no-op for tracking).

## Engine dispatch rule (why unconditional edges are dangerous)

`_node_is_dispatchable` (runtime.py:240-300): for an incoming edge with no
`condition`, the source only needs phase `done` for the target to dispatch.
There is no verdict check. Conditions attach to EDGES, and only conditional
edges get OR-semantics evaluation against `${nodes.*.output.*}`.

## Option A — Conditional DAG (recommended)

Mirror `templates/dev-review-loop.json`. Add `fix` + `re-verify` as graph nodes.

```jsonc
"edges": [
  {"from":"plan","to":"verify","condition":"${nodes.plan.output.plan_complete} exists"},
  {"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'PASS'"},
  {"from":"verify","to":"fix","condition":"${nodes.verify.output.verdict} == 'FAIL'"},
  {"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'ESCALATE'"},
  {"from":"fix","to":"re-verify"},
  {"from":"re-verify","to":"close","condition":"${nodes.re-verify.output.verdict} == 'PASS'"},
  {"from":"re-verify","to":"fix","condition":"${nodes.re-verify.output.verdict} == 'FAIL' AND ${nodes.re-verify.iteration} < 3", "max_iterations": 3},
  {"from":"re-verify","to":"close","condition":"${nodes.re-verify.output.verdict} == 'ESCALATE'"}
]
```

- verify body: REMOVE "create fix cards" instruction; stamp verdict + findings only.
- `fix` may internally call `kanban_chains` if findings span many files (it's the
  caller → structurally blocks until terminals done; that path IS safe).
- re-verify→fix back-edge is conditional + capped → validator accepts it
  (model.py:307-335 enforces an iteration cap on every cycle).

## Option B — Self-blocking verify via kanban_chains (fragile)

Keep 3 graph nodes. Rewrite verify body so on FAIL it calls `kanban_chains`
(fix→re-verify-passthrough) and dependency-parks until the terminal is done.
verify re-stamps verdict=PASS, then completes.

Avoid. Pushes correctness into body text — the thing lesson #1 calls "IGNORED"
by the agent. The iteration cap can't be enforced by the graph's iteration
counter here. Only the graph (Option A) makes the invariant a structural fact.

## Option C — Honest terminal FAIL (no retry loop)

Make FAIL an honest terminal, not a false merge:

```jsonc
{"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'PASS' OR ${nodes.verify.output.verdict} == 'ESCALATE'"},
{"from":"verify","to":"fail-terminal","condition":"${nodes.verify.output.verdict} == 'FAIL'"}
```

`fail-terminal` (tech-lead) creates a replan backlog via `kanban_chains`, then
completes the instance with `verdict=failed-needs-replan`. The board shows a
real failure instead of a fake merge. Acceptable when integration-stage FAILs
are rare; loses the dev-review-loop iteration benefit otherwise.

## Anti-pattern to avoid

Any "the verifier creates fix cards and we trust close to wait for them" design.
`kanban_create` in a node body is untracked by the engine (lessons #3, #11). The
only two things that structurally block a node are: (a) another graph node it
depends on, or (b) `kanban_chains` where the node is the caller. Body-issued
cards are neither.
