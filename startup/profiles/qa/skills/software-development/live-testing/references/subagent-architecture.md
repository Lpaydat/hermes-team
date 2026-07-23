# Subagent & Kanban Architecture — Orchestration Constraints & Patterns

How QA should split test execution across delegate_task subagents and kanban child cards. Based on analysis of how the verifier, tech-lead, and developer profiles delegate, and research into big tech QA patterns.

## The hard constraint: shared running artifact

QA needs to build the artifact once and have multiple test workers test against the same running instance. This constraint determines which delegation mechanism works:

| Mechanism | Shares host process? | Can reach a running server? | Durable? | Context isolated? |
|---|---|---|---|---|
| **`delegate_task`** (in-session subagent) | YES — shares parent's host, filesystem, process namespace | YES — `localhost:PORT` started by parent is reachable | NO — dies if session crashes | YES — fresh context each |
| **kanban child card** (dispatcher-spawned) | NO — fresh workspace (`worktree` = new git worktree, `scratch` = fresh tmp, `dir` = shared path but separate process) | NO — not reliably; built artifact may not exist, server process not inherited | YES — survives crashes, auto-resumes | YES — fresh session each |
| **kanban child card + container** | NO — isolated workspace | YES — child starts its own container from pre-built image | YES — survives crashes, auto-resumes | YES — fresh session each |

**Rule:** `delegate_task` is the ONLY mechanism that supports build-once-test-many without containers. Kanban child cards require each worker to rebuild independently (wasteful, risks version drift) — UNLESS the main session builds a container image once and each child worker starts its own container from that image.

## When to use which mechanism

### Small artifacts — single session (no delegation)

All 8 phases in one session. No subagents, no child cards. Use when: CLI tool, library, <10 claims, stateless.

### Small-medium artifacts — delegate_task (in-session subagents)

When context pressure is a concern but the artifact is still small enough to build in-session. Use `delegate_task` for phases 3–5. The parent builds and starts the artifact; subagents test against the running instance.

- **Pros:** build-once-test-many (subagents share host), fresh context per subagent, parallel execution.
- **Cons:** dies on session crash, shares rate limit, not durable.

Pattern:
```
Main session: Phase 0-2 (receive, plan, build + smoke)
    Artifact running on localhost:PORT.
    ↓
delegate_task fan-out (parallel, restricted context each):
    Subagent A: Phase 3 — prove claims (gets plan claims + connection details)
    Subagent B: Phase 4 — walk journeys (gets plan journeys + connection details)
    Subagent C: Phase 5 — non-functional smoke (gets connection details + smoke ref)
    Each returns: per-item PASS/FAIL + evidence pointers (not raw output)
    Each writes evidence to ~/projects/<slug>/qa-evidence/<qa-card-id>/phase-N/
    ↓
Main session: Phase 6 (explore — needs full context, keep in-session)
              Phase 7 (synthesize verdict + report from subagent summaries)
```

### Medium/large artifacts — kanban fan-out + containers (v3.0)

When the artifact is large enough to need isolation and durability. The main session builds a container image once, creates child kanban cards, then blocks. Child workers each start their own container and test in isolation.

- **Pros:** durable (survives crashes, auto-resumes), context-isolated, parallel, resource-limited.
- **Cons:** can't share a running server (solved by containers), dispatcher round-trip latency, each worker needs container startup time.

Pattern:
```
Main session: Phase 0-2 (receive, plan, build + containerize + smoke)
    Container image: qa-test:<card-id>
    Child kanban cards created (one per test aspect)
    kanban_block(reason="dependency: waiting for N child test workers")
    ↓
Dispatcher spawns child workers (parallel, fresh sessions):
    Worker A: Phase 3 — prove claims (starts container on port 18081)
    Worker B: Phase 4 — walk journeys (starts container on port 18082)
    Worker C: Phase 5 — non-functional + security (starts container on port 18083)
    Worker D: Phase 6 — exploratory (starts container on port 18084)
    Each: podman run → health check → test → write evidence → podman rm -f → complete
    ↓
All children complete → parent auto-promotes
    ↓
Main session: Phase 7 (synthesize verdict + report from evidence ledger)
```

## Context pressure estimate

Running all 8 phases in one session will blow the context window:

| Phase | Pressure source | Est. tokens |
|-------|----------------|-------------|
| Phase 2 (Build) | Build logs, dependency output, startup logs | 5–10K |
| Phase 3 (Prove claims) | 20+ claims × 5 edge cases = 100+ test results with curl/CLI output | 15–30K |
| Phase 4 (Journeys) | Multi-step API/browser sequences, screenshots, DOM snapshots | 5–15K |
| Phase 5 (Non-functional) | wrk output, axe-core reports, security depth results | 5–10K |
| Phase 6 (Explore) | Probe scripts, unexpected output, degradation logs | 5–10K |

Total: potentially 35–75K tokens of raw test output. The plan (Phase 1) and verdict (Phase 7) would be buried.

## Evidence ledger (crash recovery)

Every test result written to disk immediately. Protocol resumable from any phase. Read `summary.json` on re-dispatch → skip completed phases, re-run only incomplete.

```
~/projects/<slug>/qa-evidence/<qa-card-id>/
  plan.json                    — the test plan (from Phase 1)
  phase-3-claims/
    claim-01-proven.txt        — actual test output
    claim-02-disproven.txt     — actual failing output
    summary.json               — [{claim_id, verdict, evidence_file, risk_level}]
  phase-4-journeys/
    admin-flow-01.txt
    summary.json
  phase-5-smoke/
    security.txt
    performance.txt
    summary.json
  phase-6-explore/
    charter-01.txt
    summary.json
  overall-summary.json         — all verdicts, complete/incomplete status, crash recovery checkpoint
```

Keyed by QA card id. The ledger survives session death; a re-dispatched QA worker reads `overall-summary.json` to recover state without re-testing.

Never write test artifacts to the workspace under test — evidence goes to `~/vault/` or `/tmp`, never the repo.

## Subagent context restriction (independence guarantee)

Borrowed from the verifier's Phase B pattern. When dispatching a fresh-eyes re-verification subagent:

- `context`: ONLY the spec/claims + connection details
- **Never pass**: prior findings, QA's verdicts, or evidence
- The restricted context IS the independence guarantee — passing prior findings destroys it

Disagreements between QA's verdicts and fresh-eyes verdicts are high-signal — both looked at the same thing and saw different results. Investigate every disagreement.

## Container-based build-once-test-many (v3.0 innovation)

The fundamental problem: kanban child cards can't access a running server started by the parent (isolated workspaces). The solution: build a container image once in the main session, then each child worker starts its own container from that image.

```
Main session:                    Child workers (kanban-dispatched):
  build artifact                   receive child card
  podman build -t qa-test:ID .     podman run -d -p 1808X:PORT qa-test:ID
  create child cards               health check
  kanban_block                     run assigned tests
                                   podman rm -f
                                   kanban_complete with summary
```

This gives us: build-once (image built once), test-many (each worker has its own isolated instance), durable (kanban cards survive crashes), parallel (up to 4 workers), resource-limited (1GB/1CPU per container).

## What the three profiles teach

| Profile | Delegation mechanism | Why QA borrows it |
|---|---|---|
| **Verifier** | `delegate_task` for Phase B (fresh-eyes), parallel with Phase C | In-session parallelism, shared worktree, restricted context for independence |
| **Tech-lead** | `kanban_delegate` for dev/verifier cards, blocks and auto-resumes | Cross-session durability, automatic dependency tracking |
| **Developer** | External harness as terminal tool (no subagents) | Trace-ledger discipline → evidence ledger pattern |
