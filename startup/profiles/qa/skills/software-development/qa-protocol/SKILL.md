---
name: qa-protocol
description: "Use when you receive a QA card or are the verifier/synthesizer in a QA swarm. Creates the swarm via kanban_chains, blocks until the synthesizer verdicts, then files a combined report to tech-lead. The ONLY skill that creates QA swarms and files findings."
version: 3.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, protocol, orchestrator, swarm, verdict, chains]
    related_skills: [qa-build, qa-functional, qa-journeys, qa-security, qa-exploratory, team-delegation]
---

# QA Protocol — the orchestrator loop

The **swarm** is the unit of QA work: you build the artifact, create ONE swarm of test workers via the `kanban_chains` tool, block until the synthesizer returns a **verdict**, then file a **triage** — one deduped report to tech-lead. The verdict is the gate: PASS, FAIL, or BLOCK.

`kanban_chains` handles all linking and blocking internally. Never call `kanban_link` or `kanban_block` manually — the tool does it for you.

## Step 1 — Receive

Read the kanban card body, the linked PRD/spec, and any parent task handoff. Extract what was built, what it claims to do, artifact type, and scope.

**Done when:** you can state in one sentence what you're testing and what artifact type it is.

## Step 2 — Plan + Size

Extract claims from the spec and risk-rank them P0–P4 (risk = likelihood × impact). Then size the artifact:

| Criterion | Small | Medium | Large |
|---|---|---|---|
| Type | CLI, library | API server, daemon | Webapp + API + auth |
| Claims | <10 | 10–20 | 20+ |
| Execution | Single session | Swarm (2–3 workers) | Swarm (3–4 workers + containers) |

**Done when:** claims extracted, risk-ranked, sizing determined.

## Step 3 — Build

Build the real artifact from source. For medium/large stateful artifacts, build a container image. Load the `qa-build` skill for build detection, Containerfile generation, and podman build.

**Done when:** artifact builds and you have positive evidence it's running.

## Step 4 — Create swarm (medium/large only)

Call `kanban_chains` ONCE with chains (parallel workers) + after (verifier + synthesizer). Choose workers based on what the artifact needs:

| Worker | When | Skill |
|---|---|---|
| Functional | ALWAYS | qa-functional |
| Exploratory | ALWAYS | qa-exploratory |
| Journeys | Multi-step user flows | qa-journeys |
| Security | Accepts input or has auth | qa-security |

Write each worker's body with its specific checklist. The tool links the caller to the synthesizer and blocks. Your session ends. You will be auto-promoted when the synthesizer completes.

```
kanban_chains(
    goal="QA: test <feature>",
    chains=[
        [{"assignee": "qa", "skill": "qa-functional", "title": "[QA] Functional", "body": "<checklist>}"],
        [{"assignee": "qa", "skill": "qa-security", "title": "[QA] Security", "body": "<checklist>}"]
    ],
    after=[
        {"assignee": "qa", "title": "[QA] Verifier", "body": "Check all workers posted results"},
        {"assignee": "qa", "skill": "qa-protocol", "title": "[QA] Synthesizer", "body": "Dedup findings, file triage to tech-lead"}
    ],
    blackboard={"image_tag": "<tag>", "container_port": 3000, "env_facts": "<facts>"}
)
```

**When re-dispatched:** check if a synthesizer has already completed for this card via `kanban_show`. If yes, skip to Step 5 — creating a second swarm orphans the first swarm's workers.

**Stale claim lock:** if re-dispatched but the card sits at `ready` for 30+ minutes without being spawned, the dispatcher may be skipping it due to a stale `claim_lock`. Run `hermes kanban --board <board> dispatch --dry-run` — if it shows `Spawned: 0` despite a ready card, clear the lock: `UPDATE tasks SET claim_lock = NULL, claim_expires = NULL WHERE id = '<id>'`. See `references/platform-constraints.md` for full diagnosis.

## Step 5 — Verdict

When re-dispatched after the synthesizer completes, read its completion via `kanban_show`. The synthesizer already deduped findings by root cause and filed one combined triage report to tech-lead.

`kanban_complete` the QA card with the verdict:
- **PASS:** all claims proven, no Critical findings. Include the test report.
- **FAIL:** Critical findings exist. The triage report is already filed to tech-lead. Tech-lead will triage, delegate fixes via `kanban_chains`, and create a new QA card for re-test if needed.

The re-test is a separate QA card — not a continuation of this one. Complete this card; the pipeline handles the rest.

## Verifier role (in swarm)

1. Read the root card's blackboard (comments with `[swarm:blackboard]` prefix)
2. Check that ALL workers posted results
3. Missing? `kanban_block(reason="missing worker results")`
4. All present? `kanban_complete(metadata={gate: "pass"})`

## Synthesizer role (in swarm)

The synthesizer runs the **triage**:

1. Read the root card's blackboard and all worker completions via `kanban_show`
2. **Dedup by root cause:** multiple workers independently find the same issue (e.g., SSRF found by 3 workers). Group as one finding.
3. **File one triage report** to `tech-lead` — a single card with all findings grouped by root cause, severity-ranked. Each finding: claim, severity, reproduction steps, evidence.
4. `kanban_complete(metadata={verdict, findings_count, root_causes, claims_tested, claims_proven})`

Tech-lead reads the triage report and uses `kanban_chains` to create dev+verifier pairs.

**Beads vs kanban:** When planning work, use beads (`bd create` + `bd dep`). Beads are the planning layer; kanban is the execution layer.

## Evidence flow

Short evidence goes inline in the triage report. Long evidence goes to `/tmp/qa-evidence/<card-id>/` with the path referenced in the report. Structured verdicts go in `kanban_complete(metadata={...})`.

`~/vault/` is the knowledge base — QA evidence never goes there.
