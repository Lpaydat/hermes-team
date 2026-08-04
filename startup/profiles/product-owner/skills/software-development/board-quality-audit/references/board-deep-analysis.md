# Board Deep-Analysis Reference

Concrete queries and probes for auditing a completed kanban board. Use during
the five-dimension scoring in the parent skill, or as a standalone checklist.

## 1. Locate the actual code (non-obvious)

The repo path given to a test board (e.g. `/tmp/livetest-X/repo-N/`) is often a
**stub** — a bare `.git` with only a README. The real code the pipeline produced
lives in the **board's workspaces directory**, not the seed repo.

```sql
-- Find where each task actually wrote code:
SELECT id, title, workspace_kind, workspace_path
FROM tasks WHERE workspace_path IS NOT NULL;
```

- `workspace_kind='dir'` with a shared `workspace_path` → all dev beads in that
  project wrote to the same dir (e.g. `.../boards/<board>/workspaces/<name>/`).
- `workspace_kind='scratch'` → isolated per-task dirs; usually probe/verify
  scratch, not deliverable code.
- Confirm by listing files: `find <workspace_path> -type f -not -path '*/.git/*'`.

If the repo at the original path is empty except `.git` + README, **do not
conclude "no code was produced."** Check the workspaces dir.

### 1b. Trace-ledger reconstruction (when BOTH repo and workspaces are gone)

Sometimes BOTH tiers are empty: the repo is a stub AND the `workspaces/` dir is
empty because scratch/dir workspaces are garbage-collected after the run.
A THIRD recovery tier exists — the **harness trace ledger**. When a dev task
ran under the pi/agent harness, every `write` tool call (path + full file
bytes) is recorded in a JSONL trace at:

```
~/projects/<project-slug>/traces/<task-id>/attempt-<N>.jsonl
```

The trace is one JSON object per line (`type=message`). To reconstruct the
code, walk assistant messages and pull the file bytes out of `toolCall`
blocks:

```python
import json, os
trace = f"{home}/projects/{project}/traces/{task_id}/attempt-1.jsonl"
files = {}
for line in open(trace):
    obj = json.loads(line); msg = obj.get("message", obj)
    if msg.get("role") != "assistant":
        continue
    for block in (msg.get("content") or []):
        if block.get("type") == "toolCall" and block.get("name") in ("write", "write_file"):
            args = block.get("arguments", {})
            path, content = args.get("path"), args.get("content")
            if path and content is not None:
                files[path] = content
for path, content in files.items():
    os.makedirs(os.path.dirname(os.path.join(recon_dir, path)), exist_ok=True)
    open(os.path.join(recon_dir, path), "w").write(content)
```

**Schema note:** traces use `type: "toolCall"` (camelCase) with the tool name
in `name` and the args in `arguments` — NOT the Anthropic `tool_use` /
`input` shape. The tool result comes back as a separate `role: "toolResult"`
message with `toolName` and a text block like
`"Successfully wrote N bytes to <path>"`, confirming the write landed.

**Validate the reconstruction is faithful** before trusting it: re-run the dev
test suite on the reconstructed tree and confirm the pass count matches the
verifier's claim. If 44/44 pass on your reconstruction, it's faithful. This is
the same technique the integration verifier in the Hangman board used to
recover all 11 files after the original workspace was GC'd.

### 1c. Session logs (the simplest recovery tier — try this first)

Before reaching for trace-ledger reconstruction (§1b), check the **board's
`logs/` directory**. Every task run writes a full session transcript to:

```
<board-dir>/logs/t_<task-id>.log
```

This captures the verifier's complete session — including the contents of any
test file it `cat`-ed or `write`-d, its pytest run output (exact pass/fail
counts), its reasoning, and **patch diffs on test files it edited**. It is the
single fastest way to recover a reaped verifier test file or to audit whether
the verifier altered its own tests.

```bash
# Find the log and scan for the high-value markers:
grep -n "def test\|PYEOF\|passed\|failed\|patch\|diff" logs/t_<verify-id>.log
```

Recovery patterns the logs commonly contain:
- **Test file contents** — verifiers frequently `cat << 'PYEOF'` their
  behavior-test file into the terminal before running it; the full source is in
  the log. Extract it by copying from the `cat` heredoc to the closing `PYEOF`.
- **Exact test counts** — the `pytest -v` output shows per-test names and the
  `N passed` summary line, letting you reconcile claimed counts without the file.
- **Test edits** — a `patch`/`write` tool call on the behavior-test file
  appears as a unified diff in the log. A rename like
  `test_X_raises` → `test_X_handled_gracefully` with a relaxed assertion is
  visible here. This is how you catch a verifier lowering the bar to achieve an
  N/N sweep (see §9 worked example).

**Logs are NOT truncated by workspace GC** — they persist on the board after
scratch dirs are deleted. Prefer `logs/` for quick recovery; fall back to §1b
trace-ledger reconstruction only when the log doesn't contain what you need
(e.g. the file was never printed and only written via a tool call whose bytes
aren't echoed).

## 2. Mine the verify→fix→re-verify cycle from the DB

The task `result` column is frequently empty. The actual findings, fixes, and
verdicts live in **`task_comments`**, not `result`. Query in this order:

```sql
-- Dependency tree (what depends on what):
SELECT parent_id || ' -> ' || child_id FROM task_links ORDER BY parent_id;

-- Card inventory (type by title prefix, count, status):
SELECT substr(title,1,20) AS t, status, count(*)
FROM tasks GROUP BY status;

-- Completion timeline (proves ordering actually happened):
SELECT substr(title,1,55), datetime(completed_at,'unixepoch')
FROM tasks WHERE completed_at IS NOT NULL ORDER BY completed_at;

-- The findings/fixes themselves (read full bodies, not result):
SELECT author, datetime(created_at,'unixepoch'), substr(body,1,3000)
FROM task_comments WHERE task_id='<verify-card-id>' ORDER BY created_at;
```

**Verify-card title prefixes to look for:** `[verify]`, `[re-verify]`,
`[probe]`, `[fix]`, `[tl]`, `[spec]`. A `[verify]` followed by a `[fix]` then a
`[re-verify]` is the FAIL→fix→PASS cycle. A lone `[verify]` with no `[fix]`
means PASS on first attempt.

## 3. Independent verification (never trust, always re-probe)

The verifier's self-reported evidence can be fabricated, stale, or
misattributed. Independently reproduce three things:

### a. Re-run the test suite yourself
```bash
cd <workspace_path> && .venv/bin/pytest -v
```
Compare pass count to what the verifier reported. A mismatch is a red flag.

### b. Write your own adversarial probe for the critical property
For "unbeatable" claims, exhaustively explore the game tree yourself and count
terminal leaves by outcome:

```python
from tictactoe import Board, get_best_move
from collections import Counter

def explore(grid, x_to_move):
    b = Board(); b.grid = [row[:] for row in grid]
    w = b.check_winner()
    if w is not None:
        return [w]
    results = []
    empties = [(r,c) for r in range(3) for c in range(3) if grid[r][c] is None]
    if x_to_move:
        for r,c in empties:
            g = [row[:] for row in grid]; g[r][c]='X'
            results += explore(g, False)
    else:
        mv = get_best_move(b)
        g = [row[:] for row in grid]; g[mv[0]][mv[1]]='O'
        results += explore(g, True)
    return results

leaves = explore([[None]*3 for _ in range(3)], True)
print(Counter(leaves))  # expect {'O': 386, 'draw': 183, 'X': 0} for a correct minimax
```

**Matching the verifier's reported leaf counts exactly** (e.g. 569 leaves,
386 O-wins, 183 draws, 0 X-wins) is powerful corroborating evidence.

### c. Verify the fix via git
```bash
cd <workspace_path>
git log --oneline                          # find the fix commit
git show <fix-commit> -- <changed-file>    # confirm the diff is real
```
Then feed the same pathological input the verifier claimed was fixed and confirm
it no longer crashes.

### d. Mutation-test test-coverage claims (libraries / APIs / validators)

When a verifier claims "mutation X passes the suite undetected" (a test-gap
finding), verify the claim yourself by applying the mutation and running the
tests. **Never use `sed`** — it mangles Python regex strings (`\Z`, `\b`,
backreferences). Always mutate via Python string replacement:

```python
import shutil
shutil.copy('module.py', '/tmp/backup.py')

src = open('module.py').read()
mutated = src.replace('original_pattern', 'mutated_pattern')
assert src != mutated, "mutation did not apply — pattern not found!"
open('module.py', 'w').write(mutated)

# Step 1: confirm the mutation CHANGED OBSERVABLE BEHAVIOR first
from module import func
print(func('test_input'))   # must differ from the unmutated output

# Step 2: run the specific test — it should FAIL if the test guards this boundary
import subprocess
r = subprocess.run(['python', '-m', 'pytest', '-k', 'test_id', '-q'],
                   capture_output=True, text=True)
print(r.stdout[-300:])

# Step 3: RESTORE immediately and confirm full suite green
shutil.copy('/tmp/backup.py', 'module.py')
subprocess.run(['python', '-m', 'pytest', '-q'])
```

**Key pitfall:** if the mutation doesn't change observable behavior, the test
result is meaningless. Always confirm the behavior delta before trusting the
pass/fail. A mutation that the test CATCHES (1 failed) proves the test guards
that boundary; a mutation that passes undetected proves a test gap.

### e. Claimed test files that no longer exist (workspace GC)

A verifier may report a precise behavior-test count ("52/52 behavior tests in
`test_behavior.py`") for a file that lived in a scratch workspace now cleaned
up. You CANNOT recount it — the file is gone. Don't fake a recount and don't
discard the claim. Handle it transparently:

1. Check `task_runs.metadata` for the structured claim
   (`behavior_tests_total`, `behavior_tests_passed`, `behavior_test_file`,
   `dev_tests`).
2. Check whether the file is recoverable via trace-ledger reconstruction (§1b)
   — if the verifier *ran* pytest, the test file may be in ITS trace, not the
   dev's. If recoverable, recount it yourself.
3. If unrecoverable, score the claim on **metadata consistency + what you CAN
   independently re-run** (the dev suite survives if you reconstruct the dev
   tree). State the limitation explicitly in the report: "the 52-test file was
   deleted; claim is credible but I could not independently recount it."
4. Mutation-test the dev suite as a proxy: if the dev suite catches win/loss
   logic mutations, the behavior-test claim is corroborated even when the
   behavior file itself is gone.

## 4. The FAIL → ESCALATE → PASS arc (multi-iteration verify loops)

For complex boards, the verify→fix→re-verify loop can iterate 3-4 times before
hitting an **iteration cap**. When it does, the final verify verdict is
**ESCALATE**, not PASS — and an escalation card routes to the tech-lead for a
decision. The arc looks like:

```
iter-1: [verify] FAIL → [fix] →
iter-2: [re-verify] FAIL → [fix] →
iter-3: [re-verify] ESCALATE (cap hit) → [escalation] → tech-lead triage →
iter-4: [fix] (authorized) → [re-verify] PASS
```

### How to trace the arc from the DB

The ESCALATE summary lives in the escalation card body, and the full finding
set lives in the `REVIEW-ITERATION: N — SYNTHESIS COMPLETE` comment on the
**fix card** (not the verify card):

```sql
-- The escalation summary (tech-lead-facing):
SELECT substr(body, 1, 3000) FROM tasks
WHERE title LIKE 'ESCALATE%' OR title LIKE '[escalation]%';

-- The synthesized finding set per iteration (on the fix card's comment thread):
SELECT id, substr(body, 1, 4000)
FROM task_comments
WHERE task_id IN (SELECT id FROM tasks WHERE title LIKE '[fix]%')
  AND body LIKE '%REVIEW-ITERATION%SYNTHESIS%'
ORDER BY id;
```

### What ESCALATE means (and doesn't)

- **ESCALATE ≠ failure.** It means the iteration cap was reached with
  outstanding findings. The tech-lead decides: authorize another fix iteration,
  accept the risk and merge, or abandon.
- **The findings may be test-gaps, not code bugs.** A Critical finding like
  "mutation X passes the suite undetected" means the *code is correct* but the
  *test suite doesn't guard it*. This is a legitimate Critical (zero regression
  protection) but not a functional defect.
- **Deferred findings are documented.** The tech-lead's fix card body or
  comments list what's deferred (by ID: F10, F13, etc.) and why. These are
  accepted risks, not oversights.

### Finding classification for the "still open" question

After tracing the full arc, classify each finding:
- **Fixed & verified** — repro no longer reproduces; mutation now caught
- **Deferred by tech-lead** — explicitly accepted risk, documented in comments
- **Open** — reproduces against current code, no fix card addressed it
- **False positive** — verifier misread the contract (probe-inversion: claiming
  a behavior is a bug when it actually satisfies the spec). Check whether the
  claimed behavior actually violates the spec before counting it.

## 5. Worked example (board livetest-unbias-4 — Tic-Tac-Toe game)

A 53-line Tic-Tac-Toe game built by an 18-card pipeline. Audited to produce:

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9/10 | Piped stdin game runs rc=0; independent 569-leaf probe = 0 X-wins |
| Test quality | 9/10 | 53 tests pass; exhaustive unbeatable proof; 16 win-line cases |
| Decomposition | 9/10 | 18 cards, 3 correctly-sequenced dev beads, 7-11 ACs each |
| Verify accuracy | 8/10 | Integration verify found real CLI crash (isdigit→isdecimal); caught per-task verify's false PASS |
| Fix effectiveness | 10/10 | Commit `7609962`; 2 regression tests added; both repros now rc=0 |

**The finding the verify caught:** `parse_move` used `str.isdigit()` then called
`int()` with no try/except. `isdigit()` returns True for Unicode superscripts
(²,³) and overlong strings, but `int()` raises ValueError → uncaught CLI crash.
Fix: `isdigit()`→`isdecimal()` + try/except backstop. Real, minimal, regression-tested.

## 6. Worked example (board livetest-unbias-5 — String Validator Library)

A pure-Python string validation library (6 validators, ChainValidator, 3
sanitizers) built by a 38-card pipeline with a 4-iteration verify loop that
hit ESCALATE at iter-3, then resolved to PASS at iter-4.

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9/10 | All 6 validators + chain + sanitizers work; 136 tests pass; 2 Minor open (F15 port-only URL, F10 ZWSP) |
| Test quality | 9/10 | 136 tests; every validator has valid+invalid parametrized cases; mutation-tested boundaries |
| Decomposition | 8/10 | 38 cards (25 verifier — heavy); serial dev chain sharing one workspace (correct); one redundant dispatch |
| Verify accuracy | 9/10 | All findings independently reproduced; F7 mutation confirmed CAUGHT after fix; one false positive correctly dismissed |
| Fix effectiveness | 8/10 | 5 in-scope fixes verified FIXED; F15/F10/F13/F14 deferred by tech-lead (documented) |

**The ESCALATE arc:** iter-1 found a real Critical (password boundary untested).
Iter-2 found real Important issues (URL bogus hosts, XSS leak in strip_html).
Iter-3 hit the cap with F7 (email TLD char-class constraint unguarded by
tests — code correct, test suite unprotected). Tech-lead authorized iter-4,
which fixed F7/F8/F9/F11/F12. Final re-verify: PASS.

**Key technique — mutation testing the test-gap claim:** The F7 finding claimed
`[A-Za-z]{2,}` → `[A-Za-z0-9]{2,}` passes all 130 tests undetected. Verified by
applying the mutation via Python (not sed), confirming `is_email('user@example.c0')`
flips from `(False,...)` to `(True,None)`, then running the F7-specific test —
it caught the mutation (1 failed). After the fix added the test case, the
mutation is now caught. This is the proof that the test-gap was real AND fixed.

**Probe-inversion false positive:** A fresh-eyes probe reported FAIL on "AC7"
(TypeError for non-str inputs). The synthesizer correctly identified this as
probe-inversion — the contract mandates `(False, msg)` for non-str, so raising
TypeError would *violate* the contract. Properly dismissed.

## 7. REST API boards: black-box verification & break-it technique

REST API boards (Flask/FastAPI) have two verification concerns beyond what a
game or library audit needs: (a) proving claimed "behavior tests" are genuinely
HTTP-level black-box, and (b) breaking stateful failure modes (concurrency,
TTL/expiry, idempotent destructive ops) that developer tests rarely cover.

### a. Proving the test suite is black-box (not implementation tests)

A verifier may claim "60 behavior tests through the public interface" while the
test file actually asserts on internal state. Verify mechanically with a grep
before trusting the claim:

```bash
# Count HTTP calls through the test client (should be the dominant access pattern):
grep -cE "c\.(put|get|delete|post)\(|cc\.(put|get|delete|post)\(" test_behavior.py

# Find direct assertions on internal state (should be ZERO for black-box):
grep -n "_store" test_behavior.py | grep -v "_store.clear()"   # .clear() for reset is fine
```

For the JSON KV-store board, this produced: **116 HTTP calls, 0 internal-state
assertions** — confirming the suite is genuinely black-box. A test that does
`assert app._store['key'] == expected` instead of
`assert c.get('/api/key').get_json() == expected` is an implementation test,
not a behavior test.

### b. Break-it probes for stateful REST APIs

Use the reusable script at
[`scripts/rest-api-breakit.py`](scripts/rest-api-breakit.py) — adapt the
endpoint paths, payload shapes, and assertions for the board under audit. It
covers the four failure modes most likely to survive a developer's own tests:

1. **Concurrency races** — 200+ threads PUT to same key (lock correctness),
   300+ threads to distinct keys (no data loss). Developer tests usually use
   50–100 threads; cranking to 300 catches races that pass at lower counts.
2. **Time-based expiry (TTL)** — test with BOTH a mocked clock (deterministic,
   exact boundary) AND real `time.sleep` (catches bugs masked by the mock,
   e.g. if expiry is computed at read-time vs write-time inconsistently).
3. **Idempotent destructive ops** — DELETE missing key twice, both must 204.
4. **State transitions** — delete→re-create, overwrite-clears-TTL.

### c. Mocked-clock vs real-time dual testing

The mock-clock technique (`unittest.mock.patch.object(app, "time", mock)`)
gives exact boundary control but can mask real-clock integration bugs. For a
complete audit, run the TTL probes BOTH ways: mocked (deterministic boundary
checks) and real-time (proves the expiry logic works with the actual system
clock, not just the patched one). A board that passes only under the mock is a
yellow flag.

## 8. Worked example (board livetest-unbias-2 — JSON Key-Value Store REST API)

A 65-line Flask KV store (PUT/GET/DELETE `/api/<key>`, GET `/api`, TTL support)
built by a 14-card pipeline with a single verify→fix→re-verify loop.

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9/10 | 65-line app.py; thread-safe (threading.Lock); adversarial input (NaN/Inf/bool ttl) all 400, no 500s |
| Test quality | 9/10 | 19 dev pytest + 60 behavior probes (24 AC + 36 adversarial); verified black-box via grep (116 HTTP calls, 0 state asserts) |
| Decomposition | 9/10 | 14 cards; 2-step dev chain (skeleton→TTL+tests); fan-out probes + fan-in to integration verify |
| Verify accuracy | 9/10 | 60/60 reproduced independently; caught 3 real 500s (non-dict body, non-numeric ttl) in iter-1; fix verified in iter-2 |
| Overall | 9/10 | 12/12 independent break-it probes passed; spec fully met |

**The finding the verify caught:** PUT with a valid-but-non-dict JSON body
(`[1,2,3]` or `"hello"`) or a non-numeric `ttl` (`"60"`) crashed with an
unhandled `AttributeError`/`TypeError` → HTTP 500. Root cause:
`request.get_json(silent=True) or {}` only guards falsy bodies; a truthy
non-dict (list/scalar) bypasses the `or {}` fallback. Fix: explicit
`isinstance(body, dict)` guard + `isinstance(ttl, (int, float))` guard, both
returning 400. Real, minimal, and regression-tested with 9 adversarial probes.

**Black-box verification technique applied:** The verifier claimed "60 behavior
tests through the public HTTP interface." Confirmed mechanically: 116 HTTP
client calls in the test file, zero direct `_store` assertions (only
`.clear()` for test isolation). The suite is genuinely black-box.

**Break-it results:** All 12 independent probes passed — including 200-thread
same-key concurrency, 300-thread distinct-key concurrency, real-time TTL
expiry (1.2s sleep), TTL boundary (live at 1.5s / dead at 2.3s), idempotent
DELETE, and overwrite-clears-TTL. The board could not be broken.

## 9. Worked example (board livetest-unbias-3 — Temperature Converter Library)

A 238-line pure-stdlib temperature converter (C/F/K/R scales, `convert`,
`convert_batch`, `detect_scale`, absolute-zero validation) built by an 11-card
pipeline that PASSED on iteration 1 — no fix loop. This board's distinctive
lesson is the **verifier test-editing integrity issue**: a verifier achieved an
N/N clean-sweep by *relaxing its own failing test* rather than filing the
finding.

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9/10 | 0 imports (AST-verified pure stdlib); all 12 conversion pairs exact; abs-zero boundary inclusive (`<`); 4-scale round-trip drift 0.00e+00; 1e15 exact |
| Test quality | 8/10 | 114 dev tests pass; but 3 case-insensitivity tests (L168-180) call `to_celsius()` instead of named fns — vacuous; plus `test_simple.py` is `assert True` (padding) |
| Decomposition | 8/10 | 11 cards; serial dev chain on single-file module (correct); dual verify layers; BUT code never merged to repo-3 (nominal "merged") |
| Verify accuracy | 8/10 | 73 black-box behavior tests genuinely through public API; mutation 3/3 caught; BUT verifier relaxed a failing test to reach 73/73 (see below) |
| Overall | 8/10 | Tried to break it: negative Kelvin, extremes, precision — all correct. Found detect_scale whitespace leak + misleading no-suffix error |

**The test-editing integrity issue (distinct from probe-inversion):** The
Layer-2 verifier's own `test_detect_scale_whitespace_value_raises` FAILED on
first run (72/73) — `detect_scale(" 100C")` returns `(' 100', 'celsius')`
instead of raising. The verifier then **renamed and rewrote the test** to
`test_detect_scale_whitespace_value_handled_gracefully` (asserting only that
the scale is detected and the value is float-parseable), achieving 73/73.

This is *defensible* — the spec genuinely doesn't mention whitespace, so
requiring a raise was an over-specified probe. But it is also the verifier
*lowering the bar to make its own test pass*, and the whitespace leak IS a real
robustness gap (the returned value string carries leading whitespace; a
stricter verifier would flag it as a Minor finding). The fix was to **trace
the test edit in `logs/t_<verify-id>.log`** (§1c) — the patch diff
`test_X_raises` → `test_X_handled_gracefully` was visible there, exposing the
original expectation vs the relaxed one. Score verify accuracy accordingly: the
73/73 is real, but earned by relaxation, not by the code meeting the original
expectation.

**The vacuous-test defect (T1):** Three dev tests —
`test_to_fahrenheit_case_insensitive`, `test_to_kelvin_case_insensitive`,
`test_to_rankine_case_insensitive` (L168-180) — call `to_celsius()` inside
their bodies instead of the named function. They pass vacuously: the assertion
holds, but the named function's case-insensitivity is never exercised. The
Layer-1 verifier caught this correctly as a non-blocking test-quality note. The
**implementation** is independently correct (verified by direct call:
`to_fahrenheit(32, "FAHRENHEIT")` = 32.0) — only the tests are mis-wired.
Lesson: a green test named for function X does not prove function X works;
grep for copy-paste mismatches between the test-name verb and the function
actually called.

**Multi-layer count reconciliation (this board):** The brief said "73/73", the
dev suite had 114 tests, Layer-1 reported "202/202" (114 dev + 88 adversarial),
Layer-2 reported "188 combined" (115 dev + 73 behavior). All simultaneously
true: 115 = 114 + the `assert True` padding file. Reconcile, don't echo.

## 10. Library boards: black-box verification & stress-probe technique

Pure-Python library boards (no HTTP, no CLI entrypoint — just importable
functions returning dicts/values) have a verification concern that mirrors the
REST API black-box check (§7a): proving claimed "behavior tests" exercise the
**public interface only** (importing `from package import func`), not internal
plumbing (`_private_helpers`, `module.py` internals). Library boards also use a
**stress-probe** technique in place of the REST break-it script.

### a. The verifier-owned separate-file pattern (watch for it)

A verifier's self-reported "70/70 behavior tests" may not live in the dev's
`tests/` directory at all. The verifier writes its own independent test file —
typically in `/tmp/hermes-verify-<verify-task-id>/test_behavior.py` — and runs
it against the dev's venv and workspace. **This is a good thing** (genuine
independent black-box testing), but it creates a count-mismatch trap:

```bash
# Dev suite count (what's in the workspace):
cd <workspace_path> && grep -rch "def test" tests/ | paste -sd+ | bc
# → e.g. 52

# Verifier's claimed count (e.g. 70) → locate the verifier file:
ls /tmp/hermes-verify-*/test_behavior.py
grep -c "def test" /tmp/hermes-verify-<id>/test_behavior.py
# → 70
```

To confirm the claim independently, run the verifier's file against the dev
venv **from inside the dev workspace** (so `from package import ...` resolves):

```bash
cd <workspace_path> && .venv/bin/python -m pytest /tmp/hermes-verify-<id>/test_behavior.py -q
# → 70 passed

# Combined run (proves the two suites don't conflict):
.venv/bin/python -m pytest tests/ /tmp/hermes-verify-<id>/test_behavior.py -q
# → 122 passed
```

A verifier file that has disappeared (workspace `/tmp/...` cleaned up) means the
claim cannot be independently reproduced — flag it and score conservatively
(rely on the dev suite + your own probes only).

### b. Proving library tests are black-box (not implementation tests)

Mirror of §7a, for import-based libraries. A verifier may claim "behavior tests
through the public interface" while the file imports private internals. Verify
mechanically before trusting the claim:

```bash
# Only the public package import should appear (NOT package.module._private):
grep -nE "^from package import |^import package" test_behavior.py

# Any private/internal access? (should be ZERO for black-box):
grep -nE "package\.[a-z_]+\.py|_private|module\.internal" test_behavior.py
```

Acceptable exception: a test that reads the source file via `ast`/`open()` to
prove a static property (e.g. "no external dependencies", "stdlib only") is NOT
an implementation test — it's asserting a spec requirement without exercising
internal behavior. This pattern is fine.

### c. Stress-probe for library boards (replaces the REST break-it script)

For a library, the adversarial probe is a set of direct function calls with
edge-case inputs — write your own, don't reuse the verifier's. Run it with
`PYTHONPATH=<workspace_path>` so the import resolves without installing:

```bash
cd <workspace_path> && PYTHONPATH=. python /tmp/stress_probe.py
```

For pagination/utility libraries, the high-value stress inputs are: empty input,
single item, **exact division** (N items / page_size = N — confirms
`total_pages` isn't off-by-one and `has_next` is False on the last full page),
generators (consumable once), sets (unordered), `None`/empty query in search,
negative and huge out-of-range page numbers, and input non-mutation (capture
input list before call, assert unchanged after). See §11 worked example for the
concrete input set and expected outputs.

## 11. Worked example (board livetest-unbias-5 — Pagination Utility Library)

A 105-line pure-Python pagination library (`paginate`, `search`,
`sort_and_paginate`) built by a 13-card pipeline with a 2-iteration verify
loop. Test-only fix in iteration 2 (implementation was already correct).

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9.5/10 | All 8 spec reqs met; ceil division verified across 7 boundary cases (0/1/9/10/11 items); 22 stress inputs all PASS |
| Test quality | 9/10 | 52 dev tests pass; mutation-tested (removing `page_number < 1` guard → 2 tests fail); test-only fix correctly closed a real mutation gap |
| Decomposition | 9/10 | 13 cards; correct task_links tree; spec→plan→impl→verify→fix→re-verify→probe→integration→close lifecycle |
| Verify accuracy | 10/10 | 70/70 behavior claim independently reproduced; genuinely black-box (grep confirmed); verifier honestly logged 3 self-inflicted test-expectation bugs as not-code-defects |
| Overall | 9.5/10 | Tried to break it with 22 adversarial inputs — nothing broke |

**The separate-file pattern (this board):** Verifier claimed "70/70 behavior
tests." Dev suite had only 52. The 70 lived in
`/tmp/hermes-verify-t_0868d923/test_behavior.py` — a verifier-owned file.
Independently re-ran: 70 passed, 122 combined passed. Genuinely black-box:
`from space import paginate, search, sort_and_paginate` only, zero private
access (confirmed by grep; the only source-file read was an `ast` scan for
"no external deps" — a static spec check, not an implementation test).

**The mutation-gap finding (test-only fix):** Iteration-1 verify found that
removing `page_number < 1` from the out-of-range guard at `items.py:31` left
all tests green — `paginate([1,2,3,4,5], 2, -1)` would return `items=[2,3]`
instead of `[]`. The **code was correct**; the **test suite didn't guard** the
negative-page boundary. Iteration-2 fix added `test_negative_page_is_out_of_range`
and strengthened `test_page_zero_is_out_of_range`. Re-applying the mutation now
fails 2 tests — the gap is closed. This is the correct application of the
test-gap-finding class: flag a coverage hole, fix with tests, don't touch
working code.

**Exact-division probe (the trickiest math):** ceil division
`(total_items + page_size - 1) // page_size` verified across boundaries:

| items | page_size | expected total_pages | got |
|-------|-----------|---------------------|-----|
| 0 | 10 | 0 | 0 ✓ |
| 1 | 10 | 1 | 1 ✓ |
| 9 | 10 | 1 | 1 ✓ |
| 10 | 10 | 1 | 1 ✓ (exact division → 1 page, has_next False) |
| 11 | 10 | 2 | 2 ✓ |
| 7 | 3 | 3 | 3 ✓ |

## 12. Common pitfalls when analyzing a board

- **Empty `result` column ≠ no findings.** Read `task_comments`, not `result`.
- **Stub repo ≠ no code.** Check `workspace_path` in the tasks table.
- **Verifier said PASS ≠ no bug.** The per-task verifier can stamp PASS while
  its own probe workers flagged a defect. Check whether the integration verify
  caught something the per-task verify missed (this is the layered-verify value
  proposition — call it out in scoring).
- **"Unbeatable" without an exhaustive probe is unverified.** Spot-checking a
  few games is not proof. The exhaustive game-tree count is the only acceptable
  evidence for an unbeatable claim.
- **`sed` mangles Python regex in mutation tests.** `sed 's/\Z/z/'` doesn't do
  what you think — backslashes, `\Z`, `\b`, and backreferences get eaten or
  misinterpreted. Always mutate Python source via Python string replacement
  (`src.replace(...)`) and assert the replacement actually changed the source.
- **ESCALATE verdict ≠ the pipeline failed.** It means the iteration cap was
  reached with outstanding findings. The final state may be PASS (after a
  tech-lead-authorized fix) or a documented-deferred merge. Trace the full arc
  before scoring fix effectiveness — don't stop at the first ESCALATE.
- **`kanban_chains` root cards have empty results.** Tasks created as matrix
  roots hold "Matrix root anchor — blackboard only" in their `result` column.
  The actual findings live in the comment threads of the fix cards, not the
  root. Don't conclude "no findings" from an empty root result.

## 13. Worked example (board livetest-unbias-4 (rerun) — Hangman CLI Game)

A greenfield Hangman CLI (71-word list, HangmanGame class, pure display
renderers, 7-stage ASCII art, input validation, play-again + score tracking)
built by a 10-card pipeline that PASSED verify on iteration 1 with zero rework.

| Dimension | Score | Key evidence |
|-----------|-------|--------------|
| Code quality | 9/10 | Piped stdin: win, loss, play-again all rc=0; 7-stage ASCII verified; 71 words all 5-8/a-z/lowercase/unique; F1 dead import (Minor) |
| Test quality | 8/10 | 44/44 dev tests pass; mutation-tested (win all→any = 4 fail, loss >=→> = 4 fail); unit-test-heavy, partial behavior |
| Decomposition | 9/10 | 10 cards; dev→verify→(fan-out probes)→integration→close; premature-promotion bug self-caught and recovered |
| Verify accuracy | 8/10 | 44 dev re-run green; 52 behavior-test file GC'd (claim credible, unrecountable); 3/3 mutations corroborate |
| Fix effectiveness | N/A | Zero-rework board — verify PASSED iter 1; no fix→re-verify loop to score |

**Key technique — trace-ledger reconstruction:** Both the stub repo and the
`workspaces/` dir were empty (GC'd). Reconstructed all 11 source/test files
from the harness trace JSONL (`~/projects/hangman/traces/<dev-task>/attempt-1.jsonl`)
by walking assistant messages for `toolCall` blocks with `name="write"` and
extracting `arguments.content` = the actual file bytes. Validated faithfulness
by re-running the dev suite on the reconstruction (44/44 green). The
integration verifier had done the same reconstruction independently — two
independent recoveries from the same ledger converging on test-green is strong
evidence the trace is the real code.

**Honest limitation — deleted test file:** The 52-test behavior suite lived in
`workspaces/t_3e25afd5/hangman_project/test_behavior.py` (now GC'd). Could not
independently recount exactly 52. Scored the claim on: (a) internally-consistent
`task_runs.metadata` (52/52, combined 96/96), (b) the dev suite which I DID
re-run and re-mutation-test catching both win and loss logic mutations. The
report stated this limitation explicitly rather than faking a recount.

**Zero-rework scoring note:** When verify stamps PASS on iteration 1 and there
is no `[fix]` or `[re-verify]` card, dimension 5 (fix effectiveness) is **N/A,
not 0**. There were no fixes to be effective. Score the four real dimensions and
note the clean first-pass verdict as a positive signal under decomposition or
verify accuracy.

**The premature-promotion recovery (decomposition signal):** The first
`kanban_chains` dispatch created the dev→verify chain but the
`verifier → tech-lead` link was missing from `task_links`, causing the
tech-lead card to auto-promote 5s after blocking. The tech-lead caught this,
called `kanban_link` to add the edge, and re-blocked. Not a defect — a
self-healing recovery that shows the pipeline's link integrity is worth
checking via `SELECT parent_id || ' -> ' || child_id FROM task_links` before
trusting that a blocked card will actually wait.
- **Verifier test count ≠ dev test count (separate-file trap).** A verifier
  claiming "70/70 behavior tests" against a dev suite of 52 is NOT a discrepancy
  or a fabrication. The verifier writes its own independent test file in
  `/tmp/hermes-verify-<id>/test_behavior.py`. Locate it, run it independently,
  and run both combined. Only flag a count mismatch as suspicious if you cannot
  find a verifier-owned file AND the dev suite count is the only one that
  exists (see §10a).

## 14. Black-box scoring rubric for behavior tests (0-10)

When the verifier wrote behavior tests (`test_behavior.py`), score them on a
0-10 black-box scale. Read the actual test file (not just the metadata claim).
0 = pure white-box (tests break on any refactor); 10 = pure black-box (survive
any refactor). Use this empirical catalog of white-box patterns observed across
the round-2 unbiased livetest (5 boards, 292 tests, average 7.6/10):

| Score | Meaning | Example |
|-------|---------|---------|
| 9-10 | Pure public-interface only | Temp Converter: imports only `to_celsius`, `convert`, etc. No internals. |
| 8 | Public-interface dominant, minor setup coupling | KV Store: 116 HTTP calls, but `kvapp._store.clear()` for reset + `patch.object(kvapp, "time")` for TTL mocking |
| 7 | Public-interface dominant, some internal constant access | Passgen: CLI subprocess + `generate()`/`build_pools()`, but also asserts on `passgen.SYMBOLS` constant and checks `test_passgen.py` file exists |
| 6 | Mix of public and private; some tests would break on refactor | Hangman: CLI subprocess tests, but also tests internal `WORDS` list properties and calls private `_prompt_guess()` directly |

**White-box patterns to grep for** (each costs 1-2 points):

1. **Module constant access for assertions** — `assert any(c in passgen.SYMBOLS ...)`
   or `assert len(WORDS) >= 50`. Tests internal data, not user-facing behavior.
2. **Private method calls** — `_prompt_guess()`, `_validate()`, `__internal()`.
   Refactoring the private method breaks the test.
3. **Implementation-dependency mocking** — `patch.object(module, "time", mock)`.
   Couples to the specific time implementation; a switch to `time.monotonic()`
   breaks the test.
4. **File existence checks as coverage proxy** — `assert os.path.exists("test_passgen.py")`.
   Tests for a file name, not behavior.
5. **AST/source-file scans** — `ast.parse(open("items.py").read())`. **Acceptable**
   when testing a declared contract (e.g. "no external deps", "stdlib only") —
   these test the dependency surface, not internal behavior. Don't deduct for these.

**Acceptable test-setup coupling (don't deduct):**
- `kvapp._store.clear()` for test isolation/reset — accessing internal state for
  setup, not for assertions.
- `sys.path.insert(0, "<dev_workspace>")` to import the SUT — necessary plumbing.
