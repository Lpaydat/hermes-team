---
name: project-config-scaffolding
description: "Scaffold static config files into a new project via manifest-driven resolution. Use when setting up a project's tooling configs after architecture review and before ticket decomposition. Language-agnostic: Python (ruff/pyproject.toml), Rust (clippy/rustfmt), TypeScript (biome), Go (golangci-lint). All preferences flow from tech-preferences.json (117 tools, 63 toolkits, 41 recipes) — NEVER hardcode language-specific tools in template body text. Includes compatibility research: auth/backend matrix, Drizzle DB coverage, toolkit conflict resolution, chart library performance hierarchy, animation/media/validation ecosystem, Node-RED for IoT/automation, Astro for content sites, language-aware TUI per language, and verifier lint enforcement (Phase 3.5 — make lint + make format-check now enforced on every dev card). Board isolation via active-projects.json allowlist restricts trigger scanning to active boards only."
---

# Project Config Scaffolding

When a new project is promoted from prototype to production, it needs real config files — linters, formatters, test runners, gitignore. This skill defines the pattern for storing those files centrally and copying the right set into each project based on the architect's `tech_stack` decision.

## Pipeline placement

```
[spec] → [architect] → [scaffold configs] → [decompose] → [ticket-NN...]
```

The scaffold step runs AFTER the architect gate (which decides `tech_stack`) and
BEFORE ticket decomposition. You cannot scaffold before architecture — you don't
know the stack yet.

## CRITICAL: No hardcoded tool assumptions

**NEVER hardcode language-specific tools** in template body text, skill prose, or
config file instructions. All tool preferences flow from `startup/tech-preferences.json`
through the architect. The setup node detects the language from the architect's
`tech_stack` output and applies language-appropriate configs.

**The Makefile is the language-abstraction layer.** Verifier nodes call `make check`,
not bare tool commands. The Makefile maps generic targets to language-specific tools.

This rule was established after the user discovered hardcoded `pytest` and `paved road`
(Python-only) assumptions in 5 places across the pipeline (commit `cd6df82` + `396410f`).
Recipe livetest proved 2 of 3 specs got Python instead of the user's preferred Rust.
See Pattern 15 in `loop-engine-convergence-patterns` for the full audit process (search all
16 templates + skills for hardcoded patterns, classify each as standalone-command / hardcoded-default /
language-detection-block, fix the first two, leave the third).

## Directory layout

Store real config files as a sibling to workflow templates:

```
startup/scripts/workflow_engine/configs/
├── manifest.json       ← index: maps tech_stack string → file list
├── _shared/            ← language-agnostic (copied to every project)
│   ├── .gitignore
│   └── Makefile
└── python/             ← one dir per language
    ├── pyproject.toml  ← composite: [project] + [tool.ruff] + [tool.pytest]
    ├── ruff.toml       ← standalone variant
    └── conftest.py
```

One directory per language/runtime, mirroring the paved-road stack. `_shared/`
holds cross-language files copied to every project regardless of stack.

## Manifest-driven file discovery

The scaffolding step does NOT hardcode file paths. It reads `manifest.json`,
which maps a stack key to a declared file set:

```json
{
  "version": 1,
  "stacks": {
    "python-paved": {
      "match_keywords": ["python", "pytest"],
      "files": [
        {"source": "_shared/.gitignore", "target": ".gitignore"},
        {"source": "python/pyproject.toml", "target": "pyproject.toml", "substitute": true},
        {"source": "python/conftest.py", "target": "tests/conftest.py"}
      ]
    }
  }
}
```

A resolver script (`setup_configs.py`) reads the manifest, matches the
architect's `tech_stack` output string to a stack key via `match_keywords`, and
copies the declared files. This enables keyword-based stack resolution from
free-text strings like `"python3 + pytest + sqlite"`.

## Composite configs: full template over fragment assembly

`pyproject.toml` is the hard case: `[project]` metadata + `[tool.ruff]` +
`[tool.pytest.ini_options]` in one file.

**Use a full template file with `${}` placeholders** for the two project-specific
values (`${PROJECT_NAME}`, `${PROJECT_VERSION}`). The resolver does simple string
substitution.

**Do NOT use fragment assembly** (storing `[tool.ruff]` and `[tool.pytest]` as
separate fragments to concatenate). Reasons:

1. Requires TOML-aware merging — can't blindly append sections if `[project]`
   already exists.
2. Adds a build step and a TOML parser dependency.
3. The fragments are only ever used together on the paved road — there is no
   reuse benefit from splitting them.

If a project needs BOTH a standalone `ruff.toml` AND a `pyproject.toml` (ruff
auto-discovers `ruff.toml` and ignores `[tool.ruff]`), use a separate manifest
stack entry (`python-ruff-standalone`) with a `pyproject-minimal.toml` that
omits `[tool.ruff]`.

## Static-first templating

Minimize `${}` placeholders — every substitution is a failure mode.

| File | Strategy |
|------|----------|
| `ruff.toml` | 100% static — copy as-is |
| `conftest.py` | 100% static |
| `.gitignore` | 100% static |
| `Makefile` | 100% static |
| `pyproject.toml` | Two `${}` only: `${PROJECT_NAME}`, `${PROJECT_VERSION}` |

Config files encode team-wide rules identical across every paved-road project.
There is nothing project-specific to substitute in a linting config.

## Makefile targets: scaffold check-only variants (CRITICAL)

The scaffolded `Makefile` must include **check-only** variants of any tool that
mutates files, because the downstream verifier is forbidden from editing dev
code (verifier Phase 4: "Do NOT Edit Dev Code"). `ruff format` without
`--check` rewrites files; `ruff format --check` reports without touching.

Required targets on the paved road:

```makefile
.PHONY: test lint format format-check check

test:
	pytest -v

lint:
	ruff check src tests

format:
	ruff format src tests

format-check:
	ruff format --check src tests

check: lint format-check test
```

**The `check` target is the canonical "is this code shippable" gate.** It
folds lint + format-check + test into one command. Verifier nodes and the close
node should run `make check`, not bare `pytest -q` — otherwise unformatted or
lint-failing code ships through the pipeline. (See lesson #42 in
`workflow-engine-gauntlet-lessons`.)

**The Makefile is the language-abstraction layer.** Verifier node bodies call
`make lint` / `make format-check` / `make check`, not `ruff check` directly.
This keeps the template language-agnostic: the same verifier body works for
Python (ruff) today and Node (eslint/prettier) tomorrow, because the Makefile
maps the generic target name to the language-specific tool. If you hardcode
`ruff check` in the verifier body, the template breaks the moment a project
deviates to a non-Python stack.

## Verifier enforcement contract (NOW LIVE — commit `f7be428`)

Scaffolding tooling without enforcing it is **dead config.** The setup node
creates `ruff.toml`, `pyproject.toml`, and the Makefile, but unless downstream
verifier nodes actually invoke `make lint` / `make format-check`, a developer
can land unformatted, lint-failing code and the workflow will PASS it.

**This is now enforced.** The verify and re-verify nodes in tech-lead-execute.json
have Phase 3.5: Lint + Format Check. After behavior tests pass (Phase 3), the
verifier runs `make lint` and `make format-check` (or language-specific commands
if no Makefile). Lint errors route through the same FAIL→fix→re-verify loop as
test failures — no new edge needed.

The contract is bidirectional:
- **Setup node (this skill):** scaffolds the Makefile with `lint`,
  `format-check`, and `check` targets. Missing `format-check` is a setup-node
  bug, not a verifier bug.
- **Verifier nodes (Phase 3.5):** runs `make check` (or `make
  lint && make format-check`) and treats lint errors as `verdict = FAIL`, which
  routes through the existing verify→fix loop with zero edge changes.

When designing or auditing a pipeline, check both sides: does the scaffold
include check-only targets, and do the verifiers call them?

## Implementation: command node

In a workflow template, the scaffold step is a `command`-type node (no agent
card, runs a shell script synchronously, completes in the same tick):

```json
{
  "id": "setup_configs",
  "type": "command",
  "profile": "",
  "skill": "",
  "body_template": "",
  "command": "python3 .../configs/setup_configs.py --project-dir ~/projects/${trigger.slug} --project-name '${trigger.title}' --tech-stack '${nodes.architect.output.tech_stack}'",
  "depends_on": ["architect"]
}
```

## Tech Preferences System — tools, toolkits, recipes

The setup node and architect both consume the user's tool preferences. The architect reads `startup/tech-preferences.json` to decide tech stack (prefer favorites, override if clearly better, propose alternatives for T2+). The setup node reads the same file to choose which config files to copy.

**Three levels (user's final design — NOT per-language profiles):**

- **Tools** — flat array of individual favorites (`ruff`, `pytest`, `react`, `sqlite`). Each has `id`, `category`, `when_to_use`, `alternatives`, `tags`. Tags replace graph edges for discovery.
- **Toolkits** — small composable groups for ONE concern (`python-cli` = python3+argparse+pytest+ruff, `local-db` = sqlite+drizzle, `offline-sync` = electric-sql). Each has `tools: [id, ...]`, optional `requires_toolkit`, optional `config_files`. Multiple toolkits compose into a full project.
- **Recipes** — project types mapped to toolkit combinations (`cli-tool` → [python-cli], `mobile-offline` → [react-mobile-ui, local-db, offline-sync]). Each has `match_keywords` for spec matching.

**File:** `startup/tech-preferences.json` (v2: 117 tools, 63 toolkits, 41 recipes)

Covers Rust (priority), Python (prototype), TypeScript (frontend), Go (ecosystem edge). Includes all databases (PostgreSQL, Neon, SQLite, Supabase, Pocketbase, MongoDB, Qdrant, sqlite-vec, SurrealDB, Dgraph, Neo4j, Memgraph, FalkorDB, GraphQLite, ArangoDB, Cloudflare D1, sqlx, rusqlite), auth (Better Auth, Logto, SuperTokens), AI stacks (OpenAI-compatible priority, AI SDK+Mastra, rust-genai, pydantic-ai/LangGraph), UI libraries (shadcn/ui, gluestack, shadcn-svelte), queues (Redis, RabbitMQ, BullMQ, Cloudflare Queues), payments (Stripe), workflows (Temporal, Inngest), charts (Chart.js, ECharts, Lightweight Charts, uPlot, Visx, deck.gl, Cytoscape.js, React Flow, Plotly.js), animation (Motion, anime.js, GSAP, Auto-Animate), media (Vidstack, Media Chrome), validation (Zod, Valibot, serde+validator, pydantic, go-playground/validator), state management (Zustand, TanStack Query, React Hook Form, TanStack Table, Sonner), TS backend (Hono, PartyKit, Resend), automation (Node-RED), content sites (Astro), TUI frameworks per language (ratatui/Rust, Textual/Python, OpenTUI/TypeScript, Bubble Tea/Go), and all canonical Rust/Python/Go backend crates.

**Chart library selection (verified performance, not claimed):**

Performance hierarchy: `uPlot > Chart.js > ECharts > Lightweight Charts >> Recharts`

| Use case | Pick | Why |
|---|---|---|
| General (bar/line/pie) | **Chart.js** | 68KB canvas, fast, framework-agnostic |
| Complex/power (100+ types, real-time) | **ECharts** | 332KB canvas+WebGL, LTTB downsampling built-in |
| Financial/trading | **Lightweight Charts** | 45KB, TradingView candlestick/volume |
| Real-time streaming | **uPlot** | 22KB, fastest, TypedArrays, handles millions of points |
| Scientific (contour/violin/isosurface/SPLOM) | **Plotly.js** | 1.36MB — ONLY when ECharts can't handle it. Justify in ADR. |
| Graph/network (Obsidian-style) | **Cytoscape.js** | What Obsidian actually uses |
| Node editor / flow diagrams | **React Flow** | Interactive node-based UIs |
| Custom React charts | **Visx** | D3 + React primitives |
| Geospatial | **deck.gl** | Large-scale WebGL maps |

ECharts handles most scientific charts natively (3D scatter, surface, heatmap, box plot, parallel coords). Plotly only needed for: contour, violin, isosurface, volume rendering, SPLOM, native error bars. Recharts (148KB SVG) is the worst performer — use only for shadcn/ui integration with small datasets.

**Key decisions:** Drizzle ORM (schema IS type system), Biome (TS linting), Better Auth (MIT primary), shadcn/ui family (Tailwind-based UI), all graph DBs included with different use cases.

"Prefer OSS" means free to use without subscription — BSL 1.1/SSPL acceptable (production free, restriction only on reselling as hosted DBaaS).

**Config files stored as real files** in `startup/scripts/workflow_engine/configs/`:
```
configs/python/     ← pyproject.toml, ruff.toml, Makefile, conftest.py, .gitignore, mypy.ini
configs/rust/       ← clippy.toml, rustfmt.toml, Makefile (cargo clippy/fmt/test), .gitignore
configs/node/       ← biome.json, Makefile (vitest/biome), .gitignore
configs/go/         ← .golangci.yml, Makefile (go test/golangci-lint/gofmt), .gitignore
configs/_shared/    ← .gitignore.global (OS/editor patterns)
```

All 4 language directories are livetested. The setup node detects the language from the architect's `tech_stack` output and copies the matching configs. If no configs exist for a language, the tech-lead creates minimal ones following the same pattern (linter + formatter + Makefile + .gitignore).

**LIVETESTED (27 recipes, 7 batches — all passed):**
- Batch 1: cli-tool (Rust), api-service (Rust/axum), tui-app (Rust/ratatui)
- Batch 2: cli-tool-with-storage (Rust+AES-256), library-sdk (Rust crate), mobile-online (RN/Expo+gluestack)
- Batch 3: web-app-react (React+shadcn/ui), static-site (SvelteKit), game (React+shadcn/ui)
- Batch 4: desktop-app (Tauri+React), ai-app (FastAPI+sqlite-vec), graph-cli (Rust+SQLite)
- Batch 5: web-app-data-viz (React+Chart.js+TanStack Table), web-app-financial (React+Lightweight Charts), web-app-node-editor (React+React Flow), web-app-media (React+Vidstack+Hono)
- Batch 6: api-service-ts (Hono+CF D1), api-service-go (Go stdlib net/http), ai-app-python (FastAPI+pydantic-ai), workflow-app (Rust+Temporal)
- Batch 7: bot (Rust+teloxide), browser-extension (React+MV3), iot-automation (Node-RED+MQTT), web-app-graph-viz (React+Cytoscape.js)

All 27: architect correctly read tech-preferences.json, matched specs to recipes, chose correct toolkits. Setup node created correct per-language config files. The architect showed sophisticated decision-making — e.g. chose SQLite over GraphQLite for single-hop adjacency queries (ADR-justified), chose Python over Rust for AI/RAG (ecosystem advantage), deviated from sqlc to database/sql for a 2-query Go service (justified), dropped Better Auth for a read-only app (no auth surface).

Config files exist for all 4 languages (python/, rust/, node/, go/) and were verified during livetest across all 7 batches.

**Design lesson (user's correction):** I proposed over-engineered designs TWICE — first flat per-language profiles with no composition, then profile inheritance with graph edges and conditional logic. The user simplified to tools + toolkits + recipes: flat lists, composable building blocks, no inheritance, no graph. When the user says "keep it simple," they mean structurally simple, not feature-poor.

**JSON not database (user's decision):** At 113 tools, the user asked if we should switch to a database. Answer: keep JSON. The architect loads the entire file into context — it doesn't query it. SQLite would make it unreadable for hand-editing, un-diffable (no version control), and add a tool dependency. Only switch if the file grows 10x (1000+ tools).

**TUI must match project language (user's correction):** TUI frameworks should match the project's backend language, not always default to Rust. A Python AI tool needing a dashboard should use Textual, not rewrite in Rust just for the TUI. Added: ratatui (Rust), Textual (Python), OpenTUI (TypeScript/Zig core), Bubble Tea (Go). The `when_to_use` field on each tool guides the architect to match TUI to project language.

**Astro for content sites (user's decision):** SvelteKit ships Svelte runtime + router even when fully static. Astro ships zero JS by default — better for content sites (blogs, docs, marketing). Astro uses Svelte components via @astrojs/svelte. The `static-site` recipe was changed from `svelte-web-ui` to `astro-content`. SvelteKit stays for interactive web apps.

See [references/tech-preferences-system-design.md](references/tech-preferences-system-design.md) for the full 5-subagent analysis: scaffolding tools research (cookiecutter/cargo-generate/CRA), profile inheritance (extends + deep-merge), config file storage (static templates over fragment assembly), architect consumption (tier-gated deviation), and verifier enforcement (make lint + format-check).

See [references/chart-library-decisions.md](references/chart-library-decisions.md) for the full chart library comparison: 9 included (scored), 10 excluded (scored + reason), ECharts scientific coverage verified from source, performance hierarchy measured not claimed, decision matrix.

## Reference

- [references/design-spec.md](references/design-spec.md) — the full design document with complete example files, resolver script source, and manifest schema. Originally produced for the paved-road Python stack (python3 + pytest + ruff).
- [references/tech-preferences-system-design.md](references/tech-preferences-system-design.md) — the tech-preferences system design from 5-subagent analysis. Covers two-file split (preferences + configs), profile inheritance, polyglot layering, and verifier lint enforcement.
- [references/verifier-lint-enforcement.md](references/verifier-lint-enforcement.md) — the cross-node contract gap: scaffolding tooling without enforcement is dead config. Why the scaffolded Makefile needs `format-check`, why verifiers must call `make check` not bare `pytest`, and the general cross-node enforcement principle.
