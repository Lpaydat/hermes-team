# ngin Grill Session — Complete Example

Real grill session (2026-08-05) that produced 8 ADRs + CONTEXT.md + spec for the
ngin harness-agnostic workflow orchestration platform. This is a reference for
how the grill-with-docs pattern works end-to-end.

## What was grilled

Extracting Hermes's task dispatch + workflow orchestration capabilities into a
standalone Rust platform (ngin) that works with any agent runtime via a harness trait.

## Key decisions and how they were reached

### ADR-0001: Harness trait (pluggable agent runtimes)

Research phase: read Paperclip's adapter system (14 built-in types including
hermes_local, hermes_gateway, pi_local, claude_local). Paperclip uses npm packages
with schemas. For ngin (Rust), a trait-based approach is simpler and doesn't need
a package manager. Decision: `trait AgentHarness` with implementations per runtime.

### ADR-0002: Daemon spawns, agents never poll (HARD RULE)

The PO proposed "agents poll bd ready" THREE times during the grill. The user caught it
each time. The correct model: daemon claims issue → spawns agent → passes issue ID
via env var → agent reads/writes beads → daemon polls for completion. Same as Hermes
kanban's dispatch pattern. Recorded as a hard rule + ADR + memory entry.

### ADR-0003: Unified graph format (nginbot-api + 8 additions)

Ran 5 subagents to compare nginbot-api's graph format vs Hermes templates vs ngin's
flat steps[]. nginbot-api's IGraphSchema is structurally richer (source directives,
composite edges, expr-eval, versioning). 8 additions needed: triggers, COMMAND/WAIT
nodes, maxIterations, exists/is-empty operators, loop index, body/title templates,
title prefix isolation.

### ADR-0004: Daemon owns graph walk

Daemon walks the graph node-by-node, dispatching each as a separate run. Worker
never sequences nodes. Required for per-node crash recovery, back-edge iteration,
and trigger composition.

### ADR-0005: Execution-layer features

7 features mapped: heartbeat, max_runtime, per-profile concurrency, typed blocks,
workspace management, worker-config injection, attachments. All solvable in daemon
SQLite + beads. No beads modifications needed.

### ADR-0006: Work in existing repo

ngin repo already has Cargo workspace (daemon + ngin-db + tui). Adding modules is
natural. Starting fresh means re-cloning proven infrastructure.

### ADR-0007: Build phasing

Phase 1: harness + dispatch (smaller, immediate value). Phase 2: graph walker
(bigger, benefits from real Phase 1 usage).

### ADR-0008: Parallel system (NOT replacement)

The most important framing decision. ngin does NOT replace Hermes. Both coexist.
"Building twitter, not deleting facebook." The PO initially framed multiple ADRs
as "replacing Hermes" — user corrected. All docs rewritten.

## Pattern: CONTEXT.md as living document

During the grill, CONTEXT.md was updated inline as decisions crystallized:
- Terms resolved (Run, Flow, Node, Harness, Heartbeat) → Language section
- Hard rules (daemon spawns, beads as tracker, two databases, don't touch Hermes) → Hard Rules section
- Each ADR written immediately after its decision was reached

## Pattern: ADR-driven spec

The spec's Implementation Decisions section references ADRs directly rather than
re-explaining decisions. The ADRs are the design record; the spec is the requirement.

## Mistakes made and how they were caught

1. **Proposed agent polling 3 times** — caught by user each time. Fixed via ADR-0002 + CONTEXT.md Hard Rule #1 + memory.
2. **Described Hermes dispatcher wrong** — said "each gateway polls for its own cards." Actually: ONE dispatcher with singleton lock. Caught when user asked to verify. Subagents had already documented it correctly.
3. **Framed as "replacement"** — multiple ADRs said "replaces Hermes kanban." User corrected: parallel system. Required rewriting 5 ADRs + spec.
4. **Coupled to Hermes** — harness trait listed "PiHarness, ProcessHarness" but not a Hermes harness, despite Hermes being the first target. Fixed: "first implementation targets Hermes runtime."
5. **Left implementation undecided** — spec said "or reuse cwd" for workspace column. Fixed: decide in the spec, not in the architect phase.
6. **Added backward compat / migration language** — spec contained "existing tables (keep)", "already exists in bd.rs", "cutover/migration tooling" out-of-scope. User corrected: "we don't need any backward compatibility, we don't need migration code. this should be complete from the first build." Required removing all legacy/migration/backward language from the spec.
7. **Didn't check repo archived status** — ADR-0006 said "work in ngin repo" but the repo had SUPERSEDED.md. The tech-lead agent caught this during pipeline execution and blocked with `needs_input`. The PO had to un-archive the repo mid-pipeline.

## Automated spec review pattern

Manual review passed "no issues" twice. Automated Python scan found 12 hits
the third time. The script checks for: replace/legacy/migration/cutover
language, sequential story numbering, phase boundary leaks, contract
completeness. Use grep as a final gate:

```bash
grep -rn "replace\|legacy\|migration\|cutover\|backward" spec.md
```

Then verify story numbering is sequential, phase boundaries are clean (no
Phase 2 concepts in Phase 1), and the harness contract is complete.

## Pipeline dispatch: dedicated board

Spec was dispatched on a dedicated `ngin` board (not `hermes-hq`). The Hermes
dispatcher auto-discovers all boards every tick (`_kb.list_boards(include_archived=False)`).
Workers inherit `HERMES_KANBAN_BOARD` via `_default_spawn` env injection.

**Engine tick CLI syntax:** `python3 workflow_engine/main.py --verbose tick`
(NOT `tick --board X`). The engine scans all boards by default.
