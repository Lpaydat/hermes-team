# Spec: Intercom Broker Durability

Status: ready-for-agent · Owner: operator · Origin: 2026-07-10 intercom audit

## Problem Statement

The intercom broker is the communication backbone for agent-to-agent conversations (venture-builder ↔ product-owner pitches, grilling exchanges, report-backs). It is a single shared process that has been observed to exit silently within an hour of starting, leaving no traceback. Its watchdog runs only every 60 minutes, so the backbone can be dead for up to an hour while the rest of the system assumes messages are flowing. A separate watchdog bug (fixed during the audit) had the healthcheck falsely reporting "already starting" whenever *any* process's command line merely contained the broker's start string — the watchdog refused to spawn the broker while reporting success, and the cron recorded `ok` for runs that healed nothing. The combination means agents can `send` into a void with nobody noticing.

## Solution

Make the broker effectively always-on: supervise it so it restarts immediately on exit, shorten the detection window as a belt-and-braces fallback, and make liveness observable. Diagnose (or render moot) the silent-exit cause by having supervision own the process lifecycle rather than a fire-and-forget `nohup` from a cron shell.

## User Stories

1. As any profile agent, I want intercom sends/asks to reach their target whenever the machine is up, so that inter-agent conversations never silently drop.
2. As venture-builder, I want my pitch to product-owner delivered or visibly failed, so that a venture never dies in a dead socket.
3. As the ops profile, I want the broker supervised with automatic restart, so that a silent exit heals in seconds, not an hour.
4. As the ops profile, I want the watchdog to detect a dead socket within minutes, so that even supervisor failures are caught quickly.
5. As the operator, I want broker liveness and restart history observable (log + healthcheck output), so that I can see when and how often it died.
6. As an agent whose recipient is offline, I want my message queued and delivered on their next connect, so that transient downtime degrades to latency, not loss.
7. As a developer of the broker, I want the silent-exit cause identified or eliminated by design, so that reliability rests on understanding, not restarts alone.
8. As the operator, I want the watchdog's process detection to match only real broker processes, so that diagnostic commands or shells can never fake a healthy state (regression guard for the fixed bug).

## Implementation Decisions

- **Primary: supervised lifecycle.** Run the broker under a user-level supervisor with restart-on-exit (systemd user service with `Restart=always` or the platform's equivalent). The supervisor — not a cron shell — owns the process group, which also removes the suspected cause of the silent exits (a `nohup`-spawned child reaped with its parent's session).
- **Belt-and-braces: watchdog cadence.** Keep the healthcheck as a fallback probe and tighten its schedule from hourly to a few minutes. The healthcheck stays socket-first (a stale process with a dead socket is not healthy).
- **Process matching by process identity, not command-line substring** (already fixed; codify as a regression requirement): liveness checks must match the process's executable identity, never a substring of any command line.
- **Queue semantics stay in-broker** (offline messages drain on next connect). Document explicitly that queued messages do NOT survive a broker restart (in-memory), and that senders of `ask` receive a timeout — the pipeline's escalation paths treat an intercom timeout as "recipient unavailable," not as an answer.
- **Observability:** broker start/stop/restart events appear in the broker log with timestamps; the healthcheck reports the socket path, probe result, and action taken. No new dashboard.

## Testing Decisions

- **Seam: the broker socket protocol** (existing 60-test suite + the session's round-trip script) — tests assert externally observable behavior: connect, register, send, ask/reply, presence, queue-drain.
- **New drills at the same seam:** (a) kill the broker process → assert the supervisor restores a live socket within its restart window and a subsequent round-trip succeeds; (b) send to an offline profile → connect that profile → assert queued delivery; (c) restart the broker with messages queued → assert documented loss semantics (and that `ask` callers time out rather than hang).
- **Watchdog regression test:** with a decoy process whose command line contains the broker start string (but is not the broker), a dead socket must still trigger a spawn.
- **Prior art:** the existing test suite already boots real brokers on temp sockets; extend that harness rather than mocking.

## Out of Scope

- Cross-machine or network transport; authentication/encryption on the socket (same-user Unix socket trust model unchanged); durable message persistence across restarts; delivery guarantees stronger than at-most-once for queued messages; broker feature work (rooms, broadcast, history).

## Further Notes

- The false-positive watchdog bug and the qa profile's missing plugin symlink were both fixed and verified live during the audit (round-trip confirmed). This spec covers the remaining durability work only.
- The broker is pure-stdlib Python with a small surface (~2k lines); prefer supervision and small hardening over architectural change.
