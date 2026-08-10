# Hashtree Full E2E + Three Pipeline Fixes

The hashtree e2e test (2026-08-09) was the first complete spec→milestone-gate
run on the unified pipeline. It exposed three bugs, all root-caused and fixed.

## E2E Test Results

- **Project:** hashtree — recursive directory tree hasher (Rust CLI, 4 user stories)
- **Board:** hashtree
- **Cards:** 109 total, all done
- **Workflow instances:** 9 (1 dev-dispatch, 6 tech-lead-execute, 2 milestone-gate)
- **Time:** ~5 hours (08:34 → 13:27)
- **Code built:** 10 Rust files, 129 tests passing, 14 git commits
- **Binary:** `hashtree <dir> [--json] [--exclude <glob>]`

### Pipeline path (key nodes)

```
08:34  [spec] → dev-dispatch → architect → setup → decompose → 4 tickets → 2 milestones
08:52  tech-lead-execute fires for all 4 tickets (parallel)
       Each: plan → loop_engine(task/verify) → verify-b → fix loops → close → merge-verify
09:19  ticket-01 verify-b PASS → milestone-gate fires for milestone-01
       qa-receive (sized medium, 18 claims) → qa-build → 4-card fan-out → qa-verdict
09:33  → refactor-scan → refactor-review → refactor-decompose → refactor ticket created
10:14  ticket-04 close
13:10  ticket-03 close (3 rebase fix iterations)
11:55  milestone-gate fires for milestone-02
12:07  → refactor-scan → refactor-review → refactor-decompose
13:27  All complete
```

### Cards by assignee

| Assignee | Cards |
|----------|-------|
| verifier | 47 |
| tech-lead | 30 |
| product-owner | 10 |
| developer | 10 |
| hashtree (loop_engine) | 7 |
| qa | 4 |
| architect | 1 |

## Three Issues Found and Fixed

### Issue 1: Stale Commit SHA in Refactor Tickets

**Symptom:** refactor-decompose pins a commit SHA into ticket body. By the time
the developer picks it up, main has advanced. Developer blocks on stale baseline.

**Root cause:** Agent behavior, not template. SHA enters as free-text in
REFACTOR.md (written by refactor-review verifier), propagates through 3 LLM hops.

**Fix (commit d93b4c0):** Three anti-SHA instructions added across templates:
1. refactor-review: "Do NOT embed specific commit SHAs in REFACTOR.md"
2. refactor-decompose: "Do NOT branch from a specific commit SHA. Always work from current main."
3. tech-lead-execute plan: "Before writing task cards, run git rev-parse main. Do NOT trust commit SHAs from the spec card body."

### Issue 2: Verifier Heartbeat Failure

**Symptom:** verify-b card ran for 2.5+ hours without heartbeating. Last
heartbeat at 12:01, claim extended 3x by PID-alive mechanism, required manual kill+reclaim.

**Root cause:** No background heartbeat thread in hermes-agent. Heartbeats
piggyback on `_touch_activity()` from the event loop. When terminal tool call
blocks the loop (cargo build/test), no heartbeats sent. PID-alive extension
keeps the claim alive. 60-min stale threshold too generous.

**Fix (commit d93b4c0):** Added stale-claim reaper (phase 6) to
workflow-engine.py cron. Reclaims tasks where PID is dead AND heartbeat >15min
stale. Logs WARNING for alive-but-stuck (needs hermes-agent background thread fix).

**What we CANNOT fix without touching hermes code:** The alive-but-stuck case
(process running, consuming CPU, but not heartbeating). This needs a background
heartbeat thread in run_agent.py. The reaper catches crashed processes; the
stuck-alive case still requires manual intervention.

### Issue 3: tech-lead-execute Instances Stuck Active

**Symptom:** All 6 tech-lead-execute instances showed status='active' after all
nodes completed. Only milestone-gate and dev-dispatch instances completed correctly.

**Root cause:** The fix↔re-verify back-edge cycle creates a circular deadlock
in dead-branch skip propagation. When verify PASSES (no fix needed):
- fix can't be skipped because re-verify (its incoming edge source) is pending
- re-verify can't be skipped because fix (its incoming edge source) is pending
- Neither dispatches, neither can be skipped, circular dependency

**Fix (commit d93b4c0):** Made `_reachable_nodes` (runtime.py:1661) condition-aware.
Filter edges to only traverse those where `condition is None` OR
`evaluate_condition(condition, ctx)` returns True. When verify→fix condition
(verdict=='FAIL') is false, fix is not reachable. The back-edge from re-verify
is also not traversable (re-verify itself is unreachable). Both excluded from
reachable set → completion check sees only terminal nodes → instance completes.

```python
# BEFORE (broken):
edges = wf.edges or [...]
return bfs_reachable(edges, seeds, node_ids)

# AFTER (fixed):
raw_edges = wf.edges or [...]
live_edges = [e for e in raw_edges
              if e.condition is None or evaluate_condition(e.condition, ctx)]
return bfs_reachable(live_edges, seeds, node_ids)
```

**Proof:** Old reachable set: {close, fix, merge-verify, plan, re-verify, verify}.
New reachable set: {close, plan, verify}. All terminal → instance completes.

## Investigation Methodology

Three subagents dispatched in parallel, each investigating one issue:
- Task 0: read runtime.py code, query state blobs, simulate completion check
- Task 1: trace heartbeat mechanism, query session DB, find blocking tool call
- Task 2: trace SHA propagation chain through card bodies and REFACTOR.md

Each produced independent root cause analysis with evidence (file:line citations,
DB queries, state blob dumps). Results matched parent's independent analysis.

Three fix subagents dispatched in parallel in isolated worktree:
- Task 0: fix runtime.py _reachable_nodes + test
- Task 1: patch milestone-gate.json + tech-lead-execute.json templates
- Task 2: add stale-claim reaper to workflow-engine.py

All fixes verified in worktree before applying to real code. Ad-hoc verification
script (7/7 checks) confirmed all three fixes on real code post-commit.
