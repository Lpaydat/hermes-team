---
name: agent-harness-integration
description: "Integrate multiple agent runtimes (pi, Hermes, generic process, HTTP) into a dispatch daemon via a trait-based harness abstraction. Covers the harness interface, heartbeat/liveness model (from Paperclip), daemon dispatch pattern, parallel-system framing (not replacement), and spec-writing pitfalls for extraction projects. Load when designing agent dispatch, building harness adapters, reasoning about how the daemon talks to agent runtimes, or writing specs for platform extraction projects."
version: 1.0.0
metadata:
  hermes:
    tags: [architecture, harness, dispatch, hermes, ngin, migration]
    category: software-development
---

# Agent Harness Integration — pluggable agent runtimes

The dispatch daemon (ngin) must talk to multiple agent runtimes without being
coupled to any one. Today it spawns pi's `subagent-runner`. Tomorrow it dispatches
to Hermes profiles. Later it talks to a custom Rust agent runtime. The harness
abstraction makes this possible without daemon core changes.

## The harness trait

```rust
trait AgentHarness {
    fn spawn(&self, run: &Run, config: &HarnessConfig) -> Result<Pid>;
    fn check_alive(&self, pid: Pid) -> bool;
    fn heartbeat(&self, run_id: &str) -> Result<()>;
    fn get_result(&self, run_id: &str) -> Result<RunResult>;
    fn prepare_workspace(&self, run: &Run, mode: WorkspaceMode) -> Result<PathBuf>;
    fn cleanup_workspace(&self, run: &Run) -> Result<()>;
}
```

Implementations:
- **PiHarness** — current subagent-runner (node_modules/.bin/)
- **HermesLocalHarness** — `hermes -p <profile>` CLI process
- **HermesGatewayHarness** — HTTP to Hermes API server (apiBaseUrl)
- **ProcessHarness** — generic process spawn
- **HttpHarness** — generic HTTP endpoint

Harness selection: per-agent via `agents.json` or flow metadata. Each agent entry
specifies `harness: "hermes_local"` (or omit for default pi).

## Paperclip's adapter model (reference architecture)

Paperclip solves this with 14 built-in adapter types:

```
acpx_local, claude_local, codex_local, cursor, cursor_cloud,
gemini_local, grok_local, hermes_gateway, hermes_local,
openclaw_gateway, opencode_local, pi_local, process, http
```

Each adapter has:
- `adapterType` — string slug
- `adapterConfig` — adapter-specific settings (e.g. `apiBaseUrl` for hermes_gateway)
- `agentDefaultsPayload` — secrets/env/config passed to the agent

Two Hermes modes:
- `hermes_local` — Paperclip spawns `hermes` CLI on same host
- `hermes_gateway` — Paperclip calls an already-running Hermes API server

Paperclip source: https://github.com/paperclipai/paperclip

## Heartbeat and liveness (beyond TTL)

Paperclip's heartbeat is NOT "agent pings to say I'm alive." It classifies agent
productivity from output:

- `runnable` — agent made real progress (comments, files, tests)
- `plan_only` — agent only talked about what it would do
- `blocked_external` — agent is stuck (waiting on credentials/access)
- `manager_review` — agent needs human approval
- `unknown` — can't classify

For ngin, start with TTL-based heartbeat (agent extends lease). Add liveness
classification later. The concept: a RUN has a liveness STATE, not just a
lease timer.

### Hermes's actual heartbeat implementation — and its critical gap

Reverse-engineered from a real stuck-worker incident (2026-08-09): a verifier
agent ran for 47 minutes with a dead heartbeat but was never auto-reclaimed
because its PID was alive. Full details in
[`references/hermes-heartbeat-internals.md`](references/hermes-heartbeat-internals.md).

**Key findings that should inform any harness heartbeat design:**

- **No background heartbeat thread.** Hermes heartbeats are activity-bridged via
  `_touch_activity()` — called from the event loop at API call boundaries and
  inside `_wait_for_process` poll loops. If the event loop is blocked inside a
  tool call that never returns, heartbeats stop completely. A background thread
  decouples liveness from activity and is strictly more robust.

- **PID-alive extends the claim indefinitely (up to 1 hour).** The dispatcher's
  `release_stale_claims()` extends a claim by +15 min if the worker PID is alive
  and the heartbeat is < 1h stale. A stuck-but-alive process holds its claim for
  up to 60 minutes before the heartbeat-stale backstop triggers.

- **Activity callback is thread-local** (`base.py:46`). If a tool executes on a
  thread where the callback wasn't set, `touch_activity_if_due()` is a silent
  no-op — heartbeats stop even though the poll loop is running.

- **Terminal timeout (600s) was not enforced.** A trivial git command held the
  worker for 47 minutes — the `_wait_for_process` deadline check was somehow
  bypassed, suggesting the poll loop never started or the subprocess handle was
  corrupted.

## Hermes dispatch model — the CORRECT version

**Corrected from a session error.** The PO incorrectly stated "each gateway
polls for its own cards." The user caught this. The actual model:

### Singleton-lock dispatcher

There is ONE dispatcher across ALL profiles — not one per gateway.

```
gateway A starts → acquires kanban/.dispatcher.lock → OWNS dispatch
gateway B starts → lock CONTENDED → skips dispatching entirely
```

The dispatcher runs `dispatch_once()` every `dispatch_interval_seconds`:

1. Reap zombie children
2. Release stale claims (TTL, heartbeat, PID)
3. Detect crashed workers
4. Enforce max runtime
5. Promote todo→ready (dependency resolution)
6. Find ALL ready tasks across the ENTIRE board
7. Atomically claim each ready task
8. Call spawn_fn → `hermes -p <assignee>`
9. Record worker PID

Individual profile gateways do NOT dispatch. They serve as messaging interfaces
and process runners when spawned.

Source: `kanban_watchers.py:953` (`_kanban_dispatcher_watcher`),
`kanban_db.py:8204` (`dispatch_once`).

### Why this matters for ngin

ngin daemon IS a dispatcher. Its claim→spawn→track→reap loop provides the same
dispatch semantics as Hermes's embedded singleton-lock dispatcher, but reads
beads (`bd ready`) instead of kanban.db. Both systems can run in parallel —
ngin with beads, Hermes with kanban. ngin does NOT modify or replace Hermes.

## What ngin needs to add (5 items)

1. **Harness trait** — swap spawn target from pi to Hermes (or any runtime)
2. **Heartbeat** — workers extend their lease on long tasks
3. **Max runtime enforcement** — Phase 2 extended: check started_at + max_runtime
4. **Per-profile concurrency** — group running count by assignee/role
5. **Workspace management** — configurable Scratch/Worktree/Dir modes per-agent

These are modifications to existing proven Rust code, not new subsystems.

**Important sequencing note (verified 2026-08-05):** The harness trait (item 1)
is NOT a hard dependency for graph walk or workflow engine work. The existing
`ProcessSpawner` + `RunnerEnv` traits in `spawn.rs` already provide the
abstraction graph walk dispatches through. Graph walk (plan unit 2.2) can be
built and tested against `ProcessSpawner` today. Harness unification is a
mechanical refactor that lands with workspace + worker-config (0.4+0.5), not a
prerequisite that blocks the engine. See
[`references/ngin-build-plan-dependency-analysis.md`](references/ngin-build-plan-dependency-analysis.md)
for the full dependency verification.

## Hard Rule: daemon spawns, agents NEVER poll

**The daemon owns dispatch.** It claims an issue, spawns the agent process, and
hands it the task ID via env var (`BD_ISSUE_ID`). The agent reads the task,
does the work, writes results back.

This rule exists because the PO proposed "agents poll bd ready for work"
THREE separate times during the design session — once as "decoupled via beads",
once as "harness translates kanban→beads", and once as "gateway polls beads".
Each time the user caught it. The polling model reverses the dispatch
relationship and breaks the daemon's ownership of concurrency, claim lifecycle,
and workflow node activation. It is WRONG. ADR-0002 at
`~/workspace/ngin/docs/adr/0002-daemon-spawns-agents-never-poll.md` is the
enforcement document. Any proposal where agents discover or poll for work
is rejected on sight.

## Parallel system, not replacement

ngin is a standalone platform that extracts dispatch + workflow capabilities
into a harness-agnostic system. It does NOT replace, modify, or obsolete any
existing system. Both ngin and the source system can coexist indefinitely.

The user's framing: "if current one is facebook, we're building twitter." You
don't delete facebook while building twitter. The new system stands on its own.

Integration with existing agent runtimes happens through NEW plugins, skills,
API endpoints, or CLI tools — NEVER by modifying existing code. The user
corrected this explicitly: "how can you ask user to change their hermes
setting to use tool? we can create plugin, skill, api, command line. many
solution other than messing with what is working."

## Beads plugin pattern (additive integration)

For agent runtimes that need bd_* tools, create a NEW plugin that registers
`bd_*` tools (bd_show, bd_complete, bd_comment, bd_block, bd_heartbeat,
bd_create) — mirroring existing tool patterns 1:1. The daemon spawns the agent
with `BD_ISSUE_ID` env var. The agent calls `bd_show($BD_ISSUE_ID)` to read
its task. Same dispatch pattern, swapped backend.

Do NOT modify existing agent runtime code, SOUL.md, or skills. Do NOT create
a translation layer. One task tracker, one path.

## The daemon↔worker flow execution boundary

The daemon and worker split flow execution across a hard boundary. The daemon is
a **dumb pipe**: it reads the flow JSON, treats `steps` as opaque `Vec<Value>`
JSON (never inspecting contents), serializes a `SubagentRunConfig` to a temp
file, and spawns `subagent-runner`. All step semantics — sequential iteration,
`{previous}` threading, match/when/loop/subflow control flow, parallel groups,
checkpointing, tree visualization — live in the **worker** (TypeScript
`executeFlow()`, ~700 lines of control-flow logic).

This matters for any steps[]→graph migration. The daemon's `FlowConfig.steps`
is already a format-agnostic blob. However, the architectural decision
(ADR-0004) is that the daemon OWNS the graph walk — it parses graph JSON,
evaluates node activation, dispatches ready nodes, and handles back-edge loops.
The worker's step sequencing becomes dead code. The daemon reuses its existing
claim→spawn→reap lifecycle for each node's execution. The worker becomes a
simple task executor — it receives one task per dispatch and never sequences
nodes.

**Full data contract, dual checkpoint model, step failure behavior, and migration analysis**: [`references/ngin-flow-execution-architecture.md`](references/ngin-flow-execution-architecture.md)

**Build plan dependency analysis (2026-08-05)**: [`references/ngin-build-plan-dependency-analysis.md`](references/ngin-build-plan-dependency-analysis.md) — verified the 21-unit IMPLEMENTATION-PLAN against actual source code. Key findings: harness trait is NOT a hard dependency for graph walk (graph walk uses existing `ProcessSpawner`, not the unbuilt `AgentHarness`); triggers (2.5) have a hidden dependency on the graph parser (1.1) the plan misses; critical path is the 6-unit engine spine 1.1→1.2→2.1→2.2→2.3→2.4. Read when sequencing ngin dev tickets or deciding parallelism.

## Pitfalls

- **NEVER propose that agents poll for work.** This was caught three times.
  The daemon spawns, the agent receives. This is non-negotiable. If you find
  yourself writing "the agent watches beads" or "the gateway polls bd ready",
  STOP — you are designing the wrong system.
- **Don't modify existing agent runtime code to teach it about beads.** Don't rewrite
  SOUL.md, don't modify the kanban tool, don't change profile configs. Create
  a NEW plugin (registers bd_* tools) and optionally a NEW skill (teaches the
  agent the bd workflow). Additive only — never modify what works.
- **Don't create a translation/bridge layer.** The "harness translates
  kanban→beads" proposal was rejected. It adds a second system that must be
  maintained. The agent talks to beads directly via the plugin tools. One
  task tracker, one path.
- **Don't frame the new system as a replacement.** ngin is a parallel system.
  The source system (Hermes, pi, whatever) continues working unchanged. The
  user corrected this: "what we are going to build is not touch the current
  workflow and kanban system at all. if current one is facebook, we're
  building twitter."
- **Read subagent output before restating system behavior.** During the grill
  session, subagents documented that Hermes uses a singleton-lock dispatcher
  (one gateway owns a file lock). Despite having this output, the PO proposed
  a question based on "each gateway polls for its own cards" — completely
  wrong. The user caught it: "I can't believe you still lied to me even after
  having subagents doing deep research." When subagents have already researched
  the system, READ their output. When no research exists, READ THE CODE. Never
  state system behavior from memory or assumption.
- **Don't propose the same wrong pattern in different forms.** After being
  corrected on "agents poll beads," the PO re-proposed "harness translates
  kanban→beads" then "gateway polls bd ready" — same polling pattern in three
  different wrappers. When corrected, internalize the correction and design
  from the corrected understanding.
- **Verify system behavior before asserting it.** The PO incorrectly stated
  "each gateway polls for its own cards" — stated as fact without reading
  code. The user caught it: "I can't believe you still lied to me even after
  having subagents doing deep research." If subagents already documented the
  correct behavior, READ their output. Do not restate from memory or assumption.
- **Don't assume per-profile polling.** The Hermes dispatch model is
  singleton-lock, not per-gateway. One gateway owns the dispatcher lock and
  dispatches ALL profiles. ngin replaces that one dispatcher.
- **Paperclip's adapter system is TypeScript/npm-based.** Don't copy the
  package-manager approach. The Rust trait is the right abstraction for a
  compiled daemon.
- **Heartbeat is more than a ping.** Paperclip classifies agent productivity
  from output text. Start simple (TTL extension) but design for liveness
  classification from the beginning.
- **Hermes's activity-bridged heartbeat fails when a tool call blocks the
  event loop.** Verified in incident 2026-08-09: a verifier stuck inside a
  terminal tool call sent no heartbeats for 47 minutes because there's no
  background thread — `_touch_activity()` only fires at event-loop boundaries.
  PID-alive claim extensions stretched the TTL to match the 1-hour stale
  threshold. Any harness heartbeat must be background-threaded, independent
  of the worker's event loop. See
  [`references/hermes-heartbeat-internals.md`](references/hermes-heartbeat-internals.md).
- **Spec-writing: frame as extraction, not replacement.** When writing the spec
  for a harness-agnostic platform, every layer "provides the same capability as"
  the source system — NOT "replaces" it. The user caught replacement framing 4
  times in one spec review: (1) "replaces kanban" in the Solution section,
  (2) "migration/cutover tooling" in Out of Scope, (3) coupling to Hermes as
  the only harness, (4) backward compat with legacy formats. The fix each time:
  rewrite as "provides the X layer (same role as Y)" and remove all migration,
  cutover, backward compat, and legacy references. The system is built complete
  from the first build.
- **Spec-writing: remove ALL backward compat and migration language.** The user's
  hard line: "we don't need any backward compatibility, we don't need migration
  code. this should be complete from the first build." This means: no "existing
  tables (keep)", no "already exists in bd.rs", no "port from Hermes", no
  "migration path" in analysis doc references, no "users start fresh", no
  "cutover" anywhere. The spec describes a complete system — not a delta from
  an existing one. When referencing research docs that have "migration" in
  their filename, describe what they contain (e.g. "feature gap analysis")
  rather than using the migration-flavored filename description.
- **Design drift: the wrong pattern keeps resurfacing in new wrappers.** When
  designing a parallel system, the source system's architecture bleeds into
  your thinking. "Agents poll bd ready" was proposed three times: as "decoupled
  via beads", as "harness translates kanban→beads", and as "gateway polls
  beads." Each was the same wrong pattern in different clothing. The fix is not
  just "don't propose polling" — it's to actively check every new proposal
  against the hard rules (ADR-0002: daemon spawns, agents receive) before
  presenting it. When you catch yourself designing how the agent DISCOVERS work,
  stop — the agent never discovers work. The daemon hands it work.
- **PO decomposes specs into tickets.** The PO owns decomposition via
  to-tickets. The PO reads the spec, creates `[ticket-]`-prefixed ticket cards
  assigned to tech-lead. Each ticket triggers tech-lead-execute's
  plan→verify→fix→close pipeline independently (via `title_prefix_any` trigger
  matching `[spec]` and `[ticket-]`). When the PO assigned a raw spec directly
  to tech-lead, the user caught it: "why you delegate spec to tech-lead
  instead of PO to make it create tickets?" The PO's job is decomposition —
  then tickets go to tech-lead for the workflow pipeline.
- **Kanban card bodies should be minimal — stop overcomplicating.** When
  creating ticket cards, include only the spec path, ADR paths, and context
  docs — NOT elaborate guidance or implementation hints. The user corrected
  this: "just create kanban card with the spec and docs and assign to PO.
  just this. no more, no less than this. stop overcomplicated things already."
  Tech-lead reads the spec and writes its own contract.
- **Dependency links require kanban_link tool — NOT raw SQL inserts.**
  Inserting into `task_links` via `conn.execute("INSERT INTO task_links ...")`
  bypasses `recompute_ready()` in kanban_db.py (line 4135). The dispatcher's
  `dispatch_once` finds all `ready` cards and claims them — it does NOT check
  task_links for unfinished parents. Without recompute_ready, children with
  unfinished parents stay `ready` and the dispatcher claims them immediately.
  ALL dependency edges are silently ignored. This was discovered when 21 ngin
  tickets with 20 dependency edges ALL went to `running` simultaneously.
  Fix: use the `kanban_link` tool API (which calls recompute_ready), or call
  `recompute_ready(conn)` manually after any raw SQL insert.
- **Spec/ADR validation + repo management for large-worktree repos**: [`references/ngin-spec-validation-and-repo-management.md`](references/ngin-spec-validation-and-repo-management.md) — (1) verified result: ngin spec + 8 ADRs remain valid against the evolved Hermes engine (Hermes-side changes are impl details, not design-affecting). (2) Backup pattern for repos with multi-GB worktrees (git branch/tag, not cp -r) and worktree safety check before deletion. Read when re-validating the ngin spec or managing the ngin repo's large worktree set.

- **Board cleanup requires cleaning BOTH databases.** When killing a workflow
  run, you must clean both `kanban/boards/<board>/kanban.db` (archive cards)
  AND `kanban/workflow-state.db` (delete instances, trigger_keys,
  trigger_watermark). Archiving cards alone leaves stale trigger state —
  the engine re-fires on old triggers or dedup-blocks new ones. Kill worker
  processes too: `pkill -f "hermes.*<board>"`.
- **Ticket review: run subagents to validate before publishing.** When the PO
  drafted 16 tickets, 3 subagents found 5 real issues (missing blocking edge,
  2 oversized tickets, 2 missing tickets, 7 orphaned stories). The review
  caught blocking edge bugs, sizing problems, and hidden dependencies before
  any work was dispatched. Always validate a ticket breakdown against the spec
  and ADRs before publishing.
- **Gateway config is read once at startup — restart after changes.** The
  `max_in_progress_per_profile` and `max_in_progress` settings in
  `profiles/<name>/config.yaml` are loaded when the gateway process starts. If
  you change the config while the gateway is already running, it will NOT
  enforce the new limits until restarted. This caused 7 tickets to spawn
  simultaneously when the limit was 3 — the gateway had been running for 10
  hours before the config was added. Always `systemctl --user restart
  hermes-gateway-<profile>` after setting concurrency limits, and BEFORE
  creating cards that depend on the cap.
- **NEVER bypass kanban tools with raw SQL — now enforced by sqlite3 guard.**
  The agent repeatedly took shortcuts by writing directly to kanban.db and
  workflow-state.db via Python `sqlite3.connect()` instead of using the
  kanban_* tools. EVERY shortcut broke something: dependency gating failed
  (raw `INSERT INTO task_links` skips `recompute_ready`), stale workflow
  instances persisted, orphan cards accumulated across boards. The user had
  to build a two-layer sqlite3 guard (CLI wrapper at `/usr/bin/sqlite3` +
  Python `sitecustomize.py`) to block direct writes to `*kanban*.db` and
  `*workflow-state.db`. If you hit the guard, use the kanban tool — do NOT
  try to work around it. The guard blocks INSERT/UPDATE/DELETE/DROP/ALTER/
  CREATE/REPLACE. Reads (SELECT, PRAGMA) pass through.
- **Always check before answering — never answer from memory.** The user
  asked "is this scope creep?" about 4 tickets. The PO answered immediately
  from memory: "yes, scope creep." Then the user asked "did you check?"
  Answer: NO. All 4 were in the approved spec. The user's words: "why not
  check it now instead of keep lied and apologize?" The pattern the user
  hates: answer fast from memory → get caught → apologize → repeat. The
  apology is worthless — it's the same shortcut as the raw SQL. Rule:
  when asked a factual question about the spec, the code, or the state of
  the board, READ THE SOURCE before opening your mouth. Use `read_file`,
  `search_files`, or `kanban_list` — not your memory.
- **The workflow pipeline has a specific card-routing order — follow it.**
  The Hermes dev pipeline is: `[spec] card assigned to product-owner → PO
  decomposes via to-tickets → creates ticket cards → dev-dispatch routes
  → tech-lead-execute per ticket → qa-gate`. The PO tried to skip this by
  assigning the raw spec directly to tech-lead. That bypasses decomposition
  entirely. The user caught it: "why you delegate spec to tech-lead instead
  of PO?" Then the PO tried to create cards assigned to product-owner but
  the tech-lead-execute template fires on `[spec]` prefix + tech-lead
  assignee — so the routing chain broke. Always: PO decomposes FIRST, then
  tech-lead executes each ticket.
- **Atomic card creation with parents=[] prevents the dispatcher race.**
  When creating cards with dependencies, use `kanban_create` with
  `parents=[...]` — the card AND its parent edges are set in one call, and
  the child starts as `todo` (blocked). NEVER create cards first and link
  later: the window between creation and linking lets the dispatcher claim
  children before the parent gate exists. This caused all 21 tickets to go
  to `running` simultaneously because `task_links` were inserted after the
  cards were already `ready`.
- **Scope discipline: don't invent features. But don't cut approved spec
  features either.** Every ticket must map to an approved spec story. When
  the user asks "is this scope creep?", CHECK THE SPEC BEFORE ANSWERING.
  The PO was asked about scope creep, answered from memory that Mermaid,
  subworkflow, foreach, and observability were scope creep — then verified
  and found ALL of them were explicitly in the approved spec (stories 27,
  28, 14, 15, 39, 36). The user caught the lie: "you only agree with me
  without checking or you really check them already?" Answer: did NOT
  check. Rule: if a feature is in the approved spec, it is NOT scope creep.
  Period. Do not override the user's spec decisions.
- **Check if a repo is archived before writing ADRs about it.** When writing
  ADR-0006 ("work in ngin repo"), the PO didn't check if the repo was actually
  active. The tech-lead agent found `SUPERSEDED.md` stating the repo was archived
  read-only per tau ADR-0029, with code moved to `~/workspace/personal/pir/`.
  The tech-lead correctly blocked with `needs_input`. Always check for
  `SUPERSEDED.md`, `ARCHIVED.md`, or README archival notices before committing
  to a repo in an ADR. If the user says "un-archive it", remove the
  `SUPERSEDED.md`, commit, and push — then unblock the card.

## References

- **Paperclip adapter types**: `server/src/adapters/builtin-adapter-types.ts`
- **Paperclip heartbeat service**: `server/src/services/heartbeat.ts`
- **Paperclip liveness classification**: `server/src/services/run-liveness.ts`
- **Paperclip hermes_gateway doc**: `server/src/adapters/hermes-gateway-doc.ts`
- **Hermes dispatch_once**: `hermes_cli/kanban_db.py:8204`
- **Hermes singleton-lock watcher**: `gateway/kanban_watchers.py:953`
- **ngin daemon spawn.rs**: `~/workspace/ngin/daemon/src/spawn.rs`
- **ngin daemon state_machine.rs**: `~/workspace/ngin/daemon/src/state_machine.rs`
- **Full gap analysis**: `~/workspace/ngin-vs-hermes-gap-analysis.md`
- **Paperclip dispatch research**: [`references/paperclip-dispatch-research.md`](references/paperclip-dispatch-research.md) — condensed research from reading the Paperclip codebase: 14 adapter types, heartbeat/liveness model, regex classifiers, runtime config, watchdog system. Read when designing heartbeat, liveness classification, or adapter selection.
- **Kanban board operations**: [`references/kanban-board-operations.md`](references/kanban-board-operations.md) — correct patterns for atomic card creation with dependencies, board cleanup, sqlite3 guard interaction, dispatcher board scanning, and the workflow pipeline card-routing order. Read when creating ticket cards, cleaning up failed runs, or debugging dispatch issues.
- **Hermes heartbeat internals**: [`references/hermes-heartbeat-internals.md`](references/hermes-heartbeat-internals.md) — reverse-engineered heartbeat/claim/reclaim internals from `kanban_db.py`, `run_agent.py`, `kanban_tools.py`, and `environments/base.py`. Documents: no background thread (activity-bridged only), thread-local callback gap, PID-alive extension loop, 1-hour stale threshold, and the terminal-timeout enforcement failure. Includes a step-by-step investigation recipe for stuck workers (board DB event timeline → session DB last messages → agent.log freeze point). Read when debugging stuck/dispatcher-stale workers or designing heartbeat for any harness.
