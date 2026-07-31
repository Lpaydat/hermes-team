# Profile & Team Diagnosis — Complete Data Source Map

When diagnosing a profile (or a set of profiles as a system), read beyond the
core trio (SOUL.md, config.yaml, skills). The files below are essential for
understanding what a profile **does automatically**, not just what it's
configured to do interactively.

## Per-profile data sources

| Source | Path | What it tells you |
|--------|------|-------------------|
| **Charter** | `<profile>/SOUL.md` | Identity, role, boundaries, what it must never do |
| **Config** | `<profile>/config.yaml` | Toolsets, disabled skills, mandatory pins, plugins, command_allowlist, approvals mode, concurrency limits |
| **Skills** | `<profile>/skills/**/SKILL.md` | Operational procedures — the how-to for each class of task |
| **Cron job definitions** | `<profile>/cron/jobs.json` | Scheduled jobs: schedule, model/provider, skills loaded, script, no_agent flag, last_status, last_error, delivery config |
| **Cron scripts** | `<profile>/scripts/*.sh`, `<profile>/scripts/*.py` | Watchdog/automation logic (healthcheck, guard, backup, archiver) |
| **Cron run output** | `<profile>/cron/output/<job-id>/<timestamp>.md` | What actually happened on the last run (transcript or status summary) |
| **State files** | `<profile>/state.db`, `<profile>/state/gateway.heartbeat` | Runtime state, session history, gateway liveness |
| **Bootstrap marker** | `<profile>/.bootstrap_complete` | Whether the profile has been specialized |

## Cross-profile data sources

These live outside any single profile and tie the team together:

| Source | Path | What it tells you |
|--------|------|-------------------|
| **Active projects** | `~/.hermes-teams/startup/active-projects.json` | Which projects the workflow engine processes (each maps to a kanban board) |
| **Workflow engine** | `<product-owner>/scripts/workflow-engine.py` | Cross-cutting automation: bead-sync, dispatch, human-escalation, scanner, qa-trigger |
| **Kanban boards** | `~/.hermes-teams/startup/kanban/boards/<board>/kanban.db` | Task state, runs, events, comments — the shared coordination surface |
| **Operator board** | `~/.hermes-teams/startup/kanban/boards/hermes-hq/kanban.db` | Where human-escalation cards land (assignee=default) |
| **QA trigger state** | `~/.hermes-teams/startup/kanban/qa-trigger-state.json` | Last SHA per board that triggered a QA card |

## Cron job state fields worth checking

For each job in `jobs.json`, these fields reveal health without reading run logs:

- `last_status` — `"ok"` / `"error"` / `null`
- `last_error` — the error string if last run failed (e.g. missing API key, script not found)
- `last_delivery_error` — delivery channel failures (e.g. `"platform 'telegram' not configured/enabled"`)
- `repeat.completed` — how many times it has run (high count = long-running stable job)
- `enabled` / `state` — whether it's active
- `no_agent` — if `true`, it's a zero-token script (watchdog); if `false`, it spawns an LLM agent

## Diagnosis output structure (proven)

A useful multi-profile diagnostic covers:

1. **What each profile does** — role, model, toolsets, key skills, responsibilities
2. **Triggers** — what starts work (cron, kanban dispatch, user request, guard script)
3. **Scanner monitoring** — what the workflow engine watches and escalates
4. **Human escalation** — the two mechanisms (scanner HUMAN_REQUIRED comment vs human-flagged bead HQ card)
5. **Cron management** — scheduled jobs, their patterns, what they do/don't cover
6. **Work discovery** — how work flows between profiles (e.g. scout → researcher handoff)
7. **JSON node definitions** — each automatable task as a structured trigger/action/output block

## Common cross-profile findings

- **Stalled pipeline**: upstream profile's cron is broken (missing API key, wrong script path) → downstream profile receives no work → entire chain stalls silently
- **Charter-capability mismatch**: SOUL.md describes a capability (e.g. "writes Obsidian notes") but the enabling skills are disabled in config
- **Dual workflow engine**: old engine still running while new engine is broken — both fire every minute, old one masks the new one's failure
- **Disabled delivery**: cron job configured to deliver to Telegram/Discord but the platform isn't configured → output produced but never reaches the user
