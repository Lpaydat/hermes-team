# ngin Build Plan — Dependency Analysis (2026-08-05)

Session-specific analysis of the 21-unit IMPLEMENTATION-PLAN.md dependency
graph, verified against actual daemon source code. Read when working on the
ngin build plan, sequencing dev tickets, or deciding what to parallelize.

## Verified dependency questions

### Does graph walk (2.2) need the harness trait (story 3)?

**No hard dependency.** Graph walk dispatches TASK nodes by creating a beads
issue and spawning a run. Today, spawning goes through `spawn.rs`'s
`ProcessSpawner` + `RunnerEnv` traits — NOT the spec's unified `AgentHarness`
trait, which doesn't exist yet (no `harness.rs` in the tree; story 3 is marked
`[PARTIAL]` in the plan).

Graph walk (2.2) can be built and tested against the existing spawner
abstraction. The plan treats harness-trait unification as an impl detail that
"falls out of units 0.4 + 0.5" — NOT a stated dependency of 2.2. This is
correct.

**Risk:** if graph walk is built before harness unification, it couples to
`ProcessSpawner` and needs a mechanical refactor when `AgentHarness` lands.
Low risk. Mitigate: land harness unification (0.4+0.5) before or with 2.2.

### Does triggers (2.5) need graph walk (2.2)?

**Testable without, functionally inert without.** Triggers instantiate
workflow instances (create `workflow_instances` row); the graph walker then
advances those instances. A trigger that fires with no walker is a no-op.

For the trigger unit's own tests (match/dedup/watermark/self-trigger
suppression), you can assert "instance row created" without the walker. So 2.5
is testable without 2.2 but functionally inert without it. The plan's dependency
(2.5 depends on 2.1+2.2) is conservative-but-right.

## Hidden dependencies the plan misses

1. **Triggers (2.5) → graph parser (1.1).** Trigger condition matching
   (`title_prefix`, `assignee`, `metadata`) parses the top-level `triggers`
   block from the flow JSON. The plan says 2.5 depends on 2.1+2.2 but does NOT
   list 1.1. You cannot match trigger conditions without first parsing the
   triggers block that 1.1 produces. **Add 1.1 as a dependency of 2.5.**

2. **RESET/back-edges (2.4) → idempotency extension.** The existing
   `idempotency.rs` generates step-index keys (`run-{id}-step-{n}`). Story 32
   requires *iteration-aware* keys. The plan mentions this under 2.4 but the
   existing module is a refactor target, not a greenfield add.

3. **Worker-config injection (0.5) → spawn env-var contract.** 0.5 emits
   `NGIN_SKILLS`/`NGIN_MODEL` env vars, but the harness contract (spec line
   122) says the harness "ensures the agent runtime loads them." If 0.5 lands
   before harness unification, the Hermes harness must still honor these env
   vars or skills silently no-op.

## Critical path

`1.1 → 1.2 → 2.1 → 2.2 → 2.3 → 2.4` — 6 units, serial. This is the longest
dependency chain. Layer 0 (Phase 1 completion) runs on a fully independent
parallel track and never touches this chain. 2.5 (triggers) branches off 2.2;
2.6 (GC) off 2.5. Layer 3 (dry-run, TUI, events, startup recovery) all hang
off Layer 2 and are off the critical path.

## Parallelization opportunities

- **7 independent starters from t=0**: 0.1, 0.2, 0.3, 0.4, 0.6, 1.1, 1.2.
- **0.5** starts once 0.4 lands.
- **0.7** (bd plugin) after 0.6.
- **1.3** (flow registry) after 1.1 — parallel with the entire Layer 2 engine
  track.
- Within Layer 2: **2.5 (triggers)** can start as soon as 2.2 completes, in
  parallel with 2.3 and 2.4 (plan already shows this branch). Max useful
  concurrency on the engine track is ~2 (the 2.3→2.4 chain vs. the 2.5→2.6
  chain), because 2.3/2.4/2.5 all read state written by 2.2 and 2.4 depends
  on 2.3.

## Source verification

Claims verified against actual code:
- `daemon/src/spawn.rs` — `ProcessSpawner` + `RunnerEnv` traits exist; no
  `AgentHarness` trait, no `harness.rs`.
- `daemon/src/tick.rs` — Phase trait + `run_phases()` with panic isolation;
  phase order 7→1→2→3→4→8→5→6.
- `daemon/src/idempotency.rs` — step-index keys (`run-{id}-step-{n}`), not
  iteration-aware.
- `.ngin/flows/` — empty; `.ngin/runs.db` — empty (0 bytes).
- beads DB — blocked by v42→v53 schema-migration gate; contains no issues.
