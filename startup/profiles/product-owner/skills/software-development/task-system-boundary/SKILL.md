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

## Reference

- **`references/beads-kanban-boundary.md`** — full failure/recovery matrix, the 7 double-dispatch prevention layers, the crash recovery chain, corruption handling internals, and the critical gap (kanban has no off-machine backup). Read this for the detailed evidence.
- **`references/artifact-routing-policy.md`** — decision matrix for every artifact type (epic, feature, bug, dev card, verifier card, QA card, etc.) with the one-line test: "would a human want this in the backlog a month from now?" Includes anti-patterns and future unification plan.
- **`references/pipeline-gaps-livetest.md`** — 8 gaps discovered during end-to-end livetest (deadlocks, missing QA triggers, orphaned bugs, unmerged debugger fixes). Each with symptom, root cause, and fix. Read when debugging pipeline flow issues.
