---
name: board-quality-audit
description: "Score a completed kanban board's pipeline quality across five dimensions — code quality, test quality, decomposition, verify accuracy, and fix effectiveness. Works for any deliverable type: CLI tools, games, REST APIs, libraries, validators. Load when asked to 'deep-analyze', 'audit', 'score', 'review the board', 'evaluate the pipeline', 'were the findings real?', 'what's still open?', or to grade how well a build-from-spec run actually went. Knows how to locate the real code (workspaces, not the stub repo), mine verify→fix→re-verify evidence from task_comments, trace the FAIL→ESCALATE→PASS arc across multi-iteration loops, mutation-test coverage claims, and independently re-probe findings rather than trusting self-reported verdicts."
---

# Board Quality Audit

Score a finished kanban board end-to-end: did the pipeline actually produce a
working artifact backed by real evidence, or did it go through the motions?
This skill is the methodology — the concrete probes and DB queries live in
[`references/board-deep-analysis.md`](references/board-deep-analysis.md), and
the reusable REST API break-it probe lives in
[`scripts/rest-api-breakit.py`](scripts/rest-api-breakit.py).

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
- **Score behavior tests for black-box quality.** When the verifier wrote
  behavior tests (`test_behavior.py`), read the actual file and score 0-10:
  0 = pure white-box (tests private methods, internal data structures, regex
  patterns — breaks on any refactor); 10 = pure black-box (tests only through
  the public interface — CLI stdout/exit, HTTP status/body, public function
  return values — survives any refactor). Common white-box leaks to check:
  (a) accessing module constants for assertions (`module.SYMBOLS`, `module.WORDS`);
  (b) calling underscore-prefixed private methods (`_prompt_guess`);
  (c) `patch.object(module, "time")` mocking implementation dependencies;
  (d) AST/source-file scans for static contract checks (acceptable — tests
  declared requirements, not internals);
  (e) checking file existence as a proxy for coverage. Use the grep techniques
  in [`references/board-deep-analysis.md`](references/board-deep-analysis.md)
  §7a (REST) and §10b (library) to mechanically verify.
- Cite: pass count, which ACs have dedicated tests, any gaps, the black-box
  score with specific white-box patterns found (if any).

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
- **Check for verifier test-editing (a distinct integrity issue).** A verifier
  whose own behavior test FAILS may rewrite the test to pass (e.g.
  `test_X_raises` → `test_X_handled_gracefully`) rather than filing the finding
  OR honestly dismissing it as a probe-inversion. This is different from
  probe-inversion: the test wasn't *wrong*, the bar was *lowered*. Trace the
  verifier's test-file edits in `logs/t_<verify-task-id>.log` — look for patch
  diffs on the behavior test file. If an N/N clean-sweep was achieved by
  relaxing a failing test, note the original expectation vs the relaxed one and
  score accordingly. See §10 in the reference file.
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
- **Zero-rework boards: dimension 5 is N/A, not 0.** When verify stamps PASS on
  iteration 1 with no `[fix]` or `[re-verify]` card, there are no fixes to be
  effective. Score the four real dimensions and note the clean first-pass as a
  positive signal. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §10.

## The imperative: never trust, always re-probe

A verifier's self-reported evidence can be stale, misattributed, or fabricated.
The whole point of this skill is independent reproduction. Three things you
must re-run yourself:

1. **The test suite** — compare your pass count to the verifier's claim.
   **Reconcile the numbers, don't echo them.** A brief saying "73/73" and a
   dev suite of 114 and a verifier claiming "202" can all be *simultaneously
   true* because they count different things. Know the three layers and where
   each file lives: (a) **dev suite** in the dev workspace; (b) **verifier
   Layer-1 adversarial suite** written to `/tmp/hermes-verify-<task-id>/` (may
   be reaped on completion — recover from `logs/t_<verify-id>.log`); (c)
   **verifier Layer-2 behavior suite** — a separate file the verifier authored,
   often `test_behavior.py`, testing through the public API. Run each
   independently AND combined; confirm the combined count matches the
   verifier's claim. For REST API boards, also confirm the tests are genuinely
   black-box (HTTP-level, not implementation tests) via the grep technique in
   [`references/board-deep-analysis.md`](references/board-deep-analysis.md)
   §7a. For library boards, see §10 for the library black-box equivalent.
   **Watch for padding:** a trivial `assert True` test file inflating the dev
   count by 1 is a test-quality yellow flag.
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
- **GC'd workspaces — recover from the trace ledger.** When BOTH the repo and
  `workspaces/` are empty, reconstruct the code from the harness trace JSONL
  (`~/projects/<slug>/traces/<task>/attempt-N.jsonl`) by extracting
  `toolCall.arguments.content` from `write` calls. Validate faithfulness by
  re-running the dev suite on the reconstruction. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §1b.
- **Empty `result` column.** Findings/fixes live in `task_comments`, not
  `result`. Query comments ordered by `created_at`.
- **Per-task verify false PASS.** A per-task verifier can stamp PASS while its
  own probe workers flagged a defect. Check whether integration verify caught
  what per-task verify missed.
- **"Unbeatable" without exhaustive proof.** Only a full game-tree count is
  acceptable evidence. A few played games prove nothing.
- **Claimed behavior-test files may be deleted.** A verifier's
  "52/52 behavior tests" file can be GC'd with its scratch workspace. Don't
  fake a recount; score on metadata consistency + dev-suite mutation tests, and
  state the limitation. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §3e.
- **Missing task_links edge.** A `kanban_chains` dispatch can omit the
  verifier→tech-lead link, causing premature promotion. Before trusting that a
  "blocked" card actually waited, check
  `SELECT parent_id || ' -> ' || child_id FROM task_links`.
- **Reaped scratch workspaces lose the verifier's test files.** Scratch
  (`workspace_kind='scratch'`) task dirs are deleted when the task reaches
  `done`. The verifier's `test_behavior.py` or adversarial suite often lived
  there and is now gone from disk. **Recover it from
  `logs/t_<verify-task-id>.log`** — the full session transcript (test file
  contents via `cat`/`write` tool output, patch diffs, pytest output) is
  preserved there. `grep -n "def test\|PYEOF\|passed\|failed" logs/t_<id>.log`
  to find the test bodies and counts.
- **"Merged" can be nominal, not real.** A close card may stamp verdict=merged
  while the code was never actually merged to the seed repo — it lives only in
  scratch workspaces. Check the repo at the original path (`git ls-files`); if
  it's still just `.gitignore` + README, the "merge" was nominal. The close
  card body often admits this ("no git merge target; deliverable is the
  validated library in the developer's workspace"). Note it in the
  decomposition score, not code quality.
- **Vacuous tests pass green but test the wrong function.** A test named
  `test_to_fahrenheit_case_insensitive` that calls `to_celsius()` inside passes
  vacuously — it never exercises the named function. These inflate the green
  count while proving nothing about the named behavior. Grep for copy-paste
  mismatches between test-name verbs and the function actually called in the
  body. (The implementation may still be correct — independently verify rather
  than assume the test proves it.)
