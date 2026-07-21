---
name: multi-agent-test-isolation
description: Isolate and clean the environment before testing cross-agent interactions (grill loops, review gates, swarm patterns). Use when setting up a test of any multi-agent workflow, when a "fresh" test got contaminated by prior context, or when cleaning up after a test run. Load BEFORE creating any test card or sending any test message.
version: 1.0.0
metadata:
  hermes:
    tags: [coordination, testing, isolation, kanban, multi-agent]
    category: coordination
    related_skills: [team-delegation]
---

# Multi-agent test isolation — clean slate for workflow tests

When you test a cross-agent interaction (grill loop, review gate),
the participating agents carry their full history into the test session: memory,
session_search results, and board visibility all leak prior context. A "fresh" test
on a real board with a real subject will almost always get contaminated — the agent
finds prior work on the same topic and references it instead of working from your
test brief.

## When to use

- Testing cross-agent kanban interactions and grill loops between profiles
- Testing a grilling/interview loop between two agents
- Testing any kanban-based workflow (swarm, chains, review gates) before real use
- A prior test got contaminated and you need to clean up and restart
- Setting up a clean-room validation of a new skill or plugin

## Isolation checklist (do ALL before creating any card)

### 1. Create a throwaway board
```bash
hermes kanban boards create <test-slug> --name "Test: <what>"
```
Never reuse a real work board (`hermes-hq`, venture boards, etc.). Test tasks pollute
pipeline scans, portfolio state, and dispatcher loops.

### 2. Pass board explicitly on EVERY kanban call
```
kanban_create(board="<test-slug>", ...)
kanban_show(board="<test-slug>", ...)
```
Without `board=`, the tool resolves to the "current" board symlink — which may point
at ANY board, not what you assumed. **This is the #1 cause of test cards landing in
the wrong place.** Always verify with `hermes kanban boards list` after creation.

### 3. Clean agent context (if the test needs a true clean slate)
If the agent has prior sessions about the test subject, purge them. See
`references/clean-agent-context.md` for the full procedure, and
`references/intercom-troubleshooting.md` for intercom message delivery debugging
(broker OOM silent-failure mode, send vs ask semantics). Quick version:

```bash
# Check what sessions exist
hermes -p <profile> sessions list --limit 50

# Purge old sessions (be careful not to delete active real work)
hermes -p <profile> sessions prune --before "<date>" --yes

# For surgical cleanup, delete specific sessions
hermes -p <profile> sessions delete <session-id> --yes

# Rebuild FTS index after bulk deletion
hermes -p <profile> sessions optimize
```

**CRITICAL:** Before purging, identify sessions for REAL work (running tasks) and
exclude them. Check `ps aux | grep "hermes.*kanban task"` for active workers.

See also `references/dispatched-worker-debugging.md` for the full crash-vs-hang
diagnostic path, the blocking-call audit (the #1 cause of silent worker death),
and the clean run-stop sequence.

Also check the agent's MEMORY.md for references to prior test runs:
```bash
cat ~/.hermes-teams/startup/profiles/<profile>/memories/MEMORY.md
```
Remove lines referencing test artifacts (use `patch` with `cross_profile=True`).

### 4. Use a synthetic test subject
Never use a real portfolio item or idea the agent has seen before — it exists in
their memory and sessions and will be found via session_search. Use a fabricated
idea that exists nowhere in the agent's context. This forces the agent to work
only from the card body.

### 5. Add explicit no-search instructions to the card body
```
## CRITICAL: Clean-room test
Do NOT search your memory, session history, or other boards.
Work ONLY from the brief in this card.
```

## Board mechanics (know these)

- **Board resolution:** `kanban_create` without `board=` param → uses "current" symlink.
  The symlink target changes when you `switch` boards or when a dispatch runs. Never
  assume which board is "current" — always pass `board=` explicitly for tests.
- **Dispatch:** Not a long-running daemon per board. Dispatch ticks run on-demand
  (triggered after card creation) or manually via `hermes kanban --board <slug> dispatch`.
  A `--dry-run` shows what would spawn without spawning.
- **Board deletion:** `hermes kanban boards rm <slug>` archives (recoverable).
  `hermes kanban boards rm --delete <slug>` hard-deletes (gone forever). Use
  `--delete` for pure throwaway tests.

## Cleanup after test

```bash
# 1. Reclaim the run FIRST (releases the dispatcher's claim), then kill the worker.
#    Killing the pid alone triggers auto-respawn — the dispatcher sees "running +
#    dead pid" and spawns a new worker before you can archive. Reclaim breaks the loop.
hermes kanban --board <test-slug> reclaim <task-id> --reason "test cleanup"
# If reclaim says "not running" (card already archived), skip to archive check below.
kill <pid>

# 2. Archive the card (stops further respawns). Verify it stuck:
hermes kanban --board <test-slug> archive <task-id>
hermes kanban --board <test-slug> show <task-id> | grep status   # expect: archived

# 3. Kill any worker the dispatcher spawned during the race (check twice):
pgrep -f "hermes.*kanban task <task-id>" && kill <that-pid>

# 4. Delete the test board
hermes kanban boards rm --delete <test-slug>

# 5. Delete test sessions from participating agents
hermes -p <profile> sessions delete <test-session-id> --yes

# 6. Remove test artifacts from agent memory if any were written
```

**Respawn-race note:** the dispatcher is on-demand (ticks after card events), not
a daemon — but a kill counts as an event and triggers a tick. If you see a new
worker pid appear within seconds of killing one, that's the race, not a daemon.
`reclaim` + `archive` (in that order) is the reliable stop; killing pids alone is
not. If the card is already archived but still says "run still active," the stale
run record keeps respawning — `reclaim` clears it.

## Common pitfalls

1. **Omitting `board=` on kanban_create.** The card lands on whatever board the
   "current" symlink points at — often a real work board. The dispatcher picks it
   up and spawns a worker on the wrong board before you notice.

2. **Using a real portfolio subject.** The agent finds it in session_search or
   memory and pulls in prior analysis, making the test results invalid.

3. **Forgetting to kill workers before deleting the board.** The dispatcher respawns
   workers from queued cards. Kill the process AND archive/delete the card.

4. **Purging sessions without checking for active real work.** Always verify which
   sessions belong to running tasks before bulk-deleting. Check `ps aux` first.

5. **Not rebuilding FTS after bulk session deletion.** After direct DB manipulation
   or large prunes, run `hermes -p <profile> sessions optimize` to rebuild the FTS
   index — otherwise session_search may return stale results.

6. **Session DB timestamps are UTC, display is local.** `sessions prune --before`
   filters on UTC time. A session showing "2h ago" in local display may not match
   a `--before` filter set in local time. When in doubt, use `--older-than <duration>`
   which is timezone-agnostic.

7. **Over-specifying the test subject.** A test subject written as a full pitch deck
   (pricing, TAM, monetization, ICP) contaminates the test — it front-loads answers
   the workflow is supposed to discover. Keep test subjects as raw one-paragraph
   concepts: "a smart fermentation sensor for homebrewers" is a good test subject;
   "a $99 IoT sensor with $4.99/mo subscription targeting 1.5M US homebrewers" is
   not. Let the workflow (grill, build, test) develop the details.

8. **Intercom broker (legacy, removed) OOM → silent message failure.** The intercom broker
   (`hermes-intercom-broker.service`) could accumulate RAM (up to 4GB+) under load
   and silently drop messages. The sending agent reported success (`"ok": true`) but
   the receiving agent never got the message. Intercom has been removed from all
   profiles (2026-07-21). This entry is kept for debugging legacy sessions only.
   ```bash
   systemctl --user status hermes-intercom-broker.service | grep Memory
   # If still running and Memory > 1GB (legacy systems only):
   systemctl --user restart hermes-intercom-broker.service
   ```
   See `references/intercom-troubleshooting.md` (marked DEPRECATED) for the full debugging path.

9. **Board recreation says "already exists" after deletion.** `hermes kanban boards
   rm --delete <slug>` removes the DB but the board may reappear (auto-recreated on
   next `boards list` query or cached in the registry). If you need a truly fresh
   board, use a different slug rather than fighting recreation.

10. **Blocking calls (`intercom ask`) are a two-way kill — they freeze YOUR
    session AND kill the worker whose skill told it to `ask`.** Two failure modes,
    both observed (intercom is now removed, but the lesson applies to any blocking call):

    - **Your session freezes:** `ask` is blocking — if the target is crashed,
      hung, or on a long LLM turn, your whole session sits dead until the timeout
      (default 900s). The user sees you go silent ("you also dead??"). **Never use
      blocking calls on dispatched workers.** Use fire-and-forget patterns (kanban
      comments, file-based RPC) instead. The lesson generalizes: any synchronous
      call to a worker that might be unresponsive will freeze you.

    - **The worker kills itself:** if a skill the worker loaded instructs it to
      use `ask` (e.g. a grill/interview skill saying "reach the other agent via
      `intercom ask`"), the worker blocks waiting for a synchronous reply that
      will never come, stops heartbeating, and the dispatcher reaps it for
      inactivity — recorded as `crashed: pid not alive`. Symptom: worker claims
      `running`, then `crashed`, with no error beyond the pid death, and no
      message ever arrives at the other end. **Before dispatching a worker with a
      skill, audit that skill for any blocking instruction and rewrite it to
      fire-and-forget + `kanban_comment` + `kanban_heartbeat` + end-turn.** See
      `references/dispatched-worker-debugging.md` §"Blocking-call audit".

    If a worker's reply never arrives, check `kanban_show` runs[] + `ps -p <pid>`
    before assuming it's slow — it may have crashed and your blocking call is
    waiting on a dead session. Full debugging path in
    `references/dispatched-worker-debugging.md` and
    `references/intercom-troubleshooting.md`.

11. **Multi-turn agent interviews (grills, design reviews) should use file-based
    RPC, not kanban+intercom.** The `block_loop_detected` limit (2) + triage
    auto-escalation + `auto-decomposer` card rewrites create a loop where the
    worker loses context and re-asks the same question every 2-3 minutes. This is
    not a bug to fix in kanban config — it's the wrong substrate for multi-turn
    interviews. **Use the file-based RPC pattern instead** (skill: `peer-grill-rpc`):
    interviewer writes questions to a file, the subject answers via
    `hermes --resume` (synchronous — blocks until the interviewer writes the next
    question). No polling, no cron, no kanban, no intercom. Proven to
    reach Q15+ existential depth where the kanban loop never passed Q3. See
    `peer-grill-rpc` skill for the full architecture and pitfalls.

12. **`notify_on_complete=true` floods the next session.** Background processes
    with `notify_on_complete=true` queue completion notifications. If the session
    ends before they're delivered, they flood the NEXT session on startup —
    causing it to start working immediately on stale context without a user
    prompt. For synchronous RPC calls already handled via `process action=wait`,
    do NOT set `notify_on_complete=true` — the wait handles completion; the
    notify just creates queue pollution. Before ending a session with background
    processes, run `process(action='list')` and `close_terminal` any stale ones.

    **Note:** Intercom has been removed from all profiles (2026-07-21). The intercom
    plugin is disabled, the intercom skill is deleted, and SOUL.md/MEMORY.md are
    cleaned across all startup-team profiles. Agent-to-agent communication for grills
    is exclusively via file-based RPC + session resume. See the `self-grill` skill
    (shared, global, all profiles) for the launcher, and `peer-grill-rpc` for the
    detailed architecture reference.
