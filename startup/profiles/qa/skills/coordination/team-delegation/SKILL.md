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

## The kanban_chains tool (unified delegation)

`kanban_chains` is a global plugin that replaces all profile-scoped delegation tools (`kanban_delegate`, `qa_swarm`, manual `hermes kanban swarm` CLI). It handles every delegation topology — parallel chains + optional sequential fan-in — in one atomic tool call.

**Two parameters:**
- **`chains`**: parallel chains of sequential steps (fan-out). Each chain is `[{assignee, title, body, skill}]`.
- **`after`**: optional sequential steps that run after ALL chains complete (fan-in — verifier, synthesizer, report compiler).

The caller is linked to the terminal card (last `after` step, or last step of each chain if no `after`) and blocked with `kind=dependency`. The tool handles all linking and blocking internally — never call `kanban_link` or `kanban_block` to set up a topology the tool already manages.

| Profile | chains | after | Caller blocks on |
|---|---|---|---|
| tech-lead | `[[{dev}, {verifier}], ...]` | none | all verifiers |
| QA | `[[{worker}], ...]` | `[{verifier}, {synthesizer}]` | synthesizer |
| research | `[[{scout}], ...]` | `[{report_compiler}]` | report |

`kanban_delegate` and `qa_swarm` are deprecated — skills reference `kanban_chains` exclusively.

## Finding routing: findings go to tech-lead, not developer

When a profile (QA, verifier, any evaluator) discovers findings that require code changes, file them to **tech-lead**, not directly to `developer`. The tech-lead triages (is it real? worth fixing now?) and uses `kanban_chains` to create a dev+verifier pair — guaranteeing every fix gets adversarial review.

Filing directly to `developer` creates a lone card with no verifier child. This silently breaks the dev→verifier pipeline invariant: every code change must pass through dev→verifier→merge, regardless of whether it originated from the normal implementation loop or from a QA finding.

Additionally, **dedup before filing.** Multiple workers or evaluators will independently find the same issue (e.g., SSRF found by functional + security + exploratory testing). Group these as one finding noting which workers confirmed it, then file one combined report — not N redundant cards. The synthesizer step handles this — it reads all worker results, groups by root cause, and files one triage report to tech-lead.

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
- **Using generic block (`kind=null`) instead of `kind=dependency`.** A generic block creates status `blocked` — which requires manual unblocking. A dependency block creates status `todo` (dependency wait) — which auto-promotes when the parent completes. If you're waiting on another card to finish, ALWAYS use `--kind dependency`. The agent model sometimes calls `kanban_block` manually with no kind after a tool returns, creating a stuck `blocked` card. When re-blocking after auto-promotion, always pass `--kind dependency`.
- **Beads vs kanban — which layer are you in?** The team has two systems: **beads** (planning — scope, acceptance criteria, dependency ordering) and **kanban** (execution — task lifecycle, dispatch, session management). When the user says "create beads", "create tickets with dependencies", or "break this into tickets", use `bd create` + `bd dep --blocks` in the project's beads database — NOT `kanban_create`. The beads-watchdog cron (every 5 min) bridges beads→kanban automatically when a bead becomes ready. Creating kanban cards directly when asked for beads is wrong regardless of whether it "works" — it bypasses the planning layer the team relies on for dependency tracking, milestone management, and duplicate prevention.

Beads live at `<project_path>/.beads/`. A project must be in `~/.hermes-teams/startup/active-projects.json` for the watchdog to scan it. `bd init` creates the database; `bd create --title "..." --description "..."` adds an issue; `bd dep <blocker-id> --blocks <blocked-id>` wires dependencies.
- **Creating a second swarm/chains on re-dispatch.** When the orchestrator is auto-promoted after a swarm/chain completes, the dispatcher re-dispatches it. The model sometimes interprets this as "create another swarm" instead of "read the synthesizer's results and proceed." Before creating any new topology on re-dispatch, check `kanban_show` on your own card for child task completions. If a synthesizer/verifier already completed, consume those results — do not create duplicate topology.
- **Calling `kanban_chains` again to re-block on fix verifiers.** When the verifier creates fix cards on FAIL, the tech-lead is re-dispatched. Do NOT call `kanban_chains` again — that creates a brand new topology (new root, new workers). Instead, link yourself to the existing fix verifier cards and block with `--kind dependency`: `kanban_link <fix_verifier_id> <my_card_id>` then `kanban_block <my_card_id> "dependency: waiting for fix verifier" --kind dependency`. `kanban_chains` creates topology; it is not a re-block mechanism.
- **Leaking manual tool calls the plugin handles internally.** When a skill documents how to use a plugin tool (`kanban_chains`), the skill body must NOT also teach the agent to call `kanban_link` or `kanban_block` for the same topology — the plugin handles all linking and blocking. Teaching manual calls alongside the plugin creates two execution paths: the agent sometimes uses the plugin (correct), sometimes falls back to manual calls (error-prone). The skill should say "the tool handles linking and blocking internally" and never show manual link/block for the same purpose.
- **Skills must show the actual call shape.** A skill that says "call `kanban_chains` with chains and after" without showing the object structure leaves the agent guessing at parameter shapes. Always include a concrete call example with the real parameter structure: `chains=[[{"assignee": "qa", "skill": "qa-functional", "title": "...", "body": "..."}]], after=[{"assignee": "qa", "title": "..."}]`. The agent needs to see the shape, not infer it from prose.
- **Dispatcher per-board scan interval can be 15+ minutes.** The dispatcher (whichever gateway holds `.dispatcher.lock`) reaps zombie workers every ~1 min but only does a full board scan at irregular intervals (~15 min observed). A `ready` card can sit idle for 15+ minutes before the dispatcher picks it up. This is NOT a stuck card — it's dispatch latency. Check the dispatcher log (`grep 'dispatcher.*team' <dispatcher_profile>/logs/agent.log`) to see the actual scan interval before assuming a card is stuck.
- **Checking skills for cross-profile regressions after migration.** When migrating a skill from one tool to another (e.g., `kanban_delegate` → `kanban_chains`), check ALL profiles' skills AND their reference files for stale references. The main SKILL.md may be updated but `references/*.md` files can still reference the old tool name. Run `grep -rn '<old_tool_name>' <all_profiles>/skills/` to catch stale references before testing.
- **Claiming system behavior without reading actual logs.** When asked "who triggered this?" or "is the team self-healing?", do NOT guess from card titles and statuses. Read the session DB (`sqlite3 <profile>/state.db`), task events, and the `created_by` field. Tasks with `created_by: "auto-decomposer"` are the platform's response to dashboard/intercom submissions — they are NOT agents self-correcting. Verify against source before making claims about why something happened.
- **Never use `blocked` status for intermediate/draft cards.** There is a cron that scans for `blocked` tasks and handles escalation (unblock loops, triage routing). Creating cards in `blocked` status as a "draft until committed" pattern will trigger the escalation cron — drafts get unblocked, re-blocked, and eventually routed to triage. If you need a non-dispatchable intermediate state, use `scheduled` (parked, not dispatchable, no escalation cron) or don't create the cards until the commit step.
- **Don't use subprocess CLI calls in plugins that modify kanban state.** A plugin that calls `hermes kanban block` (or any write) as a subprocess creates a cross-process DB state divergence. The dispatcher's zombie reaper runs in a different gateway process and may read stale state on its next tick — seeing the card as still `running` and firing `protocol_violation`. Use the in-process `kanban_db` API directly (`from hermes_cli import kanban_db; with kanban_db.connect_closing() as conn: ...`). All operations in a single connection context commit atomically — no race condition. This pattern caused multiple test failures before the `kanban_chains` refactor from subprocess to in-process API.
- **Stale claim_lock blocking dispatch.** A card can sit at `ready` for hours because `claim_lock` retains a stale value from a prior spawn. The dispatcher's `release_stale_claims` doesn't always clean it (especially when the lock was placed by a different gateway). Diagnose with `hermes kanban --board <board> dispatch --dry-run` — if `Spawned: 0` despite a ready card, check `SELECT claim_lock, claim_expires FROM tasks WHERE id='<id>'`. If expired, clear: `UPDATE tasks SET claim_lock=NULL, claim_expires=NULL WHERE id='<id>'`.
- **Team config is startup/config.yaml, not ~/.hermes/config.yaml.** Team gateways read `startup/config.yaml` at boot. Changes to `max_in_progress_per_profile` or other kanban settings in `~/.hermes/config.yaml` have no effect on team gateways. Always edit `startup/config.yaml` and restart the dispatcher-holding gateway after changes.
- **Designing workflow before verifying against the actual codebase.** When designing or modifying a workflow that involves kanban topology, delegation plugins, or cross-profile coordination, read the real platform source (`kanban_swarm.py`, `kanban.py`), the real skill files of other profiles, and the kanban DB schema BEFORE making architecture decisions. The user catches this pattern reliably — a design that looks right on paper but doesn't match the platform's real mechanisms will fail silently. Ground every design decision in code you've actually read.
- **Synthesizing approaches before all research is complete.** If you've dispatched research subagents to inform a design decision, do not write specs or make architecture decisions until ALL research streams have returned or definitively failed. Partial research produces partial designs that miss entire dimensions.

## kanban_chains in-process API — why it matters

`kanban_chains` uses the `kanban_db` Python API directly (`connect_closing`, `create_task`, `link_tasks`, `block_task`, `complete_task`, `add_comment`). All DB operations run in a single `with kb.connect_closing() as conn:` context — card creation and the caller block commit atomically.

**Why not subprocess calls:** The original implementation called `hermes kanban` CLI as subprocesses. Each subprocess opened its own DB connection and committed independently. The dispatcher's `detect_crashed_workers` (running in a different gateway process) could read stale DB state between the subprocess commit and the next dispatcher tick — seeing the card as still `running` with `worker_pid IS NOT NULL` and firing a `protocol_violation`. This caused the orchestrator's card to crash and move to `blocked` even though the swarm cards ran correctly.

**Lesson for plugin authors:** Any plugin that modifies kanban state (block, complete, create, link) must use the in-process `kanban_db` API, not subprocess CLI calls. The in-process API uses the same DB connection mechanism as the platform's built-in kanban tools — no cross-process state divergence.

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
