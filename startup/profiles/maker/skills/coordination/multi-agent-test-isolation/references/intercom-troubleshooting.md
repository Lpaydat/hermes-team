> ⚠️ **DEPRECATED (2026-07-21):** The intercom plugin has been removed from all profiles. This file is kept as historical reference for debugging legacy sessions. For current agent-to-agent communication, use file-based RPC + session resume.

# Intercom troubleshooting — when messages silently fail

the file-based RPC pattern routes messages through a shared broker service
(`hermes-intercom-broker.service`). When it's healthy, `intercom send` returns
`{"ok": true}` and the message arrives within seconds. When the broker is degraded,
the sender still gets `{"ok": true}` (queued) but the message is never delivered.

This silent-failure mode is the most confusing intercom problem: the sender reports
success, the receiver sees nothing, and there's no error.

## Symptom: "I sent it but they never received it"

### Step 1 — Check the broker's memory
```bash
systemctl --user status hermes-intercom-broker.service | grep Memory
```

| Memory | Status |
|--------|--------|
| < 100 MB | Healthy — look elsewhere |
| 100 MB – 1 GB | Growing — monitor |
| > 1 GB | Degraded — restart |
| > 3 GB | OOM-imminent — restart NOW |

### Step 2 — Restart the broker if degraded
```bash
systemctl --user restart hermes-intercom-broker.service
```
After restart, memory should drop to ~10 MB. Verify:
```bash
systemctl --user status hermes-intercom-broker.service | grep Memory
# Expect: Memory: 9M-15M
```

### Step 3 — Send a health-check ping
```python
# From the sender profile
kanban(action="send", to="<target>", text="ping — intercom check after broker restart", topic="intercom-health-check")
```
If this arrives, the broker is fixed. If not, continue debugging.

### Step 4 — Verify the target profile gateway is running
```bash
systemctl --user status hermes-gateway-<profile>.service | grep Active
# All should be: active (running)
```

## Symptom: intercom action returns "queued" but never delivers

The message was accepted by the broker but the target gateway isn't picking it up.

1. Check if the target profile is online:
   ```python
   kanban(action="sessions")
   # Look for the target profile with status: "online"
   ```

2. If target is online but message doesn't arrive, the gateway may need a restart:
   ```bash
   systemctl --user restart hermes-gateway-<target-profile>.service
   ```

3. Resend the message after gateway restart.

## Symptom: all intercom ops timeout

This is the OOM crash signature. From PO's memory:
> "if ALL intercom ops timeout, broker likely OOM'd (4.3G RAM). Fix: systemctl --user
> restart hermes-intercom-broker (deprecated)."

**Recovery:**
```bash
systemctl --user restart hermes-intercom-broker.service
# Wait 2-3 seconds for socket to be ready
# Messages sent during the OOM period are LOST — resend them
```

## PITFALL: `ask` freezes the *caller's* whole session — prefer `send`

This is the most dangerous intercom misuse. `ask` is a **blocking** call: your
session sits idle until the target replies or the timeout expires. If the target
agent is crashed, hung, or just slow, **you freeze for the full timeout** — and if
you're the orchestrator, the user sees you go dead.

The trap is especially bad because the target may *look* alive (heartbeat visible,
process in `ps`) but actually be crashed at the LLM layer or stuck in a long turn.
A blocking `ask` on such a target freezes you for nothing.

### Rule: never use `ask` to ping a worker you don't control

When coordinating with another Hermes agent via kanban:

- **Default to `send`.** Fire-and-forget. It returns immediately and the reply
  arrives asynchronously as a new message on your next turn. Poll separately.
- **Only use `ask` when** the target is a human or an agent you know is responsive
  AND the answer is cheap enough that blocking on it is acceptable. Even then, set
  a short timeout — a 900s default is an eternity to freeze for.
- **Before `ask`-ing a dispatched worker**, check its liveness first:
  ```bash
  # Is the worker process actually alive?
  ps -p <pid> -o pid,etime,stat
  # Has it crashed and respawned? (kanban show → runs[].status)
  kanban_show(task_id=..., board=...)
  ```
  If the worker crashed and you `ask`-ed the dead PID's session, you will freeze
  until timeout with zero chance of a reply.

### Symptom: "I froze and the user saw me go dead"

You almost certainly called `kanban comment` against a target that never
replied (crashed, hung, or wrong topic). Recover by:
1. Don't re-issue the same `ask`.
2. `send` a non-blocking nudge instead.
3. Investigate target liveness via `kanban_show` runs + `ps -p <pid>`.

### Quick reference: `send` vs `ask`

- `send` — async, returns immediately, reply arrives as a future message. Default.
- `ask` — blocking, freezes your session until reply or timeout. Use only on
  known-responsive targets with a short timeout.
- If `spawn: true` is set on `send` and the target is offline, a new session is
  spawned to process the message immediately.
- **Timed-out `ask` replies may still be recoverable** from the target's session
  DB — the reply can exist even if `ask` didn't return it.

## Prevention

The broker accumulates memory under heavy intercom traffic (many agents, rapid
message exchanges, grill loops with tight question-answer cycles). If you're running
a long multi-agent test, check broker memory periodically:
```bash
systemctl --user status hermes-intercom-broker.service | grep Memory
```
Restart proactively if it crosses 1 GB during a test session.
