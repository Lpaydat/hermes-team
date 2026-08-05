# Worked Example: ngin 16-Ticket Implementation Review

Reviewed 16 implementation units (Layer 0: 0.1–0.7, Layer 1: 1.1–1.3,
Layer 2: 2.1–2.6) for a Rust dispatch daemon against the actual codebase.
This reference shows the technique applied to a real, complex codebase.

## Baseline verification

- `cargo build` → clean (14 warnings, 0 errors)
- `cargo test` → 574 passed, 1 failed (environmental bd-migration gate, documented)
- Schema v11 (migrations 001–012)

**Lesson:** always record the green baseline. One failure was environmental,
not a code defect — distinguishing the two is essential for blast-radius work.

## Technique: drill into exact code per ticket

These findings came from reading the SPECIFIC code each ticket touches, not
module overviews:

### Finding SQL-query gaps

Ticket 0.1 (max_runtime_secs) said "check started_at + max_runtime_secs".
Reading `find_running_runs` (crash_detect.rs:194):
```sql
SELECT r.run_id, r.issue_id, r.pid, r.exit_code
FROM runs r JOIN runs_ngin rn ON ...
WHERE rn.dispatch_state = 'running' AND r.pid IS NOT NULL
```
**Does NOT select `started_at`.** The `RunningRun` struct (crash_detect.rs:31)
has no `started_at` field. Both must be extended — a hidden gap the plan didn't
mention.

### Finding missing process-kill step

Ticket 0.1 said "transition to timed_out" but a timed-out run's PID is still
alive. Must SIGTERM first (like reclaim does), THEN classify. Hidden step.

### Finding terminology mismatch

Ticket 0.3 said "COUNT running runs GROUP BY assignee" but assignee lives on
the beads issue, NOT on `runs_ngin`. The table has `role` (set from assignee
at claim time, migration 007). Must GROUP BY `role`.

### Finding loop-structure change needed

Ticket 0.3 (per-profile cap) needs the claim loop (claim.rs:401-414) to change
from `break` (global cap reached → stop) to `continue` (per-profile cap → skip
this issue, try next). Different control flow.

### Finding trait-fit (no change needed)

Ticket 0.4 (workspace) — the `ProcessSpawner::spawn` trait already takes
`cwd: &Path`. The change is in how cwd is *resolved*, not the trait signature.
Blast radius smaller than it appears.

## Cross-cutting findings

### Migration numbering collision (HIGH)

Plan assigned migrations 12–19 across two tracks claimed as "independent."
Layer 0 (migrations 12–15) and Layer 2 (migrations 16–19) collide if built in
parallel. **Fix:** assign migration numbers at merge time, not plan time.

### Shared-function merge risk

Tickets 0.4 and 0.5 both modify spawn.rs — 0.4 touches `spawn_run` (cwd
resolution), 0.5 touches `build_spawn_env` (env vars). Different functions, so
they CAN be parallel despite the plan saying 0.5 depends on 0.4. Verified by
reading both functions.

### Prefactoring opportunity (HIGH LEVERAGE)

`ProcessSpawner` + `RunnerEnv` are separate traits; spec wants unified
`AgentHarness`. Tickets 0.4+0.5 are the natural unification point. Doing the
trait unification as a standalone prefactoring commit BEFORE 0.4/0.5 lets both
build against the unified trait.

### Dead code before reuse

`idempotency.rs` has two never-used functions (`find_existing_child`,
`ensure_child` — build warnings confirm). Ticket 2.4 plans to extend the module.
Clean dead code first.

## Architecture-fit assessment

The 8-phase tick pipeline (Phase trait + run_phases, wired in main.rs:604):

```
ExitClassify → Reclaim → CrashDetect → AutoResume → DepPromote
→ Triage → Claim → Spawn
```

**Question: does it need restructuring for 4 new Layer-2 phases?**
**Answer: NO.** The `Phase` trait supports arbitrary insertion — new phases are
just new `Box<dyn Phase>` entries in the vec[]. No trait signature change.
Only `TickContext` needs a `registry` field added. Proposed 12-phase ordering
worked out by reasoning about data flow (triggers create instances → sync
reflects completions → reset handles back-edges → graph walk dispatches).

**Lesson:** well-designed extension mechanisms usually support additive change.
Confirm by reading the trait signature and the wiring point. Don't assume
restructuring is needed — prove it isn't by showing the insertion point.

## Summary table (abbreviated)

| Ticket | Scope OK? | Blast Radius | Key finding |
|--------|-----------|--------------|-------------|
| 0.1 max_runtime | ✅ | Small | query doesn't select started_at; must kill PID |
| 0.3 per-profile cap | ⚠️ | S-Medium | GROUP BY role not assignee; loop break→continue |
| 0.4 workspace | ⚠️ | Medium | git worktree failure modes underestimated |
| 2.2 graph walker | 🔴 | Large | bundles 5 node types; COMMAND blocks tick loop |
| others (12) | ✅ | Small-Zero | ready as-specified |

**Verdict:** 12/16 ready, 4 need adjustment. Architecture is sound — additive
extension, no restructuring.
