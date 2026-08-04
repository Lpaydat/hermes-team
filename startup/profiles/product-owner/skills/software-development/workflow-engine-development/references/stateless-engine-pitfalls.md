# Stateless Engine Pitfalls

Hard-won lessons from building the stateless graph engine (T1-T7) + dev-dispatch workflow.

## Back-edge annotation: DFS discovery order, NOT SCC membership

Tarjan SCC marks ALL edges in a cycle as back-edges. This is WRONG for the engine:
in a 2-node cycle (build→review, review→build), only review→build should be a
back-edge. Use DFS discovery times instead: a back-edge is one where `to_node`
was discovered BEFORE `from_node` AND both are in the same SCC. This correctly
marks only the cycle-CLOSING edge.

Self-loops (A→A) are always back-edges regardless of discovery order.

## Back-edge reset must clear the SOURCE node

When a back-edge fires (review FAIL → reset build), the reset pass must also
clear the SOURCE node (review): card_id, card_status, output, done flag, AND
bump its iteration. Otherwise:
- The stale FAIL output re-triggers the back-edge every tick
- The source's idempotency key doesn't change → dedup adopts the old card
- The loop never advances past iteration 1

## Entry nodes with only back-edge incoming edges

If a node's ONLY incoming edges are back-edges from nodes that haven't run yet,
treat it as an entry node on the first iteration. Back-edges can't fire until
the source completes at least once — they shouldn't block initial dispatch.

Implementation: in `activation_rule_satisfied`, check if all incoming edges are
back-edges AND no source has run. If so, treat as entry node (dispatchable).

## Command-type entry nodes for routing junctions

When a template needs conditional routing (diamond pattern), use a `command`
type entry node (synchronous, no card) as the junction. Task-type entry nodes
create unnecessary cards and require extra ticks to complete.

Example (dev-dispatch.json):
```json
{"id": "entry", "type": "command", "command": "echo '{\"status\": \"routing\"}'"}
```
Then conditional edges from `entry` to each route node.

## Trigger context must include 'title'

`_start_from_trigger` must include `trigger_card.title` in the trigger context.
Body templates like `${trigger.title}` resolve against this. Without it, routed
card bodies show empty titles.

## Back-edge cap validation: sibling edges

In a 2-node cycle, the validation should require an iteration cap on at least
ONE edge in the cycle — not every edge. The forward edge (build→review) can lack
a cap as long as the back-edge (review→build) has `max_iterations` or an
iteration-referencing condition.

## Reachability validation excludes back-edges

When computing entry nodes for reachability validation, exclude back-edges from
the `has_incoming` set. A back-edge pointing at `build` doesn't make `build`
non-entry — it can't be traversed on the first pass.

## _update_blob_after_dispatch: wait node semantics

For wait nodes, `ok=False` means "still waiting" (not "failed"). Only set `done`
when the condition resolves. Transient dispatch failures (card creation error)
should NOT set `failed: True` — stay pending for retry on next tick.

## Subagent worktree contention

Multiple delegate_task subagents writing to the SAME worktree branch cause file
collisions: one agent stashes changes, another's edits get lost. Use SEPARATE
worktrees per subagent for code changes, OR do the edits yourself and dispatch
subagents only for read-only analysis.

## Design review cycle

The design went through 4 review rounds (5 reviewers → 3 reviewers → fixes →
final approval). Key pattern:
1. Write design doc
2. Dispatch 3-5 subagents in parallel, each reviewing a specific axis
3. Read all reviews, categorize findings (CRITICAL / HIGH / non-blocking)
4. Fix all CRITICAL/HIGH items
5. Re-review with fewer subagents focused on whether fixes are correct
6. Repeat until all reviewers say APPROVED

This caught: non-atomic state blob (CRITICAL), completion model gap (CRITICAL),
self-trigger guard bug (P0), node_phase blind spot (HIGH), and scope estimate
being 2x naive (HIGH).

## Deploy immediately after verification — do not wait

After a feature is verified (tests pass, live E2E confirmed), DEPLOY IT. Do not
report status and wait for the user to ask "is it done?" — merge to main, copy
templates to production, create the live test card. The user's time is valuable;
reporting "ready to deploy" and then waiting 30 minutes is a failure mode.

Pattern: test passes → merge → deploy → create real card → show result → THEN report.

## Kanban metadata lives in task_runs, not tasks

When creating spec cards for live testing, metadata goes in the `task_runs` table
(not `tasks`). The `tasks` table has no `metadata` column. `find_recent_completions`
joins `tasks` with `task_runs` to get metadata. Insert both a `tasks` row AND a
completed `task_runs` row with the metadata JSON.

## dev-dispatch routing diamond pattern

The dev-dispatch template uses a command-type entry node as a routing junction,
with 5 conditional edges to route nodes. Dead-branch skip propagation ensures
only ONE route fires per trigger. Key design decisions:
- Entry is `type: "command"` (synchronous, no card created)
- Routes are conditional edges from entry: `${trigger.type} == 'bug'` etc
- Default route (tech-lead) uses negative conditions for all other types
- trigger context includes `title` field for body template resolution
