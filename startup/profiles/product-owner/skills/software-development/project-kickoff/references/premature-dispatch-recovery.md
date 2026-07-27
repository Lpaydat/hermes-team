# Premature Dispatch Recovery

When the workflow engine auto-dispatches builder work before the design phase is complete (before the human has reviewed gate cards, before the spec is finalized), you need to kill the processes, clean the repo, and reset the board.

This happened in a real session (2026-07-27): registering the project in `active-projects.json` while beads still had `ready-for-agent` caused the scanner to immediately dispatch. A matrix chain (kanban_chains) was spawned that routed to `developer` instead of `tech-lead`, and code was scaffolded in the repo root instead of the monorepo `frontend/` directory.

## Symptoms

- Cards on the project board with `assignee: developer` (should be `tech-lead`)
- Card bodies saying "Matrix root anchor — blackboard only"
- Running developer processes writing code into the repo root
- Git worktrees under `.worktrees/` with only context files (AGENTS.md, CLAUDE.md) or premature scaffold
- A feature branch with code that doesn't match the monorepo structure

## Recovery procedure

### 1. Kill running processes

```bash
# Find the PIDs from kanban events or ps
ps aux | grep -E 't_<task-id>' | grep -v grep
# Kill them
kill <pid>
# If they respawn (dispatcher reclaims), use SIGKILL
pkill -9 -f 't_<task-id>'
```

Verify: `ps aux | grep -E 't_<task-id>' | grep -v grep | wc -l` should be 0.

### 2. Remove git worktrees and branches

```bash
cd <project-dir>

# Remove all worktrees
for wt in .worktrees/t_*; do
  git worktree remove --force "$wt"
done

# Delete worktree branches
for branch in $(git branch | grep '^  wt/'); do
  git branch -D "$branch"
done
```

### 3. Reset the repo to clean master

```bash
# Remove premature code artifacts
rm -rf node_modules/ dist/ src/ pb/ public/ package.json package-lock.json vite.config.ts tsconfig.json eslint.config.js index.html
rm -rf .harness-prompt.md .pi/ traces/ journal/

# If on a feature branch, restore tracked files and switch to master
git checkout -- .
git checkout master
git branch -D <feature-branch>

# If design docs were only on the feature branch, recover from reflog
git log --oneline <feature-commit-hash>
git cherry-pick <feature-commit-hash>  # brings just the docs onto master
```

### 4. Archive all cards on the project board

```bash
# List all task IDs on the board, then archive them
hermes kanban --board <board-slug> archive <task-id-1> <task-id-2> ...
```

Note: `--board` goes BEFORE the subcommand: `hermes kanban --board <slug> archive`, not `hermes kanban archive --board <slug>`.

### 5. Remove ready-for-agent from beads

```bash
cd <project-dir>
for issue in <bead-id-1> <bead-id-2> <bead-id-3>; do
  bd update "$issue" --remove-label "ready-for-agent"
done
```

This prevents the scanner from immediately re-dispatching when it next ticks.

### 6. Push clean state to GitHub

```bash
git push origin master
git push origin --delete <feature-branch>  # if it was pushed
```

### 7. Verify

- `git status` clean on master
- `git branch` shows only master
- No running developer/builder processes
- Project board has no non-archived cards
- Beads have no `ready-for-agent` label
- `.driver/` and `docs/adr/` intact on master

## Prevention

### Timing gate (design before dispatch)

The correct sequencing is: design complete → gate cards resolved by human → design applied to ADRs → THEN add `ready-for-agent` to beads and register in `active-projects.json`. See the project-kickoff skill's Step 5 notes on `active-projects.json` as a dispatch trigger.

### Skill enforcement (prevent kanban_chains misuse)

The workflow engine (`workflow-engine.py`) creates PO dispatch cards with the skill name in prose only (`"Run dev-dispatch"`) but WITHOUT a `--skills dev-dispatch` flag. This is the root cause of matrix chain routing: the PO reads prose, doesn't load the skill, and improvises with `kanban_chains`. 

**Fix:** Add `--skills dev-dispatch` to the dispatch card creation in `workflow-engine.py`:

```python
# Current (broken — prose only, PO may ignore):
"create", f"[dispatch] {len(new_beads)} ready bead(s)",
"--assignee", "product-owner",
"--body", f"## Ready beads to dispatch\n\n{bead_list}\n\nRun `dev-dispatch` to create tech-lead cards.",

# Fixed (skill force-loaded):
"create", f"[dispatch] {len(new_beads)} ready bead(s)",
"--assignee", "product-owner",
"--body", f"## Ready beads to dispatch\n\n{bead_list}\n\nRun `dev-dispatch` to create tech-lead cards.",
"--skills", "dev-dispatch",  # force-loads the skill — tool-level enforcement
```

This is the tool-level enforcement vs. prompting principle: prose instructions to LLMs are suggestions, skill loading is enforcement.
