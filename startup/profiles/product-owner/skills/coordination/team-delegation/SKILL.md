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

### 2a. Pre-flight: verify every assignee can actually receive work
**Before** creating tasks, confirm each target profile is ready to dispatch — a worker that
can't claim stalls silently and you won't know until you wonder why nothing happened:
- **Gateway running?** Profiles need their gateway service installed AND started to receive
  dispatched tasks: `hermes gateway status --profile <name>`. If stopped:
  `hermes gateway install --profile <name> && hermes gateway start --profile <name>`.
  A freshly-created profile has no systemd service until you install it.
- **Tools enabled?** `hermes -p <name> tools list` — confirm terminal, file, code_execution
  are enabled for coding tasks. A profile with tools disabled will fail mid-task.
- **Approvals mode?** Check `config.yaml` for `approvals.mode: smart` (or `yolo`) — a profile
  in default confirm mode will hang waiting for human approval that never comes in headless dispatch.
- **Harness on PATH?** If the task uses external coding tools (pi, zlaude, etc.), verify they
  resolve from a clean bash shell (headless workers run bash, not fish):
  `env -i HOME=$HOME PATH="$HOME/.local/bin:/usr/bin" bash -c 'which <tool>'`.
  Fish-only aliases and fnm session shims are invisible to dispatched workers — create stable
  wrappers in `~/.local/bin/` if needed.

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
  **Critical role-separation (do NOT get this wrong):**
  
  | Role | Profile | Does | Never Does |
  |------|---------|------|------------|
  | Planner | `tech-lead` | Contracts work, creates kanban cards for `developer` | Writes code |
  | Generator | `developer` | Invokes coding harness (`pi`/`zz`) as subprocess, runs mechanical gates | Grades quality, merges |
  | Verifier | `verifier` (was `reviewer`) | Executes tests independently, adversarial verification, `/review` static analysis, merges on pass / creates fix card on fail | Writes code |

  **⚠️ Naming:** The `reviewer` profile was renamed to `verifier` in Jul 2026 based on
  academic research (generator-verifier pattern — 6/11 surveyed papers use "verifier").
  The profile does BOTH dynamic verification (runs tests) AND static review (`/review`
  skill on diff vs contract + bead criteria). "Verifier" is broader and matches the
  academic consensus. The `/review` skill (mattpocock) is a **tool** the verifier uses,
  not a role name. See `references/loops-engineering-architecture.md` for details.
  
  **⚠️ Biggest mistake (made Jul 2026):** assigning build cards directly to `tech-lead`. Tech-lead
  wrote code using its own Hermes tools (write_file, terminal, patch) — bypassing the entire
  harness architecture. This is the **sycophancy trap** — the planner and generator are the same
  agent, so there's no independent generation. The harness (`pi`/`zz`) was NEVER invoked.
  The tests passed because GLM 5.2 is strong, but the **loops-engineering architecture was not
  tested at all** — only the kanban dispatch mechanism was.
  
  **Correct flow:** tech-lead creates card → assigned to `developer` (NOT tech-lead) → developer
  invokes harness (`pi`/`zz`) in worktree → harness writes code → developer runs gates → developer
  captures trace → verifier evaluates. The harness uses a **different model** (e.g. Gemma 4, GLM 4.5-air)
  than the governance layer (GLM 5.2) — this independence is what makes the adversarial review real.
  
  See `references/loops-engineering-architecture.md` for the full role separation model, Mermaid
  diagrams, crash recovery table, and workspace architecture.
  
  **AC checklist gate (prover-verifier pattern, designed Jul 2026):** The verifier's step 6
  independently re-verifies each bead acceptance criterion. The developer's completion report
  must include an AC-to-evidence mapping (claims); the verifier writes its own probe for each AC
  and executes independently (facts). If a developer claims "AC met" but the verifier's probe
  fails → Critical finding. This catches test-tampering — the classic generator cheat where tests
  are weakened to pass. The developer-loop skill enforces the AC mapping in every completion report.
  
  **Two-phase verification protocol (adversarial-review v4.0.0, designed Jul 2026):** Every
  verification iteration runs BOTH a delta check AND a fresh-eyes pass — preventing confirmation
  bias (backward-only verification degrades over iterations, per Huang et al.). The fresh-eyes
  subagent (`delegate_task` with deliberately restricted context) gets ONLY contract + ACs + diff,
  never prior findings. Finding routing on FAIL: fix card → developer directly (warm resume),
  NOT tech-lead — keeps the loop tight. Verifier uses `delegate_task` subagents, NOT a coding
  harness (it's judging code, not writing it). See `references/loops-engineering-architecture.md`.
  
  **Battle-tested Jul 2026 (Test 5 — single-slice loop):** the full failure-fix cycle was verified
  end-to-end with a weaker harness model (GLM 4.5-air). The harness (pi) produced code with 2
  real bugs (CLI summary counting + zero CLI tests); the developer's 35 tests passed but missed
  them; the reviewer's 43 independent probes found them. Reviewer blocked → created fix card →
  developer **warm-resumed** the pi session (`pi --session <id>`) → harness fixed all 3 bugs +
  added 5 CLI tests → re-review APPROVED. Total wall-clock: ~40 min.

  **Battle-tested Jul 2026 (Test 5R — multi-slice automation loop):** PO created PRD (15 user
  stories via `to-prd`) → beads (3 slices with dependencies via `to-issues`) → created ONE card
  per bead with ONLY bead ID + workspace path → tech-lead ran autonomously for all 3 slices.
  Slice 1: delegate_task (GLM 5.2, wrong — skill patched to prefer pi). Slice 2+3: pi harness
  (GLM 4.5-air, correct role separation). 92 tests, 8 defects found across all slices, all
  resolved. Tech-lead used git branches (feature/slice2-cli), created .venv, ran adversarial
  probes itself. `bd close` needed explicit reminder in card body (skill patched to include it).
  Total: ~44 min. See `references/battle-test-results.md` (Test 5R) for full case study.
  
  **Battle-tested Jul 2026 (Test 20 — 5-slice dependency chain, concurrent verifier race):**
  The deepest test of the self-healing system. Two verifier sessions claimed the same parent
  review simultaneously, both filed FAIL, and created duplicate fix chains — one assigned to
  verifier (role violation), one to developer (correct). The wrong-session verifier blocked
  itself ("I constitutionally cannot write code"). The board scanner detected the deadlock
  and escalated to tech-lead. Tech-lead posted an authoritative override comment identifying
  the canonical chain, archived the dead chain, and the correct iteration-3 review proceeded
  to PASS. **Key lesson**: the system self-heals even when agents make mistakes (concurrent
  sessions, role violations, misleading comments). The resolution pattern is: verifier
  self-blocks on role violation → scanner escalates → tech-lead arbitrates → dead chain
  archived → canonical chain proceeds. See `references/enterprise-test-results.md` § Test 20.
  
  **Key verified `pi` invocation** (the `developer-loop` skill has WRONG flags):
  ```bash
  # Cold start
  timeout 900 pi --provider zai --model glm-4.5-air -p "Read PRD.md..." \
    --tools read,write,edit,bash,grep,find,ls --mode json
  # Warm resume (harness keeps prior memory)
  timeout 900 pi --provider zai --model glm-4.5-air --session <session_id> \
    -p "Read FIXES.md. Apply all findings..." --mode json
  ```
  `--auto-test` and `--max-turns` DO NOT EXIST in pi — only Claude Code has `--max-turns`.
  For pi, the wall-clock `timeout` wrapper IS the only cap.

- **Dynamic decomposition (orchestrator → children):** one agent receives a task too large for
  one pass, creates child tasks via `kanban_create` (all assigned to the same or appropriate
  specialist profiles), blocks itself with `kanban_block(reason="delegated: waiting for N child
  modules")`, and completes only after all children finish and integration is verified.
  **Battle-tested Jul 2026:** an ETL pipeline with 3 modules was decomposed this way — tech-lead
  created 3 child tasks dynamically, dispatcher serialized them (max_in_progress=1), all 137/137
  tests passed, integration built on re-dispatch. See `references/dev-workflow-test.md` and
  `references/battle-test-suite-2026-07-04.md` for timings and the full case study.
  
  ⚠️ **Deadlock trap:** if children set `parents=[orchestrator-id]`, they cannot promote to `ready`
  until orchestrator is `done`, but orchestrator blocks until children complete. 
  **Solution (PROVEN Jul 2026):** Use the `kanban_delegate` plugin tool (formerly `delegate_and_wait`,
  renamed because the old name was too unclear — tech-lead skipped it and polled manually). The tool
  bundles card creation + link + block into one atomic call. Children get no parent link (`parents=[]`).
  Orchestrator links ITSELF as CHILD of each verifier: `kanban_link(parent=verifier_id, child=orchestrator_id)`,
  then blocks with `kind=dependency` (routes to `todo`, NOT `blocked`). Kanban's built-in `recompute_ready`
  auto-promotes the orchestrator when ALL verifier parents reach `done`. No cron, no scanner.
  For multiple parallel chains: pass N contracts to `kanban_delegate` in one call.
  **PROVEN:** 3 parallel dev→verifier chains, tech-lead stayed in `todo` for 14min until all 3
  verifiers completed, then auto-promoted and completed. Zero manual intervention.
  
  ⚠️ **Kanban ownership enforcement (LIVE-TESTED Jul 2026):** the tool API (`kanban_unblock`,
  `kanban_complete`, `kanban_block`) enforces worker ownership via `_enforce_worker_task_ownership`
  in `tools/kanban_tools.py:135`. A dispatched worker (with `HERMES_KANBAN_TASK` set) CANNOT
  mutate foreign task IDs — the tool returns an error. BUT the CLI (`hermes kanban unblock`)
  has NO ownership check — it bypasses the tool API entirely. This means:
  - **Agents** (using tool API): can only mutate their OWN task. Cannot unblock/comment on
    foreign tasks (except `kanban_comment` which is explicitly allowed).
  - **Cron scripts** (using CLI subprocess): can mutate ANY task.
  - **The board scanner** (zero-token cron using CLI): is the "unblock bridge" — it unblocks
    tasks after an escalation agent resolves them, because the agent itself cannot.
  When designing escalation or handoff flows, remember: the agent comments the resolution,
  completes its own escalation card, and the scanner (CLI) unblocks the original task.
  
  ⚠️ **Multi-phase workspace continuity:** `scratch` workspaces (the default) are cleaned up on
  completion/archive. For multi-phase builds where Phase 2 needs Phase 1's files, use
  `workspace_kind="dir"` pointing to a stable project directory so files persist across phases.
  **Battle-tested Jul 2026:** without this fix, Phase 2 found an empty workspace and
  rebuilt Phase 1's files from the spec — resilient but wasteful (~2 min extra, spec-drift risk).
  See `references/battle-test-suite-2026-07-04.md` (Test 3) for timings.

## 5. Stay in the loop without hovering
After delegating: keep working. Check back via the task's comments/events (`kanban show`,
`tail`, `runs`), not by re-doing the work. If an assignee **blocks** (`needs_input`/`dependency`),
that's the signal to step in — answer the question or resolve the parent, then unblock.

### 5a. How to watch a task (and give feedback on the work)
You get the full execution trace — every tool call, terminal command, file diff, and the
agent's reasoning between steps. Use it to inspect quality and coach:
- **`hermes kanban log <task_id>`** — the primary tool. Full timestamped log of every action
  the worker took: file writes (with diffs), terminal commands (with output + exit codes),
  patches, reads, skill loads, and the agent's own narration. Add `--tail N` for the last N
  bytes. This is how you see *how* the agent worked, not just what it produced.
- **`hermes kanban tail <task_id>`** — live-follow a running task (polls every 0.5s). Use while
  a task is in `running` state to watch progress in real time.
- **`hermes kanban show <task_id>`** — task body + comments + event timeline + run metadata.
  The comments section is where workers post their completion handoff (findings, decisions, file list).
- **`hermes kanban runs <task_id> --json`** — structured run metadata: start/end timestamps,
  outcome, and the worker's self-reported `metadata` dict (test counts, verdicts, changed files).
- **`hermes kanban watch`** — board-wide real-time event stream (claims, heartbeats, completions).
  Good for monitoring multiple tasks at once.
- **Giving feedback:** post a `kanban_comment` on the task — workers and operators both read the
  comment thread. For corrections that should outlive the task, update the governing skill (this one).

## 6. Block honestly yourself
  
When *you* can't proceed, block with the truthful kind instead of looping or guessing:
`needs_input` (a human must decide/provide something), `dependency` (waiting on a parent task),
`capability` (no agent can currently do this). A clear block moves the whole board forward; a
spinning agent stalls it.

## 6a. PO role boundaries — do NOT become the planner

**⚠️ Biggest correction (Jul 2026):** the PO's job in the dev workflow is to **delegate and
observe**, not to plan the technical implementation. Violating these boundaries invalidates
the test — the PO did the planner's job and tech-lead just copied the contract.

**PO owns WHAT** (product decisions):
- Grill the user (`grilling`) → write PRD (`to-prd`) → decompose into slices (`to-issues`)
- Create beads + dependencies (masterplan) → prioritize which bead is next
- Create ONE kanban card for tech-lead with just the bead content
- Observe via kanban logs, take notes, steer only on fatal breakage

**PO does NOT do:**
- ❌ Write contracts/specs in task bodies (that's tech-lead's job after receiving the bead)
- ❌ Give tech-lead step-by-step plans or explicit guidance
- ❌ Manually unblock tasks (the reviewer creates fix cards itself)
- ❌ Interfere with the loop unless something is fatally broken

**Communication between profiles** has no direct messaging channel. Use: kanban card body
(handoff), kanban comments (async discussion), beads issues (masterplan), files on disk
(PRD.md, contract.md), and `bd memory` (priority context that persists across sessions).

See `references/po-role-boundaries.md` for the full beads-as-masterplan architecture,
the automation loop design, and the FAANG WHAT/HOW split.

### 6a. Block→unblock→resume pattern (battle-tested Jul 2026)
When a task encounters a genuine decision it should not make itself:

```
# Worker: post analysis, then block
kanban_comment(body="Evaluated options A vs B vs C. A is the natural fit but [tradeoff]. Which do you prefer?")
kanban_block(reason="need-decision: <specific question>", kind="needs_input")

# Operator: read the analysis, answer, unblock
kanban_comment(task_id="...", body="Use A. [reason]")
kanban_unblock(task_id="...")
```

On re-dispatch, the agent gets the full comment thread and **remembers the decision** — no need to re-ask.

**Battle-tested (kv_store.py, 61 tests):** the agent evaluated JSON vs INI vs TOML vs YAML under a "stdlib-only"
constraint, correctly noted TOML has read-only stdlib support (no write capability), YAML needs `pyyaml`,
and INI can't handle nested JSON-serializable values. It recommended JSON and blocked — the operator
confirmed, the agent resumed with the decision intact, and proceeded to build with atomic writes, reentrant
locking, and 61 passing tests. See `references/battle-test-suite-2026-07-04.md` (Test 4).

### 6b. Workflow battle-testing methodology
When you need to verify the kanban dev workflow is enterprise-ready, use a progressive
battle-test approach rather than a single pass. The goal is to push each mechanism to its
failure boundary and observe the result, not just confirm the happy path.

**Test plan design (6 essential test types):**

| # | Test | What it exercises | How to trigger |
|---|------|-------------------|----------------|
| 1 | Closing loop | Spec→build→review→(reject?)→fix→re-review | Provide a strict spec with subtle requirements the builder may miss. If GLM 5.2 passes on first try (common — its code quality is high), note it as a positive finding. |
| 2 | Emerging task | Dynamic mid-run task generation via `kanban_create` | Give an orchestrator a decomposable task with instructions to create child tasks. Include the deadlock warning (see §4). |
| 3 | Deep chain | Multi-phase sequential build with cross-phase workspace continuity | Create Phase 1 → complete → create Phase 2 → complete → create Phase 3. Use `dir` workspace for all phases to avoid cleanup. |
| 4 | The Block | Error recovery via `kanban_block` → unblock → resume | Give a task with an intentionally omitted design decision. Instruct the agent to block rather than guess. |
| 5 | Crash recovery | Auto-reclaim when a worker process dies mid-run | Create a task, wait for it to start executing, then `kill -9 <pid>`. Observe: dispatcher auto-reclaims within 1-3 min. New agent verifies prior work independently. Use `hermes kanban reclaim <task_id>` to force immediate reclaim instead of waiting. |
| 6 | Automation loop | Cron-driven `bd ready` → PO creates card → tech-lead executes → bead closed | Set up a beads project with dependencies. Create a cron job that checks `bd ready` and creates kanban cards. Watch for: duplicate card race condition (use `--idempotency-key` to prevent), cron repeat exhaustion (use `repeat: forever` for production). |

**Progressive testing rules (user's preference, embedded Jul 2026):**
- **If test passes:** note the result with all metrics (timeline, tests, findings), then continue to the next test. A pass is not the end.
- **If test fails:** note the failure with severity (FATAL / MAJOR / MINOR / NIT), analysis, and continue to the next test. Document what failed and how.
- **FATAL failures only:** stop immediately and report. Fatal = dispatcher not working, task stuck forever with no heartbeat, agent crashes without recovery, data corruption.
- **Log everything:** per-test tracking with start/end timestamps, task IDs, timeline, pass/fail status, detailed findings with severity, and log excerpts. Test plan (`TEST-PLAN.md`) and results (`RESULTS.md`) live in a dedicated directory.

**How to observe and give feedback:**
- `hermes kanban log <task_id>` — every tool call, terminal command, file diff, reasoning step
- `hermes kanban runs <task_id> --json` — structured duration + test count + verdict metadata
- `hermes kanban show <task_id>` — comments + events + handoff context
- Workers who post comments with findings make analysis easier. The verifier's `adversarial-review` skill produces the richest handoffs (independent verification scripts, severity-graded findings).

See `references/battle-test-suite-2026-07-04.md` for a complete executed example (4 tests, 13 tasks, ~500 tests, zero fatal failures).

## Anti-patterns
- Assigning by name out of habit instead of by the description that fits the work.
- A task with no acceptance criteria ("look into X") — the assignee can't know when it's done.
- Delegating a tightly-coupled sliver you're mid-way through — the hand-off costs more than the work.
- Fan-out with overlapping slices — workers duplicate effort and collide.
- Fire-and-forget: delegating, then never reading the result or unblocking the assignee.
- **Creating tasks before verifying assignees can receive them** — a profile with no gateway
  service or disabled tools will stall silently. Always run the §2a pre-flight first.
- **No sandboxing between profiles** — all profiles run as the same OS user with no filesystem
  isolation. A bug in generated code, or a misconfigured verifier, can write/delete files outside
  the workspace. For enterprise use, wrap pi/zz in firejail/bubblewrap or use container-per-task.
  This is an infrastructure gap (Jul 2026), not a workflow design issue.
- **429 rate limits cause premature reclaim** — Z.AI frequently returns HTTP 429 under concurrent
  load. The default 3 retries (~17s) is too few — the task crashes and auto-reclaims, wasting
  2-3 min per cycle. Increase `agent.api_max_retries` to 10 and set `rate_limit_delay: 60` on
  the zai provider for ~10 min of in-session resilience before reclaim.
- **Concurrent verifier sessions race on the same parent** — if two verifier sessions claim the
  same parent review task (dispatcher race), both will file FAIL verdicts and create duplicate
  fix chains. One may assign the fix card to the wrong profile (verifier instead of developer).
  The system self-heals (verifier self-blocks on role violation, scanner escalates, tech-lead
  arbitrates), but it wastes dispatch cycles. Future fix: merge-slot-style lock on FAIL verdict
  filing. See `references/enterprise-test-results.md` § Test 20.
