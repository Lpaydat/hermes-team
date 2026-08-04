---
name: board-quality-audit
description: "Score a completed kanban board's pipeline quality across five dimensions — code quality, test quality, decomposition, verify accuracy, and fix effectiveness. Works for any deliverable type: CLI tools, games, REST APIs, libraries, validators. Load when asked to 'deep-analyze', 'audit', 'score', 'review the board', 'evaluate the pipeline', 'were the findings real?', 'what's still open?', or to grade how well a build-from-spec run actually went. Knows how to locate the real code (workspaces, not the stub repo), mine verify→fix→re-verify evidence from task_comments, trace the FAIL→ESCALATE→PASS arc across multi-iteration loops, mutation-test coverage claims, and independently re-probe findings rather than trusting self-reported verdicts."
---

# Board Quality Audit

Score a finished kanban board end-to-end: did the pipeline actually produce a
working artifact backed by real evidence, or did it go through the motions?
This skill is the methodology — the concrete probes and DB queries live in
[`references/board-deep-analysis.md`](references/board-deep-analysis.md), the
reusable REST API break-it probe lives in
[`scripts/rest-api-breakit.py`](scripts/rest-api-breakit.py), the reusable
the reusable CLI/log-tool break-it probe (delimiter injection, SIGINT handling, corrupt
state files) lives in [`scripts/cli-breakit.py`](scripts/cli-breakit.py),
the reusable library/codec break-it probe (oracle cross-check, round-trip
matrix, purity check, streaming chunk stress) lives in
[`scripts/library-breakit.py`](scripts/library-breakit.py), and
the reusable CRUD-resource-REST-API break-it probe (validation, filtering,
sorting, aggregation, lifecycle, delimiter injection, concurrency, production
mode) lives in
[`scripts/rest-api-crud-breakit.py`](scripts/rest-api-crud-breakit.py) —
use this one for Expense-Tracker / Todo / Inventory class specs rather than
the KV-store/TTL `rest-api-breakit.py`, and the reusable markup/text-transform
break-it probe (XSS injection in text/URLs/link-text, escape-ordering,
double-escape, inline-formatting leakage into code blocks, CRLF leakage) lives
in [`scripts/markup-breakit.py`](scripts/markup-breakit.py).

## When to load

- User says "deep-analyze board X", "score the board", "audit the pipeline",
  "review how livetest-N went", "evaluate the build quality".
- You are the gauntlet's Step-5 analyst grading a competing template run
  (see `template-ab-testing`).
- You need to compare two boards' quality head-to-head.
- You are auditing **decomposition/planning quality** across one or more boards
  (does this template under-decompose?, score the plan cards, compare the
  decomposition across these 3 specs, did loop_engine actually iterate?).
  This is a planning-quality audit (coverage/atomicity/AC/dependencies/right-sizing
  + convergence-loop impact), distinct from the execution-quality audit below —
  see [`references/decomposition-audit.md`](references/decomposition-audit.md).

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
- **Adversarial break-it probes — write your own, don't reuse the verifier's.**
  The four dimensions most likely to survive both dev and verify suites (load
  [`scripts/cli-breakit.py`](scripts/cli-breakit.py) for CLI tools,
  [`scripts/rest-api-breakit.py`](scripts/rest-api-breakit.py) for REST APIs,
  [`scripts/library-breakit.py`](scripts/library-breakit.py) for
  libraries/codecs,
  [`scripts/markup-breakit.py`](scripts/markup-breakit.py) for markup/text-transform
  specs like Markdown→HTML):
  1. **Delimiter injection** (CLI/log tools): a user-provided string field that
     collides with the output format's separator (tab, comma, newline). A task
     name containing `\t` corrupts a 4-field tab-separated log into 5 fields.
     This is the bug that most commonly slips past both dev and verify because
     testers check quotes and spaces but rarely the actual delimiter character.
  2. **Signal handling + partial side effects** (long-running CLIs/servers):
     SIGINT must exit cleanly (rc 0 or 130, no traceback) AND leave no partial
     side effect — a half-written log entry, a dangling lock, an unflushed
     buffer. Use `subprocess.Popen` + `send_signal(SIGINT)`, then check the
     state dir for partial writes.
  3. **Corrupt/empty input files**: read commands on missing, empty, or
     malformed state files. Whether a corrupt-JSONL crash is a contract FAIL
     or a robustness NOTE depends on whether the contract guarantees tolerance
     of externally-corrupted input (usually it only guarantees the app *writes*
     valid data).
  - **Production-mode testing**: spin up a real server
    (`app.run(host='127.0.0.1', port=<free>, debug=False, use_reloader=False)`
    in a daemon thread) and hit it with `urllib.request` / `httpx` — NOT the
    Flask test_client, NOT with `TESTING=True`. A verifier claim of
    "production mode tested: true" is corroborating evidence; reproduce it
    yourself because test_client and conftest fixtures mask deployment bugs
    (Werkzeug vs production WSGI server behaviour, reloader double-execution,
    debug-mode HTML error pages). The reusable harness is
    `probe_production_mode()` in
    [`scripts/rest-api-crud-breakit.py`](scripts/rest-api-crud-breakit.py).
  4. **Boundary arg values**: zero-length timers (`--work 0`), negative counts
     (`--cycles -1`), non-numeric args — these hit the `range()` off-by-one
     and argparse-validation gaps that injected-function unit tests miss.
- Cite: the entrypoint command, the piped-game output, your adversarial probe
  results (leaf counts, field counts, signal exit codes).

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

Read `task_links` for the dependency tree. Confirm dev beads are ordered
correctly (foundation → algorithm → integration → verify). Then score the
decomposition on five sub-dimensions (0-10 each), each with cited evidence:

- **Spec coverage** — does every spec requirement have a task? Enumerate the
  spec's numbered requirements and map each to a dev card. List any gaps. This
  is the floor: a plan that drops a requirement scores badly regardless of the
  other four.
- **Task atomicity** — are tasks small enough for a junior dev (5-8 ACs,
  one coherent responsibility), or are multiple separable concerns crammed into
  one card? A card bundling N distinct subsystems (e.g. an alignment engine +
  an escaping engine + an error handler + the test suite) is under-decomposed.
  Decompose by *concern*, not by output artifact: a single file with separable
  layers (engine / I-O / tests) should still become 2-3 cards.
- **AC quality** — are ACs testable assertions with exact expected values /
  exit codes / output strings, or vague goals? "Pipe escapes to `\|`" is good;
  "handles escaping" is bad. The strongest ACs pin numeric or string outputs.
- **Dependency structure** — are serial/parallel dependencies correct? Verify
  the `task_links` graph actually encodes the claimed ordering. Watch for
  `kanban_chains` topology bugs (see pitfalls below): a parallel verify edge
  left behind after a manual serial-fix, or a missing verifier→tech-lead link
  causing premature promotion. Check the plan-card comments for the tech-lead's
  own dispatch-failure confessions.
- **Right-sizing** — is the dev-card count appropriate for spec complexity?
  Rule of thumb: 1 dev card per 2-4 spec requirements, more for specs with many
  separable sub-domains. A single card for a 9-10 requirement spec with distinct
  sub-domains is almost always under-decomposed.

**Under-decomposition's tell:** the verifier card has to invent edge cases the
dev card omitted (reverse conversions, boundary counts, fallback rules). When
the dev AC checklist is missing cases the spec implies and the verifier
supplies them, the single dev card was too coarse to specify tightly.

Cite: total card count, the dependency tree, AC examples, and the per-card AC
count.

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
- **Forensic re-read of the verifier's own test file for false-confidence.**
  A verifier can report `score=1.0, gaps=[]` with N/N green tests and STILL
  have missed a bug class — because its tests *claimed* coverage they never
  *exercised*. The three tell-tale patterns: (1) happy-path lock-in (every
  format assertion uses the spec's literal example string, never hostile
  input); (2) docstring-vs-input mismatch (docstring says "tabs, quotes" but
  the test body only injects quotes); (3) no negative/stress oracle on the
  format dimension. These are NOT caught by re-running the suite (it stays
  green) — they require reading the test inputs and checking whether any test
  ever injects the output delimiter into a user-supplied field. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §18
  for the detection technique + worked example (tab-injection surviving two
  verifier suites).
- **For the two-phase "Attack Your Own Tests" verify body (newer integration
verify prompt), check whether Phase 2 actually executed.** This body asks the
verifier to first write a behavior-test matrix (Phase 1), then re-read every
test, find gaps, and write ADDITIONAL attack tests (Phase 2). Phase 2 now uses
4 PRINCIPLES (honesty check, adversarial thinking, independence, completeness)
rather than a specific checklist — see gauntlet-lessons #38. The five
evidence signals that Phase 2 genuinely ran: (a) two physically distinct
files (`test_behavior.py` + `test_attack.py`); (b) the attack file has a
higher count AND tests different things (the verifier reasoned about what
THIS code is vulnerable to); (c) `attack_categories_covered` in the run
metadata; (d) a self-caught probe-inversion (strongest signal — the verifier
admits its own test was wrong); (e) coverage of gaps the verifier identified
through adversarial reasoning rather than following a fixed checklist. See
[`references/two-phase-verify-forensics.md`](references/two-phase-verify-forensics.md)
§19 for the full detection technique, the 5-signal checklist, and a worked
example (Markdown→HTML board where all five signals were present).
- **Self-caught probe-inversions are a POSITIVE verify-integrity signal, not a
  defect.** When the verdict metadata records `probe_inversions_caught_and_fixed: N`
  with a detail string, the verifier genuinely re-read its own tests, found one
  was wrong, and corrected the assertion rather than filing a false positive or
  silently relaxing the bar. A verifier that NEVER reports a single self-caught
  error across a large adversarial suite is suspicious; one that reports and
  correctly dismisses 1-2 probe-inversions has higher epistemic integrity. Do
  not score this as a defect — score verify-accuracy UP for it.
- **Detect dual-track boards and run the method head-to-head.** When a board
  has BOTH a static-review track (`[probe] static review`, `[probe]
  fresh-eyes`) AND a principle-based behavior track (`[verify-b]` integration
  with a Phase-2 "attack your own tests" body), build the comparison table:
  for every bug on the board, mark which track found it. Bugs in only one
  column are the audit headline. The robust pattern observed across boards:
  principle-based behavior verify catches I/O crash bugs (unhandled exception
  on NUL byte, bad UTF-8, broken pipe, ENOSPC, closed fd) that static review
  structurally cannot — static review reads what the code *says*, behavior
  verify discovers what it *does* under inputs the author never imagined.
  Static review wins on readable-logic bugs (a missing quote-escape visible in
  a regex). See
  [`references/verify-method-comparison.md`](references/verify-method-comparison.md)
  for the detection query, the comparison-table methodology, and a worked
  example (5 I/O crash bugs all missed by static review, all caught by
  principle-based behavior verify).
- **Read the multi-iteration re-verify chain as escalation evidence, not
  verifier failure.** When `[verify-b] FAIL → fix → re-verify FAIL → …` runs
  3-6 iterations, each iteration typically finds a NEW real bug (the
  "whack-a-mole" I/O pattern: each fix guards one path, leaving the next
  unguarded). This is the verifier working correctly. Score verify-accuracy
  UP for sustained finding of true positives; score fix-effectiveness on
  whether the final holistic fix (usually a tech-lead escalation card) closed
  the systemic root cause in one pass. The tech-lead's I/O-surface matrix
  (every path + its guard status) is the convergence evidence.
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
- **On zero-rework boards, score "Overall robustness" as the substitute fifth
  dimension.** When fix-effectiveness is N/A (no fixes happened), the operative
  fifth dimension is *independent break-it*: throw your own adversarial inputs
  at the public interface across ALL spec dimensions at once (range boundaries,
  invalid sequences, type confusion, empty/null/whitespace, very-long strings,
  mixed case, CLI edge args) rather than probing one dimension at a time. This
  is where the auditor adds the most marginal value on a clean board — the code
  and verify suites are already green, so the only new signal is whether *you*
  can find something they both missed. Score it on whether the code handles
  every thrown input by either returning the correct value or raising a caught
  exception (no unhandled traceback within the documented type contract).
  Document any spec-permitted-but-debatable quirks found (e.g. `to_roman('007')`
  → VII via int parsing) as notes, not deductions.

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

For **planning/decomposition-only audits** (no execution evidence to probe —
score the plan cards and dev-card bodies against the spec, not the shipped
code), the 5-sub-dimension decomposition rubric, the convergence-loop impact
analysis, a cross-spec A/B comparison methodology, the **critic-impact**
dimension (for self-grill / critic-decomp templates), and
**dispatch-artifact detection** (PROBE-ONLY-DELETE cards, double-dispatch
chains) live in [`references/decomposition-audit.md`](references/decomposition-audit.md).
The critic-impact dimension (§4 there) scores whether the critic actually
found real issues and whether the dispatch honored the revision — score it
only for critic variants. Dispatch-artifact detection (§5 there) catches
`kanban_chains` probe leakage and abandoned first-attempt chains.

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
- **GC'd workspaces — the integration verifier's scratch copy survives.** When
  the shared workspace AND per-task workspaces are all reaped, there is a THIRD
  recovery path: the `[verify-b]` (integration verify) card often wrote its own
  copy of the SUT + all tests to `/tmp/hermes-verify-<slug>/` (or
  `/tmp/hermes-verify-<task-id>/`). Because that scratch dir lives in `/tmp`,
  NOT under the board's `workspaces/`, it is outside the board's post-completion
  cleanup lifecycle and frequently still exists. The close-card body usually
  names the surviving path ("surviving canonical copy at
  `/tmp/hermes-verify-b64/`"). `grep -rh "hermes-verify" logs/ | sort -u` lists
  every scratch path any worker used. This is faster and more faithful than
  reconstructing from the trace JSONL — read the close card FIRST for the path.
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
- **`kanban_chains` matrix-root cards inflate dev-card counts.** A
  `kanban_chains` dispatch creates a root blackboard card (body starts
  "Matrix root / shared blackboard", assignee is the dev profile) that is NOT a
  real dev task. Counting dev cards with `assignee='developer'` includes it.
  Filter on `title LIKE '[task]%'` (real dev cards) or exclude
  `body LIKE 'Matrix root%'` to get the true count. A brief saying "4 dev
  cards" may actually mean 3 dev cards + 1 root — reconcile before scoring
  right-sizing.
- **Plan-card comments are a first-class evidence source for dispatch failures.**
  The tech-lead's `[tl] Plan:` card often carries a comment confessing a
  `kanban_chains` misuse that was hand-recovered: a `block_verified=false`
  state race, parallel verify chains created when serial was needed, a manually
  re-added verifier→tech-lead link. Query it:
  `SELECT body FROM task_comments c JOIN tasks t ON t.id=c.task_id WHERE t.title LIKE '[tl] Plan%';`
  A confessed manual recovery is a dependency-structure yellow flag even if the
  final `task_links` graph looks correct — the stale wrong edge may still be
  present (e.g. a root→verify parallel edge left after the serial fix).
- **Partial dispatch trap (plan says N tasks, only M dispatched).** A tech-lead
  plan can enumerate N converged leaf tasks in its comments but only dispatch
  M < N of them via `kanban_chains`. The plan card is stuck in `running` (never
  reached `done`) because Phase 3 didn't complete. This is a **spec-coverage**
  failure, not a code failure. Cross-check the converged task count named in
  the plan comment against `SELECT id FROM tasks WHERE title LIKE '[task]%'`.
  The delta = dropped requirements. Observed on a loop_engine board where 2 of
  3 converged tasks (spec reqs #5 and #6) had no dev card at all.
- **Convergence-loop metadata lives in comments, not the result/metadata field.**
  For loop_engine / iterative-decomposition templates,
  `decomposition_iterations`, `sizing_summary`, and `task_ids` are logged in
  the plan card's `task_comments` — NOT in `result` or kanban_complete
  `metadata` (the plan card may never reach `done`). Always mine comments for
  convergence evidence; do not trust an empty `result` to mean no convergence
  happened. See
  [`references/decomposition-audit.md`](references/decomposition-audit.md) §6-7
  for the full planning-quality / decomposition audit methodology and worked
  examples across decomposition variants.
- **loop_engine's `loop_state` blackboard is the authoritative per-phase
  evidence source.** For loop_engine boards, the root loop card (assignee =
  the loop profile, e.g. `livetest-unbias-3`) carries a series of
  `[swarm:blackboard]` comments with key `loop_state`. Each comment is a full
  JSON snapshot at a phase transition: `phase_index`, `iteration_counter`,
  `execution_card`, `verifier_card`, `terminal_ids`, `max_iterations`,
  `no_progress_streak`, and the entire `phases[]` array with each phase's
  execution/verifier contract + ACs. This is *better* than mining plan-card
  comments — it gives you the exact iteration count per phase, the dev↔verify
  card pairing, and the convergence state machine, all in one query. See
  [`references/board-deep-analysis.md`](references/board-deep-analysis.md) §16
  for the query and a worked example. Read it FIRST on any loop_engine board —
  it tells you how many phases, how many iterations each took, and which cards
  to pull before you look at anything else.
- **Verification probe-swarm fan-out inflates card counts on loop_engine
  boards.** When a verify card returns FAIL, loop_engine re-dispatches a fresh
  dev card AND spawns a 3-way parallel probe swarm: fresh-eyes AC verification
  + static review + delta-check-vs-iter-1, each as a separate `[probe]` card.
  On a 5-phase board with 4 failed-first-attempt phases, this produces ~30
  probe cards on top of ~16 core dev/verify cards. When scoring right-sizing,
  **separate ceremony cost (probe swarms, matrix-root anchors, wrapper cards)
  from dev decomposition (the phase plan itself).** A 46-card board for a
  120-line tool looks over-decomposed by raw count, but if only 16 cards are
  real dev/verify work, the *decomposition* may be right-sized while the
  *verification topology* is heavy. Score them as two separate observations:
  "the 5-phase plan was correctly sized; the 3-way probe fan-out per failed
  iteration was the card-count driver." Query to separate them:
 `SELECT title, count(*) FROM tasks GROUP BY substr(title,1,15)` — `[task]`/
 `[verify]` are core; `[probe]`/`Matrix root`/`verify t_` are ceremony.
 - **The integration verifier's behavior test file often survives in
 `attachments/`.** When the verifier passes `kanban_complete(artifacts=[...])`,
 the file is copied into the board's `attachments/<verify-task-id>/`
 directory, which is OUTSIDE the per-task workspace cleanup lifecycle. So even
 after every `workspaces/` dir is reaped, the `test_behavior.py` (the most
 valuable artifact for your forensic re-read) is recoverable via
 `ls attachments/t_<verify-id>/` or
 `SELECT filename FROM task_attachments WHERE task_id='<verify-id>'`.
 This is the FOURTH recovery path (after: workspaces dir, trace JSONL, /tmp
 scratch dir). Read it BEFORE reconstructing from logs — it's the original
 file, not a transcript reconstruction.
- **Delimiter injection is the most-missed CLI/log bug.** When the spec defines
  a delimited output format (tab-separated, CSV, pipe-separated), a user string
  field containing the delimiter character corrupts the column structure.
  Verifiers reliably test quotes and spaces but almost never test the actual
  separator byte. A `--task "a\tb"` on a tab-separated log line silently
  produces 5 fields instead of 4. Always probe with the literal separator
  character in every user-supplied string field — this bug class has survived
  two independent verifier suites on a clean board. See
  [`scripts/cli-breakit.py`](scripts/cli-breakit.py) probe 5.
- **Mutation testing by the verifier is the strongest verify-accuracy signal.** A
  verifier that not only writes behavior tests but then *deliberately breaks
  the code* (revert the symlink guard → crash returns; restore → green; break
  `n+=1` → hardcoded `_1` → data loss) and confirms its tests catch the
  mutation has proven its tests are load-bearing, not vacuous. Look for
  "mutation" in verifier run summaries (`SELECT task_id, summary FROM
  task_runs WHERE profile='verifier' AND summary LIKE '%mutation%'`). A board
  where verifiers ran mutations AND caught them is a 9-10 on verify accuracy
  even if some individual probes missed edge cases — the mutation loop is the
  integrity guarantee. Cross-check: if the verifier claims "3/3 mutations
  caught" but you can't find the mutation in the logs, the claim is unverified.
- **"Implement from scratch, no stdlib X" specs need a dedicated purity probe.**
  When a spec mandates a pure-Python (or otherwise forbidden-dependency-free)
  reimplementation of a stdlib module (base64, json, csv, hashlib, urllib…),
  the purity constraint is a CRITICAL pass/fail gate that a self-reported
  "pure-python confirmed" verdict can lie about or stale out on. Verify it
  yourself with two layered checks: (1) on-disk grep —
  `grep -rn "import base64\|from base64" <sut-dir>/` (exit 1 = clean); (2)
  in-memory source scan — `inspect.getsource(<sut-module>)` then assert
  neither `import <forbidden>` nor `from <forbidden>` is a substring. The
  second catches dynamic/exec'd imports the disk grep misses. The reusable
  probe is `probe_purity()` in
  [`scripts/library-breakit.py`](scripts/library-breakit.py) — adapt
  `FORBIDDEN_IMPORTS` to the spec. The oracle (stdlib `base64`, etc.) may be
  imported by YOUR probe and by the verifier's cross-check scripts, but never
  by the SUT itself — trace any `import base64 as _oracle` you find to confirm
  it lives in a `/tmp/hermes-verify-*` probe, not in `b64/`.
- **Markup/HTML-emitter specs need a dedicated XSS + escape-ordering probe.**
  For any spec whose output is HTML (Markdown→HTML, RST→HTML, BBCode, wiki
  markup), the #1 risk class is HTML injection in the INPUT that survives into
  the OUTPUT as a live tag (`<script>`, `<img onerror=>`). The critical
  invariant is **escape-before-format**: HTML-escape the raw text FIRST, then
  apply inline Markdown formatting (`**bold**` → `<strong>`). If the order is
  reversed, the generated `<strong>` tags get re-escaped to `&lt;strong&gt;`
  and the output is broken — OR worse, injected `<script>` survives because
  escaping ran on the wrong pass. Three distinct injection vectors to probe:
  (1) raw HTML in text content; (2) HTML in link URLs (attribute breakout via
  `"` in the URL, `javascript:` scheme); (3) HTML in link TEXT (renders inside
  the `<a>` anchor). Also check: double-escape in code blocks (`&` → `&amp;`
  once, not `&amp;amp;`), inline formatting leaking INTO fenced code blocks
  (should be verbatim), and CRLF leakage (`\r` surviving into `<p>` content
  because the parser splits only on `\n`). The reusable probe is
  [`scripts/markup-breakit.py`](scripts/markup-breakit.py) — adapt `MARKERS`
  and the feature flags to the spec's syntax.
- **CLI tools that write to stdout have a 5-path I/O exception surface — probe
  all 5.** Any tool that can `print()` or `sys.stdout.write()` has five
  distinct unhandled-exception paths that LLM-authored code routinely leaves
  unguarded: (1) **input read OSError** (file not found, permission denied,
  IsADirectoryError); (2) **input decode UnicodeDecodeError** (non-UTF-8 byte
  — NOT an OSError subclass, so a bare `except OSError` misses it); (3) **output
  `-o` write OSError** (full disk, nonexistent dir); (4) **stdout broken pipe**
  (`| head` closes early — must exit SILENTLY per Unix convention, empty stderr,
  NOT print `error:`); (5) **closed stdout `>&-`** (CPython sets
  `sys.stdout=None`, so `sys.stdout.write` raises `AttributeError`, NOT an
  OSError subclass — escapes both `except BrokenPipeError` and `except OSError`).
  Path (5) is the sneakiest: `AttributeError` is not in the OSError hierarchy at
  all. The correct guard is `if sys.stdout is None:` BEFORE the write, not
  `except AttributeError` (too broad — masks real bugs). This whack-a-mole
  pattern (each fix guards one exception type, leaving the next) survived 6
  verify iterations on a Markdown→HTML board. Probe all 5 yourself:
  `md2html.py x.md 2>&1 >/dev/full` (ENOSPC), `md2html.py x.md | head -1`
  (broken pipe), `md2html.py x.md >&-` (closed stdout). Each must produce a
  clean `error:` on stderr + exit 1 (or silent exit for broken pipe), NEVER a
  raw traceback.
