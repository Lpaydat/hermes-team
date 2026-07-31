# ngin — the user's existing dispatcher platform

The user has a working dispatcher platform at `~/workspace/ngin/` that is 90% of what the
Hermes workflow engine rebuild needs. This was discovered during the workflow engine design
discussion (2026-07-31).

## What ngin already has

- **Rust daemon** (`ngin-daemon`) — continuous tick loop (30s default) with 8 ordered phases:
  classify exits → reclaim stale → detect crashes → auto-resume → promote deps → triage → claim → spawn
- **Beads as single source of truth** — issues, status, dependencies, comments all in bd/Dolt
- **Agent registry** (`<project>/.ngin/agents.json`) — assignee-based dispatch (flow/graph/chain/human)
- **Flow definitions** (`.ngin/flows/*.json`) — static workflows
- **TUI dashboard** (`ngin-tui`, ratatui) — board view, runs view, log view, detail view
- **Auto-unblock** when dependencies resolve (the key feature Hermes kanban lacks)
- **Circuit breaker, orphan handling, crash recovery, ownership guard**
- **Per-project SQLite** (`<project>/.ngin/runs.db`) for run state
- **Signal protocol** — BUILD_COMPLETE, BUILD_BLOCKED, GUARD_REJECTED (protocol, not code dependency)
- **Comments as inter-task communication** — same model as Hermes kanban_comment
- **Worker tools** — heartbeat, context refresh, checklist (CLI wrappers, not pi.registerTool)
- **ngin-db** — shared Rust crate owning schema, migrations, queries, domain types
- **Recurring/ephemeral tasks** — via bd mol wisp + systemd timers (no internal scheduler)

## What ngin spawns

`pi-subagents` subagent-runner processes. This is the gap — Hermes profiles use
`hermes -p <profile> --cli` via gateway-managed sessions, not pi subagent-runner.

## The integration path (Path A)

Replace ngin's spawn target from `pi-subagents` to Hermes profiles:
- Keep everything else (daemon, beads, flows, TUI, ngin-db)
- Hermes plugins (kanban_chains, loop_engine) become profile-internal tools — ngin doesn't
  need to know about them
- The 645-line workflow-engine.py cron disappears entirely — ngin's daemon replaces it
- Beads becomes the single source of truth (already ngin's model)
- Hermes kanban becomes an execution cache — ngin creates cards for Hermes to pick up

## Other ngin locations

- `~/workspace/pro/nginbot/` — possibly a newer version
- `~/workspace/pro/nginbot/ngin-db/` — ngin-db as separate package
- `~/workspace/personal/ngin-bot/nginbot-api/` — API layer
- `~/workspace/pro/archive/ngin.bot/` — archived
- `~/workspace/pro/archive/nginbot/` — archived

The main one is `~/workspace/ngin/` (most complete, has daemon + TUI + docs).

## Key files to read when designing the integration

- `~/workspace/ngin/docs/architecture.md` — full architecture doc (93K, very detailed)
- `~/workspace/ngin/docs/prd-dispatcher.md` — dispatcher PRD with all 21 design decisions
- `~/workspace/ngin/bd-adapter.ts` — bd CLI adapter
- `~/workspace/ngin/extensions/dispatch.ts` — dispatch logic
- `~/workspace/ngin/daemon/src/` — Rust daemon source
