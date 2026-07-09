---
name: live-testing
description: "Use when you receive a QA card or are asked to test an assembled, running artifact. Drives the QA protocol v3.0: adaptive sizing (small/medium/large), container-isolated parallel test execution (Podman-first), risk-based planning, two-pass screening, evidence ledger for crash recovery, expanded security and edge-case depth. Re-test loop handles developer fixes across kanban cards. Dispatches to per-type reference playbooks."
version: 3.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, testing, live-testing, empirical, integration, e2e, protocol, container, podman, adaptive]
    related_skills: [team-delegation, find-skills]
---

# Live Testing — the QA protocol v3.0

You test the **assembled, running artifact** to prove it works in the real world. You never read code, review diffs, or fix bugs. You build it, run it, use it like a real user, and break it.

The verifier proves the code is built right. You prove the right thing was built and that it survives contact with reality.

## The protocol — adaptive execution

Every QA card runs the same 8-phase spine. The **execution strategy** adapts to artifact size:

- **Small** (CLI tool, library, <10 claims, stateless): all 8 phases in a single session. No container. This is the v2.0.0 baseline.
- **Medium** (API server, daemon, 10–20 claims, stateful): kanban fan-out with container isolation. 2–3 parallel child workers.
- **Large** (webapp + API + auth, 20+ claims, multi-service): kanban fan-out with containers. 4 workers (one per test aspect). Evidence ledger.

The sizing decision is made in Phase 1 (Plan). Phases 0–2 and 7 always run in the main session. Phases 3–6 run in the main session for small, or are delegated to child kanban cards for medium/large.

### Phase 0 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract:

- **What was built** — the feature, fix, or change under test
- **What it claims to do** — the spec's expected behaviors
- **Artifact type** — CLI, API server, webapp, TUI, mobile, blockchain, daemon, library (see §Program type dispatch)
- **Scope** — is this one feature, one merged PR, or the whole artifact? The card or parent task should state this. If it doesn't, infer from the parent chain and state your assumption.

**Done when:** you can state in one sentence what you're testing and what artifact type it is. If the spec is too vague to identify what was built, file a finding (Note: "spec too vague to test") and block the card.

### Phase 1 — Plan + Size

Before touching the artifact, extract claims and risk-rank them from the spec. The plan IS the card structure on the board — it is not a comment.

1. **Claims checklist** — translate every spec feature into testable claims (specific, pass/fail assertions). Vague specs ("it should work well") get translated into concrete claims by you. If a feature resists a pass/fail framing, mark it _untestable_ with the reason.
2. **Risk ranking** — rank each claim P0–P4 (see §Risk-based planning). High-risk claims get full depth testing; low-risk claims get smoke only.
3. **User journeys** — 1–3 end-to-end flows per persona, covering the core goal. One sentence each.
4. **Exploration targets** — 1–2 high-risk areas to probe beyond the spec (auth flows, file handling, payment processing, concurrent access). One sentence each.
5. **Non-functional dimensions** — which smoke checks apply (security always; performance for servers/APIs; accessibility for webapps). See `references/non-functional-smoke-checks.md` for the expanded security depth checklist.

Then **size the artifact**:

| Criterion | Small | Medium | Large |
|---|---|---|---|
| Artifact type | CLI, library | API server, daemon | Webapp + API + auth |
| Claim count | <10 | 10–20 | 20+ |
| Statefulness | Stateless | Stateful (DB, sessions) | Multi-service, external integrations |
| Execution | Single session | Kanban fan-out + container | Kanban fan-out + containers |
| Workers | 1 (in-session) | 2–3 (child cards) | 4 (one per aspect) |

**For small artifacts:** proceed directly to Phase 2 (build + smoke) in the same session. The plan stays in your context.

**For medium/large artifacts:** create dynamic test-aspect kanban cards (see §Kanban card structure). Each card's body contains the claims, journeys, or exploration targets assigned to it. The card structure IS the plan — the board shows what's being tested. Complete this card with `kanban_complete(metadata={claims: [...], risk_ranking: [...], aspects: [...], sizing: "medium"|"large"})` so the verdict session can read the plan programmatically.

**Done when:** for small — claims extracted and risk-ranked in context. For medium/large — dynamic test-aspect cards created with claims in their bodies, and this card completed with the plan in metadata. Every spec feature maps to at least one claim, journey, or exploration target.

### Phase 2 — Build, containerize, smoke

Build the real artifact from source, the way a user would. See §Build system detection.

**For medium/large artifacts** that need container isolation, this phase runs as a **parallel kanban card** alongside Phase 1 (Plan). Plan and Build don't depend on each other — Plan extracts claims from the spec; Build compiles and containerizes. Dynamic test cards depend on BOTH (they need the plan to know what to test, and the build to have the container image).

1. **Detect or generate a Containerfile.** If the project has a `Dockerfile` or `Containerfile`, use it. If not, generate one based on the detected build system (see `references/container-testing.md`).
2. **Build the image:** `<runtime> build -t qa-test:<card-id> .` (runtime = podman by default, docker as fallback).
3. **Verify the image starts and passes health check** — `podman run -d -p 18080:<app-port> qa-test:<card-id>`, poll health, then stop.
4. **Complete this card** with `kanban_complete(metadata={image_tag: "qa-test:<card-id>", container_port: <app-port>, build_success: true})` — dynamic test cards read this via `kanban_show` to get the image tag.

Then **smoke test** — confirm the artifact is actually running and reachable before testing anything:

- CLI: `--help` or `--version` produces output
- Server: health endpoint responds, or `ss -tlnp` shows it listening
- Webapp: the URL renders in a browser
- TUI: the interface appears on screen
- Daemon: process is running and accepting connections
- Library: `import` succeeds in a real script

**Done when:** the artifact builds without errors AND you have positive evidence it's running and reachable. For medium/large: container image is built and child cards are created. Capture the smoke proof — it's evidence for all phases that follow.

If the build fails, capture the full error output and file a finding (Critical: "build fails"). Stop. If the build succeeds but the artifact won't start, file a finding (Critical: "artifact won't start") and stop.

### Phase 3 — Prove claims (two-pass)

**Small:** run this in-session. **Medium/large:** this runs in a child worker card.

**Pass 1 — Smoke all claims (fast):** For each claim, run the happy path only. If a core claim's happy path fails, file immediately (Critical) and skip its edge cases — a disproven core claim blocks everything downstream. This catches broken happy paths before wasting deep-test effort.

**Pass 2 — Deep test passing claims:** For each claim that passed smoke, apply edge cases from §Universal edge case categories and §Expanded edge case categories. Depth is determined by risk ranking:
- **P0/P1 (high-risk):** full depth — 10+ edge cases, degradation probes, concurrent access tests
- **P2 (medium-risk):** standard depth — 5 edge cases, happy path journeys
- **P3/P4 (low-risk):** smoke only — happy path

Give each claim a **verdict**: _proven_, _disproven_, or _untested_.

**Evidence:** return short evidence inline in `kanban_complete(summary=...)`. Write long evidence to `/tmp/qa-evidence/<card-id>/` (ephemeral). Return structured verdicts in `kanban_complete(metadata={verdicts: [...], findings: [...]})` — the verdict session reads this via `kanban_show`.

**Done when:** every claim on your checklist has a verdict, each backed by captured evidence. _Untested_ claims have the reason noted.

### Phase 4 — Walk user journeys

**Small:** in-session. **Medium/large:** child worker card.

Claims verify features in isolation. Journeys verify a user can actually accomplish a goal end-to-end. Individual claims can all pass while the flow breaks — session lost between steps, state not carried, dead-end after success.

Execute each journey from your plan as a real user would: click through the UI, call the API sequence, pipe the CLI commands. Give each journey a verdict.

A journey that can't be completed gets a _disproven_ verdict even if every component claim passed — the broken flow itself is the finding.

**Done when:** at least one journey per persona has a verdict with evidence (screenshot sequence, API call chain, or CLI command chain). Write to evidence ledger.

### Phase 5 — Non-functional smoke + security depth

**Small:** in-session. **Medium/large:** child worker card.

Run the cheap, fast checks that catch regressions the functional claims miss. Load `references/non-functional-smoke-checks.md` for concrete commands per program type, including the expanded **security depth** checklist:

- **Security smoke:** IDOR, auth bypass, secrets in output, dependency scan
- **Security depth (new in v3.0):** CSRF, XSS, SSRF, open redirect, path traversal, command injection, session fixation
- **Performance:** response time, 30s smoke load, degradation under concurrency
- **Accessibility** (webapps only): axe-core scan, tab-order, contrast check
- **Expanded edge cases** (see §Expanded edge case categories): data integrity, idempotency, cache invalidation, graceful shutdown, connection pool exhaustion, locale/i18n, Unicode normalization, GraphQL depth, API versioning, pagination drift, rate limiting, WebSocket reconnection, upgrade/migration, recovery

Each check passes, fails (becomes a finding), or is skipped (not applicable — note the reason). Write results to evidence ledger.

**Done when:** all applicable smoke checks have been run or explicitly skipped with a reason. Security depth checks run on all artifacts that accept input or have authentication.

### Phase 6 — Explore beyond the spec

**Small:** in-session. **Medium/large:** child worker card (but the main session retains the right to run additional exploratory probes with full plan context).

Claims, journeys, and smokes test what the spec says. This phase finds what the spec _didn't anticipate_ — bugs in the gaps between features, in unexpected input combinations, in edge interactions.

For each exploration target from your plan, write a **charter** — a one-sentence mission bounding the probe:

- "Probe the file-upload feature for size, type, and encoding edge handling"
- "Probe the auth flow for token expiry, refresh, and concurrent session behavior"

Spend a bounded effort per charter writing and running probes that go beyond the spec's claims. Log every unexpected behavior with evidence.

Also test **graceful degradation**: kill the DB, make an upstream return 500, fill the disk — does the artifact handle the error or crash? Also test **recovery**: crash the process, restart, verify state is intact. These failure modes are where running-system testing finds bugs that code-level testing (verifier) can't.

**Done when:** at least one exploratory charter has been executed with findings logged, and graceful-degradation + recovery have been tested (or skipped with a reason).

### Phase 7 — Verdict & report

**For small artifacts** (all in-session): proceed directly to verdict.

**For medium/large artifacts:** the main session was blocked waiting for child workers. When all children complete, the parent card auto-promotes. Read child card completions via `kanban_show` (which returns each child's `metadata` — structured verdicts, findings, evidence pointers) and synthesize. Do NOT read from `~/vault/` — evidence flows through kanban.

Every claim, journey, and smoke check now has a verdict. Close the loop.

**If any finding is Critical:** file findings as kanban cards assigned to `developer` (see §Filing findings), then `kanban_block(reason="dependency: N critical findings filed for fix")`. The card resumes when fixes are merged.

**If findings are Important/Minor/Note only:** file findings, then complete the card with a test report including all findings. The team decides whether to fix before shipping.

**If all claims are _proven_:** complete the card with a test report:
- Claims tested and proven (with risk levels)
- Journeys completed
- Edge cases covered (by category)
- Non-functional checks run (security depth included)
- Exploratory findings (if any)
- Testability feedback (see below)
- What you couldn't test and why

**Testability feedback (Google TE pattern):** Include a "testability notes" section in the verdict — design decisions that made testing hard. Missing health endpoints, stateful sessions that prevent clean test isolation, no way to reset state between tests, untestable auth flows. File as a Note-severity finding addressed to `tech-lead`. This is the highest-leverage QA-survivor skill: catching testability gaps at the system level feeds back into better designs.

**Verdict is a machine-readable gate:** PASS (all claims proven, no Critical findings), FAIL (Critical findings exist), BLOCK (blocked on fixes). Include in the completion summary.

**Done when:** the QA card is completed with a verdict for every claim and journey, or every Critical finding has a filed kanban card and the card is blocked on those fix cards.

## Adaptive execution: small vs medium vs large

### Small execution (single session)

All 8 phases run in the current session, sequentially. This is the v2.0.0 baseline — no containers, no child cards, no evidence ledger needed (though writing evidence is still good practice). Use when the artifact is a CLI tool, library, or small stateless service with <10 claims.

### Medium/large execution (kanban card fan-out + containers)

Phases 0, 7, and the creation of Card 1 + Card 2 run in the main session. Card 1 (Plan) and Card 2 (Build) run **in parallel** as separate kanban cards. Dynamic test cards (A-D) are created by Card 1 and depend on both Card 1 and Card 2. The main session blocks after creating Card 1 + Card 2; it auto-promotes when all test cards complete, then runs Phase 7.

#### Container runtime selection

Detect at runtime:
```bash
command -v podman && echo "podman" || (command -v docker && echo "docker" || echo "none")
```

- **Podman (default):** rootless, daemonless, lighter. `podman build` reads Dockerfile. `podman run` accepts the same flags as Docker.
- **Docker (fallback):** used when Podman is not available or configured explicitly.
- **Workspace isolation (last resort):** if neither is available, each worker builds from source in its own workspace. Only safe for stateless artifacts (CLI, library). For stateful artifacts, file a finding: "cannot isolate test environment — container runtime not available."

Configurable in config.yaml: `qa.container_runtime: podman` (or `docker` or `none`).

#### Container lifecycle

1. Main session builds image once: `<runtime> build -t qa-test:<card-id> .`
2. Each child worker starts its own container: `<runtime> run -d --memory=<limit> --cpus=<limit> -p <unique-port>:<app-port> qa-test:<card-id>`
3. Port allocation: sequential from 18081 (18081, 18082, 18083, 18084)
4. Health check: poll the health endpoint or TCP port for up to 30 seconds
5. Cleanup: `<runtime> rm -f <container-id>` after testing is complete

Resource limits (configurable): 1GB memory, 1 CPU per container, max 4 parallel.

See `references/container-testing.md` for Containerfile generation templates, health check patterns, and cleanup procedures.

#### Kanban card structure

**Default cards** (always created by Card 0 / Phase 0):

| Card | Phase | Assignee | Parents | Purpose |
|---|---|---|---|---|
| Card 0: Receive | 0 | qa | QA Card | Read spec, identify type, determine sizing, create Card 1 + Card 2 |
| Card 1: Plan | 1 | qa | Card 0 | Extract claims, risk-rank, create dynamic test cards |
| Card 2: Build | 2 | qa | Card 0 | Build from source, containerize, verify image |
| Card 7: Verdict | 7 | qa | Card A, B, C, D | Read child completions, synthesize, file findings |

**Dynamic cards** (created by Card 1 based on test plan):

| Card | Phase | Assignee | Parents | Purpose |
|---|---|---|---|---|
| Card A: Functional | 3 | qa | Card 1, Card 2 | Prove/disprove claims, happy path + edge cases |
| Card B: Journeys | 4 | qa | Card 1, Card 2 | Walk end-to-end user flows |
| Card C: Security+NonFunc | 5 | qa | Card 1, Card 2 | Security depth, perf, a11y, chaos |
| Card D: Exploratory | 6 | qa | Card 1, Card 2 | Charter probing, degradation |

Card 1 (Plan) and Card 2 (Build) run **in parallel** — they have no dependency on each other. Dynamic test cards (A-D) depend on BOTH: `parents=[Card1, Card2]`. The dispatcher won't promote them until both are done. Card 7 depends on all test cards.

For medium artifacts, workers A+B can be merged (2–3 workers). For large, all 4 are separate.

Each child card body includes: test aspect, claims/journey list, container image tag (`qa-test:<card-id>`), allocated port.

Each child completes with: `kanban_complete(summary=<human-readable results>, metadata={verdicts: [...], findings: [...]})` — the verdict session reads this via `kanban_show`.

#### Evidence flow — through kanban, not ~/vault/

Evidence flows through the kanban system. **Never write to `~/vault/`** — that's the knowledge base (journal, wiki, ventures, traces). QA evidence is runtime data, not knowledge.

| Evidence type | Where it goes | Lifecycle |
|---|---|---|
| Short (curl output, exit codes, HTTP status) | Inline in `kanban_complete(summary=...)` or finding card body | Persists with card |
| Long (full logs, wrk output, axe-core reports) | `/tmp/qa-evidence/<card-id>/` | Ephemeral — cleaned when session ends |
| Visual (screenshots) | `task_attachments` on finding card | Persists in kanban DB |
| Structured (per-claim verdicts) | `kanban_complete(metadata={...})` as JSON | Auto-injects into parent context |

**Crash recovery:** child workers write structured results to `kanban_complete(metadata=...)`. If the verdict session crashes, a re-dispatched worker reads child card completions via `kanban_show` — no file system needed. Ephemeral evidence in `/tmp/` may be lost on crash, but the structured verdicts in kanban metadata survive.

This mirrors how the developer hands off to the verifier (`kanban_complete(metadata={branch_name, worktree_path, ...})`) and how the verifier comments findings on the developer card. QA uses the same mechanisms.

#### Why kanban fan-out for medium/large (not delegate_task)

`delegate_task` subagents share the parent's host — a running server IS reachable. But they die if the session crashes, and they count against the same rate limit. Kanban child cards are durable (survive crashes, auto-resume), get fresh sessions with isolated context windows, and are dispatched independently by the Hermes kanban dispatcher.

The trade-off: kanban child workers get isolated workspaces and **cannot access a running server started by the parent**. This is why we build a container image once in the main session — each child worker starts its own container from that image. Build-once, test-many via containers.

For small artifacts where context pressure isn't a concern, `delegate_task` remains a valid option for splitting phases 3–5 (see `references/subagent-architecture.md`).

#### The `hermes kanban swarm` command (platform-native fan-out)

The platform ships a `hermes kanban swarm` CLI command that creates the full worker → verifier → synthesizer topology in one atomic call. For medium/large artifacts, prefer this over manually creating+linking individual cards:

```bash
hermes kanban swarm \
  "QA: test <feature> for <project>" \
  --worker qa:"Functional claims"[:qa-functional] \
  --worker qa:"User journeys"[:qa-journeys] \
  --worker qa:"Security + non-functional"[:qa-security] \
  --worker qa:"Exploratory"[:qa-exploratory] \
  --verifier qa \
  --synthesizer qa \
  --created-by qa \
  --json
```

This creates a root card (shared blackboard), parallel worker cards (each with its skill loaded), a verifier gate, and a synthesizer — all with correct parent/child dependencies wired automatically.

Workers post structured results to the root card's blackboard (JSON comments). The synthesizer reads all blackboard updates via `latest_blackboard()` and produces the final verdict. This is the evidence-flow mechanism — no `~/vault/`, no file system, all in the kanban DB.

**Critical constraint: `max_in_progress_per_profile: 1`.** If all workers are `assignee=qa`, they execute serially (one at a time). The swarm topology is still correct — it's just slower. To get true parallelism, raise the cap in the ROOT `~/.hermes/config.yaml` (not per-profile config — the dispatcher reads only the root config; restart the gateway after changing), or accept serial execution (still durable and crash-safe).

#### `kanban_delegate` is NOT a real tool

The tech-lead skill references `kanban_delegate` as if it's a tool — it is not. It does not exist in the CLI, source, or kanban module. It is a convention name for "create children + link + block." If you need to create cards manually (instead of using `kanban swarm`), use the real tools: `kanban_create(assignee=..., parents=[...], skills=[...])` + `kanban_block(reason="dependency: ...")`.

## Risk-based planning

Claims are risk-ranked in Phase 1 using the P0–P4 severity system (Google Buganizer pattern):

| Level | Meaning | Test depth |
|---|---|---|
| **P0** | Launch blocker / data loss / security hole | Full depth: 10+ edge cases, journeys, degradation, concurrent access |
| **P1** | Major journey broken, no workaround | Full depth: 10+ edge cases, journeys, degradation |
| **P2** | Journey broken, workaround exists | Standard depth: 5 edge cases, happy path journeys |
| **P3** | Minor / cosmetic | Smoke only: happy path |
| **P4** | Suggestion / nice-to-have | Smoke only or skip |

Risk = likelihood (complexity × novelty × change volume) × impact (data loss × security × revenue × user-facing).

High-risk claims are tested first with full depth. Low-risk claims get smoke only. This ensures the most important things get the most testing effort.

## Two-pass approach

1. **Pass 1 (fast):** Smoke all claims — happy path only. If core claims fail, file immediately and block. This catches broken happy paths before wasting deep-test effort.
2. **Pass 2 (deep):** Full testing of passing claims only — edge cases, journeys, non-functional. Depth determined by risk ranking.

Configurable: `qa.two_pass: true` (default). When disabled, all claims get full depth in one pass.

## Re-test loop

When a developer fixes a filed finding and merges, the QA card unblocks. On re-test:

1. **Pull the latest** — rebuild the artifact from the updated source (rebuild container image if applicable).
2. **Delta re-test** — re-run only the specific claim/journey/smoke that was disproven. Verify the fix resolves it.
3. **Regression check** — re-run the happy path of adjacent claims to confirm the fix didn't break neighbors. You don't need to re-run the entire suite, but check anything that shares a code path or data flow with the fix.
4. **Verdict** — if the fix holds and no regression, mark the finding resolved. If the fix introduces a new issue, file a new finding (Critical or Important).
5. **Escalation** — if the same finding survives 3 fix attempts, `kanban_block(reason="escalation: <finding> not resolved after 3 attempts")` to surface it to tech-lead.

The re-test loop is where confirmation bias lives. Every re-test must re-derive the expected outcome from the spec independently — verify the fix, then probe the same area fresh for new issues.

**Done when:** all findings are resolved or escalated, and the card can be completed or is blocked on escalation.

## Grounding in industry practice

The protocol mirrors how Google, Meta, Netflix, Amazon, Microsoft, and Spotify structure QA. For per-company specifics and to justify the protocol's shape to skeptics, load `references/industry-qa-organization-patterns.md`. Key validations: devs own unit/integration everywhere; the QA specialist's unique value is exploratory + testability-review-at-design-time + verdict (Phases 5–7); fix→retest is universally automated; P0–P4 (Google) maps cleanly to our Critical/Important/Minor/Note.

## Build system detection

Detect from the repo root:

| Signal | Build command |
|--------|--------------|
| `package.json` | `npm install && npm run build` (or `yarn`, `pnpm`, `bun`) |
| `Cargo.toml` | `cargo build --release` |
| `pyproject.toml` / `setup.py` | `pip install -e .` or `pip install .` |
| `go.mod` | `go build -o <binary>` or `go install` |
| `Makefile` | `make` |
| `Dockerfile` | `docker build -t <name> .` |
| `docker-compose.yml` | `docker compose up --build` |
| `CMakeLists.txt` | `mkdir build && cd build && cmake .. && make` |
| `pom.xml` | `mvn package` |
| `build.gradle` / `build.gradle.kts` | `./gradlew build` |
| `Gemfile` | `bundle install` then `rake` or the app command |
| `mix.exs` | `mix deps.get && mix compile` |
| `flake.nix` | `nix build` or `nix develop` |

For languages beyond this table (C#/.NET, PHP, Scala, Haskell, Erlang, Lua, R, Zig, Nim), load `references/language-build-reference.md`.

If the build fails, capture the **full error output** — that's your evidence. Try to resolve obvious issues (install missing system deps). If it needs code changes, file a finding.

## Universal edge case categories

Apply these systematically to each claim in Phase 3:

1. **Empty/zero/null input** — empty string, empty file, 0, null/None, empty list, missing fields
2. **Maximum/boundary input** — very long strings, huge files, max int, buffer-size boundaries (1024, 4096, 65535), off-by-one values
3. **Special characters** — unicode (é, 日本語, 🎉), quotes (`'"`), backslashes, null bytes (`\0`), newlines embedded in fields, SQL/HTML injection strings
4. **Concurrency** — simultaneous requests, race conditions, parallel file access, concurrent writes
5. **Restart/reconnect** — kill the process mid-operation, restart, reconnect a client after server restart
6. **Resource exhaustion** — disk full, too many open files, out of memory (test cautiously — keep the host alive)
7. **Network failure** — timeout, connection refused, DNS failure, partial reads, slow network
8. **Time/date** — timezone changes, DST transitions, epoch boundaries, future/past dates, leap seconds
9. **Authorization/auth** — unauthenticated access, wrong credentials, expired tokens, role escalation attempts
10. **Rapid repeated input** — double-submit, rapid clicks, replay attacks

## Expanded edge case categories (v3.0)

14 new categories beyond the universal 10. Apply based on artifact type and claim relevance:

| # | Category | What to test | Applies to |
|---|---|---|---|
| 11 | **Data integrity** | Create→update→delete cycles, concurrent writes, cascade behavior, orphaned records | API servers, daemons, DB-backed apps |
| 12 | **Idempotency** | Same request twice = same result (POST /charge twice = no double charge) | API servers, payment systems, webhooks |
| 13 | **Cache invalidation** | Stale data served from cache after update | API servers, webapps, CDNs |
| 14 | **Graceful shutdown** | SIGTERM mid-request — does it finish in-flight work? | API servers, daemons |
| 15 | **Connection pool exhaustion** | All connections in use, new request waits/hangs | API servers, daemons |
| 16 | **Locale/i18n** | Date/number/currency format differences (US `1,000.00` vs DE `1.000,00`) | API servers, webapps, CLI tools |
| 17 | **Unicode normalization** | Composed (é) vs decomposed (é́) treated differently — login mismatch | API servers, webapps, libraries |
| 18 | **GraphQL depth/complexity** | Deeply nested query causes DoS | GraphQL APIs |
| 19 | **API versioning** | v1 endpoint behaves differently from v2 — backward compat | API servers |
| 20 | **Pagination cursor drift** | New records inserted during pagination — skip or duplicate | API servers, webapps |
| 21 | **Rate limiting** | Threshold, reset, 429 response on exceed | API servers |
| 22 | **WebSocket reconnection** | Disconnect → reconnect → state sync | API servers, daemons, webapps |
| 23 | **Upgrade/migration** | Schema migration breaks existing data | API servers, daemons, DB-backed apps |
| 24 | **Recovery** | Crash → restart → state intact (self-heal) | All stateful artifacts |

Concrete test commands for these categories are in `references/non-functional-smoke-checks.md` and `references/testing-landscape.md`.

## Program type dispatch

Load the matching reference for type-specific build/run/test commands and edge cases:

| Program type | Load reference |
|-------------|----------------|
| CLI tool | `references/cli-testing.md` |
| API server (REST/GraphQL/gRPC) | `references/api-server-testing.md` |
| Webapp (browser-based UI) | `references/webapp-testing.md` |
| TUI app (terminal UI) | `references/tui-testing.md` |
| Mobile app (iOS/Android) | `references/mobile-app-testing.md` |
| Blockchain / smart contract | `references/blockchain-testing.md` |
| Daemon / broker / service | `references/daemon-testing.md` |
| Library / package / SDK | `references/library-testing.md` |
| Container testing | `references/container-testing.md` |
| Other languages | `references/language-build-reference.md` |

**Novel type?** Map it to the closest archetype — every program either takes input and produces output (CLI-like), listens on a port (server-like), shows a UI (app-like), or is consumed by code (library-like). Apply the closest playbook, adapted. Then author a new `references/<type>-testing.md` so future runs start from your notes.

For the kanban swarm command, blackboard pattern, `max_in_progress_per_profile` constraint, and how the tech-lead/verifier blocking patterns work, load `references/kanban-orchestration-patterns.md`.

## Evidence collection

Every _disproven_ claim needs evidence — actual output, not your summary of it. If you can't show it, it's not a finding.

| Evidence type | How to capture |
|--------------|----------------|
| Command output | Full stdout + stderr, exit code |
| HTTP response | `curl -v` output, or `requests` response object printed |
| Visual state | `browser_vision` screenshot for webapps/TUIs |
| Process state | `ps aux`, `ss -tlnp`, `docker ps` |
| Log output | Tail the log file, capture relevant lines |
| Timing | `time` command, or timestamped curl output |
| File state | `ls -la`, `cat`, or `hexdump` for binary |
| Container state | `<runtime> ps -a`, `<runtime> logs`, `<runtime> inspect` |

Always include the **environment** with each finding: OS, runtime version, artifact build, container image tag (if applicable).

## Filing findings

When a claim is _disproven_, create a kanban card assigned to `developer` as a child of the QA card (so the dependency is tracked).

Load `references/finding-severity.md` for the full severity rubric.

| Severity | Maps to | Meaning |
|----------|---------|---------|
| **Critical** | P0/P1 | Blocks shipping. Core feature broken, data loss, security hole. |
| **Important** | P2 | Should fix before ship. Degraded experience or broken edge case. |
| **Minor** | P3 | Can ship with. Cosmetic or low-impact. |
| **Note** | P4 | Observation, not a bug. UX feedback, spec ambiguity. |

**Card title:** `[QA][<severity>] <the claim that failed>`
**Card body:**
- **Claim tested:** the assertion from the spec
- **Severity:** Critical / Important / Minor / Note (with P-level)
- **Actual result:** what you observed
- **Reproduction steps:** numbered, copy-pasteable commands
- **Evidence:** actual command output / response / screenshot / evidence ledger path
- **Environment:** OS, runtime version, artifact build, container image tag

Report symptoms and reproduction. The developer diagnoses root cause from the evidence.

### Testability feedback (Google TE pattern)

In the verdict, flag design decisions that made testing hard — missing health endpoints, stateful sessions that prevent clean test isolation, no way to reset state between tests, untestable auth flows. File as a Note-severity finding addressed to `tech-lead`. This is the highest-leverage QA-survivor skill: catching testability gaps at the system level feeds back into better designs.

## Config keys (config.yaml)

```yaml
qa:
  container_runtime: podman    # podman | docker | none
  container_memory: 1g         # per-container memory limit
  container_cpus: 1            # per-container CPU limit
  max_parallel_workers: 4      # max child cards dispatched simultaneously
  two_pass: true               # smoke all claims before deep testing
  risk_based: true             # rank claims by risk before testing
```

Evidence flows through kanban (card body, metadata, attachments) and `/tmp/qa-evidence/` for ephemeral long-form output. No config key needed — the kanban DB is the source of truth.

## Terminology

- **Findings** are filed as **kanban cards** assigned to `developer`, not "beads." Beads are the PO's spec slices — a different artifact entirely.
- **Fix cards** are child kanban cards created by QA when a finding needs developer action.
- **Evidence** flows through kanban: short evidence inline in card body/summary, long evidence in `/tmp/qa-evidence/<card-id>/` (ephemeral), visual evidence as `task_attachments`, structured verdicts in `kanban_complete(metadata={...})`. Never write to `~/vault/` — that's the knowledge base.
- **Container image tag** format: `qa-test:<card-id>` — built once by Card 2 (Build), used by all dynamic test cards.

## Pitfalls

1. **Using "beads" instead of kanban cards.** Beads belong to the product-owner (spec-slicing layer). QA files findings as kanban cards to `developer`. Confusing the two breaks the planning/execution boundary.

2. **Clamping all phases in one session for medium/large artifacts.** Running all 8 phases in a single session produces 35–75K tokens of raw test output that buries the Phase 7 synthesis. For medium+ artifacts, use kanban fan-out with containers. For small artifacts, single-session is fine.

3. **Using delegate_task when kanban fan-out is needed.** `delegate_task` subagents share the parent's host (good for build-once-test-many) but die on session crash and share rate limits. Kanban child cards are durable and crash-surviving but can't access a running server — use containers to solve this. Choose the right mechanism for the artifact size.

4. **Not building the container image before creating child cards.** Each child worker needs the image to exist. Build once in Phase 2, then fan out. If a child worker has to build from source, you get version drift and wasted effort.

5. **Filing findings without reproduction steps.** "It failed" is not a finding. Copy-pasteable commands that reliably reproduce the failure are a finding. Capture evidence before filing.

6. **Re-testing only the fixed claim.** The fix→re-test loop must include a regression check on adjacent claims. A fix for one claim can break a neighbor that shares a code path or data flow. Re-derive expected outcomes from the spec independently.

7. **Skipping the plan phase.** The plan (Phase 1) is what makes execution predictable. Without it, testing becomes improvisation — claims get missed, journeys aren't extracted, exploration has no targets, risk ranking doesn't happen.

8. **Not cleaning up containers.** After testing, verify no orphaned containers remain (`<runtime> ps -a | grep qa-test`). Every child worker must `rm -f` its container. The main session should verify cleanup in Phase 7.

9. **Using `clarify` for design discussions.** The clarify tool's timeout is too short for collaborative design conversations with the user. Use it only for quick binary/multiple-choice decisions. For design discussions, chat in free-form text.

10. **Designing workflow before research is complete.** If you've dispatched research subagents to inform a design decision, do not synthesize approaches or make architecture decisions until ALL research streams have returned (or definitively failed).

11. **Reviewing only the main SKILL.md and declaring reference files "clean."** When reviewing a skill against quality principles, you must actually READ every reference file — not grep for patterns and declare them clean.

12. **Skipping the two-pass smoke.** The two-pass approach (smoke all claims first, deep-test only passing ones) catches broken happy paths before wasting deep-test effort. Skipping it means you may spend 20 minutes on edge cases for a claim whose happy path is already broken.

13. **Writing evidence to ~/vault/.** The vault is the knowledge base (journal, wiki, ventures, traces). QA evidence is runtime data. Write short evidence inline in kanban card body/summary, long evidence to `/tmp/qa-evidence/<card-id>/` (ephemeral), and structured verdicts to `kanban_complete(metadata={...})`. The kanban DB is the source of truth — it's durable, card-scoped, and readable via `kanban_show` without file system access.

14. **Posting the test plan as a kanban comment instead of creating cards.** A comment is informational. The plan should BE the card structure — Card 1 creates dynamic test-aspect cards with claims in their bodies. The board shows what's being tested. A comment gets buried; card structure is visible and actionable.
