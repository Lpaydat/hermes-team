# E2E Workflow Test Methodology

> Proven 2026-08-08: before feeding ngin's 40-story spec into a workflow
> pipeline whose templates were updated the same day, the user directed
> "let test first" on a small project. This is a first-class workflow
> discipline, not optional.

## When to test first

Test the FULL workflow pipeline on a small project BEFORE feeding a large
spec into it whenever ANY of these conditions hold:

- Templates changed recently (dev-dispatch, tech-lead-execute, refactor-cycle)
- The engine code was modified since the last successful e2e run
- You haven't verified the full chain (trigger → architect → setup → decompose → milestone → tech-lead-execute → merge-verify) on the current version
- A new node type, trigger condition, or routing path was added

## Why test first

The workflow pipeline is a long chain: spec card → trigger fires → dev-dispatch routing → architect stamps spec → tech-lead scaffolds configs → PO decomposes via loop_engine → PO creates milestones → tech-lead executes each ticket → verifier writes behavior tests → fix/re-verify loop → merge → merge-verify → milestone → refactor.

A bug at ANY node silently breaks the chain downstream. Throwing a 40-story spec at an untested pipeline wastes hours of dispatch cycles before the failure surfaces.

## Test project criteria

The test project should be:
- **REAL** — not a toy/echo test. Actual code with actual tests.
- **Small** — 3-5 tickets worth, completes in minutes not hours.
- **Same stack** — if the target project is Rust, the test is Rust (validates the same `configs/<lang>/` scaffolding).
- **Fresh** — new board, new repo, new spec file. No stale state.

## Procedure (proven 2026-08-08)

1. **Create the test project:**
   ```bash
   mkdir ~/workspace/wf-test && cd ~/workspace/wf-test
   git init && echo "# <name>" > README.md && git add -A && git commit -m "init"
   ```

2. **Write a minimal spec** — 3-5 user stories, open Implementation Decisions + Testing Decisions sections (architect stamps these).

3. **Create a fresh board:**
   ```bash
   hermes kanban boards create <slug> --switch
   ```

4. **Add to active-projects.json** (replace stale entries; only `board` is required):
   ```json
   {"active_projects": [{"board": "<slug>", "repo": "/home/lpaydat/workspace/<slug>"}]}
   ```

5. **Create the [spec] card** and complete it:
   - Title must start with `[spec]` (matches `title_prefix_any` trigger)
   - Assignee must be `product-owner`
   - Body must contain the repo path (architect reads it to write the spec file)
   - metadata.type must NOT be bug/research/ops/tickets (omitting it routes to the default architect path)
   - Complete with `status: done` to fire the dev-dispatch trigger

6. **Watch the pipeline fire:**
   ```bash
   # Manual tick to verify trigger fires immediately
   cd ~/.hermes-teams/startup/scripts/workflow_engine
   python3 main.py tick 2>&1 | grep -E 'DISPATCHED|SKIPPED|DONE|STARTED'
   ```

7. **Verify each node fires correctly:**
   - `entry` command node runs ✓
   - Dead branches (route-bug, route-scout, route-ops, route-tickets) are SKIPPED ✓
   - `route-architect` DISPATCHED → architect agent spawned ✓
   - After architect completes: `route-setup` → `route-decompose` → `route-milestone` fire ✓
   - Each ticket triggers `tech-lead-execute` ✓

## What to watch for

- **Trigger not firing** → check active-projects.json has the board, check title prefix matches `[spec]`, check assignee is `product-owner`, check status is `done`.
- **Wrong routing** → check metadata.type on the completed card. Missing type → default architect path (correct for code projects).
- **Architect can't find spec file** → ensure body contains the absolute repo path.
- **Stale livetest boards in active-projects.json** → replace with only the test board to avoid scanning old data.

## After the test passes

Once the full chain is verified e2e on the small project:
1. Archive the test board's cards
2. Remove the test board from active-projects.json (or replace with the real project)
3. Feed the real spec into the pipeline with confidence
