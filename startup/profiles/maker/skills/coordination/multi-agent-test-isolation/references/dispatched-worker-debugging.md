# Dispatched worker debugging — crash vs hang vs silent

When a dispatched kanban worker (another profile running a task card) goes silent
or crashes, this is the diagnostic path. All symptoms here were observed in real
multi-agent test runs.

## Quick triage

```
# Is the worker process alive?
ps -p <pid> -o pid,etime,stat,rss

# What does the board think happened?
kanban_show(board=<slug>, task_id=<id>)   # check runs[] + events[]
```

| Symptom | Likely cause |
|---|---|
| `runs[]: crashed`, error `pid not alive`, no message arrived | Worker blocked on a call that never returned → heartbeat starvation → dispatcher reaped it. **#1 cause: the worker's loaded skill told it to use `kanban comment.** |
| Process alive (`Ssl`), no heartbeats for >5 min, no output | Worker hung on a blocking call mid-turn (same root cause, not yet reaped) or stuck on a very long LLM turn. |
| Process alive, heartbeating, no kanban comment arrived (legacy: intercom) | Worker is working but its message never delivered. Check broker OOM (pitfall #8) or wrong target profile (dangling rename reference). |
| Dispatcher keeps spawning new pids after you kill them | Respawn race — see "Stopping a run cleanly" below. |

## Blocking-call audit (the #1 silent killer)

Before dispatching a worker with a skill, grep that skill for instructions that
will freeze the worker:

```bash
# In the target profile's skill dir:
grep -rniE "kanban.*(ask|blocking)|action.*ask|to:.*ask" \
  ~/.hermes-teams/startup/profiles/<profile>/skills/
```

Any hit is a latent crash. Rewrite the skill to the async pattern:

```
# WRONG — blocks the worker, dispatcher kills it for inactivity:
(legacy) intercom → action: ask → to: <profile> → ...

# RIGHT — fire-and-forget, then end turn:
(legacy) intercom → action: send → to: <profile> → topic: <topic>
kanban_comment(task_id=<card>, body="<the question, for durable record>")
kanban_heartbeat(note="Q1 sent to <profile>, awaiting reply")
# end turn — reply arrives on next tick or via gateway
```

The worker must `send` + `comment` + `heartbeat`, then **end its turn**. It does
NOT wait inline for a reply. The reply comes back as a new message on the next
dispatch tick or through the gateway.

### Why `ask` is fatal for workers (not just callers)
- `ask` blocks the calling thread until reply or timeout (default 900s).
- A dispatched worker must heartbeat every few minutes or the dispatcher reclaims it.
- Blocked thread → no heartbeats → `dispatch_stale_timeout_seconds` (default 4h,
  but the claim lock expires in ~15 min) → dispatcher marks `crashed: pid not alive`.
- The worker never even gets to report an error. Symptom is a clean "crash" with
  no diagnostic beyond the pid death.

## Stopping a run cleanly (no respawn race)

Killing the worker pid is NOT enough — the dispatcher sees `status=running` +
`dead pid` and spawns a replacement within seconds.

```bash
# 1. Release the dispatcher's claim on the run:
hermes kanban --board <slug> reclaim <task-id> --reason "<why>"

# 2. Kill the current worker:
kill <pid>

# 3. Archive the card (prevents future dispatch ticks from respawning):
hermes kanban --board <slug> archive <task-id>

# 4. Verify no new worker spawned:
pgrep -f "hermes.*kanban task <task-id>"   # expect empty
```

If `reclaim` says "not running / unknown id" the card is likely already archived
— the stale run record may still trigger one more spawn; kill that pid and verify
again after ~10s. There is no long-running dispatch daemon to stop; the respawns
are event-driven ticks.

## Dangling rename references

After a profile is renamed (e.g. `venture-builder` → `builder`), other profiles'
skills may still target the old name. Messages `send` to the old name silently go
nowhere (no error, no delivery). Audit after any rename:

```bash
grep -rn "<old-profile-name>" ~/.hermes-teams/startup/profiles/*/skills/ \
  ~/.hermes-teams/startup/profiles/*/memories/
```

Fix with `patch` (`cross_profile=True` required — the file belongs to another
profile). Get explicit user approval before bypassing the cross-profile guard.

## Broker health (see also intercom-troubleshooting.md — LEGACY)

```bash
systemctl --user status hermes-intercom-broker.service | grep -E "Memory|Active"
# Restart if Memory > 1GB — OOM causes silent message drops (sender sees ok:true)
systemctl --user restart hermes-intercom-broker.service
```

Broker journal rarely logs delivery failures; absence of errors in the journal
does NOT mean messages were delivered. Trust `kanban_show` comments + kanban
sessions list over the journal.
