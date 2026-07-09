---
name: team-delegation
description: The CRAFT of coordinating with other Hermes agents through the kanban board — deciding when to hand work off vs do it yourself, writing a task an assignee can actually execute, and running multi-agent patterns (dependency chains, swarm, review gates). Load when you're about to delegate or orchestrate several agents. Assumes the kanban_* tools + KANBAN_GUIDANCE for the mechanics.
version: 1.0.0
metadata:
  hermes:
    tags: [coordination, delegation, kanban, teamwork, orchestration]
    category: coordination
---

# team-delegation — hand work off well, orchestrate when it helps

This is judgment, not command syntax. For the exact `kanban_*` commands (create, claim,
comment, block, link) rely on your kanban tools and the auto-injected KANBAN_GUIDANCE. This
skill is about *what makes delegation actually work*.

## 1. First decide: delegate, or do it yourself?
Delegating has real overhead (a round-trip, a worker spin-up, context you must write down).
Hand off when at least one is true:
- **It's not your specialty.** Another agent's *description* fits the work better than yours.
- **It can run in parallel** with what you're doing (independent subtask).
- **It needs isolation** — a separate workspace/branch, or a fresh perspective (e.g. review).
- **It's large** and splits cleanly into pieces with clear interfaces.

Do it yourself when it's small, tightly coupled to what you're already holding, or the hand-off
note would be longer than just doing it. **Don't delegate to avoid thinking** — you still own
the decomposition and the acceptance criteria.

## 2. Know who you're handing to (discover, don't assume)
Before assigning, see the actual roster for *this* board:
- `hermes kanban assignees` — profiles active on this board + their task counts.
- `hermes profile list` — every profile that exists (and `hermes profile show <name>` for its role).
Match the work to a **description**, not a remembered name — routing is by description, and the
roster changes. If nothing fits, either do it yourself or flag that a capability is missing
(don't dump it on a random agent).

## 3. Write a task the assignee can execute cold
An assignee starts with **zero of your context**. A good task carries everything it needs:
- **Title:** the outcome in one line ("Add Google OAuth to the login route"), not a topic.
- **Body:** the *why*, the exact inputs (files, URLs, data), any constraints/conventions, and
  **explicit acceptance criteria** ("done = tests pass + PR opened"). Link related tasks.
- **One purpose per task.** If you're tempted to write "and also…", that's a second task.
- **Right-size it.** A task another agent can finish in one focused run. Too big → split and
  `link` the pieces.
Rule of thumb: if a competent stranger couldn't start from the task alone, add what's missing.

## 4. Patterns — pick the smallest that fits
- **Single hand-off:** one task, one assignee. Most work. Comment to clarify; don't micromanage.
- **Dependency chain:** create the pieces, `link` child→parent so each waits for the one before
  (the board auto-promotes when the parent finishes). Use for build→test→review order.
- **Fan-out / swarm:** several independent workers in parallel, then a **verifier** and a
  **synthesizer** that depend on all of them. Use for "cover a lot of ground fast" — surveys,
  multi-file changes, generate-then-judge. Give each worker a distinct slice so they don't overlap.
- **Review gate:** a second agent whose description is *review*, on a task that `link`s to the
  implementer's — an independent check before "done." Cheap insurance on risky work.

## 5. Stay in the loop without hovering
After delegating: keep working. Check back via the task's comments/events (`kanban show`,
`tail`, `runs`), not by re-doing the work. If an assignee **blocks** (`needs_input`/`dependency`),
that's the signal to step in — answer the question or resolve the parent, then unblock.

## 6. Block honestly yourself
When *you* can't proceed, block with the truthful kind instead of looping or guessing:
`needs_input` (a human must decide/provide something), `dependency` (waiting on a parent task),
`capability` (no agent can currently do this). A clear block moves the whole board forward; a
spinning agent stalls it.

## The kanban swarm pattern (platform-native)

Hermes ships a `hermes kanban swarm` CLI command (backed by `kanban_swarm.py`) that creates a full parallel-worker → verifier → synthesizer topology in one atomic call. Use it instead of manually creating+linking multiple cards when you need fan-out with a gate.

```bash
hermes kanban swarm \
  "Goal: <final outcome>" \
  --worker qa:"Functional test"[:qa-functional] \
  --worker qa:"Journeys test"[:qa-journeys] \
  --verifier qa \
  --synthesizer qa \
  --created-by qa \
  --json
```

This creates:
- A **root card** (completed immediately) that acts as a shared blackboard
- **Worker cards** (ready, parallel) — each can have specific skills loaded via `[:skill,skill]`
- A **verifier card** (todo until all workers done) — gates the synthesizer
- A **synthesizer card** (todo until verifier passes) — produces the final output

Workers post structured JSON to the root card's comments via the blackboard pattern:
```python
# Post a structured update (from Python/execute_code):
# post_blackboard_update(conn, root_id, author="worker", key="verdicts", value={...})
# latest_blackboard(conn, root_id) → merged dict of all structured comments
```

The blackboard is the shared state mechanism — workers don't need to see each other's full context, just the structured facts on the root card.

**Critical constraint: `max_in_progress_per_profile: 1`.** The global dispatcher setting caps each profile to 1 concurrent task. If all swarm workers are `assignee=qa`, they execute **serially** (one at a time), not in parallel. To get true parallelism:
- Raise `max_in_progress_per_profile` in the ROOT `~/.hermes/config.yaml` (not per-profile — the dispatcher reads only the root config; restart the gateway after changing)
- Or use different profiles for different workers
- Or accept serial execution (still durable and crash-safe, just slower)

## `kanban_delegate` — a real plugin tool (tech-lead only)

`kanban_delegate` is a profile-scoped plugin at `tech-lead/plugins/dev_workflow/`. It atomically creates dev + verifier cards, links the caller as dependent on the verifier, and blocks with `kind=dependency`. It is NOT available to other profiles unless the plugin is installed there. The QA profile uses `hermes kanban swarm` CLI directly from the skill instead — a platform-native command that creates parallel workers → verifier → synthesizer with a shared blackboard.

## Anti-patterns
- Assigning by name out of habit instead of by the description that fits the work.
- A task with no acceptance criteria ("look into X") — the assignee can't know when it's done.
- Delegating a tightly-coupled sliver you're mid-way through — the hand-off costs more than the work.
- Fan-out with overlapping slices — workers duplicate effort and collide.
- Fire-and-forget: delegating, then never reading the result or unblocking the assignee.
- **Using `kanban_delegate` as if it's a real tool** — it's a convention name in the tech-lead skill, not an actual command. Use `kanban_create` + `kanban_block`.
- **Expecting parallel execution from same-profile fan-out** — `max_in_progress_per_profile: 1` (global, root config) means child cards with the same assignee run serially. Raise the cap or use different profiles for parallelism.

## delegate_task fragility under rate limits

`delegate_task` subagents are **ephemeral** — they die with the parent session and share the parent's API rate limit pool. Under sustained load (e.g., 3+ subagents running concurrently, or long-running research tasks), they frequently hit HTTP 429 rate limits and fail silently after exhausting retries. Observed failure pattern: subagent receives the prompt, makes zero tool calls, hangs for 20-40 minutes, then dies with a 429.

**When to use `delegate_task` despite fragility:**
- Short, focused tasks (< 5 minutes, < 10 API calls) — the verifier's Phase B fresh-eyes pattern.
- Tasks that need shared host state (a running server the parent started — kanban child workers can't access it).
- Tasks where losing the result on crash is acceptable (re-running is cheap).

**When to prefer kanban child cards instead:**
- Long-running tasks (> 5 minutes, research, multi-step analysis).
- Tasks that need durability (survive parent session crash).
- Tasks that need a fresh context window (not shared with parent).
- When the API is under load and rate limits are likely.

**Recovery pattern when a delegate_task subagent hangs:** Check the session database (`sqlite3 <profile>/state.db "SELECT id, message_count, tool_call_count, end_reason FROM sessions ORDER BY started_at DESC LIMIT 5"`) — a session with 1 message, 0 tool calls, and no `end_reason` is stuck on an API call. Kill the sandbox process (`pkill -f hermes_sandbox`) and either re-dispatch with simpler instructions (no web research — use training knowledge only) or do the work yourself.
