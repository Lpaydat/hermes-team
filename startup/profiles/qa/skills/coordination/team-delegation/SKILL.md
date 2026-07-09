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

Hermes ships a `hermes kanban swarm` CLI command and profile-scoped plugins (like `qa_swarm`) that create a full parallel-worker → verifier → synthesizer topology in one atomic call. Use them instead of manually creating+linking multiple cards when you need fan-out with a gate. Profile plugins are preferred — they bake tailored content into each card body instead of generic boilerplate.

The swarm creates a **root card** (completed immediately) that acts as a shared **blackboard** — workers post structured JSON results to it, and the synthesizer reads the merged state.

**Platform constraints** (work around at the profile level, never edit platform source):
- `max_in_progress_per_profile` (ROOT `~/.hermes/config.yaml`, read at gateway boot) caps per-profile concurrency. Raise it + restart the gateway for parallel same-profile workers.
- The CLI's `--worker PROFILE:TITLE[:SKILL]` brackets denote optional syntax — type `:skill` directly, never literal brackets.
- `kanban_swarm.py` hardcodes verifier skill `requesting-code-review` and synthesizer skill `humanizer`. Install stub versions if these don't exist on your profile.

For the full QA-specific swarm constraints and end-to-end test results, load `references/platform-constraints.md` from the `qa-protocol` skill.

## kanban_chains — the unified topology tool (migrating)

Profile-scoped plugins (`kanban_delegate`, `qa_swarm`) are being replaced by **`kanban_chains`** — a single global plugin that handles every delegation topology with two parameters:

- **`chains`**: parallel chains of sequential steps (fan-out). Each chain is `[{assignee, title, body, skill}]`.
- **`after`**: optional sequential steps that run after ALL chains complete (fan-in — verifier, synthesizer, report compiler).

The caller is linked to the terminal card (last `after` step, or last step of each chain if no `after`) and blocked with `kind=dependency`.

| Profile | chains | after | Caller blocks on |
|---|---|---|---|
| tech-lead | `[[{dev}, {verifier}], ...]` | none | all verifiers |
| QA | `[[{worker}], ...]` | `[{verifier}, {synthesizer}]` | synthesizer |
| research | `[[{scout}], ...]` | `[{report_compiler}]` | report |

Once `kanban_chains` is built and both skills migrated, `kanban_delegate` and `qa_swarm` are deprecated. See spec at `/home/lpaydat/kanban-chains-spec.md`.

## Finding routing: findings go to tech-lead, not developer

When a profile (QA, verifier, any evaluator) discovers findings that require code changes, file them to **tech-lead**, not directly to `developer`. The tech-lead triages (is it real? worth fixing now?) and uses `kanban_delegate` to create a dev+verifier pair — guaranteeing every fix gets adversarial review.

Filing directly to `developer` creates a lone card with no verifier child. This silently breaks the dev→verifier pipeline invariant: every code change must pass through dev→verifier→merge, regardless of whether it originated from the normal implementation loop or from a QA finding.

Additionally, **dedup before filing.** Multiple workers or evaluators will independently find the same issue (e.g., SSRF found by functional + security + exploratory testing). Group these as one finding noting which workers confirmed it, then file one combined report — not N redundant cards.

## Never edit platform source (`hermes-agent/`)

The platform source at `startup/hermes-agent/` is a git submodule tracking `NousResearch/hermes-agent`. Local edits are overwritten on `hermes update`, affect every profile on the machine, and aren't tracked in the team repo. Work around constraints at the profile level: stub skills, wrapper scripts, profile-scoped plugins. If you accidentally edit platform source, revert immediately: `cd startup/hermes-agent && git checkout -- <file>`.

## Anti-patterns
- Assigning by name out of habit instead of by the description that fits the work.
- A task with no acceptance criteria ("look into X") — the assignee can't know when it's done.
- Delegating a tightly-coupled sliver you're mid-way through — the hand-off costs more than the work.
- Fan-out with overlapping slices — workers duplicate effort and collide.
- Fire-and-forget: delegating, then never reading the result or unblocking the assignee.
- **Expecting parallel execution from same-profile fan-out** — `max_in_progress_per_profile` (global, root config) means child cards with the same assignee run serially. Raise the cap or use different profiles for parallelism.
- **Calling `kanban_block(kind=dependency)` without `kanban_link`.** The block sets status to `todo`, but without a parent→child link in `task_links`, `recompute_ready()` never promotes the card when the dependency completes — it stays stuck forever. Always pair them: `kanban_link(target, my_card_id)` first, then `kanban_block`.
- **Creating kanban cards when the user asked for beads.** Beads (`bd create` + `bd dep`) are the planning layer — scope, acceptance criteria, dependency ordering, milestones. Kanban cards are the execution layer — task lifecycle, dispatch, session management. When the user says "create beads" or "create tickets with dependencies," use `bd create` + `bd dep --blocks`, NOT `kanban_create`. The beads-watchdog bridges beads→kanban automatically when a bead becomes ready.
- **Claiming system behavior without reading actual logs.** When asked "who triggered this?" or "is the team self-healing?", do NOT guess from card titles and statuses. Read the session DB (`sqlite3 <profile>/state.db`), task events, and the `created_by` field. Tasks with `created_by: "auto-decomposer"` are the platform's response to dashboard/intercom submissions — they are NOT agents self-correcting. Verify against source before making claims about why something happened.
- **Designing workflow before verifying against the actual codebase.** When designing or modifying a workflow that involves kanban topology, delegation plugins, or cross-profile coordination, read the real platform source (`kanban_swarm.py`, `kanban.py`), the real skill files of other profiles, and the kanban DB schema BEFORE making architecture decisions. The user catches this pattern reliably — a design that looks right on paper but doesn't match the platform's real mechanisms will fail silently. Ground every design decision in code you've actually read.
- **Synthesizing approaches before all research is complete.** If you've dispatched research subagents to inform a design decision, do not write specs or make architecture decisions until ALL research streams have returned or definitively failed. Partial research produces partial designs that miss entire dimensions.

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
