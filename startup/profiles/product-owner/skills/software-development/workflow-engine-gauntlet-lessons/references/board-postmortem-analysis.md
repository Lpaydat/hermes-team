# Board Postmortem Analysis — independently auditing a pipeline run

Technique for deep-analyzing a kanban board AFTER a pipeline completes, to
check whether the "PASS / merged" verdict is actually earned. Use when
evaluating a livetest, auditing a pipeline run, or diagnosing why a
"verified" deliverable still has bugs.

The goal is adversarial independence: trust NOTHING the pipeline stamped.
Re-derive every claim from the actual code and DB state.

## 1. Read the board DB directly

```bash
DB=~/.hermes-teams/startup/kanban/boards/<board>/kanban.db

# All tasks
sqlite3 $DB "SELECT id, title, assignee, status FROM tasks ORDER BY created_at;"

# Task dependency tree
sqlite3 $DB "SELECT parent_id, child_id FROM task_links ORDER BY parent_id;"

# Run metadata (the structured facts each worker reported)
sqlite3 $DB "SELECT task_id, metadata FROM task_runs WHERE status='done';"
```

Key metadata fields to extract from each verify run:
- `verdict` (PASS / FAIL / ESCALATED)
- `acs_verified` / `acs_total`
- `dev_tests` (e.g. "14/14 PASS")
- `findings_detail` (important / minor / note, each with file_line + evidence)
- `fix_card` (which card was dispatched to fix the findings)

## 2. Find the ACTUAL code (not in the repo)

**The repo is often a red herring.** Code produced by kanban tasks lives in
per-task workspaces, NOT committed to the repo's master branch.

```bash
# Check git state — often only the initial commit exists
cd /path/to/repo && git log --oneline && git branch -a

# Find ALL versions of the deliverable across workspaces
find ~/.hermes-teams/startup/kanban/boards/<board>/workspaces/ -name "*.py" -exec ls -la {} \;

# Which workspace did each task use?
sqlite3 $DB "SELECT id, workspace_kind, workspace_path FROM tasks WHERE workspace_path IS NOT NULL;"
```

**Critical:** `workspace_kind='dir'` means a fix card SHARED a dev card's
workspace (warm edit). Track which workspace holds the "final" version by
following fix-card → workspace_path links. Multiple parallel dev chains may
each have their own workspace with different code.

## 3. Run the tests independently

```bash
cd <workspace-with-code-and-tests>
python -m pytest test_*.py -v
```

Note the test COUNT. A thin suite (14 tests) vs a comprehensive one (37
tests) is itself a signal — the merged chain may have weaker tests than a
parallel chain that was discarded.

## 4. Reproduce every verify finding against the code

For each finding the verifier filed, execute its `evidence` / `repro`
command verbatim against the CURRENT code:

```bash
# Finding said: "md2html.py:187 UnicodeDecodeError unhandled"
printf '\xff\xfe' > /tmp/bad.md && python md2html.py /tmp/bad.md; echo "exit=$?"

# Finding said: "javascript: URL XSS"
python3 -c "import md2html; print(repr(md2html.inline('[x](javascript:alert(1))')))"
```

Classify each:
- **FIXED** — code now handles it correctly (exit 1, scheme blocked, etc.)
- **STILL BROKEN** — the fix didn't work or didn't land
- **NEVER FILED** — a feature gap no verifier noticed (see below)

## 5. Check "FIXED" claims by running the ORIGINAL failing input

**This is where false confirmations hide.** The verify swarm may re-test
with an EASIER sub-case than the original finding described.

```python
# Original finding: "Combined bold+italic mis-parsed"
# Verifier marked FIXED. But did they test the ORIGINAL case or an easy one?

import md2html
# The hard case (mixed nesting):
md2html.inline('**bold and *italic***')
# If this returns '<strong>bold and *italic</strong>*' → STILL BROKEN
# The fix only handled ***both*** (easy case), not mixed nesting (hard case)
```

**Rule:** re-run the EXACT original failing input from the finding's
evidence field. "I tested bold+italic" is not verifiable. "I ran
`inline('**bold and *italic***')` and got X" is.

## 6. Hunt for missing features (never-filed gaps)

Compare the spec's feature list against what the code actually implements:

```python
import md2html
# Spec says: "code blocks" — does the code handle INLINE code too?
md2html.inline('use `printf` to print')
# If this returns literal backticks → inline code not implemented
```

```bash
# Does the test suite even test this feature?
grep -n "inline.code\|backtick" test_*.py
```

If a standard feature is absent from BOTH the code AND the test suite AND
the findings list across all iterations → it's a blind spot the whole
pipeline shared.

## 7. Compare parallel chain outputs

When two plan cards ran (producing two dev chains), compare their outputs:

| Metric | Chain A | Chain B (merged) |
|--------|---------|------------------|
| Test count | 37 | 14 |
| Feature X works? | ✓ | ✗ |
| Finding Y fixed? | ✓ (different algorithm) | ✗ (regex hack) |
| LOC | 386 | 236 |

If the non-merged chain is superior, the artifact-selection step failed.

## 8. Verify the "merged" verdict is real

```bash
cd /path/to/repo
git log --oneline  # Does the deliverable appear in any commit?
git diff HEAD      # Are there uncommitted changes?
```

If `verdict: "merged"` but the repo has only the initial commit → the
verdict is aspirational, not factual. (Expected for livetest boards; a bug
for production pipelines.)

## Concrete technique: CRLF / control-char injection verification

When a pipeline finding involves CRLF injection or control-char handling in a
URL/HTTP-header context, the independent-verification recipe is:

### Root-cause isolation (one-liner)

```python
from urllib.parse import urlparse
# urlparse SILENTLY ABSORBS control chars into netloc
for u in ['https://x.com\n', 'https://x.com\r\n', 'https://x.com\t', 'https://x.com\x00']:
    p = urlparse(u)
    print(f'{u!r} -> scheme={p.scheme!r} netloc={p.netloc!r}')
# All return scheme='https', netloc='x.com' — a naive scheme+netloc validator passes them
```

This proves the guard MUST run BEFORE `urlparse()`, not after — a post-urlparse
check on the parsed netloc misses the char entirely because it's already absorbed.

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

variants = ['\n','\r\n','\r','\t','\x00','\x7f','\x01','\x1f']
for v in variants:
    u = f'https://example.com{v}'
    print(f'{v!r}: old={old_validator(u)} (BUG)  new={is_valid_url(u)} (fixed)')
```

### Production-mode end-to-end confirmation

Always confirm the fix holds with `TESTING=False` — test mode can mask the 500
that a tainted URL causes on redirect (lesson #15). See the main SKILL.md for
why production-mode testing is mandatory.

```python
app.app.config['TESTING'] = False
c = app.app.test_client()
app.clear_storage(); app.clear_rate_limiter()

for label, payload in [('LF','https://example.com\n'),
                       ('CRLF','https://example.com\r\n'),
                       ('TAB','https://example.com\t'),
                       ('NUL','https://example.com\x00')]:
    r = c.post('/api/shorten', json={'url': payload})
    assert r.status_code == 400, f'{label} NOT blocked!'
    # Post-fix: all return 400. Pre-fix: all returned 201 (accepted → then 500 on redirect).
```

## Scoring rubric (when asked to score a board)

| Dimension | What to check |
|-----------|---------------|
| Code quality | Does it work? Run it. Does every spec element convert? |
| Test quality | Run tests. Count them. Do they cover every element + CLI + errors? |
| Decomposition | How many tasks? Were ACs testable? Redundancy level? |
| Verify accuracy | Were findings real? Were fixes effective? Any false FIXED? |
| Fix effectiveness | Were fixes applied correctly? Any regressions? |

Each scored 0-10 with specific evidence (file paths, line numbers, test
results, executed commands and their output).
