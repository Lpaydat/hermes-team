# Pattern: dev-port Workflow — Port/Migrate/Translate/Extract from Reference Repos

Created 2026-08-10 on branch `feat/dev-port-workflow`. Template: `templates/dev-port.json`.

## Problem

dev-dispatch builds from scratch — empty repo, spec only. But many real projects are ports, migrations, translations, or extractions of existing code:
- Language migration (Python → Rust)
- Open-source translation (adapt an existing repo)
- Combine multiple repos into a new one
- Build from existing tested code (like ngin's backup branch)
- Feature extraction (pull one self-contained module out of a larger project)

These projects have reference repos with existing implementations. The pipeline needs to know which spec stories are already implemented in the references (port them) vs which are gaps (build from scratch).

## Solution: dev-port Workflow

Triggered by `[port]` prefix on spec cards. Shares the downstream pipeline with dev-dispatch (setup, milestones, tech-lead-execute, milestone-gate). Only the first 3 nodes differ.

```
[port] spec card (with ref repo paths in body)
  → entry (command noop)
  → route-architect: reads spec + ref repos, builds COVERAGE MAP
     (which stories are covered/partial/gap in the references)
  → route-setup: scaffolds tooling (shared with dev-dispatch)
  → route-decompose: creates two ticket types:
     - PORT tickets (covered/partial stories): copy+adapt from ref files
     - BUILD tickets (gap stories): build from scratch
  → route-milestone: groups into milestones (shared with dev-dispatch)
  → [merges into tech-lead-execute → milestone-gate]
```

## Coverage Map

The architect's key output. A table mapping each spec story to its ref status:

```
| Story | Status | Ref location | Notes |
|-------|--------|-------------|-------|
| 1.    | covered | ref-repo:src/foo.rs | Direct port, adapt types |
| 2.    | partial | ref-repo:src/bar.rs | Needs rewrite for async |
| 3.    | gap     | — | No ref, build from scratch |
```

Status values: `covered` (direct port), `partial` (adapt significantly), `gap` (no ref implementation).

## Two Ticket Types

**PORT tickets** — title format `[ticket-NN] Port: <story>`. Body includes:
- The ref file path to port from
- What to adapt (language differences, API changes, conventions)
- Acceptance criteria from the spec

**BUILD tickets** — title format `[ticket-NN] <story>`. Body includes:
- Acceptance criteria from the spec
- Tech stack from architect decisions
- No ref implementation exists

Both fire tech-lead-execute independently (same `[ticket-` prefix trigger).

## Key Design Decisions

1. **Shares downstream pipeline** — setup, milestones, tech-lead-execute, milestone-gate are identical to dev-dispatch. Only architect + decompose differ.

2. **No routing diamond** — dev-port always goes through architect (no bug/research/ops routes). The `[port]` prefix is specific enough.

3. **Linear pipeline** — 5 nodes, 4 edges, no cycles. Instance completion is trivial (no fix↔re-verify deadlock risk).

4. **Spec card must include ref paths** — the body must contain `Repo:` (target) and `Ref:` or `Reference:` lines with filesystem paths. The architect extracts these to build the coverage map.

## Template Structure

```json
{
  "id": "dev-port",
  "trigger": {
    "source": "card_completed",
    "condition": {
      "assignee": "product-owner",
      "status": "done",
      "title_prefix_any": ["[port]"]
    }
  },
  "nodes": ["entry", "route-architect", "route-setup", "route-decompose", "route-milestone"],
  "edges": [
    {"from": "entry", "to": "route-architect"},
    {"from": "route-architect", "to": "route-setup"},
    {"from": "route-setup", "to": "route-decompose"},
    {"from": "route-decompose", "to": "route-milestone"}
  ]
}
```

No conditional edges. No cycles. No back-edges. Exit node: `route-milestone`.

## Workflow Naming — port vs compose (user decision, 2026-08-10)

Two distinct workflows, unified prefixes:

- **`[port]`** — ONE reference repo → one target. Same capabilities, different language/platform. Covers: language migration, open-source translation, feature extraction, modernization/dependency-slimming, monorepo splitting, dead code pruning, API surface redesign. The coverage map compares story-by-story — everything should be covered (PORT tickets only, zero or few gaps).

- **`[compose]`** — TWO OR MORE reference repos → one target product. Each ref repo covers different stories; the integration layer is a gap. Creates PORT tickets (from each ref) + BUILD tickets (the glue between them). Template: `templates/dev-compose.json` (built 2026-08-10, livetesting in progress).

  Key difference from dev-port: the architect builds a `source_map` (which ref repo covers which story) and the coverage map has a `Source` column. Port tickets are named `[ticket-NN] Port from <ref-name>: <story>` to track provenance. The decompose verifier checks that port tickets reference the correct ref repo and that BUILD tickets exist for integration gaps.

**Naming correction (user's insight):** I initially proposed 5 use cases (migration, translation, combine, extraction, framework-migration). The user caught that migration/translation/framework-migration are all the SAME thing from the workflow's perspective — same mechanism, same coverage map, same PORT tickets. Only the ref repo and target language change. The coverage map handles the nuance. So `[port]` unifies all single-ref cases.

Extraction does NOT need its own workflow — it's just port with a partial coverage map (spec says "I want feature X from this repo", architect marks only X as covered, everything else out of scope).

## Use Cases for `[port]`

All single-ref cases. Same workflow, same mechanism, same template:

- **Language migration**: port a Python CLI to Rust. Ref = the Python repo.
- **Open-source translation**: adapt an existing project to new conventions. Ref = the upstream repo.
- **Build from existing code**: ngin's backup branch has 20+ Rust files, 575 tests. Ref = the backup branch. Stories covered by backup code become PORT tickets. Gaps become BUILD tickets.
- **Feature extraction**: pull one self-contained module out of a larger project. Ref = the source monorepo. Covered = the feature; gap = scaffolding (new repo, CI, README, packaging).
- **Modernization / dependency slimming**: strip heavy deps for stdlib. Ref = original repo. PORT = core logic, BUILD = dependency-replacement rewrite.
- **Monorepo splitting**: split N independent packages into N standalone repos. Each package = PORT, repo scaffolding = BUILD.
- **Forking + specialization**: narrow a general tool for a specific use case. PORT = retained features, BUILD = specialization.
- **Dead code pruning**: cleaned version with only live code. PORT = live paths, BUILD = API repair.
- **API surface redesign**: "lite" version with simpler mental model. PORT = selected functions, BUILD = new wrapper.
- **Build system detachment**: extract from Bazel/Buck to cargo/go modules. Code unchanged, scaffolding rebuilt.

## Verified Test Fixtures for Feature Extraction

Two repos verified by cloning + inspecting source (2026-08-10). Both are good candidates for livetesting the dev-port extraction use case. Selection criteria: small utility (1-5 files, <500 LOC), clear single purpose, Rust/Go/Python preferred, extractable and cleanable as standalone tool.

### Fixture 1 (easy extraction): `muesli/reflow` → `dedent` package

| Attribute | Value |
|-----------|-------|
| Source | `github.com/muesli/reflow/dedent` (Go monorepo of text-formatting utils) |
| LOC | 73 source + 64 tests = 137 total |
| External deps | None (stdlib `bytes` only) |
| Internal deps | **Zero** — no imports from sibling reflow packages |
| Extraction difficulty | Easy — copy folder, rename module path, scaffold repo |

What it does: detects minimum common indentation across all lines and strips it. The `reflow` monorepo has 8 independent text-formatting packages; `dedent` is fully standalone. Extraction challenge is packaging (CI, README, LICENSE), not code decoupling.

### Fixture 2 (moderate extraction): `Textualize/rich` → `_ratio.py`

| Attribute | Value |
|-----------|-------|
| Source | `github.com/Textualize/rich/blob/master/rich/_ratio.py` (Python) |
| LOC | 153 |
| External deps | None (stdlib: `fractions`, `math`, `typing`) |
| Internal deps | **Zero** — no imports from the rest of rich |
| Extraction difficulty | Moderate — code is decoupled, but needs API/docs/packaging work |

What it does: ratio-distribution algorithm for terminal layout. Given a total width and edges with `size`/`ratio`/`minimum_size` constraints, distributes space proportionally. Used by rich's `table.py`, `layout.py`, `progress.py`, `console.py`. Defines a `Protocol` (`Edge`) that lets any object participate — generic enough for any layout system. Extraction challenge: establish public API, write usage examples, brand as general-purpose layout solver.

### How to use these for livetesting

For a feature-extraction livetest, create a `[port]` spec card:
- **Ref**: `/path/to/cloned/reflow` (or `rich`)
- **Repo**: `/tmp/dedent-standalone` (empty target repo)
- **Spec**: "Extract the dedent text-formatting utility from reflow into a standalone Go library with CI, README, LICENSE, and examples."

The coverage map should mark dedent's core logic as `covered` (direct port) and the repo scaffolding (go.mod, CI, README, LICENSE, examples) as `gap` (BUILD tickets). This validates that the PORT/BUILD split works for extraction, not just migration.

## Verification

- 23/23 structural checks pass (parse, 5 nodes, 4 edges, trigger prefix, linear pipeline, coverage map, port+build tickets, engine load)
- 28/28 engine tests pass (test_completion, test_back_edges)
- Engine loads 17 templates total (dev-port is the 16th, dev-compose is the 17th)

### Livetest results (2026-08-10, in progress)

Both dev-port and dev-compose fired correctly on first tick. Coverage maps built accurately:

**dev-port (port-csv2md: Python csv2md → Rust):**
- Architect coverage: 3 covered, 1 partial, 0 gaps (correct — csv2md covers nearly everything)
- All 4 tickets are PORT tickets (no BUILD tickets — correct for a full migration)
- dev-port instance completed cleanly, tech-lead-execute firing on tickets

**dev-compose (compose-dataviz: json-to-csv + termchart → dataviz):**
- Architect coverage: 3 covered, 0 partial, 1 gap (correct — integration layer is the gap)
- source_map correctly attributes: story 1 → termchart, story 2 → json-to-csv + termchart, story 3 → termchart, story 4 → gap
- 2 PORT tickets ("Port from termchart", "Port from json-to-csv") + 1 BUILD ticket ("Auto-detect numeric columns")
- dev-compose instance completed cleanly, tech-lead-execute firing on tickets

Both downstream pipelines (tech-lead-execute → milestone-gate) are identical to dev-dispatch — proven across 4 prior e2e tests.
