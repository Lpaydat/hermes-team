---
name: qa-protocol
description: "Use when you receive a QA card or are the verifier/synthesizer in a QA swarm. Creates the swarm via qa_swarm tool, blocks until the synthesizer verdicts, then files findings. The ONLY skill that creates QA swarms and files findings."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, protocol, orchestrator, swarm, verdict]
    related_skills: [qa-build, qa-functional, qa-journeys, qa-security, qa-exploratory, team-delegation]
---

# QA Protocol — the orchestrator loop

The **swarm** is the unit of QA work: you build the artifact, create a swarm of test workers via the `qa_swarm` tool, block until the synthesizer returns a **verdict**, then file findings or complete. The verdict is the gate: PASS, FAIL, or BLOCK.

## Step 1 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract what was built, what it claims to do, artifact type, and scope.

**Done when:** you can state in one sentence what you're testing and what artifact type it is. If the spec is too vague, file a P4 finding and block.

## Step 2 — Plan + Size

Extract claims from the spec and risk-rank them P0–P4 (risk = likelihood × impact). Then size the artifact:

| Criterion | Small | Medium | Large |
|---|---|---|---|
| Type | CLI, library | API server, daemon | Webapp + API + auth |
| Claims | <10 | 10–20 | 20+ |
| Execution | Single session | Swarm (2–3 workers) | Swarm (3–4 workers + containers) |

**Done when:** claims extracted, risk-ranked, sizing determined. For small: proceed to build and test inline. For medium/large: proceed to build, then create swarm.

## Step 3 — Build

Build the real artifact from source. For medium/large stateful artifacts, build a container image. Load the `qa-build` skill for build detection, Containerfile generation, and podman build.

**Done when:** artifact builds and you have positive evidence it's running. If build fails, file P0 and stop.

## Step 4 — Create swarm (medium/large only)

Call the `qa_swarm` tool with workers chosen based on what the artifact actually needs:

| Worker | When to include | Skill |
|---|---|---|
| Functional | ALWAYS — every artifact has claims to prove | qa-functional |
| Exploratory | ALWAYS — this is QA's irreplaceable value | qa-exploratory |
| Journeys | Multi-step user flows (webapps, API sequences, CLI pipelines) | qa-journeys |
| Security | Anything that accepts input or has auth | qa-security |

Write each worker's body with its specific checklist — the exact claims, journeys, checks, or charters to test. The tool bakes this into the card body, allocates ports, creates topology, and blocks you.

```
qa_swarm(
    goal="QA: test cross-browser-ai MVP — all 10 MUST-scope items",
    artifact_type="webapp",
    image_tag="qa-test:t_5ccbc475",
    container_port=3000,
    env_facts="DEMO_MODE=true — Supabase/Storage/Auth mocked (in-memory), AI heuristic mock, Playwright real",
    spec_path="/home/lpaydat/projects/cross-browser-ai/contract.md",
    workers=[
        {
            "title": "Functional — items 1-4",
            "skill": "qa-functional",
            "body": "Test claims: 1) Landing page (headline, URL input, Test Free CTA, browser badges). 2) Anonymous test flow (enter URL → screenshots → results). 3) Loading state with progress steps. 4) Results page (3 screenshots + AI issues list with severity/element/description)."
        },
        {
            "title": "Journeys — items 5-8",
            "skill": "qa-journeys",
            "body": "Walk journeys: signup → first test → results. Auth (GitHub OAuth + email/password). Free tier (1 anonymous, 3 authenticated). Limit reached → upgrade prompt. Stripe Checkout ($9/mo)."
        },
        {
            "title": "Security + non-functional",
            "skill": "qa-security",
            "body": "Security: CSRF, XSS, SSRF, path traversal, command injection, session fixation, IDOR, auth bypass, secrets, dep scan. Perf: response time, 30s load, concurrency. a11y: keyboard nav, contrast."
        },
        {
            "title": "Exploratory",
            "skill": "qa-exploratory",
            "body": "Charters: file:// and ftp:// URL handling. Rate limit bypass via X-Forwarded-For. Concurrent test requests. Container restart recovery. Error message information leakage."
        }
    ]
)
```

The tool handles: root card creation, worker card creation with tailored bodies + skills + ports, verifier, synthesizer, dependency linking, and blocking. It returns card IDs. Your session ends. You will be auto-promoted when the synthesizer completes.

For small artifacts: skip the swarm, run all test phases inline.

## Step 5 — Verdict

When re-dispatched, read the synthesizer's completion via `kanban_show`:

- **P0/P1 findings:** file findings as kanban cards to `developer`, then `kanban_block(reason="dependency: N critical findings filed for fix")`
- **P2–P4 only:** file findings, complete with test report
- **All claims proven:** complete with verdict: PASS

Include **testability feedback** (Google TE pattern): design decisions that made testing hard, filed as P4 to `tech-lead`.

## Re-test loop

When developer fixes a filed finding and merges:
1. Pull latest, rebuild artifact
2. Delta re-test (only the fixed dimension)
3. Regression check (adjacent claims)
4. Resolved → complete. New issue → file new finding.
5. 3+ failures on same finding → escalate to tech-lead

## Verifier role (in swarm)

When you are the verifier:
1. Read the root card's blackboard (comments with `[swarm:blackboard]` prefix)
2. Check that ALL workers posted results
3. Missing? Block with `kanban_block(reason="missing worker results")`
4. All present? Complete with `kanban_complete(metadata={gate: "pass"})`

## Synthesizer role (in swarm)

When you are the synthesizer:
1. Read the root card's blackboard
2. Read all worker completion summaries via `kanban_show`
3. File Critical findings as kanban cards to `developer`
4. Complete with `kanban_complete(metadata={verdict, findings_count, claims_tested, claims_proven})`

## Filing findings

Create kanban cards assigned to `developer`:

**Title:** `[QA][P<level>] <the claim that failed>`
**Body:** claim tested, severity (P0–P4), actual result, reproduction steps (numbered, copy-pasteable), evidence (actual output), environment (OS, runtime version, artifact build, container image tag).

Load `references/finding-severity.md` from the `live-testing` skill directory for the full rubric.

## Evidence flow

All evidence flows through the kanban system. Short evidence goes inline in blackboard comments or card bodies. Long evidence goes to `/tmp/qa-evidence/<card-id>/` with the path referenced in the blackboard. Structured verdicts go in `kanban_complete(metadata={...})`.

`~/vault/` is the knowledge base — QA evidence never goes there.
