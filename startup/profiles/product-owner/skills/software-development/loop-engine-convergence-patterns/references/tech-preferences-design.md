# Tech-Preferences System Design

## Context

The user wanted a preference database for declaring favorite tools (linting rules, test frameworks, storage choices, etc.) that the architect and setup node consult when deciding tech stack and scaffolding projects. Key requirements from the user:

1. "I want we have the one db that we collect tools I like"
2. "when consider what tools to use, like linting rules, will give these choices higher priority. but not always pick"
3. "if the other choices are clearly better or more suitable for the job, it can propose to me in important projects. or decide by itself in lower important projects"
4. "for mobile, I might prefer react-native + db of choice based on the feature and app nature"
5. "some web I might prefer astro, while some is svelte, but other is react"
6. "use rust as main code with wasm to responsible for logic together with js/ts/react as frontend"
7. "it might be a smaller list, that can compose together to be full stack"

## Evolution (3 rejected proposals)

### Proposal 1 — flat per-language profiles

Tools organized by language. Profiles = flat stack per project type. User rejected: "from your example, it seems like I can only use one language for everything."

### Proposal 2 — profiles with inheritance + graph edges

Profile inheritance (`extends`), `tool_overrides` with deep-merge, `requires_toolkit` dependencies. User rejected: "make it simple."

### Proposal 3 — the user's own design (ACCEPTED)

Three levels: tools, toolkits (composable building blocks for one concern), recipes (project types → toolkit combinations). Flat lists, no inheritance, no graph, no conditionals. Tags and simple references express relationships.

## Final structure

```
startup/tech-preferences.json (v2)
├── tools[]       — individual favorites (64 entries)
├── toolkits[]    — composable groups (39 entries)
└── recipes[]     — project types (23 entries)
```

### Tool entry
```json
{
  "id": "ruff",
  "name": "Ruff",
  "category": "linting",
  "description": "Fast Python linter and formatter written in Rust",
  "when_to_use": "Always for Python projects. Replaces flake8 + black + isort",
  "platforms": ["linux", "macos", "windows"],
  "tags": ["linting", "formatting", "python"],
  "alternatives": ["flake8", "pylint", "black"],
  "config_files": ["configs/python/ruff.toml"]
}
```

### Toolkit entry
```json
{
  "id": "python-cli",
  "name": "Python CLI Basics",
  "tools": ["python3", "argparse", "pytest", "ruff"],
  "config_files": ["configs/python/"]
}
```

Optional `requires_toolkit` expresses dependencies (offline-sync requires local-db).

### Recipe entry
```json
{
  "id": "cli-tool",
  "name": "CLI Tool",
  "match_keywords": ["cli", "command-line", "terminal", "script"],
  "toolkits": ["python-cli"]
}
```

## Design decisions

- **JSON not SQLite:** small data, hand-edited, version-controlled, hierarchical config snippets
- **Arrays not dicts:** orderable, easy to add/remove, each entry self-contained
- **Tags replace edges:** no graph traversal needed — `tags: ["linting"]` finds all linters
- **`requires` and `requires_toolkit`:** simple lists express hard dependencies without a graph
- **`when_to_use` on every level:** tools, toolkits, AND recipes — makes preferences actionable
- **Config files as real files:** copied during scaffolding, not generated from JSON
- **`${PROJECT_NAME}` placeholder:** minimal templating, not Jinja2 or Liquid

## Consumers

1. **Architect** reads tech-preferences.json when deciding tech stack during T0-T3 triage. The architecture-gate SKILL.md references this file. Livetest confirmed: API spec → Rust+axum (was Python before fix), TUI spec → Rust+ratatui (was Python+curses).
2. **Setup node** reads tech-preferences.json and copies config files from `configs/<lang>/` to project repo.
3. **Verifier** runs `make lint && make format-check` (created by setup's Makefile) on every dev card diff.

## Tier-gated deviation rule

- T0/T1 (low importance): use preferences autonomously, decide and proceed
- T2/T3 (important): propose alternatives to human, never silently drop a favorite
- Any deviation from a favorite requires an ADR stating WHY it was rejected

## Research that informed the design

Subagent research on scaffolding tools (cookiecutter, cargo-generate, CRA, yeoman, plop, degit):
- Every tool stores config as real files on disk, never inline JSON
- Static files with minimal templating is the proven approach
- For composite files (pyproject.toml): full templates, not fragment assembly

awesome-stacks (stackshareio): the right model — simple named stacks with tool lists, organized by category. No complex logic.

awesome-copilot technology-stack-blueprint-generator: WRONG model for us — it analyzes existing codebases (reverse engineering). We needed the opposite: declare preferences forward.
