---
name: board-quality-audit
description: "Score a completed kanban board's pipeline quality across five dimensions — code quality, test quality, decomposition, verify accuracy, and fix effectiveness. Works for any deliverable type: CLI tools, games, REST APIs, libraries, validators. Load when asked to 'deep-analyze', 'audit', 'score', 'review the board', 'evaluate the pipeline', 'were the findings real?', 'what's still open?', or to grade how well a build-from-spec run actually went. Knows how to locate the real code (workspaces, not the stub repo), mine verify→fix→re-verify evidence from task_comments, trace the FAIL→ESCALATE→PASS arc across multi-iteration loops, mutation-test coverage claims, and independently re-probe findings rather than trusting self-reported verdicts."
---

# Board Quality Audit

Score a finished kanban board end-to-end: did the pipeline actually produce a
working artifact backed by real evidence, or did it go through the motions?
This skill is the methodology — the concrete probes and DB queries live in
[`references/board-deep-analysis.md`](references/board-deep-analysis.md).

## When to load

- User says "deep-analyze board X", "score the board", "audit the pipeline",
  "review how livetest-N went", "evaluate the build quality".
- You are the gauntlet's Step-5 analyst grading a competing template run
  (see `template-ab-testing`).
- You need to compare two boards' quality head-to-head.

## The five scoring dimensions

Every board audit scores 0–10 on each, with cited evidence. Do not score from
memory or from the task `result` column — the result column is frequently empty.
The real evidence is in `task_comments`, the workspaces dir, and git history.

### 1. Code quality — does it work? Is the core algorithm correct?

- **Play it.** Pipe stdin into the entrypoint and confirm it renders, accepts
  input, and exits cleanly (rc=0).
- **Verify the critical algorithm independently.** If the spec claims
  "unbeatable", write your own exhaustive game-tree explorer and count terminal
  leaves by outcome. Spot-checking a few games is not proof — only an exhaustive
  count is.
- Cite: the entrypoint command, the piped-game output, your adversarial probe
  result (leaf counts).

### 2. Test quality — coverage of the right things

- Re-run the suite yourself: `cd <workspace> && .venv/bin/pytest -v`.
- Check that tests cover: core board/model logic, all win-detection cases,
  the critical property (e.g. unbeatable), input validation edge cases.
- Cite: pass count, which ACs have dedicated tests, any gaps.

### 3. Decomposition — task count, AC quality, dependency ordering

- Read `task_links` for the dependency tree. Confirm dev beads are ordered
  correctly (foundation → algorithm → integration → verify).
- Check AC count and specificity per dev bead. Good ACs are testable assertions,
  not vague goals.
- Cite: total card count, the tree, AC examples.

### 4. Verify accuracy — did verify find real findings? Were they true positives?

- Mine `task_comments` on the `[verify]` and `[re-verify]` cards for the actual
  finding text. Confirm each finding is real by reproducing it.
- For **test-coverage claims** ("mutation X passes undetected"), apply the
  mutation yourself via Python and run the tests — see mutation-testing recipe
  in [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §3d.
- **Check for false positives (probe-inversion).** A verifier may flag a
  behavior as a bug when it actually satisfies the contract. Example: flagging
  `(False, "empty input")` for non-str as a bug, when the spec mandates exactly
  that return shape. Read the spec card before counting a finding as real.
- Did the per-task verify stamp PASS while missing a bug the integration verify
  caught? Call out the layered-verify win (or the miss).
- Cite: the finding (comment id, body excerpt), your reproduction, and whether
  it's a true positive or false positive.

### 5. Fix effectiveness — did the fixes resolve the findings? What's still open?

- `git show <fix-commit> -- <file>` to confirm the diff is real and minimal.
- Re-feed the same pathological input the verifier flagged and confirm it no
  longer crashes / now returns the correct result.
- Confirm regression tests were added for the fix.
- **Trace the FAIL→ESCALATE→PASS arc.** Multi-iteration boards (3-4 verify
  loops) may ESCALATE at the iteration cap, then resolve via a tech-lead-
  authorized fix. Don't stop at the first ESCALATE — read the escalation card
  and the final re-verify verdict. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §4.
- **Classify remaining findings:** fixed-and-verified, deferred-by-tech-lead
  (documented accepted risk), open (unaddressed, still reproduces), or
  false-positive (probe-inversion). The "still open" list is the most actionable
  output for the user.
- Cite: fix commit SHA, the diff, the regression test names, re-verify verdict,
  and the deferred/open finding IDs with severities.

## The imperative: never trust, always re-probe

A verifier's self-reported evidence can be stale, misattributed, or fabricated.
The whole point of this skill is independent reproduction. Three things you
must re-run yourself:

1. **The test suite** — compare your pass count to the verifier's claim.
2. **An adversarial probe for the critical property** — write your own, don't
   reuse the verifier's test. Matching the verifier's reported counts exactly
   (e.g. 569 leaves, 0 losses) is powerful corroborating evidence.
3. **The fix** — git-diff the commit, then trigger the originally-failing input.

## Report format

A summary table of the five scores, each with 1–2 sentences of justification
and inline evidence (file:line, commit SHA, test count). Followed by a short
overall verdict. See [`references/board-deep-analysis.md`](references/board-deep-analysis.md)
for the concrete DB queries, code-location technique, and a worked example.

## Pitfalls

- **Stub repo trap.** The `/tmp/` repo path is often a bare `.git` + README.
  The real code is in the board's `workspaces/` directory — find it via the
  `workspace_path` column on the tasks table. Never conclude "no code produced"
  without checking workspaces.
- **Empty `result` column.** Findings/fixes live in `task_comments`, not
  `result`. Query comments ordered by `created_at`.
- **Per-task verify false PASS.** A per-task verifier can stamp PASS while its
  own probe workers flagged a defect. Check whether integration verify caught
  what per-task verify missed.
- **"Unbeatable" without exhaustive proof.** Only a full game-tree count is
  acceptable evidence. A few played games prove nothing.
