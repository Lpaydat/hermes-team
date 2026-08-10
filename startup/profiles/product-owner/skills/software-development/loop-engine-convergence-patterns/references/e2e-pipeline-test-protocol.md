# Full E2E Pipeline Test Protocol (validated 2026-08-08, updated 2026-08-09)

## Purpose

End-to-end test of the complete dev pipeline on a small project to verify
all workflow stages fire correctly before pointing the pipeline at a large
production spec.

## When to use

Before feeding a major project (40+ user stories) into the workflow engine.
Run a small project (3-5 tickets) through the full pipeline first to catch
broken templates, trigger issues, or dead stages.

## Protocol

### 1. Set up the test project

```bash
mkdir -p ~/workspace/<test-name>
cd ~/workspace/<test-name>
git init
echo "# <test-name>" > README.md
git add -A && git commit -m "init"
```

### 2. Write a small spec

3-5 user stories. Same tech stack as the target project (if target is Rust,
test with Rust). The spec should exercise:
- CLI/tool interface (tests architect + setup + decompose)
- Multiple independent features (tests ticket decomposition + parallel execution)
- Testing requirements (tests verify + fix loop)

### 3. Create board and add to active-projects.json

```bash
hermes kanban boards create <test-name> --switch
```

Update `~/.hermes-teams/startup/active-projects.json`:
```json
{
  "active_projects": [
    {"board": "<test-name>", "repo": "/home/<user>/workspace/<test-name>"}
  ]
}
```

IMPORTANT: Replace stale entries — don't accumulate test boards in the
allowlist, they'll all get trigger-scanned.

### 4. Create the spec card and complete it

```python
# Create card
kanban_create(
    board="<test-name>",
    assignee="product-owner",
    title="[spec] <project name>",
    body="<spec content + repo path>"
)
# Complete it to trigger dev-dispatch
kanban_complete(
    board="<test-name>",
    task_id="<id>",
    metadata={"type": "project", "spec_file": "<path>"}
)
```

### 5. Monitor the pipeline

The engine cron runs every minute. Monitor with:
```sql
-- Card count by status
SELECT status, count(*) FROM tasks GROUP BY status;

-- Currently running/todo cards
SELECT title, status, assignee FROM tasks
WHERE status IN ('running','todo','ready') ORDER BY created_at;
```

Key milestone cards to watch for:
```
[spec]           → [architect] → [setup] → [decompose] → [ticket-NN]
                                                     → [milestones]
[ticket-NN]      → triggers tech-lead-execute
                     plan → loop_engine(task/verify) → verify-b → close
[milestone-NN]   → triggers milestone-gate (QA + refactor)
```

### 6. Verify ALL stages fired

After all cards are done, check for each pipeline stage:

```sql
-- dev-dispatch routing
SELECT title FROM tasks WHERE title LIKE '[architect]%';
SELECT title FROM tasks WHERE title LIKE '[setup]%';
SELECT title FROM tasks WHERE title LIKE '[decompose]%';
SELECT title FROM tasks WHERE title LIKE '[milestones]%';

-- tech-lead-execute
SELECT title FROM tasks WHERE title LIKE '[tl-b] Plan%';
SELECT title FROM tasks WHERE title LIKE '[verify-b]%';
SELECT title FROM tasks WHERE title LIKE '[tl-b] Close%';
SELECT title FROM tasks WHERE title LIKE '[merge-verify]%';

-- milestone-gate (QA + refactor)
SELECT title FROM tasks WHERE title LIKE '[qa]%';
SELECT title FROM tasks WHERE title LIKE '[refactor-%';
```

If any stage has ZERO cards, investigate the trigger condition.

### 7. Verify the code actually works

```bash
cd ~/workspace/<test-name>
cargo test 2>&1 | grep 'test result'  # or pytest, npm test, etc.
cargo build --release && ./target/release/<binary> --help
```

### 8. Common failure modes and detection

| Stage missing | Detection query | Likely cause |
|--------------|----------------|--------------|
| [architect] | `SELECT count(*) FROM tasks WHERE title LIKE '[architect]%'` = 0 | dev-dispatch trigger didn't fire (check title prefix, assignee, status) |
| [decompose] | count = 0 | architect didn't complete, or route-decompose edge broken |
| [ticket-NN] | count = 0 | decompose loop_engine didn't produce tickets |
| [verify-b] | count = 0 | tech-lead-execute plan node didn't fire (check [ticket-] prefix match) |
| [qa]% | count = 0 | milestone-gate trigger prefix mismatch or suppression bug |
| [refactor-% | count = 0 | milestone-gate QA verdict routing broken or refactor-scan didn't fire |

### 9. Check instance completion (known Issue 3 regression check)

```sql
-- In the workflow-state DB (NOT the board DB):
SELECT workflow_id, status FROM workflow_instances WHERE board='<test-name>';
```

All instances should show `status='completed'`. If tech-lead-execute instances
show `status='active'`, the condition-aware `_reachable_nodes` fix was reverted
or regressed (see Pattern 21 in loop-engine-convergence-patterns).

## Validated result 1 (2026-08-08, wf-test board)

- Project: watchrun (file watcher CLI, Rust, 5 user stories)
- 89 cards total, all done
- Pipeline: spec → architect → setup → decompose → 5 tickets → milestones → tech-lead-execute (all 5 tickets) → close + merge-verify
- Deliverable: working Rust CLI, 18 unit + 5 integration tests, all green, 13 commits
- QA and refactor did NOT fire — both bugs found and fixed (see Pattern 18)
- Total wall clock: ~6 hours (16:30 → 22:10)

## Validated result 2 (2026-08-09, wf-gate-test board) — milestone-gate e2e

After fixing qa-gate + refactor-cycle (Pattern 18), milestone-gate was
validated end-to-end by creating a milestone card manually (simulating
all-tickets-merged state) and completing it:

- Project: watchrun milestone-01 (5 tickets, all pre-merged)
- 26 cards total
- Pipeline: [milestone-01] → qa-receive (sized medium, 18 claims) → qa-build
  (containerized build) → [qa-functional + qa-journeys + qa-security + qa-explore]
  (parallel fan-out, 4 cards) → qa-verdict (PASS, 6 follow-up findings filed)
  → refactor-scan (found 3 candidates) → refactor-review (kanban_chains fan-out,
  3 reviewer cards) → refactor-decompose (2 refactor tickets created)
- QA findings spawned real fix cards: glob-filter bug (-p main.rs silently fails),
  SIGTERM not handled gracefully
- refactor-review validated candidates against real code, dropped false positives
- Total wall clock: ~40 minutes (05:58 → 06:37)

### Key observations from milestone-gate e2e

1. Sizing routing worked: 18 claims → medium → fan-out path (not qa-quick)
2. Parallel fan-out worked: qa-build → 4 simultaneous test cards, all dispatched
   at the same timestamp
3. Composite edge gate worked: qa-verdict waited for ALL 4 test cards to complete
4. QA PASS → refactor-scan edge fired correctly (the Pattern 18 fix works)
5. refactor-review used kanban_chains correctly (3 reviewer cards, one per candidate)
6. refactor-review verdict=continue → refactor-decompose → 2 refactor tickets

## Validated result 3 (2026-08-09, hashtree board) — full spec→milestone-gate e2e

Full pipeline from spec through milestone-gate on a fresh project:

- Project: hashtree (recursive directory tree hasher, Rust, 4 user stories)
- 109 cards total, all done
- 9 workflow instances: 1 dev-dispatch (completed), 6 tech-lead-execute (stuck active — Issue 3), 2 milestone-gate (completed)
- Pipeline: spec → architect → setup → decompose → 4 tickets → 2 milestones
  → tech-lead-execute (4 tickets in parallel) → milestone-gate (both milestones)
- Deliverable: 10 Rust files, 129 tests passing, 14 commits, working binary
- Exposed 3 bugs — all root-caused via parallel subagent investigation and fixed (commit d93b4c0):
  1. Stale commit SHA in refactor tickets (agent behavior — anti-SHA template instructions)
  2. Verifier heartbeat failure (no background thread — stale-claim reaper mitigation)
  3. Instances stuck active (fix↔re-verify cycle deadlock — condition-aware _reachable_nodes)
- Total wall clock: ~5 hours (08:34 → 13:27)

Proves the ENTIRE chain works end-to-end on a fresh project, not just
milestone-gate in isolation. Also proves the three fixes work — run another
e2e after applying fixes to confirm instances now complete.

## E2E test as a monitoring tool

After a template or engine change, run a quick e2e on a 3-4 story project.
If all nodes fire and the pipeline completes (including instance status
transitioning to 'completed'), the change is safe. If any node doesn't fire
or instances stay active, the change broke something — investigate before
proceeding.
