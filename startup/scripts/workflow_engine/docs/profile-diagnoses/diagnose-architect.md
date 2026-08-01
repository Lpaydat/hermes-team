# Architect Profile — Complete Role Diagnosis

> Source: `~/.hermes-teams/startup/profiles/architect/` (SOUL.md, config.yaml,
> README.md, MEMORY.md, USER.md, skills/, meta/) +
> `~/.hermes-teams/shared-skills/{architect-gate,design-consult-rpc}/`.
> Profile dir: `startup/profiles/architect/` (gateway-less — sessions spawn per kanban card).

---

## 1. What the architect does

**One-line identity:** *Gatekeeper and design partner, never builder.*
Owns the decisions that are **expensive to reverse** — boundaries, contracts,
data models, stack, cross-cutting patterns. **Never implements, slices work, or
runs the dev loop.**

The architect operates in **two modes** (v2 redesign, 2026-07-11):

| Mode | When | What it is |
|------|------|-----------|
| **Design partner** (proactive) | New projects — after PO writes the spec, before tickets are cut | PO calls architect with a design card; architect runs the full design phase (research + peer fan-out, convergence loop, ADRs) and hands a design doc back to PO |
| **Gatekeeper** (reactive) | Incremental changes to an *existing* system | Changes go through the **T0–T3 blast-radius triage** ceremony |

### The four actions (only four, nothing else)

| Action | Description |
|--------|-------------|
| **Triage** | Every incoming change gets a tier (T0–T3) + one-line rationale |
| **Decide** | At gates, weigh ≥2 independent alternatives, pick one, record as append-only ADR |
| **Stamp** | Review spec architecture sections before decomposition, so slicing inherits reviewed boundaries |
| **Answer** | Architecture questions (kanban cards/comments) in gate posture: tier, decision, alternatives weighed, ADR reference |

### Core principle

> *Cheap-to-reverse patches ship without me; irreversible decisions do not ship without me.*
> A decision approved without comparing at least one alternative is a decision not made.

### Hard rules (never violated)

- ❌ Never implement — construction belongs to **developer**
- ❌ Never slice work — sequencing belongs to **tech-lead**
- ❌ Never run the dev loop — tracer-bullet execution belongs to **tech-lead**
- ❌ Never change an ADR inside a dev-loop card — an **architecture ticket** is the only path
- ❌ Never skip alternatives — must name what was compared and why the winner won

---

## 2. Triggers

The architect is triggered via **three channels**:

| Channel | Mechanism | Use case |
|---------|----------|----------|
| **Kanban card** (autonomous) | `hermes kanban create --assignee architect` → dispatcher spawns fresh session | Team workflows, design requests |
| **Kanban comment** (blocking Q) | `hermes kanban comment --to startup/architect --topic <slug>` | Blocking architecture question from another profile mid-work |
| **Direct** (interactive) | `hermes -p architect` | Human operator conversation |

### When to route TO the architect (✅)

- Choosing a database, framework, or messaging system
- Changing a public API contract
- Adding a cross-cutting concern (auth, logging, caching)
- New dependency adoption
- Data model / schema design
- Service boundary decomposition
- Any decision touching **security/auth/data-loss/irreversible-state** (auth-guardrail: NEVER low stakes)

### When NOT to route (❌ — T0, developer handles)

- Bug fix in existing code (no interface change)
- Adding a field to an internal struct
- Refactoring within a module (no boundary change)
- Choosing a library version to bump

### Internal trigger: `design-council` skill

The architect's only **mandatory** skill (`skill_enforcer.mandatory: [design-council]`).
Triggered when the architect **owes an irreversible design decision or ADR**, or
when a design-it-twice comparison is called for — any design output that must not
come from one agent's memory alone. Driven by the **`loop_engine`** plugin.

---

## 3. Inputs

### Design-partner mode (new projects)

The **PO** creates a design card whose body is **self-contained** (the architect
can start without reading the grilling transcript):

```yaml
title: "[design] <project> — technical design"
assignee: architect
body:
  ## Spec
  docs/specs/<project>.md          # ← the PRD/spec (required)

  ## Context (from grilling user/VB)
  - <key finding 1>
  - <key finding 2>
  - <constraints discovered>

  ## card topic
  <project-slug>-design            # ← for kanban-comment targeting

  ## Open technical questions (PO couldn't answer)
  - <question 1>

  ## Stakes
  low | standard | high            # ← PO-declared; sets loop_engine phases
```

**Input artifact = the spec (PRD) + context summary + settled decisions + open
questions + stakes tier.**

### Gatekeeper mode (incremental changes)

- A change description (interface? data-model? new dependency? crosses team?
  security surface?) → architect answers **5 mechanical triage questions** → tier.

### Runtime inputs consumed by `design-council`

| Input | Source |
|-------|--------|
| Brief / spec behaviors | The design card body / ADR draft |
| `stakes` | PO-declared on the card (low/standard/high) |
| `council:last_iteration` | Root blackboard (verifier verdict + design_version_ref + gaps) |
| `council:best_so_far` | Root blackboard (highest-scoring design-doc version) |
| `council:po_interview` | Root blackboard (PO's product-ambiguous answers) |
| Research findings | Researcher fan-out cards (`deep-research` / `research-scout` / `docs-verification`) |
| Peer perspectives | Peer-architect fan-out cards (independent — do NOT read siblings) |

---

## 4. Outputs

### Primary output: the ADR (Architecture Decision Record)

**Location:** `docs/adr/<n>-<slug>.md` — **append-only**. History is never rewritten.

**Structure:**
```markdown
# ADR-0XX: [Decision Title]
**Status:** Accepted | Superseded by ADR-0YY | Deprecated
**Date:** YYYY-MM-DD
**Tier:** T1 | T2 | T3

## Context        — why needed (problem, constraints, inputs)
## Decision       — what we chose and why (the winner)
## Alternatives Considered  — ≥2 options, each steelmanned, rejected for a real reason
## Consequences   — positive + negative (with a COST NUMBER) + residual risks
## Citations      — research + perspectives + converge verdict (with defect_traces) + PO interview
## Supersedes     — ADR-0YY (if applicable)
```

### Secondary outputs (by mode)

| Mode | Output |
|------|--------|
| Design partner (T2) | Full **design doc** + **ADR series** (one per decision) + tech-stack decisions + data-model decisions + open questions for PO |
| Gatekeeper T1 | One ADR + async peer look |
| Gatekeeper T2 | Full design doc + independent candidate comparison + **async human approval** (card blocks until `APPROVED`/`REJECTED`) |
| Gatekeeper T3 | Vision → **wayfinder decomposition**; sub-slices re-enter at T1/T2 |
| Brownfield intake | Retro-ADR-000 series (status quo accepted, not endorsed) + known-debt beads filed in the venture tracker |

### Completion metadata (machine-readable)

The architect completes cards with structured metadata:
- `design_doc` / `design_version_ref` — design-doc slug + summary
- `adr` — path to the ADR file
- `dod_verdict` (verifier only) — the DoD artifact: `behaviors[]`, `defect_traces[]`, `dod_met`, `score`, `items`, `gaps`, `evidence`, `recommendation`
- `po_interview` — PO's RPC reply

---

## 5. Handoffs

```
                    ┌─────────────┐
                    │    USER     │
                    └──────┬──────┘
                           │  (grills PO)
                    ┌──────▼──────┐
                    │ PRODUCT-    │  what/why — owns the flow
                    │ OWNER       │  (to-spec → design card → to-tickets)
                    └──────┬──────┘
                           │  design card (spec + context + stakes)
                    ┌──────▼──────┐
                    │  ARCHITECT  │  ← THIS PROFILE (decisions, T0–T3 gate)
                    └──────┬──────┘
              ┌────────────┼─────────────┐
              │            │             │
       ┌──────▼──────┐     │      ┌──────▼──────┐
       │ RESEARCHER  │     │      │  VERIFIER   │  (independent DoD judge)
       │ (scout)     │     │      │  + battery  │
       └─────────────┘     │      └─────────────┘
                           │
                    ┌──────▼──────┐
                    │  TECH-LEAD  │  how/slice — decomposes spec into tickets
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  DEVELOPER  │  build
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  VERIFIER → QA
                    └─────────────┘
```

### Handoff detail

| Direction | Counterparty | Mechanism | Content |
|-----------|-------------|-----------|---------|
| **← receives** | product-owner | Kanban design card | Spec link + context + settled decisions + open Qs + stakes |
| **→ asks** | researcher | `kanban_chains` fan-out (skill: `deep-research` / `docs-verification`) | Focused sub-topic; returns findings + citations to blackboard |
| **→ asks** | architect (peer) | `kanban_chains` fan-out | Independent peer review — do NOT read sibling perspectives |
| **→ asks** | verifier | `loop_engine` verifier phase (skill: `dod-verdict`) | DoD artifact check; returns `dod_verdict` |
| **→ asks** | verifier (battery) | `loop_engine` battery terminal (`dc-val-battery-secrets.md`) | Held-out ground-truth re-grade; both verifier AND battery must pass |
| **→ asks** | product-owner | File-based RPC (`design-consult-rpc` skill) — **unset `HERMES_KANBAN_*`, `hermes -p product-owner --skills design-consult-rpc -z "..."`) | Product-ambiguous trade-off questions; PO answers in `<A>` tags; on timeout `kanban_block(kind="needs_input")` |
| **→ delivers** | product-owner | Card completion metadata | Design doc + ADR series + tech-stack/data-model decisions + open Qs. **PO reads before running `to-tickets`.** |
| **→ stamps** | tech-lead (via PO) | Spec architecture section | Reviewed boundaries so ticket-slicing inherits reviewed decisions |
| **→ escalates** | human | `kanban_block(kind="needs_input")` sticky `hard_cap` card | When the DoD cannot be met within the cap — names exactly what the human owes |
| **→ escalates** | human | T2 gate card (blocks until `APPROVED`/`REJECTED`) | Owner decisions (pricing, brand, go-to-market) |

### Boundary with tech-lead (the key handoff)

| Architect owns | Tech-lead owns |
|---------------|----------------|
| Decisions that **outlive a slice** (boundaries, contracts, data models, stack) | Slice construction (contracts, sequencing, delegation) |
| Tier assignment | Ticket creation from spec |
| ADR authorship | Implementation within ADR constraints |
| Spec architecture-section stamping | Spec decomposition into tracer-bullet tickets |

**Conflicts resolve to the ADR.** If the ADR is wrong, supersede it through an
**architecture ticket** — never argue around it, never change it in a dev-loop card.

---

## 6. JSON node definitions

The architect's behavior is driven by the **`loop_engine`** plugin, which creates
a root blackboard card and drives phase cards. The canonical node shapes (from
`design-council/references/call-templates.md`) below.

### 6.1 The `loop_engine` call envelope (per decision)

```json
{
  "strict_fact_basis": true,
  "goal": "Converged ADR for <DECISION> (standard stakes)",
  "runner": "architect",
  "loop_id": "<root_id from first response, echoed on re-invocation>",
  "no_progress_threshold": 3,
  "phases": [ "<phase-node>...", "<phase-node>..." ]
}
```

### 6.2 Phase node — Low stakes (T1, 2 phases, no verifier)

```json
[
  {
    "execution": {
      "assignee": "architect",
      "title": "Council floor — <DECISION>",
      "body": "Read brief. Fan out kanban_chains [researcher + peer]. Synthesize ONE design-doc version. kanban_complete(metadata={'design_doc':...})."
    }
  },
  {
    "execution": {
      "assignee": "architect",
      "title": "Record ADR — <DECISION>",
      "body": "Write docs/adr/<n>-<slug>.md (Context/Alternatives/Decision/Consequences/Citations). kanban_complete(metadata={'adr':...})."
    }
  }
]
```
*Engine: T1 hard cap (`MAX_PHASE_STEPS=1`) — each phase runs once → `workflow_complete`.
AUTH-GUARDRAIL: NEVER use low for auth/security/data-loss/irreversible-state.*

### 6.3 Phase node — Standard stakes (T2, 3 phases)

```json
[
  {
    "max_iterations": 3,
    "execution": {
      "assignee": "architect",
      "title": "Council converge — <DECISION>",
      "body": "Read council:last_iteration + council:best_so_far from root blackboard. Fan out kanban_chains [researcher(deep-research) + peer]. Synthesize design-doc version. KEEP/DISCARD: revise from best_so_far on regression. kanban_complete(metadata={'design_version_ref':..., 'design_doc':...})."
    },
    "verifier": {
      "assignee": "verifier",
      "skill": "dod-verdict",
      "metric_type": "proxy",
      "battery": {
        "path": "startup/profiles/verifier/secrets/dc-val-battery-secrets.md",
        "runner": "verifier"
      },
      "artifact_required": true,
      "title": "[DoD] Converge — <DECISION>",
      "body": "Embed behaviors[] + defect_traces[] + fabrication guard. Score 6 items pass/fail. Return evidence:[]. kanban_complete(metadata={'dod_verdict':{...}}). CONTRACT: recommendation MUST NOT be 'advance' unless dod_met is true."
    }
  },
  {
    "execution": {
      "assignee": "architect",
      "title": "PO interview — <DECISION>",
      "body": "RE-ENTRANT. Check council:po_interview on blackboard — if present, complete. Else launch PO via file-based RPC (unset HERMES_KANBAN_*, hermes -p product-owner --skills design-consult-rpc). Extract <A> answer. On timeout: kanban_block(kind='needs_input')."
    }
  },
  {
    "max_iterations": 2,
    "execution": {
      "assignee": "architect",
      "title": "Record ADR — <DECISION>",
      "body": "Read council:last_iteration + council:po_interview. Write docs/adr/<n>-<slug>.md citing research + perspectives + verdict (with defect_traces) + PO interview. kanban_complete(metadata={'adr':...})."
    },
    "verifier": {
      "assignee": "verifier",
      "skill": "dod-verdict",
      "metric_type": "ground_truth",
      "title": "[DoD] ADR convention — <DECISION>",
      "body": "ADR-convention DoD ONLY (do NOT re-litigate design). Check adr_on_disk, sections_present, cites_inputs, cites_verdict, cites_po_interview."
    }
  }
]
```

### 6.4 Phase node — High stakes (T2 + 3-judge ensemble, cap 5)

Same 3-phase shape as standard, but `phases[0].max_iterations = 5` and the
converge verifier spawns **3 independent verifier sub-cards**:

```json
{
  "verifier": {
    "assignee": "verifier",
    "skill": "dod-verdict",
    "metric_type": "proxy",
    "battery": {
      "path": "startup/profiles/verifier/secrets/dc-val-battery-secrets.md",
      "runner": "verifier"
    },
    "artifact_required": true,
    "title": "[DoD] Converge ensemble — <DECISION>",
    "body": "Spawn 3 INDEPENDENT verifier sub-cards via kanban_chains (each skills:['dod-verdict'], do NOT read siblings, do NOT fan out). Each extracts behaviors[] + defect_traces[] with fabrication guard. AGGREGATE: defect_traces=UNION (latent_defect by ANY judge is latent); dod_met=AND of three; recommendation=advance only if all advance. kanban_complete(metadata={'dod_verdict':{...aggregated...}})."
  }
}
```

### 6.5 The `dod_verdict` schema (verifier output node)

```json
{
  "behaviors": [
    {"behavior": "<one stated behavior>", "brief_citation": "<exact passage>"}
  ],
  "defect_traces": [
    {
      "behavior": "<matches a behaviors[].behavior>",
      "citation": "<exact source passage — re-verified to exist>",
      "failure_implication": "CITE brief behavior + GAP design leaves + FAILURE consequence/scaling",
      "status": "traced | latent_defect",
      "fabricated": false
    }
  ],
  "dod_met": false,
  "score": 0.0,
  "design_version_ref": "<slug>",
  "items": {
    "defect_coverage": "pass | fail",
    "mechanism_accuracy": "pass | fail",
    "highest_stakes_depth": "pass | fail",
    "alternatives_steelmanned": "pass | fail",
    "failure_modes_explicit": "pass | fail",
    "consequences_complete": "pass | fail"
  },
  "gaps": [
    {
      "item": "defect_coverage | mechanism_accuracy | ...",
      "issue": "<one sentence>",
      "citation": "<exact passage>",
      "failure": "<REQUIRED for defect_coverage: concrete failure-implication>",
      "severity": "critical | important | minor"
    }
  ],
  "evidence": [
    {
      "text": "<material claim>",
      "citations": [{"artifact_type": "adr_doc|file_line|probe_result", "locator": "<...>", "quote?": "<...>"}],
      "material": true
    }
  ],
  "recommendation": "advance | replan | escalate"
}
```

**Verifier logic:** `dod_met=true` only if every `items.*==pass` AND every
`defect_traces[].status==traced` AND no `critical`/`important` gap. Contract:
`recommendation` MUST NOT be `advance` unless `dod_met` is true.

### 6.6 Stakes rubric (sets phases, cap, no-progress threshold, verifier)

| Stakes (PO-declared) | loop_engine phases | Cap (max_iterations) | no_progress_threshold | Verifier |
|---|---|---|---|---|
| **Low** (prototype/internal/throwaway) | `[converge T1, ADR T1]` | 1 | n/a | **none** (T1 spine). Auth-guardrail refuses low for auth/security/data-loss. |
| **Standard** (default) | `[converge cap3, interview T1, ADR cap2]` | 3 | 3 | **single judge** (`verifier`, `dod-verdict` skill) |
| **High** (revenue/safety/brand/hard-to-reverse) | `[converge cap5, interview T1, ADR cap2]` | 5 | 3 | **ensemble of 3** (union `latent_defect`s, `dod_met`=AND) |

---

## Appendix A — Configuration (`config.yaml`)

| Setting | Value | Significance |
|---------|-------|--------------|
| `model.default` | `glm-5.2` (`provider: zai`, 1M context) | — |
| `agent.reasoning_effort` | `xhigh` | High deliberation for design decisions |
| `toolsets` | `hermes-cli`, `kanban` | No code-execution / filesystem-wide toolset — consistent with "never implement" |
| `plugins.enabled` | `kanban_chains`, `loop_engine`, `skill_enforcer` | `loop_engine` drives design-council; `skill_enforcer` forces `design-council` mandatory |
| `skill_enforcer.mandatory` | `design-council` | Always loaded — cannot be disabled |
| `approvals.mode` | `off` (`cron_mode: deny`) | Autonomous; no human approval gate at the profile level (T2 human approval is a *card* block, not a profile setting) |
| `skills.disabled` | ~50 skills (all non-doctrine: implement, tdd, code-review, qa-*, ponytail-*, writing-*, etc.) | Only design-council + curator-administration remain active |

**Active skill set (everything else disabled):**
- `design-council` (mandatory, architecture/) — the convergence loop
- `curator-administration` (meta/) — skill self-management

> Note: README.md references 3 "active design doctrine" skills (`codebase-design`,
> `domain-modeling`, `improve-codebase-architecture`) + 2 gate skills
> (`architecture-gate`, `brownfield-intake`). Per MEMORY.md, the 3 deprecated
> skills (`design-an-interface`, `request-refactor-plan`, `ubiquitous-language`)
> were dropped 2026-07-11. The `architecture-gate` skill lives in
> `shared-skills/` and is **pinned** (v2 update pending — see design-phase.md).

---

## Appendix B — SOUL.md constitution (FROZEN)

The SOUL.md constitution block is **FROZEN** — must never be edited, deleted, or
weakened. Key invariants:
1. May improve *craft* (specialty, skills, own skill prompts). Must NEVER edit
   *conscience/evolution engine* (constitution, approvals/secret settings, `.env`,
   meta-skills `transform`/`hermes-self-evolve`).
2. Snapshot to `.bak` before any self-edit.
3. Identity changes take effect only on the NEXT session.
4. Specialization is a ONE-SHOT bootstrap that disarms itself — no scheduled/idle/unattended self-modification.

---

## Appendix C — Testing evidence

Built + tested by Claude Code across 7 tracer beads (`1y1.1`–`1y1.7`) and 6 live
edge-case drills on isolated boards. Two defects found and fixed (commit `886361b`):

1. **Blocked verdicts can't carry structured metadata** — `hermes kanban block`
   has no `--metadata`. Doctrine corrected: done-completions carry structured
   metadata; blocked verdicts carry parseable summary prefixes.
2. **Conformance no-op token mismatch** — stamped prose `"no docs/adr/"` but
   contract specified `"no-docs-adr"`. Fixed.

**Critical safety edge verified:** T2 human-REJECT does not silently open the gate
(test `test41-t2-reject`). Brownfield intake is **idempotent** (`test43-brownfield-idem`).

---

## Appendix D — Notable architectural facts

- **Gateway-less profile** — sessions spawn per kanban card; no systemd unit.
- **Use qualified form `startup/<profile>`** when sending kanban messages — bare
  names can route to the wrong team under the degraded-identity issue.
- **`kanban_chains` over `delegate_task`** — subagents are fragile (background-only,
  unreliable self-reports, don't survive session boundaries). Board cards are
  durable and observable. (Strong operator preference, recorded in USER.md.)
- **`to-tickets` stays with PO**, not tech-lead — PO has full context.
- **`docs/` is gitignored** — use `startup/docs/` with `git add -f`.
- **Researcher skill names**: `["docs-verification"]` for auth/security (ground-truth
  refs), `["research-scout"]`/`["deep-research"]` general. **No skill `"research"`.**
- **Explicit `assignee` on every card spec is load-bearing** — `runner` falls back
  to `worker`/`default` (no such profile dirs), so omitting `assignee` stalls.
