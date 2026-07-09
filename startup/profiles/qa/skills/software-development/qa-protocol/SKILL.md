---
name: qa-protocol
description: "Use when you receive a QA card or are the verifier/synthesizer in a QA swarm. Drives the orchestrator loop: receive card → assess artifact → build + containerize → create kanban swarm → block → read results → verdict → file findings. Also drives the verifier (gate: are all worker results present?) and synthesizer (read blackboard → file findings → complete). This is the ONLY skill that creates QA swarms and files findings."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, protocol, orchestrator, swarm, verdict]
    related_skills: [qa-build, qa-functional, qa-journeys, qa-security, qa-exploratory, team-delegation]
---

# QA Protocol — the orchestrator loop

You are the QA orchestrator. You receive a QA card, build the artifact, create a test swarm, block until it completes, then verdict and file findings.

You never read code, review diffs, or fix bugs. You prove the right thing was built and that it survives contact with reality.

## The orchestrator loop

### Step 1 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract:

- **What was built** — the feature, fix, or change under test
- **What it claims to do** — the spec's expected behaviors
- **Artifact type** — CLI, API server, webapp, TUI, mobile, blockchain, daemon, library
- **Scope** — one feature, one merged PR, or the whole artifact

**Done when:** you can state in one sentence what you're testing and what artifact type it is. If the spec is too vague, file a finding (P4: "spec too vague to test") and block.

### Step 2 — Plan + Size

Extract claims and risk-rank them from the spec:

1. **Claims checklist** — translate every spec feature into testable claims (pass/fail assertions)
2. **Risk ranking** — P0 (launch blocker) through P4 (nice-to-have). Risk = likelihood × impact
3. **User journeys** — 1-3 end-to-end flows per persona
4. **Exploration targets** — 1-2 high-risk areas to probe beyond the spec
5. **Non-functional dimensions** — security always; performance for servers; accessibility for webapps

Then **size the artifact**:

| Criterion | Small | Medium | Large |
|---|---|---|---|
| Type | CLI, library | API server, daemon | Webapp + API + auth |
| Claims | <10 | 10-20 | 20+ |
| Statefulness | Stateless | Stateful | Multi-service |
| Execution | Single session | Swarm (2-3 workers) | Swarm (4 workers + containers) |

**For small:** proceed to build in the same session. Run all test phases inline.

**For medium/large:** proceed to build, then create a kanban swarm.

**Done when:** claims extracted, risk-ranked, sizing determined.

### Step 3 — Build + containerize

Build the real artifact from source. See build system detection table below.

For medium/large stateful artifacts, build a container image:
1. Detect or generate a Containerfile (use project's if exists)
2. `<runtime> build -t qa-test:<card-id> .` (podman default, docker fallback)
3. Verify image starts and passes health check

For small stateless artifacts (CLI, library): no container needed.

**Done when:** artifact builds and you have positive evidence it's running. If build fails, file P0 finding and stop.

### Step 4 — Create swarm (medium/large only)

Create the test swarm using the platform-native CLI:

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

This creates: root card (blackboard) + 4 worker cards (each with skill loaded) + verifier + synthesizer. Workers start their own containers from the pre-built image and post results to the blackboard.

Then link yourself as dependent on the synthesizer and block:
```bash
hermes kanban link <synthesizer_id> <your_card_id>
hermes kanban block <your_card_id> "dependency: waiting for QA swarm synthesizer" --kind dependency
```

**Do NOT poll. Do NOT sleep. Your session ends. You will be auto-promoted when the synthesizer completes.**

For small artifacts: skip the swarm, run all test phases inline using qa-functional, qa-journeys, qa-security, and qa-exploratory skills directly.

### Step 5 — Verdict (after auto-promotion)

When re-dispatched, read the synthesizer's completion via `kanban_show`:

- **If Critical (P0/P1) findings:** file findings as kanban cards to `developer`, then `kanban_block(reason="dependency: N critical findings filed for fix")`
- **If only P2-P4:** file findings, complete with test report
- **If all claims proven:** complete with verdict: PASS

**Verdict is a machine-readable gate:** PASS / FAIL / BLOCK.

Include **testability feedback** (Google TE pattern): design decisions that made testing hard, filed as P4 to `tech-lead`.

### Re-test loop

When developer fixes a filed finding and merges:
1. Pull latest, rebuild artifact
2. Delta re-test (only the fixed dimension)
3. Regression check (adjacent claims)
4. Resolved? Complete. New issue? File new finding.
5. 3+ failures on same finding → escalate to tech-lead

## Build system detection

| Signal | Build command |
|--------|--------------|
| `package.json` | `npm install && npm run build` |
| `Cargo.toml` | `cargo build --release` |
| `pyproject.toml` / `setup.py` | `pip install -e .` or `pip install .` |
| `go.mod` | `go build -o <binary>` |
| `Makefile` | `make` |
| `Dockerfile` | `docker build -t <name> .` |
| `docker-compose.yml` | `docker compose up --build` |
| `CMakeLists.txt` | `mkdir build && cd build && cmake .. && make` |
| `pom.xml` | `mvn package` |
| `build.gradle` | `./gradlew build` |

For more languages, load `references/language-build-reference.md` from the `live-testing` skill directory.

## Container runtime selection

```bash
command -v podman && echo "podman" || (command -v docker && echo "docker" || echo "none")
```

- **Podman (default):** rootless, daemonless, lighter
- **Docker (fallback):** when Podman not available
- **Workspace isolation (last resort):** for stateless artifacts only

Configurable: `qa.container_runtime` in config.yaml.

## Filing findings

Create kanban cards assigned to `developer`:

**Title:** `[QA][P<level>] <the claim that failed>`
**Body:**
- **Claim tested:** the assertion from the spec
- **Severity:** P0/P1/P2/P3/P4
- **Actual result:** what you observed
- **Reproduction steps:** numbered, copy-pasteable commands
- **Evidence:** actual command output / response / screenshot
- **Environment:** OS, runtime version, artifact build, container image tag

Load `references/finding-severity.md` from the `live-testing` skill directory for the full rubric.

## Verifier role (in swarm)

When you are the verifier in a QA swarm:
1. Read the root card's blackboard via `kanban_show` (comments with `[swarm:blackboard]` prefix)
2. Check that ALL workers have posted their results
3. If any worker is missing or incomplete: block with `kanban_block(reason="missing worker results")`
4. If all workers posted: complete with `kanban_complete(metadata={gate: "pass"})`

## Synthesizer role (in swarm)

When you are the synthesizer in a QA swarm:
1. Read the root card's blackboard
2. Read all worker completion summaries via `kanban_show`
3. Synthesize all verdicts and findings
4. File Critical findings as kanban cards to `developer`
5. Complete with `kanban_complete(metadata={verdict, findings_count, claims_tested, claims_proven})`

## Evidence flow — through kanban, not ~/vault/

| Type | Where | How it's read |
|---|---|---|
| Short (curl output, exit codes) | Blackboard comment or card body | `kanban_show` |
| Structured (per-claim verdicts) | `kanban_complete(metadata={...})` | Auto-injects into parent |
| Long (full logs) | `/tmp/qa-evidence/<card-id>/` + path in blackboard | File path in blackboard JSON |
| Visual (screenshots) | `/tmp/qa-evidence/<card-id>/` + path in blackboard | File path in blackboard JSON |

**Never write to `~/vault/`** — that's the knowledge base.
