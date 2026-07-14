# Intercom Edge Case Testing

14-category stress test suite, developed 2026-07-08 after the 3 bug fixes. Run this after any change to broker, spawner, or protocol to catch regressions and find new edge cases. The original run found Bug 4 (bidirectional spawn session collision).

## Prerequisites

1. Broker running: `cd ~/.hermes-teams/_shared/intercom && python3 -m broker.server`
2. Socket exists: `ls ~/.hermes-teams/_shared/intercom/.intercom.sock`
3. Unit tests pass: `python3 -m pytest tests/ -v` (60 tests as of 2026-07-09)

## Test categories

Run each as a separate `execute_code` block (they have independent state).

### Batch 1: Routing & data integrity (fast, no LLM)

| # | Test | What it checks | Key assertion |
|---|------|----------------|---------------|
| 1 | Bidirectional session_id | Symmetric key: A→B and B→A produce same session_id | `sid_po_to_tl == sid_tl_to_po` |
| 2 | String content delivery | Bug #2 fix: plain string content arrives intact | `"STRAWBERRY-99" in received` |
| 3 | Pipe character in topic | Separator collision: `\|` in topic doesn't break conversation_key | Topic routed correctly, content intact |
| 4 | Long message integrity | 5000+ char message not truncated | `len(received) == len(sent)` |
| 5 | Unicode/emoji content | Multi-byte chars survive round-trip | `received == original_unicode_string` |

### Batch 2: Reliability & isolation (fast, no LLM)

| # | Test | What it checks | Key assertion |
|---|------|----------------|---------------|
| 6 | Broker restart | In-memory session mapping lost (known limitation) | `sid_before != sid_after` (expected) |
| 7 | Parallel topics | 3 topics between same pair get 3 different sessions | `len(set(sids)) == 3` |
| 8 | Topic case sensitivity | normalize() lowercases: "Test" == "test" | `sid_upper == sid_lower` |

### Batch 3: Live agent memory (slow, real LLM calls)

| # | Test | What it checks | Key assertion |
|---|------|----------------|---------------|
| 9 | Bidirectional spawn | Bug 4 (fixed `intercom-am3`): both directions spawn with separate sessions per profile | `type=="spawned"` both directions, `sid_tl != sid_scout` |
| 10 | Long conversation | 8 rounds, same topic, agent recalls all 8 codes | Resume session → all codes in response |
| 11 | Concurrent messages | 5 simultaneous messages on same topic, no loss/race | All 5 received, all same session_id |

### Batch 4: Protocol features (fast, no LLM)

| # | Test | What it checks | Key assertion |
|---|------|----------------|---------------|
| 12 | Presence after disconnect | close() removes profile from roster | `scout not in connected_after` |
| 13 | Offline queue drain | Message to offline profile delivered on reconnect | Queued message with code arrives |
| 14 | Ask/Reply blocking | Blocking ask gets reply within timeout | Reply text contains expected answer |

## Key patterns for writing tests

### Broker-level test (no LLM, fast)

```python
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/.hermes-teams/_shared/intercom"))
from broker import IntercomClient

SOCK = os.path.expanduser("~/.hermes-teams/_shared/intercom/.intercom.sock")

def make_client(team, profile):
    c = IntercomClient(sock_path=SOCK)
    c.connect()
    c.register(team, profile)
    return c

po = make_client("team-alpha", "product-owner")
tl = make_client("team-alpha", "tech-lead")

# Send (note: positional order is to_profile, topic, content)
po.send(to_profile="tech-lead", topic="test", content={"text": "Hello"})
time.sleep(0.5)
msg = tl.wait_for(lambda m: m.get("type") in ("send", "ask"), timeout=3)
```

### Spawn test (uses LLM, slow)

```python
# Spawn targets an OFFLINE profile — no client connected for it
# Use a THIRD profile as the sender so neither target nor receiver is connected
sender = IntercomClient(sock_path=SOCK)
sender.connect()
sender.register("team-alpha", "ops")

result = sender.send_message({
    "type": "send", "from_team": "team-alpha", "from_profile": "scout",
    "to_team": "", "to_profile": "tech-lead", "topic": "spawn-test",
    "content": {"text": "Remember code EAGLE-909"}, "spawn": True,
}, timeout=320)

# Check result type:
# "spawned" = target was offline, session was spawned/resumed
# "sent" = target was online, message routed to live client buffer
# "error" = spawn_failed, check detail field
```

### Verifying agent memory directly

```bash
# After spawn test, resume the Hermes session and ask what it remembers
hermes -p tech-lead chat -q "What do you remember from our conversation?" \
  -Q --pass-session-id --resume <session_id>
```

## Why edge case testing matters here

The symmetric conversation key fix (Bug 3) directly caused Bug 4 — making `A→B` and `B→A` share a conversation_key exposed a latent design flaw in the `_spawned_sessions` dict that only manifests in the reverse-direction spawn path. The unit tests passed (57/57) because they didn't test bidirectional spawns. The edge case suite caught it on the first run.

**Lesson:** When a fix changes a core invariant (like session key composition), the edge case suite is mandatory — unit tests alone can't catch the cross-component interaction bugs that invariant changes expose.

## Pitfalls when testing

1. **Stale presence:** If you close a client and immediately check presence, the broker may not have processed the disconnect yet. Add `time.sleep(1)` after close.

2. **Sender = target confusion:** When testing spawn, the SENDER must be a third profile. If sender and target are the same profile, the broker sees the target as "online" (the sender's connection) and routes instead of spawning.

3. **Content shape:** Always use `content={"text": "..."}` (dict), not a bare string, in `send_message` calls. The spawner handles strings now (Bug #2 fix) but the online path expects dicts.

4. **Broker restart:** The `_spawned_sessions` dict is in-memory. After broker restart, all session mappings are lost — spawns will create fresh sessions. This is a known limitation, not a bug.

5. **Spawn test timeout:** Each spawn launches a real Hermes chat session (~40-60s per spawn). Two spawns back-to-back will hit the 5-minute `execute_code` sandbox limit. Run spawn tests one at a time via `terminal` with `timeout=300`, not in batch inside `execute_code`.

6. **Bidirectional spawn (fixed):** Bug 4 was fixed in `intercom-am3`. `scout→TL` and `TL→scout` on the same topic now each spawn their own Hermes session — `_spawned_sessions` is keyed by `(conv_key, to_profile)`. No longer a pitfall.

7. **Machine restart leaves stale socket.** After a reboot, the `.intercom.sock` file may exist but the broker process may not be accepting connections (stale PID, crashed during shutdown). Kill any stale process (`pkill -9 -f broker.server`), remove the socket (`rm -f .intercom.sock`), and restart fresh. The ops healthcheck cron will also auto-start the broker if it detects the socket is dead, but this may take a few minutes.

8. **Spawn tests hit the 5-min sandbox limit.** Each spawn launches a real Hermes chat session (~40-60s). Two spawns in one `execute_code` block will timeout. Run one spawn at a time via `terminal` with `timeout=300`, then verify memory separately with `hermes -p <profile> chat --resume <id>`.
