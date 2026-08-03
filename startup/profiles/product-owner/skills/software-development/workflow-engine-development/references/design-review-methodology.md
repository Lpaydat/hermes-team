# Design Review Methodology — Iterative Multi-Reviewer Validation

> Distilled from the stateless graph engine design cycle (2026-08-02):
> 4 rounds, 10 reviewers total, v1 → v2 → v2.2. Started from a first-draft
> design doc, ended APPROVED (HIGH confidence) with zero remaining blockers.

## When to use this

Any complex engine design change: state model rewrites, new node types,
trigger system changes, concurrency model changes. Not for small template
additions or one-off fixes.

> **Companion:** `references/spec-vs-implementation-review.md` — the post-code
> phase. This methodology validates the design BEFORE code; that one verifies
> the diff matches the approved design AFTER code. Use both across a full
> design→implement→ship cycle.

## The core technique

Write a design doc, then run parallel focused subagent reviewers against it.
Each reviewer covers ONE concern area (concurrency, graph-walk, backcompat,
triggers, scope). Fix what they find, re-review. Repeat until all reviewers
say APPROVED.

### Round structure

**Round 1 — broad coverage (5 reviewers, 5 focus areas):**
- Concurrency / state correctness
- Algorithm correctness (graph walk, edge semantics)
- Backwards compatibility (tests, DB migration, completion model)
- Trigger / cross-workflow handoff correctness
- Scope completeness (did the design account for ALL the logic?)

**Round 2 — targeted re-review (3 reviewers on revised doc):**
Re-review ONLY the focus areas that found blockers in round 1. Each reviewer
checks whether their v1 findings were fixed, with specific verdicts (FIXED /
PARTIALLY FIXED / NOT FIXED / NEW ISSUE).

**Round 3+ — final approval (1 reviewer, full scan):**
Generalist reviewer confirms all blockers resolved, scans for remaining issues.

## Key lessons (hard-won)

### 1. A generalist final-reviewer misses bugs that focused reviewers catch

Round 3 (generalist) APPROVED the design with HIGH confidence. Round 2
(graph-walk specialist) had found a load-bearing bug in `node_phase()` that
the generalist missed entirely — the function wrote `skipped`/`failed` flags
but never read them, silently breaking skip propagation.

**Rule:** after a focused reviewer finds a bug in domain X, the re-review of
the fix MUST be done by a reviewer covering domain X — not a generalist doing
a "looks good" pass. The generalist doesn't trace function bodies line by line.

### 2. Scope review is the most important early round

The scope review ("did the design account for ALL the logic?") consistently
finds the biggest gap: the v1 design estimated ~1300 lines, the scope review
proved it was ~2500-3000. The design framed a status-model rewrite as
"removing status" when ~850 lines of dispatch/validation/card-mode logic was
orthogonal to status and had to be ported verbatim.

**Rule:** always include a scope-completeness reviewer who inventories every
method in the current code and checks each against the design doc's "what we
keep / rip / replace" lists.

### 3. Run reviewers in parallel batches (max 3 concurrent)

Dispatch reviewers in batches of 2-3 (the `delegate_task` limit). Each batch
runs concurrently and delivers a consolidated result when all complete.

### 4. Fix immediately, don't wait for all batches

When one batch delivers findings with blockers, start fixing immediately while
other batches run. The fixes are independent of the pending reviews.

### 5. Each revision gets a version number

Track design doc versions: v1 (first draft), v2 (after round 1 fixes), v2.1
(fixing round-2 blockers), v2.2 (fixing a bug found after round 3 approved).
The version history tells the next session exactly what was reviewed and when.

### 6. Commit review reports alongside the design

The REVIEW-*.md files are valuable artifacts — they document what was
considered, what was rejected, and why. Commit them to the same branch as the
design doc. A future session can read the reviews to understand the rationale
without re-deriving it.

## Concrete dispatch template

```
Round 1 (5 reviewers, 2 batches):
  Batch 1: concurrency + graph-walk + scope-completeness
  Batch 2: backcompat + triggers

Round 2 (2-3 reviewers on revised doc):
  Re-review each focus area that found blockers

Round 3 (1 reviewer):
  Final approval scan
```

Each reviewer receives:
- The design doc path (read IN FULL)
- The v1 review for their focus area (for context on what was broken)
- Specific questions to answer (not "is this good?" but "did the fix work?")
- Required output format: VERDICT + numbered findings with quotes

## What NOT to do

- **Don't skip the scope review.** It's the difference between a 1300-line
  estimate and a 2500-line reality.
- **Don't use a generalist for re-reviewing a specialist finding.** The
  generalist will miss the same class of bug the specialist found.
- **Don't claim "rock solid" after one round.** This cycle took 4 rounds and
  still found a critical bug in round 2 that round 3 missed.
- **Don't let reviewers guess at code.** Give them exact file paths and line
  numbers to read.
- **Don't report the same status twice without new progress.** The user's
  correction ("what? no progress?" / "even after 4hr?") is the signal:
  reporting stale status without taking action is worse than no report.
  Status reports are for MILESTONES, not for marking time between dispatches.
  When a subagent finishes and you commit its work, the NEXT action should be
  dispatching the next unblocked ticket — not reporting that the previous one
  completed. The user reads idle status reports as "you stopped working."
  This was the strongest user correction this session — treat it as a hard rule:
  if the last 3 messages all say variants of "waiting" or "status unchanged",
  you have failed. Act, don't report.

## Implementation workflow — from design to committed code

After the design is APPROVED, decompose into tracer-bullet tickets (use the
`to-tickets` skill), then dispatch implementation to subagents:

1. **Create a git worktree** from main: `git worktree add .worktrees/<branch> -b feat/<branch> main`.
   This isolates the work from the dirty main checkout.
2. **Check .gitignore coverage FIRST.** If the code lives under a gitignored path
   (e.g., `startup/scripts/` was not whitelisted), commit it to main first or
   the worktree will be empty. This cost a full debug cycle this session.
   **Specifically:** `git ls-files <path>` returns nothing for gitignored dirs.
   The `.gitignore` whitelist (`!startup/profiles/*/scripts/`) did NOT include
   `startup/scripts/` (the shared engine code location). Fix: add
   `!startup/scripts/` and `!startup/scripts/**` to .gitignore, exclude any
   runtime state DBs (`workflow_state.db`, `*.state.db`), commit to main, THEN
   create the worktree from that commit.
3. **Create beads** with `bd create` using `--deps parent-child:<epic>` and
   `--deps blocked-by:<dep>`. Verify dependencies resolve correctly.
4. **Dispatch ONE subagent per worktree at a time.** Parallel subagents on the
   same worktree cause DB lock contention, git index races, and file-level
   conflicts. If tickets touch DIFFERENT files, they CAN run concurrently, but
   the parent must serialize commits.
5. **Each subagent gets:** ticket spec + design doc path + exact acceptance
   criteria + workflow steps. Include "READ FIRST" pointing to specific files.
6. **When subagents hit the 50 tool-call limit**, they return partial work.
   The parent must: assess uncommitted changes, run tests, fix remaining
   failures, and commit in logical units (one commit per ticket).
7. **Close beads** with `bd close <id>` after each ticket is committed.
8. **Test triage:** categorize failures into (A) expected breaks from old query
   patterns, (B) message-format changes, (C) design-intended behavior changes.
   Only category A is mechanical; B and C need judgment.
