# Kanban Board Architecture — Single-Board vs Per-Project

The board structure determines whether the gateway dispatcher can
actually route work to agents. Get this wrong and tasks pile up on
boards nobody polls.

## The constraint that matters

**The gateway dispatcher watches ONE board.** On every tick (~60s), it
runs `dispatch_once()` against a single SQLite DB. Tasks on other
boards are invisible to it — they sit in `ready` forever.

Per-project boards sound like good isolation, but in practice they
strand work. The dispatcher never picks it up.

## Recommended: single board (`hermes-hq`)

Use one board for ALL agent dispatch. Project identity is carried in
the task title and beads ID prefix (e.g. `[tau-o4cc] Fix overlay
rendering` — the `tau-` prefix identifies the project).

```
hermes-hq (single board)
├── [tau-o4cc] Fix overlay rendering        → tech-lead
├── [tau-6vwp.2] Unify wire-decode module   → tech-lead
├── [other-proj-x1y2] Add feature Z         → tech-lead
└── Scout: research new harness release     → scout
```

### Why this works

1. **Dispatcher sees everything.** No stranded work.
2. **Concurrency is enforced at the profile level**, not the board
   level. `kanban.max_in_progress_per_profile: 1` in config prevents a
   second tech-lead spawn regardless of how many tasks are queued.
3. **Queue discipline is automatic.** Multiple ready tasks for
   tech-lead don't break anything — they queue, dispatcher picks one
   at a time in priority order.
4. **No stale boards to maintain.** Deleting a project doesn't leave
   behind an empty board. Adding a project doesn't require creating a
   new board.

### When per-project boards WOULD make sense

Only if you have a large team (5+ agents per role) where work needs
strict isolation between project teams. For a solo operator with a
small agent fleet, one board is simpler and more reliable.

## Dispatcher internals (for debugging)

- **Dispatch tick**: every 60s, the gateway's built-in watcher runs
  `dispatch_once()`.
- **Concurrency cap**: `kanban.max_in_progress_per_profile: 1` — the
  dispatcher won't spawn a second instance of the same profile while
  one is running.
- **Crash recovery**: if a worker dies mid-task, the stale timeout
  (default 14400s / 4h) reclaims it. Heartbeat every <1h keeps it alive.
- **Multi-gateway**: if multiple profile gateways run concurrently, only
  ONE should have `kanban.dispatch_in_gateway: true` (the default
  profile). Others set it to `false`.

## Duplicate task prevention (three-control pattern)

When autonomously creating tasks from beads issues, use all three:

1. **Concurrency cap**: dispatcher won't spawn duplicate workers
2. **Board scan**: query existing tasks, extract beads IDs from titles,
   skip any that already have a task
3. **Idempotency keys**: `kanban_create` with
   `idempotency_key="beads-{issue_id}"` — the board rejects duplicates

Tested: three consecutive cron ticks produce exactly one task per ready
issue, zero duplicates.
