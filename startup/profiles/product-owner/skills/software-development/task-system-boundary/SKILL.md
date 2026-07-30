---
name: task-system-boundary
description: "Understand the architectural boundary between beads (bd/Dolt) and Hermes kanban (SQLite), their failure/recovery characteristics, and where task state should live. Load when reasoning about durability vs execution, designing bead-sync workflows, deciding where to store state, debugging dispatch/recovery behaviour, or investigating a task that went wrong. Covers crash recovery, race conditions, double-dispatch prevention, corruption handling, and traceability."
version: 1.0.0
metadata:
  hermes:
    tags: [architecture, beads, kanban, durability, recovery, dispatch]
    category: software-development
---

# task-system-boundary — beads is the spec, kanban is the engine

Two task systems run side by side. Knowing the boundary prevents misplacing state
and reasoning incorrectly about what survives when things go wrong. This skill is
architectural understanding, not command syntax — see the beads skill and
KANBAN_GUIDANCE for mechanics.

## The Boundary

```
Beads (bd / Dolt)     = Source of truth for WHAT and WHY
                        Durable, versioned, git-synced, recoverable from remote

Kanban (SQLite)       = Transient execution layer
                        Dispatch, claim, crash recovery, circuit breaker
                        Local-only — rebuildable from beads
```

The bead-sync phase (workflow engine, per board) syncs kanban status → bead status.
This direction makes beads the durable canonical store and kanban the ephemeral
engine. **If the kanban board is lost, it should be reconstructable from beads.**

**One-line test:** *Would a human want to see this in the backlog a month from now?* Yes → bead. No → card. See [`references/artifact-routing-policy.md`](references/artifact-routing-policy.md) for the full decision matrix.

## Design Principles

1. **Task definitions originate in beads** — survives disk failure via git remote.
2. **Kanban cards reference their bead IDs** — so the board can be rebuilt.
3. **Never treat kanban as the sole store of a task's definition** — only its execution state.
4. **Bead-sync must run frequently enough** that the board is always reconstructable.

## When to Consult This Skill

- **"What happens if the board crashes?"** — see Failure/Recovery reference.
- **"Can two agents grab the same task?"** — yes, both have atomic claim; kanban's CAS is documented in the reference.
- **"Where should I store this state?"** — if it must survive hardware loss, it belongs in beads.
- **"Why did the dispatcher spawn / not spawn / re-spawn?"** — see the 7-layer double-dispatch prevention in the reference.
- **"Can we trace this bug back to the task?"** — beads has full Dolt version history; kanban has an append-only event log.

## Known Quirks

- **`bd create --type=bug` does not set `issue_type` to `bug` reliably.** It may set the title to "bug" but leave `issue_type` as `task`. If the workflow engine routes by `issue_type == "bug"`, the routing may not fire. Workaround: the PO's dispatch skill recognizes bug content and routes to debugger regardless of issue_type. The engine's `dispatch_bug_to_debugger()` also checks `issue_type == "bug"` — verify the bead has the correct type before relying on automatic routing.
- **`hermes kanban create` CLI does not accept `--skills`.** That's a `kanban_create` tool parameter, not a CLI flag. Passing it causes `unrecognized arguments` and the card creation fails silently in the workflow engine. Never pass `--skills` to `run_kanban()` calls.
- **Agent-creates-card is fragile for process-compliance steps.** The debugger's natural instinct is to diagnose and close — not to spawn QA re-test cards. When a handoff step is critical for pipeline correctness (like QA re-test after bug fix), move it to infrastructure (workflow engine hook) rather than relying on the agent reading its SOUL.md. The QA trigger was moved from verifier/debugger SOUL.md instructions to workflow engine phase 5 — a card-based scan that fires when any verifier/debugger card completes. Five iterations to get right: (1) git HEAD tracking (false positives on spec commits), (2) git-with-merge-count (first-run seeding bug), (3) card-based scan without debugger loop filter (spurious QA cards from loop_engine internal verifier cards), (4) parent-child debugger filter (missed loop_engine's complex parent chains), (5) regex merge detection on completion summaries (clean — fires on "merged to master", ". merged ", etc.).
- **The QA trigger uses regex merge detection on completion summaries.** The debugger's loop_engine creates many internal verifier cards (falsification, RCA checks) that complete but aren't merges. Parent-child and title-based filters all failed. The working solution: scan the card's completion summary for merge patterns (`merged to master`, `merged to main`, `. merged `, `^merged `). Internal phases say "GREEN", "RED", "RCA", "verified" — never "merged to". Validated against 18 historical cards: 6 correct triggers, 0 false positives.
- **Full script review edge cases (workflow-engine.py, 645 lines).** After 11 livetest rounds, a full review found: (1) `import re` was inside the for-loop body (redundant, already at module level), (2) ESCALATION_CHAIN was missing debugger/qa (blocked cards got immediate HUMAN_REQUIRED), (3) bug routing relied solely on `issue_type == "bug"` without label fallback, (4) the docstring still referenced the old git-based QA trigger. All fixed. Remaining known limitations: the 1-hour lookback window in phase 5 means engine downtime >1h causes permanent QA trigger misses; `completed_at` comparison assumes epoch integers (would silently skip all rows if kanban stored datetimes as strings); and the engine never exits non-zero on top-level exceptions (cron never reports failure).
- **Decomposition hierarchy: slices ARE features, not fragments.** Each tracer-bullet slice (bead) is a complete, independently shippable feature — not a piece of one feature that needs assembly. Slices are progressive enhancements: slice 2 = slice 1 + more capability, slice 3 = slice 2 + robustness. The hierarchy is: epic → slices (beads) → dev/verifier cards (kanban). Tech-lead breaks each slice into dev+verifier execution cards via `kanban_chains` — those are ephemeral kanban cards for one PR's worth of work, not beads. Don't confuse slices with sub-cards. This matters for QA timing: since each slice IS independently shippable, per-slice QA is technically correct, but when multiple slices merge near-simultaneously (parallel dev), only the last QA run tests the fully assembled system — earlier runs test progressively larger intermediate states.
- **QA-before-merge is an unexplored design alternative.** The current pipeline is reactive: bugs land on master, QA catches them, debugger fixes. A proactive alternative: make QA a pre-merge gate (verifier reviews code → QA tests assembled artifact → PASS → merge). This would eliminate post-merge bug fix cycles and simplify the pipeline (no workflow engine QA trigger phase needed). The tension: QA tests the "assembled, running artifact" — if it tests a feature branch before merge, it can't catch cross-slice integration bugs. At small scale (3-5 slices), this tradeoff may be acceptable. Not yet implemented — flagged as a future pipeline redesign candidate.

## Livetest Methodology

When testing the pipeline end-to-end, the user expects **continuous monitoring with milestone reporting** — not periodic checks with pauses between them. Key lessons from livetest sessions:

- **Monitor continuously.** Use background processes (`notify_on_complete=true`) or tight polling loops. Never stop monitoring and tell the user "I'll report when done" — the user wants real-time milestone updates as each agent picks up, completes, or fails. Background `notify_on_complete` fires ONCE when the process exits — it does NOT notify per-milestone. For per-step reporting, poll actively in foreground loops or set up milestone-tracking background scripts that detect state transitions.
- **Report every milestone.** Each gate the pipeline crosses is a reportable event: PO picks up card, architect design complete, beads created, tech-lead dispatched, dev↔verifier iterations, merge, QA, bug found, debugger converges, QA re-test. If the user asks "did it stop?" you failed to monitor — the pipeline runs for hours and every handoff is a potential silent failure. The user explicitly said "monitor and report me every step it reach too" — this is a hard requirement, not optional.
- **Never pause without reporting.** If you hit a context limit or compaction, say what happened and what state the pipeline is in. The user found a 4-hour gap with no updates because monitoring stopped — that is a failure, not an acceptable pause.
- **Trace each step's evidence.** Don't just see "done" — verify HOW it completed. Did the verifier actually review code? Did the fix actually merge? Did QA actually re-test the running artifact? Did the debugger create follow-up cards or just close the bead?
- **Check for handoff gaps proactively.** The pipeline has many handoffs (debugger→verifier for merge, verifier→QA for re-test, debugger→QA for already-fixed case). Each handoff is a potential silent failure where work sits because nobody created the next card. Verify the full chain completed — "bug closed" means nothing if QA never ran.
- **Run multiple livetests.** Each run finds different bugs. First run: structural bugs (deadlocks, missing gates). Second run: routing bugs (issue_type mismatch). Third run: edge cases (already-fixed bugs, stale QA reports). Keep testing until a full run completes with zero new bugs.

## Reference

- **`references/beads-kanban-boundary.md`** — full failure/recovery matrix, the 7 double-dispatch prevention layers, the crash recovery chain, corruption handling internals, and the critical gap (kanban has no off-machine backup). Read this for the detailed evidence.
- **`references/artifact-routing-policy.md`** — decision matrix for every artifact type (epic, feature, bug, dev card, verifier card, QA card, etc.) with the one-line test: "would a human want this in the backlog a month from now?" Includes anti-patterns and future unification plan.
- **`references/pipeline-gaps-livetest.md`** — gaps discovered during end-to-end livetest (deadlocks, missing QA triggers, orphaned bugs, unmerged debugger fixes, QA trigger firing on initial commit). Each with symptom, root cause, and fix. Read when debugging pipeline flow issues.
- **`references/workflow-engine-phases.md`** — the 5-phase workflow engine architecture (bead-sync, dispatch+bug-routing, human-escal, scanner, qa-trigger) with state files, idempotency keys, and the full lifecycle from PO dispatch to QA re-test.
- **`references/qa-trigger-parallel-pipelines.md`** — scaling the QA trigger for parallel tracer-bullet pipelines (N slices merging near-simultaneously). Why per-merge QA is preferred over post-all-merge (graceful degradation, bisection value, no epic-grouping). The debounce technique to coalesce merge bursts into one QA card. Read when QA cards are bursting in parallel dev or when considering a post-all-merge trigger. Also covers the decomposition hierarchy (epic → slices/beads → dev/verifier kanban cards) and why slices are independent features, not fragments needing assembly.
