# QA Profile — Complete Role Diagnosis

**Source:** `~/.hermes-teams/startup/profiles/qa/` — SOUL.md, config.yaml, and all skills (live-testing v3.1.0, qa-protocol v3.2.0) + their references.
**As of:** 2026-07-31

---

## 1. What QA Does

QA is the **last gate before shipping**. It tests the **assembled, running artifact** to prove it actually works in the real world.

| Does | Does NOT |
|---|---|
| Builds the artifact from source (like a user would) | Reads code |
| Runs it and uses it like a real user | Reviews diffs |
| Breaks it (edge cases, security, degradation) | Fixes bugs |
| Files findings + gives a verdict (PASS/FAIL/BLOCK) | Writes unit tests |

**Stance:** Skeptical empiricist — trusts only what it personally observed by running the thing. Every finding requires evidence (command output, screenshots, reproduction steps). Findings are filed regardless of pass/fail (a PASS with P2 findings still ships, but the findings become follow-up work).

**Boundary with verifier (explicit):**

| | Verifier (pre-merge) | QA (post-merge) |
|---|---|---|
| Operates on | The diff (code-level) | The running artifact (system-level) |
| Core question | "Is this code correct/safe to merge?" | "Does the assembled thing work for a user?" |
| Evidence | Unit tests, lint, mutation testing | Live output, HTTP responses, screenshots |
| Finds | "This function doesn't handle None" | "The signup flow crashes on emoji names" |

---

## 2. Triggers — How QA Gets Work

### Primary trigger: auto-created QA card

A **QA card** is auto-created by the workflow engine when the **verifier/debugger merges to master**. The QA card appears in `ready`, the dispatcher spawns the `qa` profile.

> SOUL.md: "QA card ← workflow engine (auto-created when verifier/debugger merges to master)"

### Skill enforcement (mandatory load)

`config.yaml` → `skill_enforcer.mandatory: [live-testing]` — the `live-testing` skill is **force-loaded** into every QA dispatch. The QA worker cannot start without it.

### Re-test trigger

When a developer fixes a filed finding and merges, the QA card unblocks and QA re-tests (delta re-test + regression check on adjacent claims).

### Re-dispatch after swarm

For medium/large artifacts, the orchestrator creates a swarm via `kanban_chains`, then blocks (status → `todo`). When the synthesizer completes, the card auto-promotes to `ready` and the orchestrator is re-dispatched to read results and file the verdict.

**Key trigger notes:**
- Trigger is NOT a manual "ask QA to test" — it's pipeline-driven (merge → QA card).
- The `qa-protocol` skill is the **orchestrator loop**: receives card → builds → creates ONE swarm → blocks → verdict.
- The `live-testing` skill is the **worker protocol**: the 8-phase test execution spine.

---

## 3. Inputs

QA reads its inputs from the **kanban card** and **parent task handoffs** — never assumes.

| Input | Source | What it contains |
|---|---|---|
| **Card body** | The QA kanban card | What to test, scope, artifact type |
| **PRD/spec** | Linked in card or parent chain | Expected behaviors → translated to testable claims |
| **Parent task handoff** | `kanban_show` parent metadata | What was built, branch, worktree, merge info |
| **Container image tag** | Card 2 (Build) completion metadata | `qa-test:<card-id>` — built once, used by all workers |
| **Blackboard** | Root card comments (`[swarm:blackboard]` JSON) | Shared facts: image_tag, container_port, env_facts, spec_path |
| **Prior findings** | Prior QA card completions (re-test) | What was disproven, to delta re-test |

**Phase 0 (Receive) extracts:**
- What was built (feature/fix/change)
- What it claims to do (spec behaviors)
- Artifact type (CLI, API server, webapp, TUI, mobile, blockchain, daemon, library)
- Scope (one feature, one merged PR, whole artifact)

If the spec is too vague to identify what was built → file a finding (Note: "spec too vague to test") and block.

---

## 4. Outputs

### Verdict (the machine-readable gate)

| Verdict | Condition |
|---|---|
| **PASS** | All claims proven, no Critical findings |
| **FAIL** | Critical findings exist |
| **BLOCK** | Blocked on fixes |

Included in `kanban_complete(summary=...)`.

### Test report (in completion summary)

- Claims tested and proven (with risk levels)
- Journeys completed
- Edge cases covered (by category)
- Non-functional checks run (security depth included)
- Exploratory findings (if any)
- Testability feedback (design decisions that made testing hard)
- What couldn't be tested and why

### Findings (bugs/notes)

Filed as **beads** (`bd create --type=bug`), NOT kanban cards. See §7.

### Evidence

| Type | Destination | Lifecycle |
|---|---|---|
| Short (curl output, exit codes, HTTP status) | Inline in `kanban_complete(summary=...)` or finding card body | Persists with card |
| Long (full logs, wrk output, axe-core reports) | `/tmp/qa-evidence/<card-id>/` | Ephemeral — cleaned when session ends |
| Visual (screenshots) | `task_attachments` on finding card | Persists in kanban DB |
| Structured (per-claim verdicts) | `kanban_complete(metadata={...})` as JSON | Auto-injects into parent context |

**Never write QA evidence to `~/vault/`** — that's the knowledge base.

---

## 5. Handoffs

```
                    ┌─────────────────────────────────────────────┐
                    │  WORKFLOW ENGINE                             │
                    │  (verifier/debugger merges to master)        │
                    └────────────────────┬────────────────────────┘
                                         │ auto-creates QA card
                                         ▼
                              ┌───────────────────┐
                              │   QA (receives)    │
                              └─────────┬─────────┘
                                        │ builds, tests, verdict
                         ┌──────────────┼──────────────┐
                         ▼              ▼              ▼
                   ┌──────────┐  ┌────────────┐  ┌──────────────┐
                   │ debugger │  │ tech-lead  │  │ product-owner│
                   │ (bugs)   │  │ (triage    │  │ (spec issues)│
                   │          │  │  report)   │  │              │
                   └──────────┘  └─────┬──────┘  └──────────────┘
                                       │ kanban_chains → dev+verifier pairs
                                       ▼
                                 ┌──────────┐
                                 │ developer│ → merge → new QA card (re-test)
                                 └──────────┘
```

### Findings routing (by type)

| Finding type | Routes to | Mechanism |
|---|---|---|
| **bug** | `debugger` | Workflow engine auto-routes the bead (`bd create --type=bug`) |
| **non-bug** (technical debt, testability) | `tech-lead` | Bead or triage report |
| **spec ambiguity** | `product-owner` | Bead |
| **Critical** (blocks ship) | Filed as bead + QA card **blocked** (`kanban_block(reason="dependency: N critical findings")`) | Resumes when fixes merged |

### The triage report (synthesizer → tech-lead)

For medium/large artifacts, the **synthesizer** (a QA role in the swarm) deduplicates worker findings by root cause and files **ONE combined triage report** to `tech-lead`:
- All findings grouped by root cause
- Severity-ranked
- Each finding: claim, severity, reproduction steps, evidence

Tech-lead then uses `kanban_chains` to create dev+verifier pairs for fixes. **QA does NOT file findings directly to `developer`** — that bypasses the verifier pipeline.

### PO report

Spec-level findings (ambiguity, missing requirements) route to `product-owner` via beads. The verdict summary (PASS/FAIL) on the QA card completion is readable by anyone via `kanban_show`.

---

## 6. Live-Testing Workflow (the 8-Phase Spine)

Every QA card runs the same 8-phase spine. Execution strategy adapts to artifact size:

| Size | Type | Claims | Execution | Workers |
|---|---|---|---|---|
| **Small** | CLI, library | <10 | Single session, no container | 1 (in-session) |
| **Medium** | API server, daemon | 10–20 | Kanban fan-out + container | 2–3 child cards |
| **Large** | Webapp + API + auth | 20+ | Kanban fan-out + containers | 4 (one per aspect) |

Phases 0–2 and 7 always run in the main session. Phases 3–6 run in-session (small) or in child worker cards (medium/large).

### Phase 0 — Receive
Read card body, PRD/spec, parent handoff. Extract what was built, claims, artifact type, scope.
**Done when:** can state in one sentence what's being tested and what type it is.

### Phase 1 — Plan + Size
1. **Claims checklist** — translate every spec feature into testable pass/fail assertions
2. **Risk ranking** — P0–P4 (risk = likelihood × impact)
3. **User journeys** — 1–3 end-to-end flows per persona
4. **Exploration targets** — 1–2 high-risk areas to probe beyond spec
5. **Non-functional dimensions** — security (always), performance (servers), accessibility (webapps)
6. **Size the artifact** (small/medium/large)

For medium/large: create dynamic test-aspect kanban cards. Complete this card with `kanban_complete(metadata={claims, risk_ranking, aspects, sizing})`.

### Phase 2 — Build, containerize, smoke
1. Detect/generate Containerfile
2. Build image: `<runtime> build -t qa-test:<card-id> .`
3. Verify image starts + health check
4. Complete with `kanban_complete(metadata={image_tag, container_port, build_success})`
5. **Smoke test** — confirm artifact is running and reachable

### Phase 3 — Prove claims (two-pass)
- **Pass 1 (smoke):** happy path only for all claims. Core claim fails → file Critical immediately, skip its edges.
- **Pass 2 (deep):** edge cases on passing claims only. Depth by risk:
  - P0/P1: 10+ edge cases, degradation, concurrent access
  - P2: 5 edge cases, happy path journeys
  - P3/P4: smoke only

Each claim gets a verdict: _proven_, _disproven_, _untested_.

### Phase 4 — Walk user journeys
Execute each journey as a real user. Journey can't complete → _disproven_ even if all component claims passed.

### Phase 5 — Non-functional smoke + security depth
- Security smoke: IDOR, auth bypass, secrets, dep scan
- Security depth: CSRF, XSS, SSRF, open redirect, path traversal, command injection, session fixation
- Performance: response time, 30s load, degradation
- Accessibility (webapps): axe-core, tab-order, contrast

### Phase 6 — Explore beyond the spec
Charter-based exploratory probing. Graceful degradation (kill DB, upstream 500, fill disk). Recovery (crash → restart → state intact).

### Phase 7 — Verdict & report
- **Critical findings:** file beads, `kanban_block(reason="dependency: N critical findings")`
- **Important/Minor/Note only:** file findings, complete card with test report
- **All proven:** complete with full test report + testability feedback

### Re-test loop (when fixes merge)
1. Pull latest, rebuild artifact
2. Delta re-test — re-run only the disproven claim/journey
3. Regression check — re-run happy path of adjacent claims
4. Verdict — fix holds → mark resolved; new issue → file new finding
5. Escalation — same finding survives 3 fix attempts → `kanban_block(reason="escalation: <finding> not resolved after 3 attempts")`

---

## 7. How QA Creates Bugs

### Mechanism: beads, NOT kanban cards

Findings are filed as **beads** via `bd create --type=bug` in the project's beads DB. Beads are durable, git-synced, visible in `bd list`. The **workflow engine auto-routes** them.

```bash
bd create --type=bug --priority=<P-level> --title="<finding title>" \
  --description="<claim tested, actual result, reproduction steps, evidence>"
bd link <bug-id> <epic-id>
```

### Severity rubric (maps to Google P0–P4)

| Severity | Maps to | Meaning |
|---|---|---|
| **Critical** | P0/P1 | Blocks shipping. Core feature broken, data loss, security hole. |
| **Important** | P2 | Should fix before ship. Degraded experience or broken edge case. |
| **Minor** | P3 | Can ship with. Cosmetic or low-impact. |
| **Note** | P4 | Observation, not a bug. UX feedback, spec ambiguity. |

### Filing rules

- **File regardless of pass/fail** — a PASS with P2 findings still ships, but findings become follow-up work.
- **Every disproven claim needs evidence** — actual output, not summary. "It failed" is not a finding. Copy-pasteable reproduction commands are.
- **Link every bug bead to the parent epic** (`bd link <bug-id> <epic-id>`) so defect counts roll up.
- **Include environment** with each finding: OS, runtime version, artifact build, container image tag.

### For medium/large: the triage path (synthesizer)

The synthesizer in the swarm:
1. Reads root card blackboard + all worker completions via `kanban_show`
2. **Deduplicates by root cause** (e.g., 3 workers independently find SSRF → 1 finding)
3. Files **one triage report** to `tech-lead` (single card, all findings grouped, severity-ranked)
4. `kanban_complete(metadata={verdict, findings_count, root_causes, claims_tested, claims_proven})`

Tech-lead triages and creates dev+verifier fix chains via `kanban_chains`. QA does NOT create fix cards or file directly to developer.

### Critical findings → block

If any finding is Critical: file beads, then `kanban_block(reason="dependency: N critical findings filed for fix")`. Card resumes when workflow engine routes bugs to debugger and fixes merge.

---

## 8. JSON Node / Metadata Definitions

QA stamps structured JSON in two places: **`kanban_complete(metadata={...})`** and **blackboard comments**.

### 8.1 Plan metadata (Phase 1 completion — medium/large)

```json
{
  "claims": ["<claim-1>", "<claim-2>", "..."],
  "risk_ranking": [
    {"claim": "<claim-1>", "level": "P0", "depth": "full"},
    {"claim": "<claim-2>", "level": "P2", "depth": "standard"}
  ],
  "aspects": ["functional", "journeys", "security", "exploratory"],
  "sizing": "medium"
}
```

### 8.2 Build metadata (Phase 2 completion)

```json
{
  "image_tag": "qa-test:<card-id>",
  "container_port": 3000,
  "build_success": true
}
```

### 8.3 Worker completion metadata (Phases 3–6, per child card)

```json
{
  "verdicts": [
    {
      "claim_id": "claim-01",
      "claim": "GET / returns 200",
      "verdict": "proven",
      "risk_level": "P1",
      "evidence": "curl -v output: HTTP/1.1 200 OK..."
    },
    {
      "claim_id": "claim-02",
      "claim": "Signup accepts emoji names",
      "verdict": "disproven",
      "risk_level": "P0",
      "evidence": "curl -v output: HTTP/1.1 500 Internal Server Error..."
    }
  ],
  "findings": [
    {
      "claim": "Signup accepts emoji names",
      "severity": "Critical",
      "reproduction": "curl -X POST /api/signup -d '{\"name\":\"🎉\"}'",
      "evidence": "500 error, stack trace in response"
    }
  ]
}
```

### 8.4 Synthesizer completion metadata (verdict + triage)

```json
{
  "verdict": "FAIL",
  "findings_count": 3,
  "root_causes": ["SSRF via /api/test", "rate limit bypass", "results page 404"],
  "claims_tested": 10,
  "claims_proven": 7
}
```

### 8.5 Verifier completion metadata (swarm gate)

```json
{
  "gate": "pass"
}
```

### 8.6 Blackboard comment format (shared worker state)

Workers post structured JSON to the root card as comments:

```
[swarm:blackboard] {"key": "verdicts", "value": {"claim_1": "proven", "claim_2": "disproven", "evidence_claim_2": "curl -v output..."}}
```

The `latest_blackboard(conn, root_id)` function merges all comments (later values replace earlier for same key).

### 8.7 kanban_chains call shape (swarm creation)

```json
{
  "goal": "QA: test <feature>",
  "chains": [
    [{"assignee": "qa", "skill": "qa-functional", "title": "[QA] Functional", "body": "<checklist>"}],
    [{"assignee": "qa", "skill": "qa-security", "title": "[QA] Security", "body": "<checklist>"}]
  ],
  "after": [
    {"assignee": "qa", "title": "[QA] Verifier", "body": "Check all workers posted results"},
    {"assignee": "qa", "skill": "qa-protocol", "title": "[QA] Synthesizer", "body": "Dedup findings, file triage to tech-lead"}
  ],
  "blackboard": {
    "image_tag": "qa-test:<card-id>",
    "container_port": 3000,
    "env_facts": "<facts>",
    "spec_path": "<path>"
  }
}
```

`kanban_chains` handles all linking + blocking internally. Never call `kanban_link` or `kanban_block` manually when using it.

---

## Appendix: config.yaml QA-relevant keys

```yaml
qa:
  container_runtime: podman      # podman (default) | docker | none
  container_memory: 1g           # per-container memory limit
  container_cpus: 1              # per-container CPU limit
  max_parallel_workers: 4        # max child cards dispatched simultaneously
  two_pass: true                 # smoke all claims before deep testing
  risk_based: true               # rank claims by risk before testing
skill_enforcer:
  mandatory: [live-testing]      # force-loaded into every QA dispatch
kanban:
  max_in_progress_per_profile: 3 # concurrent task cap (must match across ALL profiles)
plugins:
  enabled: [kanban_chains, skill_enforcer]
```

**Model:** `glm-5.2` via `zai` provider, 1M context, `reasoning_effort: xhigh`, `api_max_retries: 10`.

## Appendix: skills inventory

| Skill | Version | Role |
|---|---|---|
| `live-testing` | v3.1.0 | **Worker protocol** — 8-phase test execution spine. Mandatory (skill_enforcer). |
| `qa-protocol` | v3.2.0 | **Orchestrator loop** — receives card, creates swarm via `kanban_chains`, blocks, files verdict + triage. |
| `team-delegation` | (coordination) | Craft of delegating through the kanban board. |
| `team-observability` | (coordination) | Observing team state. |

**Disabled skills (57):** All code-authoring, review, planning, and writing skills are disabled — QA does not read code, review diffs, fix bugs, or author specs. Notable disabled: `code-review`, `diagnosing-bugs`, `domain-modeling`, `implement`, `tdd`, `prototype`, `research`, `triage`, `wayfinder`.

## Appendix: swarm topology (medium/large)

```
Root card (blackboard, completed immediately)
  ├── Card 1: Plan (Phase 1)          ─┐
  │                                     │ parallel (no dep on each other)
  ├── Card 2: Build (Phase 2)          ─┘
  │
  ├── Card A: Functional (Phase 3)     ─┐
  ├── Card B: Journeys (Phase 4)        │ all depend on Card 1 AND Card 2
  ├── Card C: Security+NonFunc (Ph 5)   │
  ├── Card D: Exploratory (Phase 6)    ─┘
  │
  └── Card 7: Verdict (Phase 7) — depends on all test cards (A–D)
```

Each child worker starts its own container from the pre-built image on a unique port (18081–18084). Build-once, test-many via containers.
