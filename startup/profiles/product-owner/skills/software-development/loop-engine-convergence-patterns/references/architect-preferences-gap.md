# Hardcoded Tool Preferences — Found, Diagnosed, and FIXED

## Problem (RESOLVED)

The pipeline had hardcoded tool assumptions in FIVE places:
1. `architecture-gate/SKILL.md` — hardcoded "paved road" (Python3 + pytest + JSON/sqlite)
2. `dev-dispatch.json` architect node body — "use the paved road"
3. `dev-dispatch.json` setup node body — Python-only instructions
4. `tech-lead-execute.json` — hardcoded `pytest -q` in close, merge-verify, and verify nodes
5. `debug-fix.json` — hardcoded `pytest -q` in verify node

The user's reaction: "I didn't even know you hardcoded it. are there any other hardcoded in the workflow too? I don't want it."

## Evidence (recipe livetest, board `recipe-test`)

Three specs tested different recipes:

| Spec | Expected stack | Architect chose | Match? |
|------|---------------|-----------------|--------|
| CSV to JSON Converter (cli-tool) | Rust CLI | **Rust** (spec explicitly mentioned Rust) | YES |
| URL Shortener API (api-service) | Rust + axum | **Python + FastAPI** (hardcoded paved road) | NO |
| System Metrics TUI (tui-app) | Rust + ratatui | **Python + curses + psutil** (hardcoded paved road) | NO |

2 of 3 recipes got Python instead of the user's preferred Rust.

## Fix Applied (commit `cd6df82` + `396410f`)

ALL hardcoded tool assumptions removed from the entire pipeline:

### architecture-gate SKILL.md
- Replaced "Paved road (the approved stack)" section with "Preferred stack (from tech-preferences.json)"
- Instructions: read `tech-preferences.json`, match spec to recipe, compose toolkits, check `incompatible_with`

### dev-dispatch.json architect node
- "use the paved road" → "read tech-preferences.json, match to recipe, use toolkits"
- Metadata example: hardcoded "python3 + pytest + sqlite" → generic "languages and tools from tech-preferences.json"

### dev-dispatch.json setup node
- Python-only instructions → language-aware for all 4 languages (Python, Rust, TS, Go)
- Hardcoded `ruff check` → language-specific linter/formatter per language
- Metadata: hardcoded values → "detected"

### tech-lead-execute.json
- close node: hardcoded `pytest -q` → `make check` or language detection
- merge-verify node: hardcoded `pytest -q` → language detection
- verify node: hardcoded `test_behavior.py` → multi-language test paths

### debug-fix.json
- verify node: hardcoded `pytest -q` → language detection

## Fix Verified (board `recipe-test2`, commit `cd6df82` + `396410f`)

After removing all hardcoded preferences, retested the same two specs:

| Spec | Before (hardcoded) | After (reads tech-preferences.json) |
|------|---------------------|--------------------------------------|
| URL Shortener API (api-service) | Python + http.server + sqlite3 | **Rust + axum** composed with sqlite-local |
| System Metrics TUI (tui-app) | Python + curses + psutil | **Rust + ratatui** + crossterm + sysinfo |

Both now match the user's preferred Rust-first stack. The architect reads `tech-preferences.json`, matches specs to recipes (api-service → rust-api toolkit, tui-app → rust-tui toolkit), and selects correct tools.

## Structural Rule (USER'S DIRECTIVE)

**NEVER hardcode language-specific tools in template body text or skill prose.** All tool preferences flow from `startup/tech-preferences.json` through the architect. Templates and skills must be language-agnostic — they use `make check` (Makefile abstraction) or language detection, never bare tool commands.

The Makefile IS the language-abstraction layer. Verifier nodes call `make check`, the Makefile maps generic targets to language-specific tools.

## Audit method — how to find ALL hardcoded preferences

The user asked "are there any other hardcoded in the workflow too?" — a systematic audit was needed. Method:

1. Search all template body text for language-specific tool commands:
   ```
   search_files(pattern="pytest|cargo test|ruff check|make check|make lint",
                path="startup/scripts/workflow_engine/templates")
   ```
2. Search all skill prose for language-specific stack declarations:
   ```
   search_files(pattern="paved.road|python3|argparse|sqlite|pytest|ruff",
                path="startup/profiles/architect/skills")
   ```
3. For each match, check context: is it inside a language-detection block ("Python: pytest, Rust: cargo test") or a standalone hardcoded command? Standalone = fix. Language-detection = fine.
4. Check the metadata schema examples in template bodies — "tech_stack: '<e.g. python3 + pytest + sqlite>'" is a hidden hardcode.

Found 5+ locations across 3 templates and 1 skill. All fixed in commit `cd6df82` + `396410f`.

## Related

- `references/tech-preferences-design.md` — the three-level tools/toolkits/recipes system
- `references/tech-stack-research-2025.md` — verified 2025 research on all tools
