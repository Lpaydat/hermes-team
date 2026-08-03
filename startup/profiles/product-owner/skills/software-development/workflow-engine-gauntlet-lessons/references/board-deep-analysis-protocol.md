# Board Deep-Analysis Protocol

Post-hoc forensic evaluation of a **completed** livetest (or gauntlet) board.
The unbiased-livetest-protocol covers how to *run* a livetest; this covers
how to *score one that finished* — reading both the kanban DB and the actual
delivered code, running the tests yourself, independently reproducing any bug
the pipeline found, and verifying the fix was correct.

Use when the user asks to "deep-analyze", "score", "review", "evaluate", or
"audit" a finished board, or when gauntlet step 5 (deep analysis) needs a
repeatable scorecard rather than ad-hoc probing.

## The three code-recovery tiers (exhaust before giving up)

A board evaluation is incomplete without the actual delivered code. Work
through these tiers in order — most boards need only tier 1, but cleaned-up
boards require tier 2 or 3.

```
Tier 1 — workspaces/   ~/.hermes-teams/startup/kanban/boards/<board>/workspaces/<name>/
                        The actual app — may NOT be in the repo at /tmp/<repo>/

Tier 2 — repo git      /tmp/<repo>/ git history (all branches, all commits)
                        Sometimes committed to a non-master branch or worktree

Tier 3 — /tmp sandboxes /tmp/hermes-verify-*  (verifier mutation-testing copies)
                        Persists after board cleanup. Contains deliverable + tests.
```

**Pitfall:** the repo at `/tmp/<repo>/` often only has the initial empty
commit. The real code lives in the board's `workspaces/` directory (a `dir`
workspace whose files are gitignored under the parent root). Always check
`workspaces/` before concluding "no code was produced."

```bash
# Tier 1: find the delivered code in workspaces
find ~/.hermes-teams/startup/kanban/boards/<board>/workspaces -type f \
  -not -path '*/__pycache__/*' -not -path '*/.git/*'
```

### Tier 3: when workspaces are cleaned up (verifier sandbox recovery)

**Boards get cleaned up.** Workspace directories are often removed after
the pipeline completes (scratch workspaces are ephemeral). When BOTH the
repo AND `workspaces/` are empty, the deliverable code can still be
recovered from the **verifier's mutation-testing sandboxes** in `/tmp/`.

During adversarial verification, the verifier copies the dev's code into
temporary directories (`/tmp/hermes-verify-*/`) to run mutation checks.
These sandboxes are NOT cleaned up with the board — they persist in `/tmp/`
until the OS reaps them. They contain:

- A copy of the real deliverable code (e.g. `dedupe.py`)
- A copy of the test suite (`test_dedupe.py`)
- Mutation output artifacts (`mut1_out.csv`, etc.)

```bash
# Recover the deliverable from verifier sandboxes
find /tmp -maxdepth 1 -name "hermes-verify-*" -type d 2>/dev/null
# Then inspect each one — the deliverable filename is stable across copies
find /tmp/hermes-verify-* -name "<deliverable>" 2>/dev/null
```

**Identifying the canonical version:** multiple sandboxes may exist (one
per verifier run — per-task verify, integration verify, mutation checks).
They may contain DIFFERENT versions of the same file. To identify the real
deliverable:

1. Cross-reference `task_runs.metadata` JSON — it lists `changed_files`,
   `worktree_path`, `imports`, `stdlib_only`, `tests_run`, etc. Match
   these structural markers (function names, line count, docstring) against
   the recovered copies.
2. The version with the most complete docstring + function decomposition
   is usually the dev deliverable; shorter versions are often test-author
   "oracles" (minimal reference implementations written to validate the
   test suite logic independently).

**Observed in livetest-unbias-3 (CSV Deduplicator):** Both the repo and
all workspace paths were empty. Two `/tmp/hermes-verify-*` sandboxes
existed: one held an 85-line minimal oracle, the other held the real
191-line deliverable with `parse_args`/`make_key`/`normalize`/
`deduplicate` — matching the developer's completion-report metadata.

## The 5-dimension scorecard

Score each 0–10 with evidence. The dimensions and what "good" looks like:

| Dimension | What to check | Evidence source |
|-----------|--------------|-----------------|
| **Code quality** | Does it work? All spec endpoints, rate limiting, input validation, no 500s in production mode | Run the app / test_client yourself |
| **Test quality** | Comprehensive? Covers happy path + error cases + the specific bug class found. Run them. | `pytest -v` directly (install deps if missing) |
| **Decomposition** | Task count sane for artifact size? ACs clear and testable? Dependency graph coherent? | `task_links` table, spec card body |
| **Verify accuracy** | Were reported findings REAL bugs? (reproduce pre-fix). Correct severity? | Verifier comments + independent repro |
| **Fix effectiveness** | Did the fix actually resolve the bug? Re-verify independently in production mode. Regression-clean? | Post-fix code + test_client probe |

## Step-by-step

### 1. Orient from the DB

```sql
-- Task count and status distribution
SELECT status, count(*) FROM tasks GROUP BY status;

-- Full task list with assignees
SELECT id, substr(title,1,70), status, assignee FROM tasks ORDER BY created_at;

-- Dependency graph
SELECT parent_id, child_id FROM task_links ORDER BY parent_id;

-- Run outcomes (crashes, completions)
SELECT t.id, tr.outcome FROM task_runs tr JOIN tasks t ON t.id=tr.task_id;

-- Structured metadata from each run (verdict, tests_run, changed_files, etc.)
SELECT task_id, metadata FROM task_runs WHERE status='done';
```

Read the **spec card** (`SELECT body FROM tasks WHERE id LIKE 'spec-%'`) to
know the acceptance criteria you're scoring against.

### 2. Read and run the delivered code

```bash
cd <workspace or recovered sandbox>
pip install -r requirements.txt   # may be needed — deps often not installed
python -m pytest -v                # run the actual test suite
```

**Pitfall:** Flask/pytest may not be installed in the system Python. Install
them; this is an environment fix, not a code defect.

### 3. Trace the verify → fix → re-verify lifecycle

The most important analysis dimension. Find every FAIL verdict and its
corresponding fix:

```sql
-- Find verify/fix tasks and their verdicts
SELECT id, substr(title,1,60) FROM tasks
WHERE title LIKE '%[verify]%' OR title LIKE '%[fix]%' OR title LIKE '%[re-verify]%';

-- Read the full finding + fix trail (comments carry the detail)
SELECT body FROM task_comments WHERE task_id='<verify-task>' ORDER BY created_at;
SELECT body FROM task_comments WHERE task_id='<fix-task>' ORDER BY created_at;
```

### 4. Independently reproduce each reported bug

This is the critical step that separates real findings from false positives.
For each finding the verifier reported:

1. **Reconstruct the pre-fix state** — simulate the vulnerable code path in
   isolation (don't rely on the verifier's claim).
2. **Confirm the bug manifests** — run the exact repro and observe the failure.
3. **Confirm the fix blocks it** — run the same repro against current code.

### 5. Verify fixes in production mode

**Always test with TESTING=False.** This is where production-only bugs hide
(lesson #15 in the main SKILL.md). The test suite runs in test mode and can
mask defects that only surface in production.

```python
app.app.config['TESTING'] = False  # PRODUCTION mode
c = app.app.test_client()
# Exercise EVERY endpoint + the specific bug class
```

### 6. Run your own adversarial probes (beyond the test suite)

The dev test suite tests the spec's happy paths. Run your own probes that
the pipeline never tried:

- **CRLF line endings** on a CSV tool — does it preserve `\r\n` on output?
- **Ragged rows** in column mode — does it crash or defend?
- **Directory as input** — clean error or crash?
- **Unicode casefold** (`Straße` vs `STRASSE`) — does `--ignore-case` work?
- **Mutual exclusion** of conflicting CLI flags — does it error cleanly?
- **Combined flags** (`--ignore-case --trim --column` together)

```python
# Example: independent adversarial probe battery
import subprocess, sys, csv, os

def run(args): return subprocess.run([sys.executable, 'dedupe.py', *args],
                                     capture_output=True, text=True)
def rows(p):
    with open(p, newline='') as f: return list(csv.reader(f))

# Each probe: run, check return code + output, print PASS/FAIL
```

## Pitfall: test-version drift across verifier sandboxes

**A subtle verification blind spot.** When the test author self-corrects a
bug mid-run (e.g. fixing a `str.strip().splitlines()` parsing bug that
mangled quoted fields), BOTH versions of the test file can persist in
different verifier sandboxes. The verifier's "28/28 pass" claim is only
accurate for the *fixed* version — it may not have validated which version
was canonical.

**Detection:** if you find multiple copies of the test file in different
`/tmp/hermes-verify-*` sandboxes, diff them. If the diff touches output-
parsing helpers (e.g. `splitlines()` → `csv.reader()`), the older version
is buggy. Run the suite against BOTH versions to confirm which one the
verifier actually ran:

```bash
# Run both versions to see which one the "28/28" claim applies to
python -m pytest /tmp/hermes-verify-A/test_dedupe.py -v   # may FAIL 4 tests
python -m pytest /tmp/hermes-verify-B/test_dedupe.py -v   # may PASS 28/28
```

**Observed in livetest-unbias-3:** the test author fixed a `splitlines()`
parsing bug (3 test failures) by switching to `csv.reader`. The fixed
version passed 28/28; the original version failed 4 tests. The verifier
ran the fixed version and stamped PASS — correctly, but without noting
the test file had been mutated mid-run or validating that the workspace's
canonical copy was the fixed one. A less careful verifier would have
been equally justified in running the original and stamping FAIL.

**Generalization:** any time a deliverable is modified mid-pipeline (test
fix, code fix), check whether ALL downstream consumers saw the fixed
version. Verifier sandboxes are independent copies — they don't update
each other.

## Concrete technique: CRLF / control-char injection verification

The URL Shortener livetest (livetest-unbias-2) found a CRLF injection bug via
its integration verifier. Here is the exact independent-verification recipe
that confirmed it was real and the fix was correct:

### Root-cause isolation (one-liner)

```python
from urllib.parse import urlparse
# urlparse SILENTLY ABSORBS control chars into netloc
for u in ['https://x.com\n', 'https://x.com\r\n', 'https://x.com\t', 'https://x.com\x00']:
    p = urlparse(u)
    print(f'{u!r} -> scheme={p.scheme!r} netloc={p.netloc!r}')
# All return scheme='https', netloc='x.com' — a naive scheme+netloc validator passes them
```

This proves the bug is in the standard library's permissive parsing, so the
guard MUST run BEFORE `urlparse()`, not after. A post-urlparse check on the
parsed netloc would miss it entirely because the char is already absorbed.

### Pre-fix vs post-fix comparison

```python
# Pre-fix (simulated): scheme + netloc check only
def old_validator(url):
    if not isinstance(url, str) or not url: return False
    p = urlparse(url)
    return p.scheme in ('http','https') and bool(p.netloc)

# Post-fix: control-char guard BEFORE urlparse
def is_valid_url(url):
    if not isinstance(url, str) or not url: return False
    if any(ord(c) < 32 or ord(c) == 127 for c in url): return False  # the fix
    p = urlparse(url)
    return p.scheme in ('http','https') and bool(p.netloc)

# Test all control-char variants against both
variants = ['\n','\r\n','\r','\t','\x00','\x7f','\x01','\x1f']
for v in variants:
    u = f'https://example.com{v}'
    print(f'{v!r}: old={old_validator(u)} (BUG)  new={is_valid_url(u)} (fixed)')
```

### Production-mode end-to-end confirmation

```python
app.app.config['TESTING'] = False
c = app.app.test_client()
app.clear_storage(); app.clear_rate_limiter()

# The bug: control-char URL accepted (201) then crashes redirect (500)
for label, payload in [('LF','https://example.com\n'),
                       ('CRLF','https://example.com\r\n'),
                       ('TAB','https://example.com\t'),
                       ('NUL','https://example.com\x00')]:
    r = c.post('/api/shorten', json={'url': payload})
    assert r.status_code == 400, f'{label} NOT blocked!'
    # Post-fix: all return 400. Pre-fix: all returned 201 (accepted).
```

## What makes this analysis high-quality

1. **Triple-source recovery** — exhaust all three tiers (workspaces → repo
   git → `/tmp/hermes-verify-*` sandboxes) before concluding "no code found."
2. **Independent reproduction** — don't trust the verifier's "FAIL" or the
   fixer's "FIXED"; reproduce both states yourself.
3. **Production mode** — always probe with TESTING=False; test mode masks bugs.
4. **Boundary precision** — test exact boundaries (rate limit: 10 allowed,
   11th blocked — not just "rate limiting works").
5. **Adversarial probes beyond the suite** — run your own probes the pipeline
   never tried (CRLF, ragged rows, unicode casefold, combined flags).
6. **Test-version validation** — when multiple test-file copies exist, confirm
   which version the verifier actually ran before trusting its pass count.
7. **Evidence table** — every score cites a concrete check that was run, not
   a reading of the verifier's self-report.
