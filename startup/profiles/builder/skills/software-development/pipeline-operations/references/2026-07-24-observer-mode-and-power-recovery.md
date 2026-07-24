# Observer Mode and Power Outage Recovery — 2026-07-24

## The mistake

During an E2E livetest (task t_7c5eef0e, AI Cost Optimization / LLM Router), the dispatcher had already spawned a worker (pid 2461, run 300). The observer session should have monitored the worker's progress. Instead, the observer:

1. Launched its OWN PO session (`hermes -p product-owner --skills grill-rpc ...`) — creating a competing PO that wrote to the same grill state
2. Ran `answer.sh` manually — sending answers to PO from a different identity
3. Created branches and locked decisions directly
4. Set up grill state directories that duplicated the worker's

The user corrected: "you know you are only observer, right? not the executor"

## Why it happened

The observer session ran on the builder profile, inside the kanban task context. The system prompt's kanban task protocol says "work the task" — so the session defaulted to executing pipeline steps rather than recognizing that a separate worker process had already been dispatched.

## Root cause

No skill or instruction distinguishes between:
- **Executor mode** — the dispatcher spawned THIS session to work the card (no other worker exists)
- **Observer mode** — the dispatcher spawned a DIFFERENT session (the worker), and THIS session was started by the user via CLI for monitoring

The session has no way to know programmatically whether another worker is running for the same task. The `kanban_show` response shows `runs[]` with the current run ID and status, but doesn't flag "another PID is already working this."

## The distinction (encoded in pipeline-operations SKILL.md section 9)

**Observer mode signals:**
- The task is `running` with a non-trivial `elapsed` time (> 5 min)
- A separate `hermes -p builder --cli` process exists for this task ID (found via `ps aux | grep "kanban task <task_id>"`)
- The `current_run_id` in `kanban_show` belongs to a process that is NOT this session

**Executor mode signals:**
- The task was just claimed (started seconds ago)
- No other `hermes -p builder` process exists for this task
- `kanban_show` shows the current run as this session's

## Power outage recovery (same session)

The system experienced two power outages during the livetest. Both times:

1. Gateways auto-restarted via systemd user services
2. The dispatcher reclaimed the `running` task (stale lock detection after reboot)
3. A fresh worker was spawned for the same task
4. The worker resumed from kanban card state — found the existing dossier, re-ran the grill from scratch (since /tmp is ephemeral)

The observer's job after each outage was to verify recovery (uptime, gateways, new worker PID, task still running) and report — NOT to restart or re-execute anything.

## What worked well

- The grill itself ran deep: 65 decisions across 4 branches (routing-classification, business-model-pricing, budget-enforcement, dashboard-ux), 60 questions total
- PO caught real gaps: Anthropic format translation problem, marketing claim hedging, ground-truth/accuracy question, API format scope
- Budget enforcement went into real engineering detail: atomic check-and-reserve via Lua scripts, reservation state machines, P90 token estimation
- The task completed successfully: prototype (53KB HTML), README (8KB, 9 sections), context files persisted to ~/projects/

## Lesson

When the user asks "report status" or "is it still running?", the answer is a read-only status check — process liveness, grill decision counts, task status. Never escalate to executing pipeline steps unless explicitly directed.
