# Subagent Worktree Isolation

Session: 2026-08-02. When dispatching multiple subagents that modify the
same files (runtime.py, model.py), use SEPARATE worktrees per subagent.
Sharing one worktree causes git stash/checkout collisions and lost work.

## Problem

Dispatching 2+ subagents to the same worktree branch, each modifying
the same file (e.g. runtime.py), causes:
- One subagent's `git stash` discards the other's uncommitted changes
- `git diff` shows interleaved changes from both agents
- Patches fail because line numbers shift from concurrent edits
- One agent resets files to HEAD, losing the other's work

## Solution

1. Create a separate worktree per subagent:
   ```bash
   git worktree add .worktrees/<sub-task-name> feat/workflow-dispatch
   ```
2. Pass the subagent's worktree path in its context
3. Merge results manually after both complete

## Alternative: serialize

If subagents must share a worktree (e.g. they have dependencies), run
them sequentially, not in parallel. One finishes and commits before the
next starts.

## When this matters

- Only when subagents EDIT files (not read-only research tasks)
- Only when they touch the SAME file(s)
- Read-only subagents (reviews, analysis) can safely share a worktree
