# Migration Repo Discovery — Finding and Evaluating Reference Repos

Created 2026-08-10. Supports the dev-port workflow (`references/dev-port-workflow-pattern.md`).

The dev-port workflow ports code from reference repos instead of building from scratch.
Finding good references is the prerequisite — the workflow needs repos that:
(1) are small enough to produce 3-5 tickets, (2) are self-contained with no heavy
language-specific runtime dependencies, and (3) have real tests to verify the port.

## Migration Candidacy Criteria

| Criterion | Why it matters |
|-----------|----------------|
| Small (<500 LOC, 1-5 source files) | Produces 3-5 tickets; completes in ~3-4 hours |
| Self-contained CLI/utility | No web server, no DB, no long-running state — easy to port and test |
| Has tests | Verification can compare port output against the original's test suite |
| Pure logic (no runtime introspection) | A repo that introspects Python classes at runtime (e.g. pydantic-to-typescript) is NOT portable — its core logic IS the runtime. Discard these. |
| Minimal dependencies | Zero deps = direct port; small framework deps (e.g. click) = reimplementation test; heavy ecosystem deps (e.g. beautifulsoup4 + html5lib) = crate-mapping test |

## Graduated Difficulty Model

When selecting 3 candidates, pick a graduated difficulty ladder:

1. **Easy (zero deps, pure data transformation)** — 1:1 port, every function maps directly. Good first migration test.
2. **Medium (small framework deps)** — tests the "replace framework dependency" pattern. You must reimplement the CLI framework (e.g. click → clap/cobra).
3. **Hard (heavy ecosystem deps)** — tests the "map to equivalent target-language crate" pattern. You must choose an equivalent library (e.g. beautifulsoup4 → scraper/html5ever in Rust).

## Discovery Methodology (GitHub API)

### Step 1: Search by criteria

Use the GitHub Search API with size + stars + language + recency filters:

```python
import json, urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"}

def github_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return json.loads(urllib.request.urlopen(req).read())

# Effective search queries (Python):
queries = [
    "language:python+cli+tool+size:<200+stars:>50+pushed:>2024-01-01",
    "language:python+cli+convert+size:<50+stars:>100+pushed:>2023-01-01",
    "language:python+markdown+convert+cli+size:<100+stars:>100",
    "user:simonw+cli+stars:>100",  # high-yield author (small, well-tested tools)
]

for q in queries:
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=20"
    data = github_get(url)
    for r in data.get("items", []):
        desc = (r["description"] or "N/A")[:90]
        print(f'{r["full_name"]} | stars={r["stargazers_count"]} | size={r["size"]}KB | {desc}')
```

**Key search tips:**
- `size:<200` (GitHub size is in KB, counts all files) is a good filter for <500 LOC repos
- Search prolific single-author maintainers (simonw is excellent — small, well-tested CLI tools)
- `language:typescript+cli+size:<200` works for TS/JS candidates

### Step 2: Get the file tree (one API call)

```python
def get_file_tree(repo):
    """Get full file tree, trying main then master."""
    for branch in ["main", "master"]:
        try:
            url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
            data = github_get(url)
            if data.get("tree"):
                return data["tree"], branch
        except Exception:
            continue
    return [], None
```

The recursive git tree API returns the complete file listing + per-file byte sizes in ONE call.
Filter for source files (`.py`, `.ts`, `.js`) and test files (`test` or `spec` in path).

### Step 3: Count LOC per file via contents API

```python
import base64

def count_loc(repo, filepath, branch):
    url = f"https://api.github.com/repos/{repo}/contents/{filepath}?ref={branch}"
    data = github_get(url)
    content = data.get("content", "")
    if data.get("encoding") == "base64":
        content = base64.b64decode(content).decode("utf-8")
    lines = content.splitlines()
    non_blank = sum(1 for l in lines if l.strip())
    return len(lines), non_blank
```

### Step 4: Read setup.py/pyproject.toml for dependencies

Fetch the dependency manifest to classify the repo on the difficulty ladder.
`install_requires` in setup.py or `[project.dependencies]` in pyproject.toml.

### Rate limit note

GitHub unauthenticated API limit is 60 req/hour. Searching + tree + contents across
~8 candidates uses ~30-40 calls. Stay within budget. The git tree API (recursive=1)
is the key efficiency trick — one call per repo for the full file list, instead of
N calls for N directories.

## Proven Candidate Set (2026-08-10)

These 3 repos were selected for dev-port workflow testing. They form a graduated
difficulty ladder. All data verified via the methodology above.

### 1. lzakharov/csv2md (EASY — zero deps)

- **URL:** https://github.com/lzakharov/csv2md
- **LOC:** ~200 source (table.py: 75, \_\_main\_\_.py: 120, exceptions.py: 8, utils.py: 8)
- **Files:** 4 source + 2 test (262 LOC tests)
- **What it does:** CLI tool converting CSV files to Markdown tables. Custom delimiters, column selection, alignment options, stdin support.
- **Why good for migration:** Zero runtime dependencies (stdlib only: csv, argparse, sys). Pure data-transformation logic maps 1:1 to Rust/Go. The `Table` class is a straightforward struct with formatting logic.
- **Best/easiest candidate for a first migration test.**

### 2. simonw/csv-diff (MEDIUM — small framework deps)

- **URL:** https://github.com/simonw/csv-diff
- **LOC:** 274 non-blank source (\_\_init\_\_.py: 198, cli.py: 76)
- **Files:** 2 source + 3 test (535 non-blank LOC tests)
- **What it does:** CLI tool diffing two CSV/JSON files — shows added/removed/changed rows and columns. JSON or human-readable output.
- **Why good for migration:** Self-contained algorithmic logic (set ops, dict comparison, SHA1 key generation). Two small deps (`click` for CLI, `dictdiffer` for diffing) that need reimplementation — tests the "replace framework dependency" pattern. Rich test suite.

### 3. simonw/strip-tags (HARD — heavy ecosystem deps)

- **URL:** https://github.com/simonw/strip-tags
- **LOC:** 267 non-blank source (lib.py: 226, cli.py: 36)
- **Files:** 4 source + 1 test + YAML test data
- **What it does:** CLI tool stripping HTML tags from input, optionally targeting CSS selectors. Minification, tag retention, attribute preservation, first-match modes.
- **Why good for migration:** Heavy dep on `beautifulsoup4` + `html5lib` (Python-specific HTML parser) — must select equivalent target crate (`scraper`/`html5ever` for Rust, `goquery` for Go). Tests the "map to equivalent target-language crate" pattern. Table-driven YAML test fixtures make cross-language verification easy.

## Pitfall: Runtime-Introspection Repos Are NOT Portable

During discovery, `phillipdupuis/pydantic-to-typescript` looked promising (432 stars,
446 LOC, 1 test file). But its core logic IS Python runtime introspection — it imports
pydantic models, inspects their fields at runtime, and emits TypeScript. The Python
runtime IS the implementation; there is no portable algorithm to translate.

**Rule:** Before selecting a repo, read its core source file. If the logic depends on
language-specific runtime features (introspection, metaclasses, decorators, dynamic
imports), it's not a migration candidate — it's a "rewrite from scratch" candidate.
Discard it and find one with portable logic.
