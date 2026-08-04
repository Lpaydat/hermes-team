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

## 7. Common pitfalls when analyzing a board

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
