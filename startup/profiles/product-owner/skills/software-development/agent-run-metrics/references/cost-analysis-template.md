# Cost-Efficiency A/B Analysis Template

Copy this template when comparing two pipeline strategies (fan-out vs
single-session, two different profiles, two different models, etc.) against
the same artifact class.

## Proven on

QA A/B test: E (qa-quick, 2 cards, adaptive sizing) vs D (full fan-out,
7 cards). Same artifact archetype (static test fixture, ~7 lines, no runtime).
E won: −57% tokens, −53% active time, +1 finding found.

## Data extraction queries

### Timing (board DB)

```sql
-- Per-run active time
SELECT r.task_id, substr(t.title,1,40) AS title,
       r.id AS run, r.profile,
       (r.ended_at - r.started_at) AS active_s,
       datetime(r.started_at,'unixepoch') AS start_ts,
       datetime(r.ended_at,'unixepoch') AS end_ts
FROM task_runs r JOIN tasks t ON r.task_id = t.id
ORDER BY r.started_at;

-- Total wall-clock
SELECT (MAX(completed_at) - MIN(created_at)) AS wall_s
FROM tasks WHERE id LIKE 't_%';
```

### Tokens + cost (profile state DB)

```sql
-- Per-session
SELECT id, title,
       input_tokens, output_tokens,
       cache_read_tokens, reasoning_tokens,
       (input_tokens + output_tokens + cache_read_tokens + reasoning_tokens) AS total_tok,
       api_call_count, estimated_cost_usd
FROM sessions
WHERE started_at BETWEEN <epoch_start> AND <epoch_end>
ORDER BY started_at;

-- Totals for a set of sessions
SELECT SUM(input_tokens) AS in_tok,
       SUM(output_tokens) AS out_tok,
       SUM(cache_read_tokens) AS cache_r,
       SUM(reasoning_tokens) AS reason,
       SUM(input_tokens + output_tokens + cache_read_tokens + reasoning_tokens) AS total_tok,
       SUM(api_call_count) AS api_calls
FROM sessions WHERE id IN ('<session1>', '<session2>', ...);
```

## The 8 comparison questions

For each side (A and B), answer:

1. **Total wall-clock** — first card created → last card completed. Include
   downstream finding triage if findings were filed.
2. **Active agent time** — sum of run durations. Note: over-counts on fan-out
   due to parallel overlap.
3. **Estimated token cost** — if `estimated_cost_usd` is 0 (provider doesn't
   bill), compare total token volume instead. Break down by input/output/
   cache-read/reasoning. The cache-read component dominates and is the key
   lever: fan-out pays it N times, single-session pays it fewer times.
4. **Cards created** — QA cards, verifier cards, finding cards. More cards =
   more board overhead, more dispatch latency, more context fragmentation.
5. **Did adaptive sizing work?** — Did the pipeline correctly size the
   artifact and route to the right execution mode? Check the plan card's
   `sizing` metadata field and whether the downstream execution matched.
6. **Is the quality loss (if any) justified by the cost saving?** — Compare
   findings count and verdict. A cheaper path that finds MORE is a clear win.
   A cheaper path that finds fewer needs a judgment call based on severity.
   Verify empirically: grep the artifact for the defects both sides should
   have caught.
7. **At what artifact size should the cheaper strategy switch to the heavier
   one?** — Based on claim count, statefulness, runtime requirements. The
   protocol's own thresholds: <10 claims/stateless → quick; 10+/stateful/
   multi-service → fan-out.
8. **Were intermediate schemas enforced?** — If one side ran before schemas
   were added to the other, the structured output in the pre-schema run was
   produced by prompt compliance, not validation. Check for: consistent vs
   inconsistent metadata field names across phases (drift = no schema),
   first-try completion with no validation errors (prompt compliance),
   presence of a schema validator in the run records. To truly test schema
   enforcement, re-run the pre-schema side WITH schemas enabled.

## Summary table format

| Metric | Strategy A | Strategy B | Advantage |
|--------|-----------|-----------|-----------|
| Wall-clock | Xs | Ys | −Z% |
| Active agent time | Xs | Ys | −Z% |
| Total tokens | XM | YM | −Z% |
| API calls | N | M | −Z% |
| Cards created | N | M | −Z% |
| Findings | N | M | who found more |
| Verdict | PASS/FAIL | PASS/FAIL | tie/winner |

## Key insight from the proven run

The dominant cost saving from single-session over fan-out is NOT fewer input
tokens or fewer output tokens — it's **fewer cache-read tokens**. Each fan-out
card re-warms the system prompt + skill context from cache. With 7 cards
that's 7 cache reads of ~200K tokens each = ~1.4M cache-read tokens. With 2
cards it's ~600K. That's where 57% of the token cost goes.

Adaptive sizing is the mechanism that prevents over-provisioning: if the
artifact is small and stateless, routing to a single session avoids the
per-card cache-read tax entirely.
