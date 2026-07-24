# loop_engine and kanban_chains for Builder (2026-07-24)

## Decision

Enabled `loop_engine` for the builder profile. Both `loop_engine` and `kanban_chains` were already available via plugins.enabled (auto-merged into dispatcher toolsets), but loop_engine was not listed. Added it.

## Rationale

User correction: "loop_engine isn't for just tech-lead. many profiles uses it already as it boost output quality. prevent agent to drift from the spec/goal by using quality gate. and break one shot build to multiple steps (which will boost quality by around 30% from research). dumb model with better workflow can outperform smart model."

loop_engine drives an iterative converge-loop with a verifier DoD gate between phases. For the builder:
- Phase 1: Build prototype → verify (runs? zero errors? matches grill decisions?)
- Phase 2: Write README → verify (all sections? specific review steps?)
- Prevents premature completion and drift from grill decisions.

kanban_chains creates parallel card topologies for batch builds (N prototypes concurrently, capped at 3).

## What was done

1. Added `loop_engine` to builder's `plugins.enabled` and `plugins.entries`
2. Updated venture-prototype skill with concrete loop_engine phase structure and kanban_chains batch pattern
3. Updated SOUL.md Team Boundaries with tools-for-quality note
4. Tagged `pre-loop-engine` for rollback

## Pitfall: hermes config set writes JSON strings

`hermes config set plugins.enabled '["kanban_chains","loop_engine"]'` saved the value as a JSON-encoded string, not a YAML list. Had to fix with Python YAML rewrite. See skill-administration pitfall.
