# Tech Preferences System Design

Produced by 5-subagent analysis, then simplified by the user into the final three-level tools/toolkits/recipes design.

## Final accepted design: tools, toolkits, recipes

The user rejected two earlier proposals (per-language profiles with no composition, then profile inheritance with graph edges) in favor of flat, composable building blocks.

### Three levels

1. **Tools** — flat array of individual favorites (111 entries, 45 categories). Each has `id`, `category`, `when_to_use`, `alternatives`, `tags`. Tags replace graph edges.
2. **Toolkits** — small composable groups for ONE concern (59 entries). Each has `tools: [id, ...]`, optional `requires_toolkit`, optional `config_files`. Multiple toolkits compose into a full project.
3. **Recipes** — project types mapped to toolkit combinations (23 entries). Each has `match_keywords` for spec matching.

### Why toolkits, not "stacks"

The user's insight: a toolkit is a small set of tools for one concern (local-db, offline-sync, python-cli). Recipes compose multiple toolkits. This is more flexible than monolithic "stacks" — you can swap one toolkit without redefining the whole stack.

### Key design decisions

- **JSON not SQLite:** small data, hand-edited, version-controlled
- **Arrays not dicts:** orderable, each entry self-contained
- **Tags replace edges:** `tags: ["linting"]` finds all linters, no graph traversal
- **`requires` and `requires_toolkit`:** simple lists express dependencies
- **Config files as real files:** in `configs/<lang>/`, copied during scaffolding
- **Minimal templating:** only `${PROJECT_NAME}` and `${PROJECT_DESCRIPTION}` placeholders

## Config file storage

Every major scaffolding tool (cookiecutter, cargo-generate, CRA, yeoman) stores config as **real files on disk**. Key findings from research:

- Static files with minimal templating is the proven approach
- Full templates over fragment assembly for composite files (pyproject.toml) — TOML merging is brittle
- Config files: pyproject.toml, ruff.toml, Makefile (lint/format/format-check/check targets), conftest.py, .gitignore, mypy.ini

## Setup node (livetested)

The setup node sits between architect and decompose:
```
route-architect → route-setup → route-decompose
```

**Livetest result (board `setup-test`, Bookmark Manager CLI):**
- Copied all 6 config files into repo
- Replaced `${PROJECT_NAME}` with `bookmark-manager`, filled description from spec
- Merged python + global .gitignore patterns
- `ruff check .` passed clean (exit 0)
- `ruff format --check .` passed clean
- Decomposition created 4 tickets inheriting architect decisions AND referencing Makefile (`make check`) and conftest.py fixtures

## Tier-gated deviation rule

- T0/T1 (low importance): use preferences autonomously
- T2/T3 (important): propose alternatives, never silently drop a favorite
- Any deviation from a favorite requires an ADR stating WHY

## Verifier enforcement (Phase 3.5 — NOW LIVE, commit `f7be428`)

Critical finding: configured tooling is dead config until verifiers invoke it. Setup creates Makefile with lint/format-check/check targets, but verifier nodes only ran pytest.

**Fix (shipped):** Both verify and re-verify nodes in tech-lead-execute.json now have Phase 3.5: Lint + Format Check. After behavior tests pass (Phase 3), the verifier runs `make lint` and `make format-check` (or language-specific commands if no Makefile). Lint errors route through the same FAIL→fix→re-verify loop as test failures — no new edge needed.

Rules:
- Lint warnings = FINDINGS (don't block PASS)
- Lint ERRORS (ruff F, clippy -D) = FAIL
- Format mismatches = FINDINGS
- No linter configured = SKIP and note

The Makefile is the language-abstraction layer — same verifier body works for Python (ruff), Rust (clippy), TS (biome), Go (golangci-lint).

## Rejected designs (for reference)

- **Proposal 1 (flat per-language profiles):** no composition — user corrected: "seems like I can only use one language for everything"
- **Proposal 2 (profile inheritance + graph edges):** too complex — user said "make it simple"
- **awesome-copilot technology-stack-blueprint-generator:** wrong direction — analyzes existing codebases (reverse engineering), we needed forward declaration
