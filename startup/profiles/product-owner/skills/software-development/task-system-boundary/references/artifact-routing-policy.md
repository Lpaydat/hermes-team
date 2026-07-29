# Artifact Routing Policy: Beads vs Kanban

**Principle:** beads = master plan (durable, git-synced, human-facing). Kanban cards = execution plan (dynamic, SQLite, agent-created, ephemeral).

**One-line test:** *Would a human want to see this in the backlog a month from now?* Yes → bead. No (pure execution detail) → card.

## Decision matrix

| Artifact | Who creates | Bead or Card | Why |
|---|---|---|---|
| Epic / feature | PO | **Bead** | Strategic scope. Durable, tracked, the thing stakeholders query. |
| Merge slot | PO / workflow | **Bead** | Durable integration gate. |
| Bug | QA (or any agent) | **Bead** | Durable defect record. Outlives the card that surfaced it. Link to parent epic. |
| Research task | Any agent | **Bead** | Durable investigation record. |
| ADR / design doc | Architect | **Bead** | Architecture decision record. |
| Discovered follow-up | Any agent | **Bead** | "File issues for remaining work" per AGENTS.md. |
| Tech-lead card | workflow dispatch | **Card** | Decomposition of a feature bead. Transient once merged. |
| Dev card | tech-lead / kanban_chains | **Card** | Execution unit. One PR's worth of work. |
| Verifier card | tech-lead / kanban_chains | **Card** | Paired execution gate. Dies on merge. |
| QA card | verifier (after merge) | **Card** | Pre-release execution step. |
| Debugger card | workflow dispatch | **Card** | Internal scratch for one fix cycle. Ephemeral. |
| Escalation card | scanner | **Card** | Transient routing for blocked work. |
| Dispatch card | workflow engine | **Card** | Transient routing for ready beads. |
| Architect design card | PO (architect-gate) | **Card** | Execution of the design phase. Dies when design completes. |

## Rules

1. **Split by artifact type, not by agent.** An agent creating net-new scope a human should track → bead. An agent decomposing already-tracked scope → card. Same agent, different artifact per intent.

2. **Loop_engine / kanban_chains dev+verifier cards are NEVER beads.** They're execution fan-out, not master-plan items. Promoting them explodes the durable backlog with one-off items humans never curate.

3. **Bug beads MUST link to parent epic** with `bd dep add <bug-id> <epic-id> --type parent-child` so defect counts roll up. Exception: cross-cutting/regression bugs with no single epic → leave unparented.

4. **Debugger internal fix cards are NEVER beads.** The debugger's reproduce → patch → re-verify cycle is ephemeral. Only the bug bead persists.

## Anti-patterns

- Promoting dev/verify card pairs to beads (backlog explosion + sync noise).
- Bugs filed as cards (defects outlive the card that surfaced them; vanish on merge).
- Debugger scratch cycles as beads (ephemeral noise in the durable record).
- Unparented bugs when an in-scope epic exists (breaks rollup queries).
- Agents filing beads for work that's just decomposition of an existing bead (the bead already tracks it).

## Future unification

When the team's own harness has a dispatcher, beads absorbs kanban entirely. The workflow engine (537-line polling bridge) disappears into native beads lifecycle hooks. Every real-world system (GitHub, Jira, Linear) eventually unifies into one store with views/hierarchy.
