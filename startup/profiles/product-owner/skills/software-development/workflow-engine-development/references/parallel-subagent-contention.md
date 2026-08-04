# Parallel Subagent Contention on a Shared Worktree

> Distilled from dispatching T1+T2+T4 as parallel `delegate_task` subagents to
> the same `feat/workflow-dispatch` worktree (2026-08-02).

## The three failure modes

### 1. Engine file lock contention

The engine takes `fcntl.flock(LOCK_FILE, LOCK_EX | LOCK_NB)` on every tick
(runtime.py:538). If one subagent's tests instantiate `Engine` (which calls
`tick()`), the lock is held for that test's duration. Other subagents' tests
fail en masse with:
- `SKIP tick: another engine process holds the lock`
- `tick failed: database is locked`
- `attempt to write a readonly database`

The live engine cron (if running) compounds this — it holds the same lock on
every tick regardless of subagent activity.

### 2. Git stash cross-contamination

`git stash` stashes ALL dirty files in the working directory, regardless of
which subagent created them. When one subagent stashes to test against a clean
base, it stashes another subagent's uncommitted work too. On `git stash pop`,
everything is restored mixed together — making it impossible to isolate which
change caused a test failure.

### 3. Commits vanishing from working directory

One subagent committed its work. Another subagent, not seeing the commit
(because it read the file before the commit), did `git stash` which reverted
the working directory to the pre-commit state. The commit exists in git
history, but the working directory no longer reflects it — and the subagent
that committed sees its changes "gone."

## Mitigations

### Prevention (preferred)

1. **Separate worktrees per subagent** when tasks touch the same files:
   ```bash
   git worktree add .worktrees/wf-t1 -b feat/t1-condition-engine main
   git worktree add .worktrees/wf-t2 -b feat/t2-self-trigger main
   ```
   Each subagent gets an isolated working directory, DB, and lock file.

2. If sharing one worktree (tasks are additive, different files), tell each
   subagent to **commit immediately** after their change passes tests.

### Recovery (when contention is already happening)

3. After all subagents complete, **review the combined working tree yourself**:
   - Run the full test suite
   - Fix integration issues (e.g. a validation added by T2 breaking a test T4 wrote)
   - Commit in logical units (one commit per ticket)

4. When a subagent reports "tests failing," check whether the failure is
   environmental before accepting as a real regression:
   - `ps aux | grep workflow-engine` — is the cron alive?
   - Run lock-free unit tests (those importing only `model.py`, not `runtime.py`)
     to isolate from engine lock contention
   - `git stash` and run the suite on the clean base to establish the pre-change baseline

## Diagnosis: lock-free unit tests

These test modules import only `workflow_engine.model` (not `runtime.py`),
so they bypass the engine lock entirely:
- `test_condition_engine.py` — condition engine logic
- `test_dataflow.py` — the `test_df_*` family
- Any `model.py`-only smoke test

If these pass while `test_engine.py` fails, the failure is lock-driven
(environmental), not a regression from the code change.
