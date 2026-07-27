# PO Timeout Pattern

**Discovered:** 2026-07-22 during v0.7.1 E2E testing

## The Problem

glm-5.2 (via zai provider) takes **60-200 seconds per turn** during grill sessions. The builder session's tooling has constraints:

1. `process wait(timeout=X)` clamps to 60s max
2. Foreground `hermes --resume` with <300s timeout gets interrupted (exit 130)
3. Background mode is the only reliable path

## The Solution

### Launching PO (background mode)

```bash
# Use background=true + notify_on_complete=true + timeout=900
# The builder keeps working while PO generates
terminal(
  command="hermes -p product-owner --skills grill-rpc -z 'Grill the builder on: ...' --cli",
  background=true,
  notify_on_complete=true,
  timeout=900
)
```

### Resuming PO (via answer.sh)

answer.sh wraps the hermes call in `HERMES_GRILL_TIMEOUT` (default 600s):

```bash
# Correct: use background + notify_on_complete + large timeout
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
terminal(
  command="answer.sh --file /path/to/answer.md",
  background=true,
  notify_on_complete=true, 
  timeout=900
)
```

### Polling for Results

After answer.sh starts in background, use **repeated polling** not one long wait:

```python
# Pattern: poll-until-done
while True:
    result = process(action="wait", session_id=sid, timeout=60)
    if result.get("exit_code") is not None:
        break
    # Still running — the 60s wait returned without exit
    # Call process(action="wait") again
```

### What NOT to do

- ❌ `process wait(timeout=60)` — returns before PO finishes
- ❌ Foreground `hermes --resume` with timeout=180 — gets killed at exit 130
- ❌ One-shot wait — PO output arrives after tool returns

## The answer.sh Internal Timeout

answer.sh wraps the hermes call in `timeout $GRILL_TIMEOUT` internally. If the PO call times out (exit 124), answer.sh produces a clear error message:

```
ERROR: hermes --resume produced no output — likely timed out after 600s or API dropped.
Fix: increase HERMES_GRILL_TIMEOUT env var, or check that the model/provider is responding.
```

Set `HERMES_GRILL_TIMEOUT=1200` for extra-slow PO responses.
