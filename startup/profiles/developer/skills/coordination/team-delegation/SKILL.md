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

## Anti-patterns
- Assigning by name out of habit instead of by the description that fits the work.
- A task with no acceptance criteria ("look into X") — the assignee can't know when it's done.
- Delegating a tightly-coupled sliver you're mid-way through — the hand-off costs more than the work.
- Fan-out with overlapping slices — workers duplicate effort and collide.
- Fire-and-forget: delegating, then never reading the result or unblocking the assignee.
