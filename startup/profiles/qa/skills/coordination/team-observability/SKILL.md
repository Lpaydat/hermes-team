---
name: team-observability
description: Read the Hermes team's own operational telemetry to diagnose how it's performing — bottlenecks, failure patterns, load imbalance, stuck tasks, structural smells. Load before running a team health check, designing an observability/analyst profile, or diagnosing why work isn't flowing across the board.
version: 1.0.0
metadata:
  hermes:
    tags: [coordination, observability, kanban, telemetry, diagnostics, sre]
    category: coordination
---

# team-observability — diagnose how the team is actually running

This skill is for when the **team itself is the patient**, not any one task. You read
the board's telemetry, the gateway state, the cron schedule, and the profile topology,
then reason about: *is work flowing, where's the friction, and is the structure right?*

This is the complement of `team-delegation` (which is about *routing* work). Here you're
*watching the routing work* — and catching when it doesn't.

## When to load

- Someone asks "how is the team doing?" / "why isn't work moving?" / "what's broken?"
- You're designing a meta-observer / SRE / analyst profile for the team.
- A scheduled health-check or heartbeat scan is running.
- You're about to restructure the team (add/split/merge profiles) and need evidence.

## Where the telemetry lives

**The #1 gotcha — don't waste time on the empty DB.** The top-level
`~/.hermes/kanban.db` is empty/legacy. The *real* board data lives at:

```
~/.hermes/kanban/boards/<board-slug>/kanban.db      ← THIS ONE
```

Find the active board via `cat ~/.hermes/kanban/current` or list
`~/.hermes/kanban/boards/`. In a default install the board is `hermes-hq`.

For the complete data-source map (every file, every schema, ready-to-run SQL), see
**`references/team-telemetry-map.md`** — load it with `skill_view` when you need the
exact queries. The map covers: kanban DB schema + diagnostic SQL, gateway state,
channel directory, cron health, profile topology, and process/worker state.

## The five diagnostic dimensions

Frame your analysis around these. Each calls for a different fix:

1. **Throughput** — tasks completed per unit time, per profile. Is anything finishing?
2. **Failure modes** — group failures by *root cause*, not symptom count. "32 crashes,
   all `protocol_violation`, all 'worker exited rc=0 without completing'" is one finding,
   not 32. Read `task_runs.error` + `task_events.payload` for `gave_up` / `crashed`.
3. **Latency** — time from `created_at` to `completed_at`, and *where it stalls*
   (which status it sits in longest). A task blocked for 3 days then done in 5 min has
   a 3-day latency problem, not a 5-min execution problem.
4. **Load balance** — task counts per assignee. One profile with 5 blocked while 7 sit
   idle is a chokepoint, possibly structural (wrong profile shape) not just a bad day.
5. **Structure** — do the profiles map cleanly to the work? Overlaps (two profiles whose
   descriptions cover the same task type), gaps (a task type no profile is suited for),
   and over/under-provisioning (11 profiles, 7 idle) are *design* findings, not incidents.

## How to reason about a finding

When you hit friction, trace it to its *class* before proposing a fix:

- **Capacity** — too much work for one profile → rebalance or split the profile.
- **Capability** — the wrong profile owns the task → re-route or redefine the role.
- **Protocol** — the worker doesn't know how to complete (e.g. exits without
  `kanban_complete`) → fix the worker's skill/prompt, not the workload.
- **Structural** — the team's shape doesn't match the work's shape → add/merge roles.

Each class has a different remedy. Don't jump to "add more profiles" before checking
whether the existing ones are mis-wired.

## Producing a useful digest

A good team-health report is **specific and clinical** — numbers before adjectives:

- ❌ "researcher seems stuck" → ✅ "researcher has 5 blocked tasks, all failing on the
  same protocol violation (worker exits rc=0 without completing) — root cause likely [X],
  recommend [Y]"
- ❌ "lots of failures" → ✅ "32 crashed runs vs 3 completed (~90% failure); 100% of
  crashes are the same protocol violation"
- ❌ "consider rebalancing" → ✅ "researcher holds 5 of 7 open tasks; reviewer, scout,
  advisor, developer, vault-keeper are idle — work is not reaching them"

Sections that work: Flow summary → Bottlenecks → Failures (by root cause) → Load balance
→ Structural findings → Recommendations (prioritized, actionable).

## Authority when acting on findings

If the profile using this skill is a *scoped-fixer* (observer + safe remediations):

- **Read everything** freely — never hesitate to dig into the DB, logs, config, processes.
- **Write via kanban only**: comments to leave diagnoses, `kanban_create` to file scoped
  fix tasks against the right profile (self-contained body — the assignee has no context).
- **Safe-ops allowlist**: unblock a task stuck on a diagnosed-benign loop, kill a verified
  zombie PID, restart a crashed cron. Log every safe-op in a comment.
- **NEVER edit another profile's config/SOUL/skills/prompts/cron.** Structural changes
  are *proposed* via filed tasks, never applied. You design; you don't impose.

## Heartbeat vs deep-dive (two cadences, one skill)

- **Deep-dive** (daily, full reasoning, always delivers): all five dimensions, root-cause
  analysis, structural recommendations. Worth reading every time.
- **Heartbeat** (every few hours, cheap scan, **silent when healthy**): only checks for
  anomalies — new crashes, stale heartbeats, gateway down, unblock loops, zombie PIDs.
  Emits NOTHING when all clear. Trust erodes fast from "all clear" spam; silence = healthy.

## Pitfalls

- **Querying the empty DB.** Always resolve the real board path first
  (`cat ~/.hermes/kanban/current`), then query `boards/<board>/kanban.db`.
- **Stale claim_lock stranding ready cards.** When a task is spawned, the dispatcher
  writes `claim_lock = "lambda:<PID>"` with a TTL (default 15 min). If the worker
  completes or crashes, the lock SHOULD be cleared by `release_stale_claims` — but
  sometimes it isn't (observed: lock expired 9+ hours ago, field still set, dispatcher
  skipped the card every tick). Symptom: a `ready` card sits idle indefinitely while
  the dispatcher reports `Spawned: 0` on every tick. Diagnosis: check
  `SELECT id, claim_lock, claim_expires FROM tasks WHERE status = 'ready'` — if
  `claim_lock` is non-NULL and `claim_expires` is in the past, the lock is stale.
  Fix: `UPDATE tasks SET claim_lock = NULL, claim_expires = NULL WHERE id = '<id>'`.
  This is NOT the same as dispatch latency (15+ min scan interval) — a stale lock
  blocks forever, dispatch latency resolves on the next tick.
- **Dispatch latency vs stuck card.** The dispatcher reaps zombies every ~1 min but
  only does a full board scan at irregular intervals (~15 min observed in practice).
  A `ready` card sitting for 15 min is normal; sitting for 30+ min warrants checking
  `claim_lock` (above) and the dispatcher log
  (`grep 'dispatcher.*<board>' <dispatcher_profile>/logs/agent.log`).
  Verify with `hermes kanban --board <board> dispatch --dry-run` — if it shows
  `Spawned: 0` despite a ready card, the card is being skipped (stale lock, profile
  cap, respawn guard).
- **Config boot-time caching.** Gateways read `kanban.max_in_progress` and
  `kanban.max_in_progress_per_profile` at boot and cache them. Changing config after
  boot does NOT affect running gateways. The dispatcher reads the **lock-holding
  gateway's OWN profile config** — the `kanban:` block of
  `startup/profiles/<profile>/config.yaml` — NOT the global `startup/config.yaml` and
  NOT `~/.hermes/config.yaml`. Because the lock-holder is non-deterministic (any
  profile gateway can hold `startup/kanban/.dispatcher.lock`), **all profile configs
  must agree** on kanban caps for a change to take effect regardless of which gateway
  dispatches. To change dispatcher caps, edit every profile's `config.yaml` and
  restart the gateway holding the dispatcher lock.
  Check which gateway holds the lock: `cat <kanban-boards-dir>/.dispatcher.lock`.
- **Reporting "no cron jobs" from one `cronjob action=list`.** That tool is
  profile-scoped; in a multi-profile team it returns `0` for every profile except
  the one the shell is running as, while the operator's GUI shows the team-wide
  total. Cron jobs live per-profile in `<profile-home>/cron/jobs.json` (under
  `~/.hermes/profiles/<name>/` or `~/.hermes-teams/startup/profiles/<name>/`).
  Enumerate across all profiles before drawing any conclusion — see Section 4 of
  `references/team-telemetry-map.md` for a copy-paste team-safe loop.
- **Counting symptoms, not causes.** 32 identical crashes is ONE finding. Group by root
  cause (error text, event payload) before reporting.
- **Treating a protocol failure as a capacity problem.** If every worker exits cleanly
  without completing, adding more workers produces more clean exits — the fix is in the
  worker's wiring, not the workload.
- **Forgetting delivery is broken too.** Gateway disconnects are themselves a finding —
  check `gateway_state.json` as part of the scan, not just the board.
- **Proposing structural changes you can't un-propose.** File split/merge/add-profile
  recommendations as tasks for a human, with a clear design and rationale. Don't apply.
