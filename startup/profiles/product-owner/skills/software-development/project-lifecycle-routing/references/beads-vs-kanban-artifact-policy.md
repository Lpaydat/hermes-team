# Beads vs Kanban Cards: Artifact Routing Policy

**Principle:** beads = master plan (durable, git-synced, human-facing). Kanban cards = execution plan (dynamic, SQLite, agent-created, ephemeral).

**One-line test:** *Would a human want to see this in the backlog a month from now?* Yes → bead. No (pure execution detail) → card.

## The decision matrix

| Artifact | Who creates | Bead or Card | Why |
|---|---|---|---|
| Epic / feature | PO | **Bead** | Strategic scope. Durable, tracked, the thing stakeholders query. |
| Merge slot | PO / workflow | **Bead** | Durable integration gate. |
| Tech-lead card | workflow dispatch | **Card** | Decomposition of a feature bead. Auto-derived; transient once merged. |
| Dev card | tech-lead / kanban_chains | **Card** | Execution unit. One PR's worth of work. |
| Verifier card | tech-lead / kanban_chains | **Card** | Paired execution gate. Dies on merge. |
| QA card | verifier | **Card** | Pre-release execution step. |
| Bug | QA (or any agent) | **Bead** | Durable defect record. Outlives the card that surfaced it. Must link to parent epic. |
| Debugger internal fix card | debugger | **Card** | Internal scratch/routing for one fix cycle. Ephemeral. |
| Discovered follow-up work | any agent | **Bead** | Durable backlog (per AGENTS.md). |

## Summary rule

> **PO writes beads (the plan). The workflow engine and every downstream agent (tech-lead, dev, verifier, debugger, QA) write cards (the execution) — UNLESS they are filing durable, human-relevant scope: a bug, a discovered follow-up, or a feature gap. Those are beads, linked to their parent epic.**

## Anti-patterns

- Promoting dev/verify card pairs to beads (backlog explosion + sync noise).
- Bugs filed as cards (defects outlive the card that surfaced them; they vanish on merge).
- Debugger scratch cycles as beads (ephemeral noise in the durable record).
- Unparented bugs when an in-scope epic exists (breaks rollup queries).
- Agents filing beads for work that's just decomposition of an existing bead.

## Known gotcha: bd --type=bug

`bd create --type=bug` may store `issue_type` as `task` depending on bd version/config. The workflow engine's `dispatch_bug_to_debugger()` checks `issue_type == "bug"`. If bd doesn't set it correctly, the engine falls through to the generic PO dispatch path. PO recognizes the content as a bug and routes manually — but this adds latency. Verify with `bd show <id> --json | jq .issue_type` after creating bug beads.
