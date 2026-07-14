---
name: intercom
description: "Operate, test, and debug the Hermes intercom — agent-to-agent communication via a Unix-socket broker. Load when debugging intercom, testing agent memory across rounds, starting/stopping the broker, or investigating whether cross-profile messages accumulate context."
---

# Intercom — Agent-to-Agent Communication Infrastructure

## When to load

Load this skill when:
- Debugging, testing, or modifying the intercom system
- Investigating whether agent-to-agent communication works correctly
- Starting/stopping the broker or diagnosing connectivity issues
- Verifying that messages accumulate context across rounds (session memory)
- Filing issues about intercom behavior

## What it is

A local Unix-socket message broker (`~/.hermes-teams/_shared/intercom/`) that routes messages between Hermes profiles. Built through the dev workflow (PRD → beads → tech-lead → developer → verifier). 60 unit tests pass (47 → 57 → 60 across two bug-fix iterations). As of 2026-07-09, 4 offline delivery bugs were fixed — filed as beads (`intercom-2ai`, `intercom-iq2`, `intercom-9qf`, `intercom-am3`), fixed via dev workflow, and verified with live agent tests + a 14-category edge case stress suite. All 4 bugs are resolved; bidirectional offline conversations now work correctly. After any code change, always run the edge case test suite (see `references/edge-case-testing.md`) before claiming intercom is functional.

**Architecture:**
- `broker/server.py` — Threaded Unix-socket server. Routes JSON messages between connected clients. Knows nothing about Hermes.
- `broker/client.py` — `IntercomClient` class for connecting, registering, sending, asking, replying.
- `broker/protocol.py` — Message types, session ID computation, normalization.
- `broker/spawner.py` — Offline delivery: spawns/resumes Hermes chat sessions for offline targets.
- `plugin/__init__.py` — Hermes plugin adapter. Registers tool + hooks (`on_session_start`, `on_session_end`, `pre_llm_call`).

**Two delivery paths:**
1. **Online** (target has a live session): messages injected via `pre_llm_call` hook into the existing session's context. Context accumulates within that session.
2. **Offline** (target has no live session): broker shells out to `hermes -p <profile> chat -q <query> -Q --pass-session-id` and tries to resume the same session per topic.

## Operating the broker

```bash
# Start (MUST run as module, not as script — relative imports)
cd ~/.hermes-teams/_shared/intercom
python3 -m broker.server

# Socket location (NOT /tmp/intercom.sock)
~/.hermes-teams/_shared/intercom/.intercom.sock
# Overrideable via INTERCOM_SOCK env var or constructor arg

# Health check
python3 -c "
import socket, json
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(3)
sock.connect('$HOME/.hermes-teams/_shared/intercom/.intercom.sock')
sock.sendall((json.dumps({'type': 'register', 'team': 'test', 'profile': 'healthcheck'}) + '\n').encode())
print(sock.recv(4096).decode().strip())
sock.close()
"
```

**Common gotcha:** `python3 broker/server.py` fails with `ImportError: attempted relative import with no known parent package`. Always use `python3 -m broker.server`.

## Testing intercom end-to-end

See `references/test-patterns.md` for the full end-to-end test recipe — how to write both broker-level routing tests and live agent memory tests using the `IntercomClient` API.

Key test types:
1. **Broker routing test** — two `IntercomClient` instances exchange messages. Verify message delivery, session ID determinism, topic isolation. Fast, no agent involved.
2. **Live agent memory test** — send messages with `spawn: True` to an offline profile, verify whether the spawned agent remembers previous messages across rounds. Slow (involves LLM calls) but tests the real delivery path.

**Pitfall — content shape:** The spawner expects `content` as a dict `{"text": "..."}`, but the `IntercomClient.send()` API accepts a bare string in the `content` positional slot. Sending a string produces an empty query to the target agent. Always use `content={"text": "..."}` when constructing raw messages for `send_message`.

**Pitfall — IntercomClient.send() argument order:** `send(to_profile, topic, content, ...)` — `topic` is positional, not keyword. Calling `send(to_profile="x", topic="y", content="z")` with a string in `content` triggers a "got multiple values for argument 'topic'" error because `content` lands positionally in `topic`'s slot.

## Session ID model

Session IDs are **deterministic and direction-independent per conversation**:
```
intercom-{team}-{profile_sorted_1}-{profile_sorted_2}-{topic}-{hash8}
```
where `hash8` = first 8 hex chars of MD5 of `to_team|sorted_profiles[0]|sorted_profiles[1]|topic`.

The two profiles are **sorted alphabetically** before hashing, so `PO→TL` and `TL→PO` on the same topic produce the **same** session ID. Bidirectional conversations accumulate in one session thread.

**Fixed in bead `intercom-iq2`** (2026-07-08) — previously the hash was positional (`from_profile|to_profile`), which split conversations into two direction-specific threads.

**Fixed limitations:**
- **Bidirectional spawn (was Bug 4).** Now fixed (`intercom-am3`, commit `406a42b`). The `_spawned_sessions` dict is keyed by `(conv_key, to_profile)` — each profile gets its own Hermes session within the same conversation. Both directions of an offline conversation work.

**Remaining limitations:**
- **Async only.** Hermes has no hook to proactively trigger a new agent turn when a message arrives. The `pre_llm_call` hook only fires reactively. Messages sit in the buffer until the agent's next turn. Live side-by-side chat does not work.
- **In-memory only.** If the broker crashes or restarts, the `_spawned_sessions` mapping is lost. Messages queued for offline profiles in the broker's memory buffer are also lost. Subsequent spawns create fresh sessions.
- **Broker auto-start.** The ops healthcheck cron auto-starts the broker if the socket is dead. After a machine restart the broker was running again within minutes.

## Plugin installation

- Lives at `_shared/intercom/plugin/`
- Symlinked into each profile: `profiles/<profile>/plugins/intercom → ../../../../_shared/intercom/plugin`
- `intercom` must be in the profile's `toolsets:` list AND `plugins.enabled:` list
- Setup script: `setup.py` automates symlinking + config updates

## References

- `references/test-patterns.md` — End-to-end test recipes (broker routing + live agent memory)
- `references/known-issues.md` — Bug fix history (4 bugs found and fixed, 0 remaining)
- `references/edge-case-testing.md` — 14-category stress test suite
- `scripts/verify-memory.sh` — Quick one-shot memory verification: send a secret code via spawn, resume session, check if agent remembers
