# Hermes Kanban Dispatcher Mechanics

How the engine's output (kanban cards) becomes agent work. The engine creates
cards; the Hermes dispatcher claims and spawns them. Understanding this lifecycle
is essential for designing workflow templates that integrate correctly.

## Where the dispatcher lives

The dispatcher runs **inside the gateway process** (not a separate daemon —
`hermes kanban daemon` is DEPRECATED). Every gateway (`hermes gateway run`)
runs a `_kanban_dispatcher_watcher` that ticks every ~60 seconds per board.

Source: `hermes-agent/gateway/kanban_watchers.py:_kanban_dispatcher_watcher`

## The dispatch tick: 4 steps

Each tick runs `dispatch_once()` (in `hermes_cli/kanban_db.py`) under a
**board-scoped dispatch lock** (cross-process `fcntl` or platform equivalent).
Two dispatchers pointed at the same board can never run concurrently — the
loser returns `skipped_locked=True` and does no writes. Unrelated boards tick
in parallel.

### Step 1: Reclaim stale running tasks

Three reclaim mechanisms:
- **TTL expired** — `running` tasks whose claim_lock TTL has passed → back to `ready`
- **No heartbeat** — `running` tasks with no recent `kanban_heartbeat` → back to `ready`
- **Crashed PID** — `running` tasks whose `worker_pid` is no longer alive → back to `ready`

Config: `dispatch_stale_timeout_seconds` (default 14400 = 4 hours).

### Step 2: Promote todo → ready

`recompute_ready(conn)` finds `todo` tasks where ALL parents are `done` and
promotes them to `ready`. This is how parent-child dependencies work: a child
card with `parent=<parent_id>` stays in `todo` until the parent completes.

**Critical for template design:** if the engine creates cards A and B where
B has `parent=A`, the dispatcher promotes B automatically when A completes.
The engine does NOT need to manage this — the dispatcher's `recompute_ready`
handles it.

### Step 3: Claim and spawn ready tasks

For each `ready` task with an assignee (ordered by `priority DESC, created_at ASC`):
1. Atomically claim it (set `status='running'`, `claim_lock=<claim_id>`)
2. Call `spawn_fn(task, workspace_path, board)` — spawns the agent process
3. Record `worker_pid` so future ticks can detect crashes before TTL

**Concurrency caps:**
- `max_spawn` / `max_in_progress` — live concurrency cap across the board (counts running + this tick's spawns)
- `max_in_progress_per_profile` — per-assignee cap (e.g., max 3 builder tasks running at once)

### Step 4: Failure handling

After `failure_limit` consecutive failures (default 2), the task is
**auto-blocked** with the last error as the reason. This prevents thrashing
on unfixable tasks.

## Card lifecycle

```
created → todo (has unmet parent deps) or ready (no parent deps)
        → ready (parents done — promoted by recompute_ready)
        → running (claimed + spawned by dispatcher)
        → done / blocked / crashed / timed_out / gave_up
```

A card with NO parents goes directly to `ready` on creation. A card WITH
parents stays `todo` until all parents reach `done`.

## What this means for workflow engine template design

### Parent-child dependencies: dispatcher handles them

If a template creates two cards where the second depends on the first:
```json
{"id": "grill", "profile": "builder", ...},
{"id": "build", "profile": "builder", ...}
```

You have two options:
1. **Engine-managed:** engine creates `grill` card, waits for completion,
   THEN creates `build` card. Uses explicit edges in the template.
2. **Dispatcher-managed:** engine creates BOTH cards at once with
   `build.parent = grill.card_id`. Dispatcher keeps `build` in `todo` until
   `grill` completes. No edge needed.

Option 1 (engine-managed) gives more control: the engine can modify the second
card's body based on the first card's output (variable resolution). Option 2
(dispatcher-managed) is simpler but the second card's body is fixed at creation
time — no access to the first card's output.

**queue-builds.sh uses option 2:** creates grill + build cards with
`--parent grill_id`. The dispatcher handles promotion. This works because the
build card doesn't need the grill output in its body — it reads it from disk.

### Card status that the engine sees

The engine's `find_recent_completions` queries for `status='done'` cards.
It does NOT see:
- `blocked` cards (agent couldn't complete — engine node stays DISPATCHED)
- `crashed` cards (dispatcher will reclaim → re-spawn → eventually done or blocked)
- `timed_out` cards (auto-blocked after max_runtime)

The engine only advances on `done`. If a card is blocked, the engine node
stays DISPATCHED forever (no automatic escalation). The old cron's `scanner`
phase handled this — blocked tasks were escalated up the chain.

### Real boards default to `ready` on creation

`hermes kanban create` sets `status='ready'` for assignable cards (those with
an assignee). Cards WITHOUT an assignee stay in `triage`. Tests should assert
`status in ("todo", "ready")` for newly created cards on real boards.

### The 4-hour stale timeout

If an agent crashes without completing or blocking, the dispatcher reclaims
the card after 4 hours. This means a crashed agent's card goes back to `ready`,
gets re-spawned, and either completes or crashes again (→ auto-blocked after
2 failures). The engine doesn't need to handle crash recovery — the dispatcher
does it.

### max_in_progress_per_profile limits parallelism

The builder config has `max_in_progress: 3, max_in_progress_per_profile: 3`.
This means at most 3 builder tasks running simultaneously. If a workflow
template creates 10 builder cards in a foreach, only 3 run at once — the rest
wait in `ready` until a slot frees up. Templates don't need to manage this;
the dispatcher does.

## How to inspect the dispatcher

```bash
# See dispatch results for a board
hermes kanban --board <slug> dispatch --dry-run --json

# Check if the gateway is running the dispatcher
ps aux | grep "gateway run" | grep -v grep

# Watch task events in real-time
hermes kanban --board <slug> watch

# List tasks by status
hermes kanban --board <slug> list --status running
hermes kanban --board <slug> list --status ready
hermes kanban --board <slug> list --status blocked
```

## What happens when a parent blocks or fails (the silent-stall risk)

**There is no propagation of parent failure to children.** This is the most
important operational gap to understand:

| Parent outcome | Parent status | Child impact |
|----------------|-------------|--------------|
| Manually blocked (`kanban_block`, sticky) | `blocked` | Child stuck in `todo` indefinitely — no event, no notification |
| Circuit breaker tripped (`gave_up`) | `blocked` | Child stuck in `todo`; parent may auto-recover if non-sticky and under failure limit |
| Block kind=`dependency` | `todo` | Child stuck in `todo` (parent's own parents not done) |
| Archived | `archived` | **Child promotes** — `archived` counts as "done" for the gate |

A child whose parent is permanently blocked or deleted-without-completion will
**silently wait in `todo` forever**. No event is emitted on the child. No
timeout exists. The child appears in `kanban list --status todo` but never
promotes.

### How to unstrand orphaned children

Three recovery paths, in order of cleanliness:

1. **Complete or archive the parent** — `hermes kanban complete <parent_id>` or
   `hermes kanban archive <parent_id>`. The child promotes on the next
   `recompute_ready` tick (called synchronously at end of `complete_task`, AND
   on every dispatcher tick).
2. **Unlink the child** — `hermes kanban unlink <parent_id> <child_id>`.
   `unlink_tasks()` calls `recompute_ready()` immediately (separate code path
   from complete_task), so a now-parentless child promotes instantly.
3. **Delete the parent** — `delete_task` removes `task_links` rows where the
   deleted task is either parent or child (`DELETE FROM task_links WHERE
   parent_id = ? OR child_id = ?`). Children become parentless and promote on
   the next tick. This is the only automatic orphan-resolution path.

### The promotion gate (exact mechanism)

`recompute_ready` (called by `complete_task` at L4623 AND every dispatcher tick
at L7912) scans ALL `todo`/`blocked` tasks:

```sql
SELECT id, status, consecutive_failures, max_retries
FROM tasks WHERE status IN ('todo', 'blocked')
```

For each, it checks parents:
```sql
SELECT t.status FROM tasks t
JOIN task_links l ON l.parent_id = t.id
WHERE l.child_id = ?
```

Promotion gate: `all(parent.status in ('done', 'archived'))`.

Two exclusions prevent auto-promotion of blocked tasks:
1. **Sticky block** — `_has_sticky_block()` checks if the most recent
   `blocked`/`unblocked` event is `blocked` (worker-initiated
   `kanban_block`). Sticky blocks stay until explicit `kanban_unblock`.
2. **Circuit breaker** — `consecutive_failures >= effective_limit` (per-task
   `max_retries` or dispatcher `failure_limit`). Prevents infinite retry loops.

### The structural invariant in claim_task (second enforcement point)

`claim_task` (L3842-3858) has a SECOND parent-gate check, defense-in-depth
against racy writers:

```sql
SELECT 1 FROM task_links l
JOIN tasks p ON p.id = l.parent_id
WHERE l.child_id = ? AND p.status NOT IN ('done', 'archived') LIMIT 1
```

If any parent is not done, the claim is **rejected** — the task is demoted from
`ready` back to `todo` with a `claim_rejected` event (`reason:
parents_not_done`). This catches the case where a buggy writer set `ready`
before parents were actually done. `recompute_ready` will re-promote when the
parents genuinely finish.

## Key source files

- `hermes-agent/gateway/kanban_watchers.py` — the dispatcher watcher loop
- `hermes_cli/kanban_db.py:dispatch_once` — the core dispatch function
- `hermes_cli/kanban_db.py:recompute_ready` (L3727) — parent-child promotion logic + SQL
- `hermes_cli/kanban_db.py:claim_task` (L3818) — atomic claim + spawn, structural invariant at L3842
- `hermes_cli/kanban_db.py:complete_task` (L4428) — calls recompute_ready at L4623
- `hermes_cli/kanban_db.py:_has_sticky_block` (L3689) — sticky-block detection
- `hermes_cli/kanban_db.py:link_tasks` (L3148) — parent-child link creation + cycle detection
- `hermes_cli/kanban_db.py:unlink_tasks` (L3201) — link removal + immediate recompute_ready
- `hermes_cli/kanban_db.py:release_stale_claims` — TTL-based reclaim
