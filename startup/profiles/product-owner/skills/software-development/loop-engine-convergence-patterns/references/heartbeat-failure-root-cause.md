# Verifier Heartbeat Failure — Root Cause Analysis

Confirmed via 3-subagent investigation (2026-08-09). The verifier agent
(PID 2055828, session `20260809_115518_c44f68`) got stuck inside a terminal
tool call that never returned for 2.5+ hours during hashtree e2e testing.

## Root Cause: No Background Heartbeat Thread

Heartbeats are NOT automatic. They piggyback on agent activity via
`_touch_activity()` (run_agent.py:3658-3711), which is called at key points:
before/after API calls, before tool execution, and inside `_wait_for_process`
poll loops (every 10s). There is no background heartbeat thread (confirmed by
searching run_agent.py — 0 results for heartbeat+thread).

## The Failure Chain

1. API call #49 returned at 12:02:06 with a `terminal` tool call (message 88930)
2. The command was a git+binary invocation that never returned
3. Last heartbeat at 12:01:47 (pre-tool-call touch)
4. `_wait_for_process` poll loop (base.py:1102-1168) should fire
   `touch_activity_if_due` every 10s, but either:
   - Never started (tool hung during subprocess spawn), OR
   - The activity callback (`get_activity_callback()`, thread-local — base.py:46)
     was None on the executing thread, making touch a silent no-op

## Why Claim Didn't Expire

- Claim TTL = 15 min (`DEFAULT_CLAIM_TTL_SECONDS = 900`, kanban_db.py:219)
- But `release_stale_claims()` (kanban_db.py:4506-4546) has a PID-alive extension:
  if the PID is alive AND heartbeat staleness < 1 hour, it extends the claim
- The process WAS alive (83% CPU, stuck in the terminal call)
- Claim was extended 3 times: 12:17, 12:32, 12:47 — each time ~15 min
- Auto-reclaim threshold: 60 min (`DEFAULT_CLAIM_HEARTBEAT_MAX_STALE_SECONDS`)
- Manual reclaim at 12:48 (13 min before auto-reclaim would have fired)

## What We Can Fix (Without Touching Hermes-Agent Code)

The root cause is in hermes-agent code (run_agent.py, kanban_db.py, base.py).
We CANNOT add a background heartbeat thread without modifying the agent core.

**Mitigation (added to workflow-engine.py cron):** A stale-claim reaper phase
that runs every minute. It checks all boards for tasks where:
1. status='running'
2. last_heartbeat older than 900s (15 min)
3. worker_pid is DEAD

For dead-PID + stale tasks: reclaim immediately. For alive-PID + stale tasks:
log WARNING (can't safely reclaim — might kill legitimate work).

This catches the crash-but-not-cleaned-up case. The alive-but-stuck case (the
actual hashtree failure) still needs the hermes-agent fix (background heartbeat
thread + lower stale threshold from 60 to 15-20 min).

## Key Evidence

| Finding | Source |
|---------|--------|
| No background heartbeat thread | run_agent.py search → 0 results |
| Heartbeat via _touch_activity → heartbeat_current_worker_from_env | run_agent.py:3693-3699, kanban_tools.py:264 |
| Last heartbeat 12:01:47, then 47 min silence | task_events table |
| Terminal tool call never returned | Session DB message 88930 (no response) |
| Claim extended 3x (PID alive + heartbeat < 1h) | kanban_db.py:4506-4546 |
| 60-min stale threshold | kanban_db.py:229 |
| 15-min claim TTL | kanban_db.py:219 |
