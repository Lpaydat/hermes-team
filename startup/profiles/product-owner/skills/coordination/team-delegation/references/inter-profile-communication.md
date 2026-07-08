# Inter-Profile Communication — Intercom Broker

## Status: BUILT + VERIFIED (Jul 2026)

The intercom broker was built through the dev workflow itself (PRD → beads → tech-lead → developer → verifier, zero human intervention, 47 automated tests + 14 manual tests).

## Architecture

A local IPC broker that routes real-time JSON messages between connected Hermes gateways over a Unix socket. One process, one socket, all teams.

```
~/.hermes-teams/_shared/intercom/
  ├── broker/
  │   ├── server.py     ← Unix socket server, routes messages
  │   ├── client.py     ← Thread-safe client helper
  │   ├── protocol.py   ← JSON-over-newline wire format
  │   └── spawner.py    ← Offline session spawning
  ├── plugin/
  │   ├── tools.py      ← Hermes plugin (intercom tool)
  │   └── __init__.py
  ├── tests/
  │   ├── test_broker.py    ← 36 broker tests
  │   └── test_plugin.py    ← 11 plugin tests
  └── PRD.md
```

## Protocol

JSON-over-newline on Unix socket. One JSON object per line.

### Message types
- `register` — gateway announces itself (team + profile)
- `send` — fire-and-forget message to another profile
- `ask` — blocking message, waits for reply (default 300s timeout)
- `reply` — respond to a pending ask
- `list` — list all connected sessions

### Message shape
```json
{
  "id": "uuid",
  "type": "send|ask|reply",
  "session_id": "intercom-{team}-{from}-{to}-{topic}-{hash8}",
  "timestamp": 1234567890,
  "from_team": "startup",
  "from_profile": "product-owner",
  "to_team": "startup",
  "to_profile": "tech-lead",
  "content": {
    "text": "Should we use Redis or SQLite?",
    "attachments": [{"type": "snippet", "name": "config.py", "content": "...", "language": "python"}]
  },
  "expects_reply": false
}
```

## Session Model: Per Conversation Topic

Session ID: `intercom-{team}-{from}-{to}-{topic}-{hash8}`

Hash is MD5 of `{team}-{from}-{to}-{topic}` → first 8 chars. Deterministic — same conversation components always produce the same session ID. Different topics = different sessions = no context mixing.

This solves the parallel-projects problem: PO discussing project A architecture with tech-lead AND reviewing project B PRD with the same tech-lead = two separate sessions, no cross-contamination.

## Delivery Paths

1. **Target gateway live (most common):** Broker forwards via persistent socket → plugin injects into session as context text. Instant.
2. **Target gateway offline:** Message queued in broker memory. When target connects, queued messages drained and delivered. Additionally, broker can spawn `hermes -p <profile> chat -q "..." --pass-session-id`, capture session ID, and resume it for future messages on the same topic.
3. **`ask` mode (blocking):** Sender's tool call blocks until reply or timeout. Default 300s (5 min), configurable per-ask via `timeout` parameter.

## Addressing — Team-Scoped by Default

- `to="tech-lead"` → resolves to the sender's own team
- `to="team-alpha/scout"` → explicit cross-team

The broker uses the sender's team from its registration to resolve relative addresses.

## Contact Lists

Each profile's config declares who to call and when:

```yaml
intercom:
  contacts:
    - profile: product-owner
      when: "requirements, PRD, priorities, planning"
    - profile: tech-lead
      when: "architecture, contracts, technical decisions"
    - profile: developer
      when: "implementation details, code questions"
    - profile: verifier
      when: "review questions, edge cases, ACs"
```

The `when` field tells the agent WHEN to call each contact. No priority field needed — the description IS the routing logic.

## Security — Open by Default

All profiles can reach all profiles (same machine, same OS user). Blocklist reserved for future.

## Broker Lifecycle

Started by ops healthcheck cron — if socket is dead, restart. Independent daemon, not tied to any single gateway.

## Verified Capabilities (Jul 2026)

- ✅ Register + presence broadcast (join/leave)
- ✅ Send (fire-and-forget) — message arrives at target
- ✅ Ask/Reply (blocking) — A asks, B replies, A unblocks with answer
- ✅ Ask timeout — TimeoutError raised cleanly after configured duration
- ✅ Deterministic session IDs — same topic always resumes same session
- ✅ Different topic = different session (no context mixing)
- ✅ Offline queue — message queued for offline profile
- ✅ Offline delivery — queued messages drained on connect
- ✅ Cross-team addressing — send to team-alpha/scout works
- ✅ Zero-findings verifier rule proven — intercom-duq (ask/reply) took 2 verifier iterations because verifier found a bug on iteration 1 and FAILed. Developer fixed, re-verified, clean PASS on iteration 2.

## Reference Architecture

Based on [pi-intercom](https://github.com/nicobailon/pi-intercom) — a local IPC broker for pi coding agent sessions. Key differences from the original:
- Python (not TypeScript)
- Hermes plugin (not pi extension)
- Per-conversation-topic sessions (not per-pair)
- Offline session spawning via Hermes CLI
- Team-scoped addressing
- Contact lists with `when` field
