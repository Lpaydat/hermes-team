---
name: qa-protocol
description: "Use when you receive a QA card or are the verifier/synthesizer in a QA swarm. Creates the swarm via kanban_chains, blocks until the synthesizer verdicts, then files a combined report to tech-lead. The ONLY skill that creates QA swarms and files findings."
version: 3.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, protocol, orchestrator, swarm, verdict, chains]
    related_skills: [qa-build, qa-functional, qa-journeys, qa-security, qa-exploratory, team-delegation]
---

# QA Protocol — the orchestrator loop

The **swarm** is the unit of QA work: you build the artifact, create a swarm of test workers via the `kanban_chains` tool, block until the synthesizer returns a **verdict**, then file a **triage** — one deduped report to tech-lead. The verdict is the gate: PASS, FAIL, or BLOCK.

## Step 1 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract what was built, what it claims to do, artifact type, and scope.

**Done when:** you can state in one sentence what you're testing and what artifact type it is. If the spec is too vague, file a P4 to tech-lead and block.

## Step 2 — Plan + Size

Extract claims from the spec and risk-rank them P0–P4 (risk = likelihood × impact). Then size the artifact:

| Criterion | Small | Medium | Large |
|---|---|---|---|
| Type | CLI, library | API server, daemon | Webapp + API + auth |
| Claims | <10 | 10–20 | 20+ |
| Execution | Single session | Swarm (2–3 workers) | Swarm (3–4 workers + containers) |

**Done when:** claims extracted, risk-ranked, sizing determined. For small: build and test inline. For medium/large: build, then create swarm.

## Step 3 — Build

Build the real artifact from source. For medium/large stateful artifacts, build a container image. Load the `qa-build` skill for build detection, Containerfile generation, and podman build.

**Done when:** artifact builds and you have positive evidence it's running. If build fails, file P0 to tech-lead and stop.

## Step 4 — Create swarm (medium/large only)

Call the `kanban_chains` tool with chains (parallel workers) + after (verifier + synthesizer). Choose workers based on what the artifact needs:

| Worker | When | Skill |
|---|---|---|
| Functional | ALWAYS | qa-functional |
| Exploratory | ALWAYS | qa-exploratory |
| Journeys | Multi-step user flows (webapps, API sequences) | qa-journeys |
| Security | Accepts input or has auth | qa-security |

Write each worker's body with its specific checklist — the exact claims, journeys, checks, or charters to test. The tool allocates ports and blocks you on the synthesizer.

For small artifacts: skip the swarm, run all test phases inline.

## Step 5 — Triage

When re-dispatched, read the synthesizer's completion via `kanban_show`. The synthesizer already ran the triage — it deduped findings by root cause and filed one combined report to tech-lead.

- **Verdict FAIL (Critical findings exist):** the report is already filed. Block on the tech-lead's triage card.
- **Verdict PASS:** complete the QA card with the test report.

Include **testability feedback** (Google TE pattern): design decisions that made testing hard, filed as P4 in the triage report.

## Re-test loop

When tech-lead delegates fixes and they merge through the dev→verifier pipeline:
1. Pull latest, rebuild artifact
2. Delta re-test (only the fixed dimension)
3. Regression check (adjacent claims)
4. Resolved → complete. New issue → file new triage to tech-lead.
5. 3+ failures on same finding → escalate to tech-lead

## Verifier role (in swarm)

1. Read the root card's blackboard (comments with `[swarm:blackboard]` prefix)
2. Check that ALL workers posted results
3. Missing? `kanban_block(reason="missing worker results")`
4. All present? `kanban_complete(metadata={gate: "pass"})`

## Synthesizer role (in swarm)

The synthesizer runs the triage — the most important step for finding quality:

1. Read the root card's blackboard and all worker completions via `kanban_show`
2. **Dedup by root cause:** multiple workers will independently find the same issue (e.g., SSRF found by functional + security + exploratory). Group these as one finding, noting which workers confirmed it.
3. **File one triage report** to `tech-lead` — a single kanban card with all findings grouped by root cause, severity-ranked:
   ```
   [QA][VERDICT] <PASS|FAIL|BLOCK> — N unique findings
   P1: SSRF — /api/test passes arbitrary URLs (confirmed by 3 workers)
   P1: Rate limiting — XFF spoof + TOCTOU race (confirmed by 2 workers)
   ```
   Each finding includes: claim tested, severity, actual result, reproduction steps (copy-pasteable), evidence, environment.
4. `kanban_complete(metadata={verdict, findings_count: N, root_causes: N, claims_tested, claims_proven})`

Tech-lead reads the triage report, decides priority, and uses `kanban_chains` to create dev+verifier pairs. Every fix goes through adversarial review — filing directly to `developer` bypasses the verifier.

**Beads vs kanban:** When planning work (breaking a spec into tickets with dependencies), use beads (`bd create` + `bd dep`), not `kanban_create`. Beads are the planning layer; kanban is the execution layer. The beads-watchdog bridges automatically when a bead becomes ready.

## Evidence flow

Short evidence goes inline in the triage report. Long evidence goes to `/tmp/qa-evidence/<card-id>/` with the path referenced in the report. Structured verdicts go in `kanban_complete(metadata={...})`.

`~/vault/` is the knowledge base — QA evidence never goes there.
