---
name: live-testing
description: "Use when you receive a QA card or are asked to test an assembled, running artifact. Drives the QA protocol: plan tests from the spec, build and smoke the real artifact, prove claims, walk user journeys, run non-functional smokes, explore beyond the spec, then verdict and report. Re-test loop handles developer fixes across kanban cards. Dispatches to per-type reference playbooks."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, testing, live-testing, empirical, integration, e2e, protocol]
    related_skills: [team-delegation, find-skills]
---

# Live Testing — the QA protocol

You test the **assembled, running artifact** to prove it works in the real world. You never read code, review diffs, or fix bugs. You build it, run it, use it like a real user, and break it.

The verifier proves the code is built right. You prove the right thing was built and that it survives contact with reality.

## The protocol

Every QA card runs these phases in order. Each phase has a **Done when** — you do not advance until the criterion is met.

### Phase 0 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract:

- **What was built** — the feature, fix, or change under test
- **What it claims to do** — the spec's expected behaviors
- **Artifact type** — CLI, API server, webapp, TUI, mobile, blockchain, daemon, library (see §Program type dispatch)
- **Scope** — is this one feature, one merged PR, or the whole artifact? The card or parent task should state this. If it doesn't, infer from the parent chain and state your assumption.

**Done when:** you can state in one sentence what you're testing and what artifact type it is. If the spec is too vague to identify what was built, file a finding (Note: "spec too vague to test") and block the card.

### Phase 1 — Plan

Before touching the artifact, draft a **test plan** as a kanban comment on the card. This is what makes execution predictable — phases 3–6 just work through what you produce here.

The plan contains:

1. **Claims checklist** — translate every spec feature into testable claims (specific, pass/fail assertions). Vague specs ("it should work well") get translated into concrete claims by you. If a feature resists a pass/fail framing, mark it _untestable_ with the reason.
2. **User journeys** — 1–3 end-to-end flows per persona, covering the core goal. One sentence each.
3. **Exploration targets** — 1–2 high-risk areas to probe beyond the spec (auth flows, file handling, payment processing, concurrent access). One sentence each.
4. **Non-functional dimensions** — which smoke checks apply (security always; performance for servers/APIs; accessibility for webapps).

Example plan:
```
Claims:
  1. POST /users returns 201 with JSON body containing id
  2. GET /users/:id returns 200 with the user object
  3. DELETE /users/:id returns 204 and the user is gone
  4. Invalid email on POST returns 400 with error message
Journeys:
  - Admin signs in → creates user → user appears in list → deletes user
Exploration:
  - Probe auth: token expiry, concurrent sessions, role escalation
Non-functional:
  - Security: IDOR on /users/:id, auth bypass, secrets in response
  - Performance: time POST /users, 30s wrk on GET /users
```

Post the plan as a `kanban_comment` on the card so the team can see what you're testing before you start.

**Done when:** the plan is posted as a comment on the card. Every spec feature maps to at least one claim, journey, or exploration target. Unmapped features are flagged.

### Phase 2 — Build & smoke

Build the real artifact from source, the way a user would. See §Build system detection.

Then **smoke test** — confirm it's actually running and reachable before testing anything:

- CLI: `--help` or `--version` produces output
- Server: health endpoint responds, or `ss -tlnp` shows it listening
- Webapp: the URL renders in a browser
- TUI: the interface appears on screen
- Daemon: process is running and accepting connections
- Library: `import` succeeds in a real script

**Done when:** the artifact builds without errors AND you have positive evidence it's running and reachable. Capture the smoke proof — it's evidence for all phases that follow.

If the build fails, capture the full error output and file a finding (Critical: "build fails"). Stop — there's nothing to run. If the build succeeds but the artifact won't start, file a finding (Critical: "artifact won't start") and stop.

### Phase 3 — Prove claims

Work through the claims checklist from your plan. For each claim:

1. **Happy path first** — does it work with normal input?
2. **Edge cases** — apply relevant categories from §Universal edge case categories

Give each claim a **verdict**: _proven_, _disproven_, or _untested_.

If the happy path of a core claim fails, file immediately (Critical) and skip its edge cases — a disproven core claim blocks everything downstream. Continue with other claims.

**Done when:** every claim on your checklist has a verdict, each backed by captured evidence. _Untested_ claims have the reason noted. At least 5 edge cases tested per major feature.

### Phase 4 — Walk user journeys

Claims verify features in isolation. Journeys verify a user can actually accomplish a goal end-to-end. Individual claims can all pass while the flow breaks — session lost between steps, state not carried, dead-end after success.

Execute each journey from your plan as a real user would: click through the UI, call the API sequence, pipe the CLI commands. Give each journey a verdict.

A journey that can't be completed gets a _disproven_ verdict even if every component claim passed — the broken flow itself is the finding.

**Done when:** at least one journey per persona has a verdict with evidence (screenshot sequence, API call chain, or CLI command chain).

### Phase 5 — Non-functional smoke

Run the cheap, fast checks that catch regressions the functional claims miss. Load `references/non-functional-smoke-checks.md` for concrete commands per program type.

- **Security:** IDOR, auth bypass, secrets in output, dependency scan
- **Performance:** time key ops, 30s smoke load, degradation under trivial concurrency
- **Accessibility** (webapps only): axe-core scan, tab-order, contrast check

Each check passes, fails (becomes a finding), or is skipped (not applicable — note the reason).

**Done when:** all applicable smoke checks have been run or explicitly skipped with a reason.

### Phase 6 — Explore beyond the spec

Claims, journeys, and smokes test what the spec says and the standard dimensions. This phase finds what the spec _didn't anticipate_ — bugs in the gaps between features, in unexpected input combinations, in edge interactions.

For each exploration target from your plan, write a **charter** — a one-sentence mission bounding the probe:

- "Probe the file-upload feature for size, type, and encoding edge handling"
- "Probe the auth flow for token expiry, refresh, and concurrent session behavior"

Spend a bounded effort per charter writing and running probes that go beyond the spec's claims. Log every unexpected behavior with evidence.

Also test **graceful degradation**: kill the DB, make an upstream return 500, fill the disk — does the artifact handle the error or crash? These failure modes are where running-system testing finds bugs that code-level testing (verifier) can't.

**Done when:** at least one exploratory charter has been executed with findings logged, and graceful-degradation has been tested (or skipped with a reason).

### Phase 7 — Verdict & report

Every claim, journey, and smoke check now has a verdict. Close the loop.

**If any finding is Critical:** file findings as kanban cards assigned to `developer` (see §Filing findings), then `kanban_block(reason="dependency: N critical findings filed for fix")`. The card resumes when fixes are merged.

**If findings are Important/Minor/Note only:** file findings, then complete the card with a test report including all findings. The team decides whether to fix before shipping.

**If all claims are _proven_:** complete the card with a test report:
- Claims tested and proven
- Journeys completed
- Edge cases covered
- Non-functional checks run
- Exploratory findings (if any)
- What you couldn't test and why

**Done when:** the QA card is completed with a verdict for every claim and journey, or every Critical finding has a filed kanban card and the card is blocked on those fix cards.

## Re-test loop

When a developer fixes a filed finding and merges, the QA card unblocks. On re-test:

1. **Pull the latest** — rebuild the artifact from the updated source.
2. **Delta re-test** — re-run only the specific claim/journey/smoke that was disproven. Verify the fix resolves it.
3. **Regression check** — re-run the happy path of adjacent claims to confirm the fix didn't break neighbors. You don't need to re-run the entire suite, but check anything that shares a code path or data flow with the fix.
4. **Verdict** — if the fix holds and no regression, mark the finding resolved. If the fix introduces a new issue, file a new finding (Critical or Important).
5. **Escalation** — if the same finding survives 3 fix attempts, `kanban_block(reason="escalation: <finding> not resolved after 3 attempts")` to surface it to tech-lead.

The re-test loop is where confirmation bias lives. Every re-test must re-derive the expected outcome from the spec independently — verify the fix, then probe the same area fresh for new issues. See how the verifier handles this in `references/qa-practices.md` §QA vs. Verifier boundary.

**Done when:** all findings are resolved or escalated, and the card can be completed or is blocked on escalation.

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
| Other languages | `references/language-build-reference.md` |

**Novel type?** Map it to the closest archetype — every program either takes input and produces output (CLI-like), listens on a port (server-like), shows a UI (app-like), or is consumed by code (library-like). Apply the closest playbook, adapted. Then author a new `references/<type>-testing.md` so future runs start from your notes.

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

Always include the **environment** with each finding: OS, runtime version, artifact build.

## Filing findings

When a claim is _disproven_, create a kanban card assigned to `developer` as a child of the QA card (so the dependency is tracked).

Load `references/finding-severity.md` for the full severity rubric.

| Severity | Meaning |
|----------|---------|
| **Critical** | Blocks shipping. Core feature broken, data loss, security hole. |
| **Important** | Should fix before ship. Degraded experience or broken edge case. |
| **Minor** | Can ship with. Cosmetic or low-impact. |
| **Note** | Observation, not a bug. UX feedback, spec ambiguity. |

**Card title:** `[QA][<severity>] <the claim that failed>`
**Card body:**
- **Claim tested:** the assertion from the spec
- **Severity:** Critical / Important / Minor / Note
- **Actual result:** what you observed
- **Reproduction steps:** numbered, copy-pasteable commands
- **Evidence:** actual command output / response / screenshot
- **Environment:** OS, runtime version, artifact build

Report symptoms and reproduction. The developer diagnoses root cause from the evidence.
