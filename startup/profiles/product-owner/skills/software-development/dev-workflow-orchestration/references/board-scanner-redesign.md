# Board Scanner v2 — Blocked Task Escalation (BUILT + TESTED Jul 2026)

## Status: BUILT + TESTED (7/7 pass)

Script: `board-scanner-v2.py` (in cleanroom-test project)
Test suite: `test-scanner-v2.py` (7 cases, all passing)

## The Model

```
ANY blocked task (status=blocked, any kind except dependency)
  ↓
Scanner creates escalation card for one-level-up profile
  ↓
Agent inspects (reads block reason, comments, code, contract)
  ├── Can fix → comment resolution on blocked task → complete escalation with "RESOLVED: ..."
  │   → scanner next tick: finds RESOLVED → unblocks original via CLI
  │   → original task returns to ready → dispatcher re-dispatches
  │   → agent reads comment + uses it as updated guidance
  ├── Can't fix → comment reason → block own escalation card
  │   → scanner next tick: escalation is blocked → escalate one level higher
  │   → chain: dev→TL→PO→human
  └── Human-only → comment "HUMAN_REQUIRED: <reason>" on blocked task
      → scanner skips (filtered out)
```

## Escalation Chain

| Who blocked | Escalate to |
|---|---|
| developer | tech-lead |
| verifier | tech-lead |
| tech-lead | product-owner |
| product-owner | human (HUMAN_REQUIRED auto-tagged) |

## Why the Scanner is the Unblock Bridge

**Agents CANNOT unblock foreign tasks** via the tool API.

Source: `tools/kanban_tools.py:135` — `_enforce_worker_task_ownership`:
```python
env_tid = os.environ.get("HERMES_KANBAN_TASK")
if not env_tid:
    return None  # orchestrator/CLI — allowed
if tid != env_tid:
    return tool_error("worker is scoped to task X; refusing to mutate Y")
```

The tool API (`kanban_unblock` → `_handle_unblock` → `_enforce_worker_task_ownership`) rejects foreign task IDs for dispatched workers.

The CLI (`hermes kanban unblock` → `_cmd_unblock` → `kb.unblock_task`) has NO ownership check. The scanner (zero-token cron) uses CLI, so it CAN unblock any task.

**Live test proof:**
```
HERMES_KANBAN_TASK=t_A hermes kanban --board startup unblock t_B
→ "Unblocked t_B"  ← SUCCEEDED (CLI bypasses ownership)
```

## Duplicate Prevention (NOT task_links)

Task_links DON'T work for escalation cards:
- Creating a card with `--parent <blocked_task_id>` when the blocked task is not `done` → child stuck in `todo` (recompute_ready won't promote)
- Even `--force` promote gets demoted back by recompute_ready on next tick

**What works**: standalone escalation cards (no parent link) + title matching.
- Title pattern: `[ESCALATION] Resolve block on <blocked_task_id>: ...`
- Detection: `SELECT ... WHERE title LIKE '[ESCALATION] %<blocked_task_id>%' AND status NOT IN ('done','archived')`
- Idempotent: if non-done escalation exists → skip

## Resolution Detection (task_runs.summary, NOT tasks.result)

**CRITICAL BUG FOUND + FIXED**: `kanban complete --summary "RESOLVED: ..."` stores the summary in `task_runs.summary`, NOT `tasks.result`. The `tasks.result` column is empty.

Wrong query (returns nothing):
```sql
SELECT id FROM tasks WHERE title LIKE '[ESCALATION] %X%' AND result LIKE 'RESOLVED:%'
```

Correct query (works):
```sql
SELECT t.id FROM tasks t
JOIN task_runs r ON r.task_id = t.id AND r.outcome = 'completed'
WHERE t.title LIKE '[ESCALATION] %X%'
  AND t.status = 'done'
  AND r.summary LIKE 'RESOLVED:%'
ORDER BY t.completed_at DESC LIMIT 1
```

## What Was REMOVED from v1

| v1 behavior | Why removed |
|---|---|
| Transient auto-unblock (2min cooldown) | Dispatcher circuit breaker handles retries natively (`consecutive_failures >= failure_limit`) |
| Children/stuck-child check | Irrelevant — blocked task needs attention regardless of children |
| Max 3 escalation limit | Agent reads comments + history, decides for itself |
| Complex state JSON tracking | Replaced by title matching + card status queries |
| Crash exhaustion detection | Dispatcher's `gave_up` + circuit breaker handles this |

## Test Results (7/7)

| Test | What It Proves |
|---|---|
| T1 | Blocked developer → escalation created for tech-lead |
| T2 | RESOLVED escalation → original task unblocked (task_runs JOIN fix) |
| T3 | HUMAN_REQUIRED comment → no escalation |
| T4 | Idempotency — scanner run twice → 1 escalation |
| T5 | Dependency block (status=todo) → not scanned |
| T6 | Escalation blocked → escalated higher to PO |
| T7 | Multiple blocked tasks → each gets own escalation |

## Deployment

**DEPLOYED Jul 2026 — now Phase 3 of `scripts/workflow-engine.py` (combined cron).**
The old standalone `board-scanner.py` script has been removed. Board scanning
now runs every 1 minute as Phase 3 of the combined workflow engine, after
bead-sync (Phase 1) and auto-dispatch (Phase 2). See
[references/workflow-engine-design.md](workflow-engine-design.md) for the
combined cron design.

**Proven in production during C6 R1**: detected a stale-worktree-blocked tech-lead (spawn_failed after leftover worktree from previous test), escalated to PO, PO resolved, scanner unblocked the task, pipeline continued autonomously.
