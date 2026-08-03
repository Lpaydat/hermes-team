# Stateless Engine Rewrite — Lessons Learned

Hard-won knowledge from the stateless graph engine rewrite + dev-dispatch template deployment.

## Merging rules (CRITICAL)

1. **Never merge a feature branch to main without explicit user approval.** "It's tested" is not sufficient. The user decides when to merge. This is the #1 mistake to never repeat.
2. **Deploying a template** to `startup/scripts/workflow_engine/templates/` via file copy is OK — it's additive, doesn't change engine code.
3. **Pausing a cron** via `cronjob action=pause` is OK — it's a config change, not a code change.
4. If you `git reset --hard` to undo an unauthorized merge, verify main is clean afterward and report the verification.

## Live testing rules

1. **Never put test cards on production boards.** Create a dedicated `wf-*-livetest` board.
2. **Add the test board to `active-projects.json`** or the engine won't scan it.
3. **Create a project directory** (even `/tmp/wf-test`) — the engine maps boards to project dirs.
4. **Insert task_runs with metadata** — the `tasks` table has no `metadata` column. Metadata lives in `task_runs.metadata` as JSON. Without a task_run, the trigger enrichment can't see `type`, `verdict`, etc.
5. **Tick manually** (`python3 workflow_engine/main.py tick`) to test without waiting for cron.
6. **Clean up**: archive test cards, delete test boards, remove test entries from active-projects.json.

## Back-edge annotation (DFS-based)

The engine uses DFS discovery-order to mark back-edges, NOT SCC membership:
- In a 2-node cycle (A→B, B→A), only B→A is a back-edge. A→B is a forward (tree) edge.
- This matters because the reset pass only fires on back-edges. If the forward edge is marked as back-edge, it resets the wrong node.
- Self-loops (A→A) are always back-edges.
- The validation gate allows a cycle where at least ONE edge has an iteration cap (not every edge).

## Loop reset semantics

When a back-edge fires (source done + condition true → reset target):
1. Archive target's current state to `iterations[]` (cap 10)
2. Clear target's card_id, card_status, terminal flags
3. Bump target's iteration (changes idempotency key → fresh card)
4. **Also clear the SOURCE node** — its done flag, output, card_id, card_status
5. **Bump source iteration too** — so its idempotency key changes → fresh card
6. Keep target's output as last-known-good (downstream sees stale but safe value)

Without step 4-5, the source's stale output re-triggers the back-edge every tick.

## Dispatch template design (dev-dispatch)

The dev-dispatch workflow routes completed spec cards:
- Trigger: `card_completed` where `assignee=product-owner, status=done, title_prefix=[spec]`
- Entry node is `type: "command"` (synchronous, no card) — acts as routing junction
- 5 conditional edges from entry to route nodes (bug→debugger, research→scout, etc.)
- Dead-branch skip propagation ensures only one route fires per trigger
- Default (no metadata.type or unknown type) → tech-lead

Key: trigger context includes `card_id`, `board`, `assignee`, `title`, and all metadata fields spread flat (e.g., `metadata.type` → `${trigger.type}`).

## Multi-subagent worktree contention

Multiple subagents writing to the same worktree cause:
- File collisions (one agent's stash clobbers another's changes)
- DB lock contention (sqlite WAL helps but doesn't prevent all races)
- Test failures that look like code bugs but are actually concurrent access

Solution: serialize commits. Or use separate worktrees per subagent.
