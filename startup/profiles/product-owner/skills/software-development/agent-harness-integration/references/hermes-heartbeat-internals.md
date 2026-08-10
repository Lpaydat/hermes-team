# Hermes Kanban Heartbeat Internals — How It Actually Works

Reverse-engineered from `hermes_cli/kanban_db.py`, `run_agent.py`,
`tools/kanban_tools.py`, `agent/tool_executor.py`, and
`tools/environments/base.py`. Verified against a real stuck-worker incident
(card `t_1e1cd553`, verifier profile, hashtree board, 2026-08-09).

## The critical finding: NO background heartbeat thread

Hermes heartbeats are **activity-bridged**, not timer-driven. There is no
daemon thread that pings the board every N seconds. Heartbeats only fire when
`_touch_activity()` is called from the event loop. If the event loop is blocked
inside a tool call that never returns, heartbeats stop completely.

## The heartbeat chain

```
Event loop fires _touch_activity()
    │
    ├── run_agent.py:3658-3711
    │   Called at: API call start/end, tool execution start,
    │   _wait_for_process poll loop (every 10s), retry backoff (every 30s)
    │
    ├── If HERMES_KANBAN_TASK env var is set (worker context):
    │   │
    │   └── kanban_tools.py:264 heartbeat_current_worker_from_env()
    │       Rate-limited: _AUTO_HEARTBEAT_MIN_INTERVAL_SECONDS = 60.0
    │       (kanban_tools.py:260)
    │
    └── kanban_db.py:7136 heartbeat_worker()
        Writes tasks.last_heartbeat_at = now
```

## Activity callback is THREAD-LOCAL

```python
# tools/environments/base.py:46
_activity_callback_local = threading.local()

def set_activity_callback(cb):
    _activity_callback_local.callback = cb  # ONLY visible on THIS thread
```

This means:
- The main thread sets it at `tool_executor.py:619` before tool execution.
- Concurrent worker threads must set it independently at `tool_executor.py:853`.
- If a tool spawns its OWN internal threads, those threads have NO callback —
  `touch_activity_if_due()` inside `_wait_for_process` is a silent no-op.

## Claim TTL and reclaim logic

### Constants (`kanban_db.py`)

| Constant | Value | Line |
|----------|-------|------|
| `DEFAULT_CLAIM_TTL_SECONDS` | 900 (15 min) | 219 |
| `DEFAULT_CLAIM_HEARTBEAT_MAX_STALE_SECONDS` | 3600 (1 hour) | 229 |
| `RECLAIM_DEFER_GRACE_SECONDS` | 120 (2 min) | 239 |
| `HERMES_KANBAN_CLAIM_TTL_SECONDS` | env override for TTL | 253 |

### `release_stale_claims()` — the dispatch tick reclaim (`kanban_db.py:4454`)

Each dispatch tick, for every `running` task where `claim_expires < now`:

```
Is heartbeat stale (> 1h since last_heartbeat_at)?
├── YES → RECLAIM (kill worker, reset to ready). Even if PID is alive.
│         This is the backstop for wedged-but-alive processes (#29747 gap 3).
│
└── NO → Is PID alive?
    ├── YES → EXTEND claim by +15 min. Log "claim_extended" event.
    │         The process is alive, probably in a long LLM call. Don't reclaim.
    │
    └── NO → RECLAIM (kill worker, reset to ready).
              The process died without completing.
```

### The PID-alive extension trap

The extend-if-PID-alive path (`kanban_db.py:4506-4546`) was designed for slow
models that spend > 15 min in a single LLM call with no tool calls (hence no
heartbeat). But it has a blind spot: if a worker is stuck inside a TOOL call
(not an LLM call), the PID is alive but the process is not making progress.
The heartbeat stale check (1h) is the ONLY backstop, and it's very generous.

**Result:** A stuck worker holds its claim for up to **1 hour** before the
heartbeat-stale backstop triggers an auto-reclaim. In the incident, manual
reclaim at 47 min preceded the auto-reclaim at 60 min by only 13 minutes.

## The terminal timeout gap

`FOREGROUND_MAX_TIMEOUT = 600` (10 min, `terminal_tool.py:112`). The
`_wait_for_process` poll loop (`base.py:891`) checks `time.monotonic() > deadline`
every iteration and kills the process at timeout.

In the incident, a trivial git command (should take < 1s) held the worker for
47 minutes — 4.7x the 600s timeout. The poll loop either never started
(hung during subprocess spawn) or the deadline check was bypassed.

## Investigation recipe for stuck workers

### Step 1: Event timeline from board DB

```sql
SELECT id, kind, created_at, substr(payload, 1, 200)
FROM task_events
WHERE task_id = '<card_id>' ORDER BY id;
```

Find: last `heartbeat` → gap → `claim_extended` events (PID-alive extensions).
The gap between last heartbeat and first extension = when the worker stopped
progressing.

### Step 2: Last session activity from profile state DB

```sql
-- Find the session (from spawned event timestamp or agent.log)
SELECT id FROM sessions WHERE id LIKE '%<YYYYMMDD_HHMMSS>%';

-- Get the last messages — if last is assistant+tool_calls with no tool response,
-- the worker is blocked inside that tool call
SELECT id, role, tool_name, substr(tool_calls, 1, 300)
FROM messages WHERE session_id = '<id>' ORDER BY id DESC LIMIT 5;
```

### Step 3: Agent log for the exact freeze point

```bash
grep "<session_id>" profiles/<profile>/logs/agent.log | tail -20
```

The last `API call #N` + `tool <name> completed` pair shows what was happening.
If there's an API call result with no following tool completion, that's the
freeze point.

### Step 4: Verify claim config vs actual TTL

```sql
-- From the claimed event payload
SELECT payload FROM task_events
WHERE task_id = '<id>' AND kind = 'claimed';
-- "expires" - "started_at" from the spawn = actual TTL used
```

## Why this matters for harness design

For any harness (ngin or otherwise), the Hermes experience shows:

1. **TTL-only liveness is insufficient.** A live PID doesn't mean the worker is
   making progress. The heartbeat must be independent of the event loop.

2. **Heartbeat must be background-threaded, not activity-bridged.** If the
   heartbeat thread runs independently, it fires even when the event loop is
   blocked inside a tool call. The current Hermes design couples liveness to
   activity, which fails exactly when you need it most (stuck tool call).

3. **The stale threshold (1h) is too generous.** No genuinely active worker
   should go > 15 min without observable progress. A 15-20 min threshold would
   catch stuck workers 3-4x sooner.

4. **Terminal timeouts must be enforced even if the poll loop is bypassed.**
   A watchdog timer (separate from the poll loop) that kills the subprocess
   after FOREGROUND_MAX_TIMEOUT regardless of poll-loop state would have caught
   this case.
