# Stateless Engine Migration — Pitfalls & Lessons

Session: 2026-08-02. Lessons from building the stateless graph engine rewrite
and deploying the dev-dispatch workflow template to production.

## Critical rules (learned the hard way)

1. **NEVER merge the feature branch to main without explicit user sign-off.**
   The user decides when to merge. Copying a template file to production
   `templates/` is OK. Merging code = user's gate.

2. **NEVER put test data on production boards.** Always create a dedicated
   test board: `hermes kanban boards create <test-name>`, add it to
   `active-projects.json`, run tests there, delete when done.

3. **DEPLOY IMMEDIATELY after verification passes.** Reporting "ready to
   deploy" then waiting 30 minutes without doing it is a failure. If you
   say "let me copy", DO IT in the same turn.

4. **Production main may have older engine code than the feature branch.**
   Template features that work in the worktree (compound AND/OR conditions,
   back-edge loops) may NOT work on production main until the branch is
   merged. Always test templates against the PRODUCTION engine code.

5. **Corrupt boards crash the engine.** `_boards_to_check` must skip boards
   with missing `tasks` table. Always guard against corrupt SQLite DBs.

## Condition engine pitfalls

- **Compound `!=` conditions are broken on production main** (pre-T1
  upgrade). The old `evaluate_condition` uses `re.match` which matches
  the FIRST clause only. `${trigger.type} != 'bug' AND ${trigger.type}
  != 'ops'` evaluates to True even when type=ops.
- The fix is T1 (condition engine upgrade with proper AND/OR split) on
  `feat/workflow-dispatch`. Until that branch is merged, compound
  conditions don't work on production.
- Workaround: use `==` conditions for routing (each route checks one
  positive match, not a negation chain).

## Template design for routing diamonds

- Use a **command-type entry node** as the routing junction (synchronous,
  no card created). All routing edges come FROM entry with conditions.
- The default route (catch-all) should use `==` conditions on the OTHER
  routes to detect "none matched" — don't use a compound `!=` chain.
- Dead-branch skip propagation handles the non-matching routes
  automatically: if entry is done and the edge condition is false, the
  target node is skipped.

## Kanban-native dispatch (no beads dependency)

The dispatch workflow triggers on `card_completed` where:
- `assignee`: product-owner
- `status`: done
- `title_prefix`: [spec]

Routing by `metadata.type`:
- bug → debugger
- research → scout
- ops → ops
- architecture → architect
- everything else → tech-lead

Metadata comes from `task_runs` table (NOT `tasks` table). When creating
test spec cards, insert a completed `task_run` with the metadata JSON.

## Board cleanup

- `hermes kanban boards delete <slug>` removes the board
- Leftover directories in `kanban/boards/` without proper `kanban.db`
  cause engine crashes — delete them manually
- `active-projects.json` must reference valid boards — clear it when
  cleaning up
