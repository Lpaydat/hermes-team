## 15. Planning-quality / decomposition audit (cross-board)

When the question is about **decomposition quality** — not whether the code
works, but whether the plan cards were any good — use this section. Typical
triggers: "score the plan cards", "compare decomposition across these 3 specs",
"did the template under-decompose?", "score Version B vs Version A", "did
loop_engine actually iterate?".

This is a **planning audit**, distinct from the execution audit in §1–14. The
six scoring dimensions below supersede the five execution dimensions when the
user is asking about the plan, not the product. You can run both (execution + 
planning) on the same board — they grade different things.

### a. The six planning dimensions (score each 0–10 with cited evidence)

| # | Dimension | What to check | Floor / red flag |
|---|-----------|---------------|------------------|
| 1 | **Spec coverage** | Enumerate the spec's numbered requirements. Map each to a dev card. List gaps. | A requirement with **no task** tanks this score regardless of the other five. |
| 2 | **Task atomicity** | Is each card junior-dev-one-sitting sized (one coherent responsibility, 5–8 ACs)? Or are separable concerns crammed into one card? | A card bundling N subsystems (engine + IO + tests) is under-decomposed. |
| 3 | **AC quality** | Are ACs testable assertions with exact expected values / exit codes / output strings? Or vague goals? | "Handles escaping" = bad. "Pipe `\|` escapes to `\|`" = good. |
| 4 | **Dependency structure** | Read `task_links`. Are serial/parallel deps correct? Does the graph encode the claimed ordering? | A convergence loop can design a correct parallel DAG that the dispatch tool flattens to serial. |
| 5 | **Right-sizing** | Is dev-card count appropriate for spec complexity? Rule of thumb: 1 card per 2–4 spec requirements. | One card for a 9–10 requirement spec with distinct sub-domains is almost always under-decomposed. |
| 6 | **Convergence-loop impact** *(only for loop_engine / iterative-decomposition templates)* | Did the loop actually iterate? Did it change the output vs a one-shot? Check `decomposition_iterations`. | `decomposition_iterations: 0` = one-shot, no loop benefit. >0 with no plan change = rubber-stamp. |

### b. DB queries for a decomposition audit

```sql
-- 1. Card inventory by type prefix (spot root-blackboard, plan, dev, verify, probe cards):
SELECT substr(title,1,30) AS t, status, assignee, count(*)
FROM tasks GROUP BY t ORDER BY t;

-- 2. The dependency DAG (confirm claimed serial/parallel ordering):
SELECT parent_id || ' -> ' || child_id FROM task_links ORDER BY parent_id;

-- 3. Plan-card convergence log (the loop_engine output lives HERE, not in result):
SELECT body FROM task_comments c
JOIN tasks t ON t.id = c.task_id
WHERE t.title LIKE '%[tl%Plan%' OR t.title LIKE '%Plan:%'
ORDER BY c.created_at;

-- 4. Spec coverage cross-check: which spec requirements have NO matching dev card?
--    Pull the spec card body, enumerate its numbered requirements, then grep dev bodies:
SELECT id, title FROM tasks
WHERE body LIKE '%<requirement-keyword>%' AND title LIKE '%[task]%';
```

### c. Convergence-loop impact analysis (dimension 6)

For templates that use a convergence loop (loop_engine, iterative refinement),
dimension 6 asks: **did the loop earn its cost?** Three checks:

1. **Did it iterate?** Find `decomposition_iterations: N` (or equivalent) in
   the plan card's comments. `N=0` means no loop ran — score the dimension as
   N/A (one-shot template, no convergence to evaluate).
2. **Did it change anything?** The convergence log records the initial coarse
   cut and each iteration's decisions (merge X, split Y, dissolve Z). Compare
   the initial task list to the final converged tree. A loop that ran 2
   iterations but produced the same tree as the initial cut is a rubber-stamp —
   low value.
3. **Did the changes improve quality?** A genuine convergence loop makes
   *substantive* decisions: merging a separate-tests ticket into vertical
   slices (to-tickets principle), collapsing an over-fragmented single-file
   tool into one card, folding a trivial function into its parent. Quote the
   specific decisions in the report.

**A/B comparison method:** when comparing a convergence template (Version B)
against a one-shot template (Version A) on identical specs, map the spec
requirements to dev cards on **both** sides. The convergence template wins if
it produces tighter per-task boundaries, explicit scope fences ("Do NOT
implement X yet"), or better atomicity. The one-shot wins if the convergence
template's dispatch was incomplete (see pitfall below).

### d. Pitfalls specific to decomposition / convergence audits

- **Partial dispatch trap.** A convergence loop can converge on an N-task plan
  but only dispatch M < N of them. The convergence log will say "3 leaf tasks:
  T1, T2, T3" but only T1 has a dev card. **Cross-check the converged task
  count against actual dispatched dev cards.** A plan card stuck in `running`
  (not `done`) is a signal that Phase-3 dispatch (kanban_chains) may be
  incomplete. Query: compare the task list named in the convergence comment
  against `SELECT id FROM tasks WHERE title LIKE '[task]%'`. The gap = dropped
  requirements.
- **Convergence metadata lives in comments, not the formal metadata field.**
  `decomposition_iterations`, `sizing_summary`, and `task_ids` are logged in
  the plan card's `task_comments` — NOT in the plan card's `result` column or
  kanban_complete `metadata` (because the plan card may never reach `done`).
  Always mine comments; do not trust an empty `result` to mean "no convergence
  happened."
- **Dispatch flattens parallel DAGs to serial.** A convergence loop can design
  a correct parallel DAG (e.g. L1 → L2 → {L3, L4, L5 in parallel}) but the
  dispatch tool (kanban_chains single-chain) serializes them (L3 → L4 → L5).
  This is a **dependency-structure** scoring penalty (efficiency loss), not a
  correctness error. Check the `task_links` graph against the DAG the
  convergence log claims.
- **Version comparison baseline.** When comparing template versions on
  identical specs, both sides must be scored on the same six dimensions. The
  one-shot side (Version A) will always score N/A on dimension 6 (no loop) —
  compare the other five, then note whether the convergence loop's gains on
  dimensions 1–5 outweigh its dispatch-reliability risk.

### e. Worked example — Version B (loop_engine) vs Version A, 3 specs

Three identical specs run through two templates: A (one-shot to-tickets) and
B (loop_engine convergence). Scored on the six planning dimensions:

| Board | Spec | Coverage | Atomicity | AC Quality | Deps | Right-size | Loop Impact | Avg |
|-------|------|----------|-----------|------------|------|------------|-------------|-----|
| B1 | Markdown Table | 9 | 9 | 9 | 9 | 9 | 8 | 8.8 |
| B2 | JSON Diff | 10 | 10 | 10 | 8 | 9 | 9 | 9.3 |
| B3 | Unit Converter | **4** | 8 | 8 | 5 | 5 | 5 | 5.8 |

**B1 (9.3 avg):** loop_engine ran 2 iterations. Initial cut = 5 tasks (by
layer: CLI / CSV / escaping / alignment / tests). Iter-1 merged because all
tasks edit the same single file → collapsed to 1 leaf. The loop *prevented*
over-fragmentation — a genuine improvement over a naive one-shot that would
keep the 5-task split.

**B2 (9.3 avg):** loop_engine ran 2 iterations. Initial cut = 8 tasks.
Iter-1 merged type-change into the diff engine and dissolved a standalone
tests ticket (to-tickets vertical-slice rule). Converged to 5 leaf tasks with
explicit scope fences ("Do NOT implement by-id / --format / --ignore yet").
vs Version A: A2 produced 3 coarser cards; B2's 5-card split is more atomic
with tighter per-task boundaries. **B2 clearly outperforms A2.**

**B3 (5.8 avg):** loop_engine converged on a 3-task plan (core+categories+
list_units / format() / convert_batch()) in 2 iterations — but **only 1 of 3
tasks was dispatched.** `format()` and `convert_batch()` (spec requirements
#5 and #6) have **zero dev cards.** The plan card is stuck in `running`.
The convergence was correct; the dispatch broke. **Version A (1 card covering
all requirements) has strictly better spec coverage than Version B3** — the
loop_engine's theoretical improvement regressed in outcome due to incomplete
dispatch.

**Net finding:** loop_engine genuinely iterated on all 3 boards (2 iterations
each) and made substantive decomposition decisions. On the 2 boards where
dispatch completed, Version B outperformed Version A in atomicity and AC
specificity. The failure mode (B3) is a **dispatch-reliability bug**, not a
convergence-loop failure. The loop works; the execution of its output is the
weak link.

## 16. loop_engine's `loop_state` blackboard — the authoritative convergence evidence

For boards produced by the **loop_engine** iterative-convergence template
(tech-lead decomposes spec into N phases → loop_engine runs each phase through
a dev↔verify convergence loop → re-dispatches on FAIL up to max_iterations),
there is a single best evidence source for the convergence story: the
`loop_state` blackboard.

### a. Where it lives

The **root loop card** (assignee = the loop/profile name, e.g.
`livetest-unbias-3`; title `Loop: <spec name>`) carries a series of
`[swarm:blackboard]` comments with key `loop_state`. Each comment is written at
a phase transition (phase advance or iteration replan) and is a full JSON
snapshot of the loop's state machine.

```sql
-- Pull every loop_state snapshot, in chronological order:
SELECT task_id, body FROM task_comments
WHERE body LIKE '[swarm:blackboard]%loop_state%'
ORDER BY id;
```

The JSON parses (strip the `[swarm:blackboard] {"key": "loop_state", "value": `
prefix) to:

```json
{
  "phase_index": 3,            // current phase (0-indexed)
  "iteration_counter": 2,      // iteration within the current phase
  "execution_card": "t_78afa558",   // the ACTIVE dev card
  "verifier_card": "t_a6b46ee6",    // the ACTIVE verify card
  "terminal_ids": ["t_a6b46ee6"],   // card(s) the loop is parked on
  "max_iterations": 5,
  "no_progress_streak": 1,
  "phases": [                  // the FULL phase plan, each with contract + ACs
    {"execution": {...}, "verifier": {...}, "max_iterations": 5},
    ...
  ]
}
```

### b. What you can extract immediately

From the `loop_state` snapshots alone — before reading any card bodies or
running any code — you get:

1. **Phase count + names.** `len(phases)` is the true decomposition; each
   `phases[i].execution.title` is the dev task title.
2. **Per-phase iteration counts.** The number of `loop_state` comments at a
   given `phase_index` = how many iterations that phase took to converge. A
   phase that needed 2+ iterations had a real defect found and fixed.
3. **The dev↔verify card pairing for every phase.** `execution_card` and
   `verifier_card` (and the replan comments' "Fresh cards: dev X → verifier Y"
   notes) give you the exact card IDs to pull for each phase.
4. **The convergence state.** `no_progress_streak`, `iteration_counter` vs
   `max_iterations` tell you whether the loop converged, escalated, or hit the
   cap.
5. **The full contract + ACs per phase.** Each `phases[i].execution.body`
   carries the contract and acceptance criteria — this is the source of truth
   for what the dev was asked to build, even better than the plan card.

### c. The convergence-trace query

To reconstruct the entire phase-by-phase convergence story (which phase took
how many iterations, which dev/verify cards, pass/fail), join `loop_state`
comments with the replan/advance summary comments on the same root card:

```sql
-- Phase transitions (advance or replan) from the runner/tech-lead:
SELECT body FROM task_comments
WHERE task_id = '<root-loop-card-id>'
  AND body NOT LIKE '[swarm:blackboard]'
ORDER BY id;
```

These human-readable comments ("Phase 3 PASSED on iteration 2", "Phase 4
replan (iteration 2/5)", with the finding the dev must fix) are the narrative
complement to the `loop_state` JSON.

### d. Worked example — livetest-unbias-3 (File Organizer Tool)

Root loop card `t_f422e80a`. 5 phases, `max_iterations: 5` each.

| Phase | Execution card(s) | Verifier card(s) | Iterations | Outcome |
|-------|-------------------|-------------------|------------|---------|
| 0 — Core categorization + move | t_6fd8c7ec | t_1b046c46 | 1 | PASS |
| 1 — Collision handling | t_07fd3cdc | t_996ae996 | 1 | PASS |
| 2 — Flags (dry-run/recursive/keep-empty) | t_db528461 → t_44723540 | t_01cf8cf9 → t_ff7d9992 | 2 | PASS (dry-run collision preview + recursive self-rename fixed) |
| 3 — Summary + empty-dir cleanup | t_9d1877d4 → t_f12624bb | t_0091ccc6 → t_eb756ae6 | 2 | PASS (symlink-to-dir crash fixed) |
| 4 — pytest test suite | t_65b7a26a → t_78afa558 | t_a3a9ec8a → t_a6b46ee6 | 2 | PASS (untested `_2` collision increment fixed) |

**Reading the table:** 4 of 5 phases needed a replan (iteration 2) because the
verifier found a real defect on iteration 1. Every defect was a genuine
data-loss-class or crash-class bug (not a phantom finding). The loop converged
within `max_iterations: 5` on every phase. This is the convergence-impact
evidence for dimension 6 of the decomposition audit — the loop earned its cost.

**Card-count decomposition (the ceremony-vs-substance split):**

| Category | Card count | Examples |
|----------|------------|----------|
| Core dev+verify (real work) | ~16 | `[task]` + `[verify]` cards |
| Probe swarm (3-way fan-out per failed iter) | ~16 | `[probe] fresh-eyes` / `static review` / `delta check` |
| Matrix-root anchors (blackboard only) | ~7 | `verify t_...` root cards |
| Wrapper / structural | ~7 | spec, plan, discover, loop root, fix cards, close |

Total: 46 cards for a 122-line tool. The right-sizing score separates these:
the **5-phase dev decomposition was correctly sized** (1 phase per coherent
feature increment); the **3-way probe fan-out per failed iteration was the
card-count driver** (verification ceremony, not over-decomposition). Score the
decomposition on the 5-phase plan; note the verification topology as a separate
cost observation.

### e. Pitfall: loop_state comments are large (119KB+ on this board)

Each `loop_state` snapshot re-serializes the *entire* `phases[]` array, so
on a 5-phase board a single comment can be 20KB+ and the full set 100KB+.
`sqlite3` CLI truncates large outputs. When pulling them, use
`substr(body, 1, 4000)` for a structural overview, then pull specific comments
by `id` range for the full JSON if you need to parse a particular phase's ACs.
The human-readable advance/replan comments (§c) are small and sufficient for
the convergence trace without parsing the big JSON.

## 17. Library / codec audit — purity probe + scratch-copy recovery (worked example: livetest-unbias-5, Base64)

Library/codec specs ("implement X from scratch, no stdlib") have two
audit-critical patterns that game/CLI/REST boards do not. This section captures
them via a worked example you can mirror for any codec (base64, json, csv,
hashlib, urlencode).

### a. The forbidden-import purity gate (verify it yourself, do not trust the verdict)

A spec that says "pure-Python, do NOT `import base64`" makes purity a CRITICAL
pass/fail dimension. A dev or verifier may self-report "pure-python confirmed"
based on a stale or mis-scoped grep. Verify independently with two layered
checks:

```sh
# 1. On-disk grep over the SUT package dir only (NOT the tests, NOT /tmp probes):
grep -rn "import base64\|from base64" <board>/workspaces/.../b64/
# exit 1 (no match) = CLEAN. exit 0 = LEAK.

# 2. In-memory source scan (catches dynamic/exec'd imports the disk grep misses):
python3 -c "import sys; sys.path.insert(0,'<sut-dir>'); import b64, inspect; \
  src=inspect.getsource(b64); print('import base64' in src, 'from base64' in src)"
# False False = CLEAN.
```

**Distinguish the oracle from the SUT.** The verifier's cross-check scripts and
the integration test file will contain `import base64 as oracle` — that is
CORRECT (the stdlib is allowed as a read-only oracle in tests). Trace every
`import base64` hit to its file: if it lives in `b64/__init__.py` it's a real
violation; if it lives in `/tmp/hermes-verify-*.py` or `test_*.py` it's a
legitimate oracle. The reusable probe is `probe_purity()` in
`scripts/library-breakit.py`.

### b. Third code-recovery path: the integration verifier's scratch copy

When the shared workspace AND all per-task workspaces are reaped post-completion
(scratch workspaces are deleted on `done`), two recovery paths are documented
above (§1b trace ledger; §"Reaped scratch" log mining). There is a THIRD, faster
one specific to boards that ran an integration verify (`[verify-b]`) step:

The integration verifier copies the full SUT + all test files into
`/tmp/hermes-verify-<slug>/` (e.g. `/tmp/hermes-verify-b64/`) to run its own
adversarial suite in isolation. That `/tmp` dir is **outside the board's
cleanup lifecycle**, so it frequently survives even after every board workspace
is gone.

```sh
# The close-card body usually names the surviving path. Read it FIRST:
sqlite3 kanban.db "SELECT body FROM task_comments WHERE body LIKE '%/tmp/hermes-verify%' LIMIT 5;"
# Or enumerate every scratch path any worker touched:
grep -rhoE "/tmp/hermes-verify[a-z0-9/-]+" logs/ | sort -u
```

On livetest-unbias-5 this recovered the complete `b64/__init__.py` (109 lines)
plus all 4 test files in seconds — no JSONL reconstruction needed. The close
verdict's "surviving canonical copy at `/tmp/hermes-verify-b64/`" pointer was
honest and load-bearing.

### c. Lenient-vs-strict decode: the honest non-defect note

A from-scratch codec often matches the stdlib's *default* (lenient) behavior
rather than strict-canonical behavior. For Base64, `decode('AB==')` returns
`b'\x00'` (the `B` carries non-zero bits in the padded zone) rather than
rejecting — this matches Python's `base64.b64decode` default and is permitted by
RFC 4648 §3.3. **Characterize this explicitly in the report as a non-defect**,
not as a silent acceptance: run the comparison against the stdlib oracle and
show they agree. A reviewer who sees `decode('AB==')` accepted without comment
will flag it; one who sees it matches the oracle default will not.

### d. Test-count reconciliation for multi-layer suites

On this board the close verdict claimed "155/155". Reconcile the layers:

| Layer | File | Count | Where it lives |
|-------|------|-------|----------------|
| Dev suite (P0–P3) | test_core.py + test_validation.py + test_streaming.py (+ test_urlsafe.py, GC'd) | 4 + 23 + 6 + ~9 = ~42 | shared workspace (GC'd); recovered in /tmp copy |
| Integration verifier suite | test_integration_behavior.py | 122 | `/tmp/hermes-verify-b64/tests/` (survives) |
| **Total** | | **155** | matches close verdict |

The dev-suite `test_urlsafe.py` was folded into the integration file in the
surviving `/tmp` copy (the integration verifier only copied core/validation/
streaming + its own). Confirm via `pytest --co -q` per file that the per-file
counts sum to the claimed total — do not echo "155" without breaking it down.

## 18. Forensic detection of verifier false-confidence on the format dimension

A verifier can write N/N green tests, declare `score=1.0, gaps=[]`, and STILL
have missed a bug class — because its tests *claimed* coverage they never
*exercised*. This is the most insidious verify-accuracy failure: the metadata
honestly reports what the tests assert, but the tests assert the wrong inputs.
The board looks clean (PASS, zero findings) and only a forensic re-read of the
verifier's actual test file exposes the gap.

Worked example: livetest-unbias-1 (Pomodoro Timer CLI). Two independent
verifier cards (`t_fa987e67` primary, `t_57119cb8` integration) both stamped
`dod_met=true, score=1.0, gaps=[]`. A tab-injection bug in
`format_log_line()` (a task name containing `\t` corrupts a 4-field TSV into 6
fields) survived BOTH suites. The forensic re-read revealed three distinct
false-confidence patterns.

### a. The three patterns to grep for in a verifier's test file

Read the verifier's test file (recovered from `verify_suite_path` in run
metadata, or `/tmp/hermes-verify-<slug>.py`, or mined from
`logs/t_<verify-id>.log`). Then check for these three patterns:

1. **Happy-path lock-in on format tests.** Every format assertion uses the
   spec's literal example string verbatim. A `format_log_line` test that
   asserts `len(fields) == 4` but only ever passes `task="implement auth"`
   (the spec example) can NEVER catch delimiter injection — the example string
   has no tabs. The test is structurally correct but epistemically inert.
   **Detection:** for every format-output assertion, check whether the input
   uses a user-supplied string field. If yes, confirm the test ever passes a
   value containing the output delimiter. If no, the format dimension is
   untested under hostile input.

2. **Docstring vs. input mismatch.** A test docstring names a threat class
   ("tabs, quotes") but the actual test input only exercises a subset (quotes
   only). The test PASSES because it never injects the named dangerous
   character. This is worse than pattern 1 — the verifier *knew* about the
   threat, wrote the word "tabs" in the docstring, but only typed quotes.
   **Detection:** for every test whose docstring or comment mentions a special
   character class (tabs, newlines, quotes, unicode), grep the test body for
   the literal byte (`\t`, `\n`, `"`, `\u`). A docstring saying "tabs" with no
   `\t` in the input is a smoking gun.

3. **No negative/stress oracle on the format dimension.** Even where field
   count is checked, it is never checked against hostile input. The verifier's
   "adversarial probes" are adversarial about *time math and missing files*,
   not about *format integrity under delimiter injection*. The probe set covers
   the spec's example shapes but not the spec's structural invariants.
   **Detection:** enumerate the adversarial/edge-case test class. Does any test
   inject the output delimiter character into a user-supplied field that flows
   into a formatted output line? If the spec defines a delimited format (TSV,
   CSV, pipe-separated) and no edge-case test puts the delimiter in a user
   field, this dimension is untested.

### b. The one-line probe that would have caught it

```python
s = {"task": "a\tb", "start": "2024-01-15T09:00:00", "end": "2024-01-15T09:25:00", "cycle": 1}
assert len(format_log_line(s).split("\t")) == 4   # FAILS: gets 5
```

Every verifier testing a delimited output format should include this shape:
inject the literal delimiter into every user-supplied string field, then assert
field-count integrity. See
[`scripts/cli-breakit.py`](scripts/cli-breakit.py) probe 5 for the reusable
version.

### c. Why this is a Dimension-4 (verify accuracy) problem, not Dimension-1 (code quality)

The code bug (no sanitization) is Dimension-1. But the *systemic* failure here
is that two independent verifier suites, both reporting `gaps=[]`, both failed
to test format integrity under hostile input. That is a verify-accuracy finding
that determines the board's PASS verdict is unreliable. When you detect these
patterns during a board audit:

- **Do not** score verify-accuracy 9-10 just because the suite is large (51+
  39 tests, 3/3 mutation checks caught). Mutation checks that target *time
  math* and *phase alternation* prove nothing about *format integrity*.
- **Do** score verify-accuracy down and name the specific gap: "format
  dimension untested under hostile input; 2 suites × 90 tests, 0 injected the
  output delimiter into a user field."
- **Do** reproduce the bug yourself (§a probe above) and report it as a true
  positive that both verifiers missed — this is the most valuable output for
  the user.

### d. Generalizing beyond tabs

The three patterns apply to ANY delimited output format where a user-supplied
string field flows into the output line:

| Format | Delimiter | User field | Injection probe |
|--------|-----------|------------|-----------------|
| TSV log | `\t` | task name | `task="a\tb"` |
| CSV | `,` | name/description | `name="a,b"` |
| Pipe-separated | `\|` | label | `label="a\|b"` |
| Newline-delimited | `\n` | comment | `comment="a\nb"` |
| JSON-in-string | `"` | any field | `field='a"b'` |

The detection technique (§a) is the same: read the verifier's test file, find
every format-output assertion, and confirm the test ever injects the delimiter
into a user field. If not, the format dimension is untested regardless of how
many tests pass.

