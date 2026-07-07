# Team Telemetry Map — where Hermes team data lives + ready-to-run diagnostics

Resolves the most common waste in team analysis: querying empty DBs, re-deriving the
schema, and guessing where gateway/cron/profile state is. Verified on Hermes as of
2026-07. Paths assume the default install (`HERMES_HOME=~/.hermes`).

## 0. Resolve the active board FIRST (don't skip)

The top-level `~/.hermes/kanban.db` is empty/legacy. Real board data lives under
`boards/<board-slug>/kanban.db`.

```bash
cat ~/.hermes/kanban/current          # → e.g. "hermes-hq"
DB=~/.hermes/kanban/boards/hermes-hq/kanban.db
sqlite3 "$DB" "SELECT COUNT(*) FROM tasks;"   # sanity: should be > 0
```

If `current` is missing, list boards: `ls ~/.hermes/kanban/boards/`.

## 1. Kanban DB schema (what each table is for)

| Table | Purpose | Key columns |
|---|---|---|
| `tasks` | One row per task card | `assignee, status, created_at, started_at, completed_at, consecutive_failures, last_failure_error, last_heartbeat_at, block_kind, block_recurrence_count` |
| `task_runs` | One row per dispatch attempt | `status` (running/done/blocked/crashed/timed_out/failed/released), `outcome` (completed/blocked/crashed/timed_out/spawn_failed/gave_up/reclaimed), `started_at, ended_at, worker_pid, error` |
| `task_events` | Immutable event log | `kind` (created/spawned/claimed/heartbeat/completed/gave_up/protocol_violation/promoted/archived/linked), `payload` (JSON), `created_at` |
| `task_links` | Parent→child dependency edges | `parent_id, child_id` |
| `task_comments` | Task threads | handoffs, questions, diagnoses |
| `task_runs.metadata` | JSON: changed_files, tests_run, decisions | per-run structured facts |

## 2. Diagnostic SQL (copy-paste, adapt the time window)

### Status distribution by assignee (where is work stuck?)

```sql
SELECT assignee, status, COUNT(*) AS n
FROM tasks
WHERE status NOT IN ('archived','done')
GROUP BY assignee, status
ORDER BY n DESC;
```

### Run outcomes + durations (throughput & failure shape)

```sql
SELECT outcome,
       COUNT(*) AS n,
       ROUND(AVG((ended_at-started_at)/60.0),1) AS avg_min,
       MAX((ended_at-started_at)/60.0)        AS max_min
FROM task_runs
WHERE ended_at IS NOT NULL
GROUP BY outcome;
```

### Failure root-cause grouping (don't count symptoms, group causes)

```sql
SELECT substr(error, 1, 80) AS root_cause, COUNT(*) AS n
FROM task_runs
WHERE outcome IN ('crashed','gave_up','timed_out','spawn_failed')
GROUP BY root_cause
ORDER BY n DESC;
```

If `error` is unhelpful, join to `task_events`:

```sql
SELECT substr(payload, 1, 100) AS detail, COUNT(*) AS n
FROM task_events
WHERE kind IN ('gave_up','protocol_violation')
GROUP BY detail
ORDER BY n DESC;
```

### Tasks failing repeatedly (circuit-breaker candidates)

```sql
SELECT assignee, substr(title,1,50) AS title,
       consecutive_failures, last_failure_error
FROM tasks
WHERE consecutive_failures > 0
ORDER BY consecutive_failures DESC;
```

### Stuck workers (running but not heartbeating)

```sql
SELECT t.assignee, t.id,
       (strftime('%s','now') - t.last_heartbeat_at)/60 AS stale_min
FROM tasks t
WHERE t.status='running'
  AND t.last_heartbeat_at IS NOT NULL
  AND t.last_heartbeat_at < strftime('%s','now') - 3600;  -- >1h stale
```

### Unblock loops (task keeps getting re-blocked)

```sql
SELECT assignee, substr(title,1,50), block_kind, block_recurrence_count
FROM tasks
WHERE block_recurrence_count >= 2;
```

## 3. Gateway & delivery health

```bash
# Platform connectivity (telegram/discord/etc.)
cat ~/.hermes/gateway_state.json
# → platforms.<name>.state: "running"=healthy, "disconnected"/"retrying"=broken

# Which channels are actually wired
cat ~/.hermes/channel_directory.json
# → platforms.<name>: list of {id, name, type, thread_id}
```

A disconnected gateway means cron digests/alerts won't be delivered — this is itself a
finding. The operator's primary channel is whatever has a non-empty entry in
`channel_directory.json`.

## 4. Cron health

### Per-profile storage — `cronjob action=list` is profile-scoped

**Top gotcha.** `cronjob action=list` only lists jobs for the *current* profile's
session. In a single-profile install this is fine; in a **multi-profile team** it
silently returns `0` for every profile except the one the shell is running as. Do not
report "no cron jobs" from a single `cronjob action=list` in a team setup — you will be
wrong, as the operator's GUI aggregates across all profiles.

Cron jobs are stored **per-profile** as JSON (NOT in `state.db`, NOT in a shared/global
location):

```
<profile-home>/cron/jobs.json        # { "jobs": [ {schedule, prompt, enabled, ...} ] }
```

Profile homes resolve to one of two layouts depending on the install:

| Layout | Profile home | When you see it |
|---|---|---|
| Single-user | `~/.hermes/profiles/<name>/` | Default `HERMES_HOME` install |
| Team / startup | `~/.hermes-teams/startup/profiles/<name>/` | Multi-profile team deployment |

### Enumerate every cron job across ALL profiles (team-safe)

Use this instead of trusting one `cronjob action=list`. It prints a per-profile count
and a grand total, and works regardless of which layout is in use:

```bash
total=0
for f in ~/.hermes/profiles/*/cron/jobs.json \
         ~/.hermes-teams/startup/profiles/*/cron/jobs.json; do
  [ -f "$f" ] || continue
  prof=$(echo "$f" | sed 's|.*/profiles/||; s|/cron/jobs.json||')
  n=$(python3 -c "import json;print(len(json.load(open('$f')).get('jobs',[])))" 2>/dev/null)
  [ -n "$n" ] && { echo "  $prof: $n jobs"; total=$((total+n)); }
done
echo "TOTAL: $total"
```

### Inspecting / mutating a specific profile's jobs

- **Read details** (names, schedules, enabled/disabled, prompts): open that profile's
  `cron/jobs.json` directly with `read_file`, or switch into that profile's session and
  run `cronjob action=list` there — the tool sees only that profile's jobs.
- **Mutate** (pause/resume/remove/update): the `cronjob` tool only operates on the
  *current* profile. To change another profile's job, either open that profile's session
  or edit its `cron/jobs.json` by hand (rare; prefer the tool from within the profile).

### What to check once you can see the jobs

- Jobs that are `paused` (or `enabled: false`).
- Jobs with no recent `last_run` / `last_success` — compare against `schedule`. The
  `cron/` dir also holds `ticker_heartbeat` and `ticker_last_success` files (epoch
  timestamps) you can `stat` to confirm the scheduler tick loop is alive.
- Jobs whose `deliver` target is a platform the gateway reports disconnected (cross-ref
  Section 3) — those jobs run but their output never lands anywhere visible.

## 5. Profile topology & load

```bash
hermes profile list                 # every profile + model + gateway state
hermes kanban assignees             # who's on THIS board + task counts
```

Look for: profiles that exist but never receive tasks (gaps/over-provisioning), profiles
holding most of the open work (chokepoints), idle profiles whose description overlaps an
overloaded one (routing smell).

## 6. Worker processes (zombie check)

```bash
# PIDs the dispatcher thinks are workers:
sqlite3 "$DB" "SELECT DISTINCT worker_pid FROM task_runs WHERE status='running';"
# Cross-reference with the OS:
ps -o pid,etime,cmd -p <pid>
```

A PID in `task_runs` with `status='running'` that `ps` shows as non-existent (or a
process whose task is no longer running) is a zombie/stale lock.

## When the schema or paths drift

Hermes is under active development. If a query errors, re-derive the schema with
`sqlite3 "$DB" ".schema <table>"` and adjust. The table names (`tasks`, `task_runs`,
`task_events`) have been stable; column names occasionally extend. If the board path
shape changes, start from `ls -R ~/.hermes/kanban/` and find the `.db` with rows.
