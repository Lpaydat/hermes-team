# STATUS.md — [Project Name]

> Single-source project dashboard. Tech-lead maintains this.
> The gate can ask "what's the status of [project]?" at any time.

## Snapshot

- **Stage:** [prototype | production | shipped | shelved]
- **Started:** YYYY-MM-DD
- **Current milestone:** [Milestone name] — [X]% complete
- **Code:** `~/projects/<slug>/`
- **Board:** `hermes kanban --board <slug>`
- **Origin:** [Door A/B/C/D — brief description]

## Milestones

| # | Milestone | Status | Target | Epics | Notes |
|---|-----------|--------|--------|-------|-------|
| 1 | MVP Core | done | 2026-07-15 | 3 epics | Shipped, verified |
| 2 | Scale & Polish | in_progress | 2026-07-30 | 4 epics | 2 epics done, 2 active |
| 3 | Launch | pending | — | — | Awaiting M2 |

## Active Epics

| Epic | Status | Tasks done | Tasks open | Blocked | Assignee |
|------|--------|-----------|------------|---------|----------|
| Auth system | in_progress | 5/8 | 3 | 0 | developer |
| Billing integration | pending | 0/5 | 5 | 0 | — |

## Tech Debt Register

| # | Debt item | Severity | Filed | Status |
|---|-----------|----------|-------|--------|
| 1 | No input validation on API endpoints | medium | 2026-07-20 | open |
| 2 | Test coverage at 60%, target 80% | low | 2026-07-22 | open |

## Decisions Log

| Date | Decision | Context |
|------|----------|---------|
| 2026-07-15 | Use FastAPI over Flask | async support needed for streaming endpoints |
| 2026-07-18 | Postgres over SQLite | need concurrent writes for billing |

## Build History

| Date | Event | Outcome |
|------|-------|---------|
| 2026-07-15 | MVP build | 3 epics, 24 tasks, all verified PASS |
| 2026-07-18 | Security fix iteration | P0 SSRF fixed, P1 rate limit fixed, verified PASS |
