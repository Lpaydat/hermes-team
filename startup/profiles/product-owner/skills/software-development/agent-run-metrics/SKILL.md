---
name: agent-run-metrics
description: "Extract timing, token, and cost data from the Hermes DB layer to analyze or compare agent run efficiency. Load when comparing pipeline strategies (A/B tests), auditing token spend, breaking down per-card cost, deciding whether adaptive sizing worked, or answering 'how much did this run cost / how long did it take'. Knows where each data type lives (board DB vs profile state DB), the worker_session_id join, and the query patterns that produce a complete cost picture."
version: 1.0.0
metadata:
  hermes:
    tags: [metrics, cost-analysis, tokens, kanban, efficiency, ab-testing]
    category: software-development
---

# agent-run-metrics — where Hermes run data lives and how to extract it

Hermes splits run telemetry across **two different database layers**. Knowing
which DB holds which data type is the difference between a 30-second query and
a 15-minute hunt through empty result sets.

## The two layers

```
Board DB     ~/.hermes-teams/startup/kanban/boards/<board>/kanban.db
             (or ~/.hermes/kanban/boards/<board>/kanban.db in older layouts)
             Holds: task definitions, task_runs (timing), task_events (lifecycle)

Profile DB   ~/.hermes-teams/startup/profiles/<profile>/state.db
             Holds: sessions (token counts, cost), session_model_usage (per-model breakdown)
```

**Timing data lives in the board DB. Token/cost data lives in the profile's state DB.**
There is no single DB that has both. You must join them via `worker_session_id`.

## Step 1 — Find the board DB

The `kanban_*` tools resolve the board automatically, but raw sqlite3 queries
need the actual file path. Check both locations:

```bash
# Primary (hermes-teams startup layout):
ls ~/.hermes-teams/startup/kanban/boards/<board>/kanban.db

# Fallback (older ~/.hermes layout):
ls ~/.hermes/kanban/boards/<board>/kanban.db

# If both fail, search:
find ~/.hermes-teams ~/.hermes -path "*boards/<board>*" -name "kanban.db" 2>/dev/null
```

If `find` with `2>/dev/null` hangs (large home dir), scope it to the kanban
directory: `find ~/.hermes-teams/startup/kanban -name "kanban.db"`.

## Step 2 — Extract timing from the board DB

Per-run active agent time (wall-clock each agent was actually working):

```sql
-- Board DB
SELECT r.task_id, substr(t.title,1,40) AS title,
       (r.ended_at - r.started_at) AS active_s,
       datetime(r.started_at,'unixepoch') AS start_ts,
       datetime(r.ended_at,'unixepoch') AS end_ts
FROM task_runs r
JOIN tasks t ON r.task_id = t.id
ORDER BY r.started_at;
```

Total wall-clock for a board (first card created → last card completed):

```sql
SELECT (MAX(completed_at) - MIN(created_at)) AS wall_s
FROM tasks WHERE id LIKE 't_%';
```

**Active time ≠ wall-clock.** Active time sums each run's duration; wall-clock
includes gaps between cards (dispatch latency, queue wait, human review).
For fan-out boards, multiple runs overlap (parallel), so summing active_s
over-counts — use min(started_at)→max(ended_at) per wave for the true elapsed.

## Step 3 — Extract token/cost data from the profile's state DB

Each kanban card that ran an agent produces a session in that profile's
`state.db`. The card's completion metadata includes a `worker_session_id`
that joins to `sessions.id`.

```sql
-- Profile state DB (~/.hermes-teams/startup/profiles/<profile>/state.db)
SELECT id, title,
       input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens,
       reasoning_tokens,
       estimated_cost_usd,
       api_call_count
FROM sessions
WHERE started_at BETWEEN <epoch_start> AND <epoch_end>
ORDER BY started_at;
```

**Per-model breakdown** (when a session used multiple models):

```sql
SELECT m.session_id, m.model, m.api_call_count,
       m.input_tokens, m.output_tokens,
       m.cache_read_tokens, m.reasoning_tokens,
       m.estimated_cost_usd
FROM session_model_usage m
JOIN sessions s ON m.session_id = s.id
WHERE s.started_at BETWEEN <epoch_start> AND <epoch_end>
ORDER BY s.started_at;
```

## Step 4 — Map sessions to cards

The `worker_session_id` field in `task_runs.metadata` (JSON) is the join key.
Read it from the board DB, then look up the session in the profile DB.

For an A/B comparison, map each session to its card manually using the
timestamps — the session that started ~60s after a card was claimed belongs
to that card. The `worker_session_id` confirms the mapping.

## Cost estimation when `estimated_cost_usd` is $0

Some providers (e.g. glm-5.2 via zai) don't report billing, so
`estimated_cost_usd` stays at 0.0 for every session. When this happens,
compare **raw token totals** instead:

```sql
SELECT
  SUM(input_tokens + output_tokens + cache_read_tokens + reasoning_tokens) AS total_tokens
FROM sessions WHERE id IN (...);
```

The dominant cost component is almost always **cache_read_tokens** — the
system prompt + skill context re-warmed on every API call. Fan-out pipelines
pay this tax once per card; single-session pipelines pay it fewer times.

## Pitfalls

- **`estimated_cost_usd` = 0.0 doesn't mean free.** It means the provider
  doesn't report billing to Hermes. Compare token volumes as a proxy.
- **Active time over-counts on fan-out boards.** Parallel runs overlap, so
  Σ(active_s) > actual elapsed. Use per-wave min/max for true wall-clock.
- **`find` without path scoping hangs on large home dirs.** Always scope to
  `~/.hermes-teams/startup/kanban` or set a timeout.
- **The board DB path depends on the setup era.** `~/.hermes/kanban/` is the
  older layout; `~/.hermes-teams/startup/kanban/` is the current one. Check
  both if the first is empty.
- **`cache_write_tokens` is often 0.** Hermes uses cache-read (prompt caching)
  but rarely writes new cache prefixes mid-session. Don't expect symmetry.
- **Profile DB differs per assignee.** A board with cards assigned to `qa`,
  `verifier`, and `tech-lead` has sessions split across three profile DBs.
  Query each profile's `state.db` separately and union the results.
- **Epoch timestamps, not ISO strings.** Both DBs store Unix epoch integers.
  Use `datetime(col, 'unixepoch')` for readable output. For time windows,
  convert your target time to epoch: `date -d '2026-08-02 20:25' +%s`.
- **Board DB can be reset/cleaned mid-analysis.** A board's `kanban.db` is a
  live file that other processes (dispatchers, cron jobs, board-archive
  operations) can modify at any time. In tl-gauntlet-a round 3, the
  `task_events` and `task_runs` tables had rich data (67 tasks, 75 links,
  hundreds of events) during the first set of queries, but a later checkpoint
  or reset left them with only 1-2 rows — **the data was gone with no warning.**
  When analyzing a live board, **capture the full result of every query
  immediately** (copy the output into your working notes). Do not assume a
  second run of the same query will return the same data. If you need
  durability, copy the DB file first: `cp kanban.db kanban-snapshot.db` and
  query the snapshot. The `workspaces/` directory and `logs/` directory are
  more durable than the DB — worker logs and git artifacts survive DB resets.

## Standard A/B cost-efficiency analysis

When comparing two pipeline strategies (e.g., fan-out vs single-session),
produce this table for each side:

| Metric | Source | Query |
|--------|--------|-------|
| Wall-clock | board DB | MAX(completed_at) - MIN(created_at) |
| Active agent time | board DB | SUM(ended_at - started_at) per run |
| Input tokens | profile DB | SUM(input_tokens) |
| Output tokens | profile DB | SUM(output_tokens) |
| Cache-read tokens | profile DB | SUM(cache_read_tokens) |
| Reasoning tokens | profile DB | SUM(reasoning_tokens) |
| Total tokens | profile DB | SUM of all four |
| API calls | profile DB | SUM(api_call_count) |
| Cards created | board DB | COUNT(*) from tasks |
| Findings | board DB | child cards / metadata.findings_count |

Then assess: did adaptive sizing route correctly? Was quality maintained or
improved? At what artifact complexity should the cheaper strategy switch to
the heavier one? See [`references/cost-analysis-template.md`](references/cost-analysis-template.md)
for the full structured-question template.

## Reference

- **`references/cost-analysis-template.md`** — the 8-question structured
  template for a complete A/B cost-efficiency comparison (wall-clock, active
  time, token cost, cards created, adaptive sizing, quality tradeoff, switching
  threshold, schema enforcement). Copy and fill for each comparison.
