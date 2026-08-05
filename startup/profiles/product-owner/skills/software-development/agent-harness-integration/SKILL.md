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
is already a format-agnostic blob; the migration question is really "who owns
step sequencing?" Keeping graph parsing in the worker (graph config passed
through as opaque JSON) is low-risk. Moving graph traversal into the daemon
(per-node process spawning) is high-risk — it forces the daemon to reimplement
the worker's entire control-flow engine.

**Full data contract, dual checkpoint model, step failure behavior, and migration analysis**: [`references/ngin-flow-execution-architecture.md`](references/ngin-flow-execution-architecture.md)

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
- **Spec-writing: frame as extraction, not replacement.** When writing the spec
  for a harness-agnostic platform, every layer "provides the same capability as"
  the source system — NOT "replaces" it. The user caught replacement framing 4
  times in one spec review: (1) "replaces kanban" in the Solution section,
  (2) "migration/cutover tooling" in Out of Scope, (3) coupling to Hermes as
  the only harness, (4) backward compat with legacy formats. The fix each time:
  rewrite as "provides the X layer (same role as Y)" and remove all migration,
  cutover, backward compat, and legacy references. The system is built complete
  from the first build.

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
