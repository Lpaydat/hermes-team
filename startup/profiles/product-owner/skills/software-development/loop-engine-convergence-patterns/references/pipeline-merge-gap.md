# Pipeline Merge Gap — The Critical Invariant Failure

## The One-Sentence Problem

The pipeline writes and fixes code on ticket branches but has no enforced invariant that master ever contains any of it — so features and bug fixes are written, verified, committed, and silently lost.

## Two Failure Modes (both confirmed in Todo CLI test)

### Failure A: Branch Stranding

Per-ticket branches never reconciled to master. The close node wrote `verdict=merged` in metadata without actually merging.

**Evidence (git forensics by developer agent):**
- ticket-01: 2 hardening commits (d8bebdc, f446df7) not in master
- ticket-02: entire `list` command (fffdc6f) not in master — still a stub in cli.py
- ticket-03: clean (only one that landed)
- ticket-04: commits not in master
- **2 of 4 ticket branches never integrated. Systemic, not incidental.**

**Fix (committed on branch `fix-v1-merge-gap`, `843a323`):**

The close node body now explicitly:
1. Merges the ticket branch into master (`git merge --no-ff`)
2. Resolves conflicts if any
3. Runs ALL tests on the merged result
4. Verifies `git log master..<branch>` is empty (nothing lost)
5. Only completes with `verdict=merged` if tests pass on merged master
6. Escalates if merge fails or tests fail after merge

### Failure B: Commits Destroyed Mid-Flight

Commits were committed then killed by `git rebase` / `git reset --hard` during ticket switching.

**Evidence:**
- Commits 393007c and 7372a68 are dangling (`git fsck` lists them; no branch contains them)
- A persona overlay fabricated git state and launched an interactive rebase of ticket-04 onto ticket-03
- `git rebase --abort` restored the repo but destroyed the commits
- Documented in `traces/t_084fccc3/RAW-EDIT-FALLBACK.md`

**Fix (committed, same commit):**

The plan node body now explicitly forbids:
```
CRITICAL GIT SAFETY: Do NOT run `git rebase` or `git reset --hard` on
any branch. These destroy commits that cannot be recovered. Use only
`git add`, `git commit`, and `git merge`. If you need to undo a change,
use `git checkout -- <file>` (discards uncommitted changes only).
```

**Note:** This is body-text enforcement (weakest layer). Structural fix would be a pre-rebase git hook that rejects rebases on `ticket-*` branches.

## Latent Issue: Stale Base

Dependent tickets were cut from a stale base (991444b, pre-hardening foundation), not from ticket-01's hardened tip. Even a correct merge-at-close would race the hardening — the dependent ticket shipped before its dependency's fix landed.

**Fix (planned):** Close node should verify all dependencies are already merged before merging. Rebase onto current master tip before merging.

## The Corrected Premise

The close node body originally said `verdict=merged` and the design assumed "user merges per contract." A grep of CONTRACT.md revealed ZERO mentions of merge. This was a fabricated design intent, not a real contract clause. Is merging the pipeline's job or the human's? The answer MUST be the pipeline — otherwise it's neither.

## merge-verify Node (Layer 2.5 — commit `9a7f07b`)

Separation of duties: the close node (tech-lead) CLAIMS it merged, but a separate merge-verify node (verifier) MECHANICALLY checks git state. The merger never verifies its own merge.

**The node runs actual git commands — no LLM judgment:**

1. `git log master..<ticket-branch>` — must output NOTHING (all commits merged)
2. `git fsck --unreachable | grep commit` — no dangling ticket/fix commits
3. `pytest -q` on merged master — ALL tests must pass
4. `git worktree list` + `git stash list` — no stray unmerged work

**CONDITIONAL — only fires when parallel dev happened:**

The merge-verify node fires via a conditional edge from close:
```
edge: close → merge-verify, condition: "${nodes.plan.output.task_count} > 1"
```

Single-task tickets (task_count <= 1) skip merge-verify entirely — close is terminal. This uses the workflow engine's edge condition evaluation on node outputs. The condition expression `${nodes.plan.output.task_count} > 1` is a valid atom: `${var} > <value>` with numeric coercion.

**Why conditional:** when tech-lead decomposes a ticket into a single task, there's only one branch — no parallel fan-out, no merge complexity, close handles it. Multi-task means parallel dev cards wrote to separate branches that need reconciliation — that's where the merge gap bites.

## Reconciliation Gate (Layer 3)

Before declaring "project done," assert:

```
1. Every ticket branch: git log master..<branch> == empty
   (branch fully merged into master)
2. git fsck shows no dangling feat:/fix: commits
   (no destroyed commits)
```

This single check would have caught ALL the Todo CLI failures. Belongs in dev-dispatch (the workflow that orchestrates all tickets), not tech-lead-execute (which handles one ticket at a time).

## Enforcement Hierarchy

1. **Git hooks** (strongest) — pre-rebase hook rejects rebases on `ticket-*` branches
2. **merge-verify node** — separate verifier mechanically checks git state after close
3. **Close node body** — explicit merge + test + verify-nothing-lost steps
4. **Plan node body** — forbids git rebase/reset (weakest — body text)
5. **Body text** (weakest) — "do NOT run git rebase" — can be ignored by LLM

Current state: layers 2-4 applied. Layer 1 (git hooks) and reconciliation gate planned.
