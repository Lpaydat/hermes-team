# Debugger Profile — Complete Role Diagnosis

> **Source files read:** `~/.hermes-teams/startup/profiles/debugger/` — `SOUL.md`, `config.yaml`, `profile.yaml`, `README.md`, `memories/MEMORY.md`, `skills/software-development/debug-loop/SKILL.md` (full, 524 lines), `scripts/drive_loop.py`.

---

## 1. What the Debugger Does

The **debugger** is a **diagnosis-team orchestrator** — the third orchestrator profile in the Hermes team (alongside `architect` → design, `verifier` → review). The debugger owns **diagnosis**.

### Core identity (from SOUL.md + profile.yaml)

> "You are a **diagnosis-team orchestrator**. You own the root cause. Defects reach you via qa triage or tech-lead ESCALATE. You drive them through a converge loop — reproduce → fix → falsify → converge — until the root cause is proven and the fix is validated. You are a pure orchestrator: you never write product code."

### The five stances (SOUL.md)

| Stance | Meaning |
|---|---|
| **Falsify-first** | "Break it another way" — falsification is an *independent verifier card*, never the debugger grading its own hypothesis. |
| **Never write product code** | Fixes ship via dispatched `developer` cards — even one-line fixes. |
| **Always write the post-mortem** | A fix without an RCA is a symptom-fix by default. |
| **Take exit B for architectural root causes** | No correct test seam → RCA + ADR stub → architect gate, not a quick patch. |
| **Use the board, not subagents** | Board cards are durable; subagents are fragile. |

### What it does NOT do
- Does **not** write product code (pure orchestrator).
- Does **not** self-grade fixes (falsification is always an independent verifier card).
- Does **not** merge bug branches to main (hands off to verifier for review+merge).
- Does **not** do feature work, design decisions, or platform decomposition.

---

## 2. Triggers — How the Debugger Receives Bugs

The debugger is a **reactive** profile — it activates when a defect card enters its queue. Three trigger sources:

### Trigger sources (SOUL.md Handoffs + debug-loop SKILL.md)

| Source | Mechanism | Condition |
|---|---|---|
| **QA** (triage) | A bug card emitted by QA profiles (`qa-functional`, `qa-exploratory`, `live-testing`) → lands in debugger's queue | QA finds a reproduced bug. QA itself has `diagnosing-bugs` **disabled** — it stops at "reproduced, here's the bug." |
| **Verifier** (FAIL) | A verifier card that FAILs a developer card → routes to debugger | **Only ambiguous FAILs** route to debugger. The verifier stamps the FAIL card with a `diagnosis-needed` flag (set when the defect's cause isn't obvious from the finding). Clear, localized defects route straight to `developer`. |
| **Tech-lead** (ESCALATE) | A tech-lead card with ESCALATE status | Complex defects the tech-lead can't resolve inline. |
| **Human** | Direct operator request | "Asked to diagnose / root-cause a bug." |

### When NOT to use the debugger (debug-loop SKILL.md "When to use")

- Clear, localized one-line defects with an obvious cause → route straight to `developer` (the verifier's `diagnosis-needed` flag routes only ambiguous FAILs to debugger).
- Feature work → `tech-lead`/`architect`.
- Design decisions → `architect`.

---

## 3. Inputs

### The defect card — input seam (README.md §7, debug-loop SKILL.md §7)

The debugger reads a **defect card** carrying this structured payload:

```json
{
  "symptom": "...",
  "repro_attempt": "...|none",
  "env": "...",
  "stakes": "low|high",
  "originator": "<profile/card-id>"
}
```

| Field | Purpose | Routing effect |
|---|---|---|
| `symptom` | What's broken | The root blackboard seed; the thing to reproduce |
| `repro_attempt` | What the originator already tried | Seeds phase-0 execution body; "none" → researcher archaeology |
| `env` | Environment context (python version, venv path, package manager) | Threaded into worker card bodies |
| `stakes` | `low` \| `high` | **Selects the tier:** floor (1 hypothesis) vs high-stakes (parallel hypothesis diverge) |
| `originator` | Who reported it (profile/card-id) | Determines the handoff back (qa re-verify / originator) |

### Round-0 preparation (debug-loop SKILL.md)

Before calling `loop_engine`, the debugger:
1. Reads the doctrine (6-phase diagnosing-bugs + 4 debug-mantras + post-mortem structure).
2. **Carves a worktree + branch**: `debug/<bug-id>-<slug>` (git worktree on a dedicated branch).
3. Reads the defect card fields (above).
4. **Seeds the breadcrumb ledger** on the root blackboard: symptom, repro_attempt, env, stakes, originator, branch_name, worktree_path.

> **Note:** The engine's `discover` phase (v2, engine-default) absorbs much of this grounding automatically.

---

## 4. Outputs

### Completion-contract metadata (README.md §7, debug-loop SKILL.md §7)

On workflow complete, the debugger calls `kanban_complete` with this structured metadata — the board seam downstream cards inherit:

```json
{
  "verdict": "fixed | escalated-design | blocked-hitl",
  "bug_id": "<bug-id>",
  "branch_name": "debug/<bug-id>-<slug>",
  "worktree_path": "<path>",
  "regression_test": "<test path or 'no-seam: documented in RCA'>",
  "postmortem_path": "docs/postmortems/<bug-id>-<slug>.md",
  "root_cause_summary": "<one line>",
  "gate_bead": "<architect gate bead, if verdict=escalated-design>"
}
```

### Three possible verdicts (outputs)

| Verdict | Meaning | Route |
|---|---|---|
| **`fixed`** | Localized bug → proven minimal fix + regression test + RCA | → qa re-verify / originator |
| **`escalated-design`** | Root cause is architectural (no correct test seam / spans a boundary) → RCA + ADR stub | → architect gate |
| **`blocked-hitl`** | No repro possible (missing env/logs/access) | → stays blocked for the human (no `done` completion) |

### Concrete artifacts produced

1. **Fixed code** — on the `debug/<bug-id>-<slug>` branch (shipped via developer cards, never by the debugger).
2. **Regression test** — written before the fix, at a correct seam (or `no-seam: documented in RCA`).
3. **Post-mortem (RCA)** — at `docs/postmortems/<bug-id>-<slug>.md`.
4. **ADR stub** (exit B only) — at `docs/adr/<bug-id>-<slug>.md`.
5. **Breadcrumb ledger** — on the root card blackboard (repro, ranked hypotheses, falsify verdicts).

### Merge gate (NOT done by debugger — debug-loop SKILL.md hard rules)

> "NEVER merge the bug branch to main — it lands on `debug/<bug-id>-<slug>`. Instead, create a verifier card (`assignee: verifier`) with the bug branch reference, what was fixed, and how to verify the merge. The verifier reviews, merges to main, and the workflow engine auto-creates a QA re-test card."

---

## 5. Handoffs

### Handoff map (SOUL.md Handoffs)

```
              ┌─────────────────────────────────────────────────┐
              │                  DEBUGGER                        │
              │          (diagnosis orchestrator)                │
              └─────────────────────────────────────────────────┘
                    ▲         │         │         │
     Defects in      │         │         │         │
     ┌───────────────┘         │         │         │
     │                         │         │         │
  ┌──┴──────┐         ┌────────┘  ┌──────┘  ┌──────┴────────────┐
  │  qa /   │         │           │         │                   │
  │ tech-   │    ┌────▼────┐ ┌────▼─────┐ ┌▼────────┐  ┌─────────┐
  │ lead    │    │developer│ │ verifier │ │ verifier│  │architect │
  │ ESCALATE│    │ (fixes) │ │(falsify) │ │(merge)  │ │  (gate)  │
  └─────────┘    └─────────┘ └──────────┘ └─────────┘  └─────────┘
                       │           │              │
                       │      re-verify      QA re-test
                       │      (verdict)     (auto-created)
                  bug branch
                  debug/<id>
```

### Detailed handoffs

| Handoff | Direction | Mechanism | What's transferred |
|---|---|---|---|
| **Defects** | qa/tech-lead → debugger | Defect card lands in queue | symptom, repro_attempt, env, stakes, originator |
| **Fixes** | debugger → developer | Dispatched card on the bug branch (`debug/<bug-id>-<slug>`) | Ranked hypothesis + falsifiable prediction, repro from ledger #0, branch/worktree, instruction to write regression test before fix |
| **Falsification** | debugger → verifier | Dispatched independent card | The fix + instruction to "break it another way" (exercise adjacent inputs/configs/paths the fix did not target) |
| **Review + merge** | debugger → verifier | Debugger creates a verifier card | Bug branch reference, what was fixed, how to verify the merge → verifier reviews, merges to main, workflow engine auto-creates QA re-test card |
| **Design flaw** | debugger → architect | Architect gate card (blocked + routed) | RCA + ADR stub (the gate's T2/T3 path) |
| **Re-verify** | debugger → qa/originator | Completion-contract `verdict=fixed` | The fix is shipped; qa re-verifies the running artifact |
| **HITL** | debugger → human | Sticky blocked card (`needs_input`) | Exactly what's needed (env access / prod logs / repro steps) — never self-completed |

---

## 6. The Debug-Loop Workflow

### High-level loop (README.md §5)

```
DEFECT CARD → debugger queue   (from: qa bug report | verifier FAIL | human)
   │  debugger reads the doctrine + the bug → carves the bug's worktree+branch
   ▼  → translates doctrine into a PER-BUG FIXING PLAN   ← the "dynamic" part
┌──────────────────────────────────────────────────────────────┐
│ PHASE 0 — REPRODUCE + MINIMISE                                │
│   dispatch → researcher (archaeology) OR developer (failing  │
│               test); minimise to smallest red scenario        │
│   GATE: a tight RED signal on the blackboard (ledger #0)      │
│   no repro possible → HITL BLOCKED CARD (not kanban)          │
└──────────────────────┬───────────────────────────────────────┘
   debugger promoted ─── reads results, RE-PLANS (adapt-between-dispatches)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 1 — HYPOTHESISE + FIX + FALSIFY  (the converge loop)    │
│   FLOOR:      1 hypothesis+fix card → developer               │
│   HIGH-STAKES: N parallel hypothesis cards → developer swarm  │
│   then ALWAYS: FALSIFY card(s) → verifier                     │
│   debugger synthesizes: keep survivor / discard symptom-fix / │
│                          loop again                           │
└──────────────────┬─────────────────────────┬──────────────────┘
                   │                         │
         no correct seam /                 round converged
         root cause spans                 (root cause proven +
         a boundary                        fix validated)
                   │                         │
                   ▼                         ▼
┌──────────────────────┐      ┌─────────────────────────────────┐
│ ESCALATE — exit B    │      │ PHASE 2 — CONVERGE (debugger)   │
│  write RCA + ADR stub│      │  write post-mortem (RCA) doc →  │
│  → architect gate    │      │    docs/postmortems/<id>-<slug> │
│  (block + route)     │      │  fix shipped on bug branch      │
└──────────────────────┘      │  regression test locked         │
                              └───────────────┬─────────────────┘
                                              ▼
                          completion-contract seam → qa re-verify / originator

  PLATEAU: N consecutive rounds fail to converge → escalate to human
           (can't crack) OR take exit B (likely a design flaw)
```

### The three loop_engine phases (debug-loop SKILL.md)

The doctrine's 4 conceptual stages map onto **3 loop_engine phases**, because **falsification is the verifier of the fix phase** (a failed falsify must replan a new hypothesis, requiring hypothesise+fix and falsify to share one converge-loop).

| §5 stage | loop_engine phase | Execution (worker) | Verifier (DoD-checker) | Max iterations |
|---|---|---|---|---|
| **Reproduce + minimise** | **Phase 0** | `researcher` (archaeology) or `developer` (failing test) | `verifier` — "tight RED achieved" | 3 |
| **Hypothesise + fix** + **Falsify** | **Phase 1** (the converge loop) | `developer` (fix + regression test, skill: `developer-loop`) | `verifier` — falsifies + code-quality review | 5 |
| **Converge / post-mortem** | **Phase 2** | `debugger` (writes RCA from the ledger) | `verifier` — "RCA has all 4 inputs + completion contract" | 2 |

### Phase detail

#### Phase 0 — Reproduce + minimise
- **Execution assignee:** `researcher` (env/log archaeology) or `developer` (failing-test harness) — decided at plan-time.
- **DoD intent:** the tightest RED signal — a reliable, minimised repro (runnable test or exact steps), every remaining element load-bearing.
- **Verifier DoD:** a reliable, minimal repro that goes RED on this bug and GREEN when fixed; minimised to the smallest scenario; recorded on the blackboard as ledger #0.
- **No-repro path:** verifier sets `recommendation: escalate` → `loop_engine` sticky-blocks the debugger card (`needs_input`) — that IS the HITL blocked card. The debugger tags the bead `human`, mints `bead-human-<bug-id>`, leaves it blocked.

#### Phase 1 — Hypothesise + fix + falsify (the converge loop)
- **Execution assignee:** `developer` (the only code-shipping profile), skill `developer-loop` force-loaded.
- **Body carries:** ranked hypothesis + falsifiable prediction, repro from ledger #0, branch/worktree, instruction to write regression test before fix.
- **Verifier DoD (five gates):**
  1. The repro now goes GREEN.
  2. A regression test exists at a **correct seam** (not a symptom-seam).
  3. The full suite is green with no new regression.
  4. **Falsify**: try to break it another way — exercise adjacent inputs/configs/paths the fix did not target. Root cause is proven.
  5. **Code-quality review**: clean/idiomatic, fix-logic correct, alternatives considered, no new debt.
- **On replan (`dod_met=false`):** `loop_engine` mints a fresh developer card (next ranked hypothesis) + fresh verifier card; debugger re-injects the breadcrumb ledger so the developer doesn't retry a dead hypothesis.
- **High-stakes tier:** if `stakes=high`, dispatch N parallel hypothesis cards (each its own `hypo-N` worktree); survivor's branch becomes the fix branch; discarded branches cleaned up.
- **Exit B signal:** if `no-correct-seam` or `root-cause-spans-boundary` → verifier sets `recommendation=escalate` → exit B (design flaw).

#### Phase 2 — Converge / post-mortem (RCA)
- **Execution assignee:** `debugger` (you — inherits `runner=debugger`; picks up own converge card in fresh worker context).
- **DoD intent:** write the RCA at `docs/postmortems/<bug-id>-<slug>.md` following the 9arm structure.
- **Verifier DoD:** all four mandatory inputs present (reliable repro + known root cause + identified fix + validated fix); code-identifiers cited and re-openable; completion-contract metadata present.
- **DoD-met on phase 2 → workflow complete.** Debugger calls `kanban_complete` with the completion-contract metadata.

### The bifurcation — exit B (design flaw)

**Trigger:** root cause has no correct test seam (Matt Pocock Phase 5) OR verifier's falsify probe keeps finding the cause spans a boundary/cross-cutting concern.

**When exit B fires:**
1. Do not quick-patch. Write the RCA + an ADR stub at `docs/adr/<bug-id>-<slug>.md`.
2. Route to the architect gate: create an architect gate card carrying the RCA + ADR stub, block+route it.
3. Completion-contract `verdict` = `escalated-design`.

### Three refinements (mechanics)

1. **HITL = a blocked card, not a blocking call** — sticky `needs_input` block; tag bead `human`; mint `bead-human-<bug-id>`; leave blocked; auto-resume on promotion.
2. **Worktree + branch per bug** — `debug/<bug-id>-<slug>`; high-stakes: `debug/<bug-id>-<slug>/hypo-N` per parallel hypothesis.
3. **Post-mortem at converge** — `docs/postmortems/<bug-id>-<slug>.md`; 9arm structure; refuses to draft without all four inputs.

### Plateau / layered exits (deterministic — plugin code, not model-enforced)

- **Hard cap per phase** (3/5/2): phase exhausts its cap without DoD → sticky HITL block.
- **No-progress:** identical verifier verdicts across consecutive iterations → sticky HITL block.
- **After N consecutive non-converging rounds** (start N=3): escalate to human (can't crack) or take exit B.

### The loop_engine contract (v2 fact-discipline layer)

The debugger is the **first consumer** of the loop-engineering plugin. It opts into the hard fact-discipline cutover by passing `strict_fact_basis=True` (workflow-wide). This makes:

- **`metric_type`** (per verifier spec) HARD-REQUIRED — validated at `_validate_metric_type`; a verifier without it is a validation error. All three debug-loop phases declare `ground_truth` (mechanical test pass/fail or structural/citation check).
- **`evidence`** (per `dod_verdict`) HARD-REQUIRED — every material claim cited (`file_line` / `test_output` / `commit_sha` / `probe_result`) and re-opened by the verifier. Un-cited material forces `dod_met=false` → replan.
- **`loop_id`** (recommended) — the durable identity is the `root_id` (root card id), not the goal hash. Captured from the first response, echoed back on every re-invocation.

### Canonical loop_engine call template

```python
loop_engine(
    strict_fact_basis=True,  # REQUIRED — first kwarg, hard-cutover opt-in
    goal="<defect: symptom + repro_attempt + env + stakes + originator + bug-id + branch/worktree — BYTE-IDENTICAL across every call for one bug>",
    runner="debugger",
    loop_id="<root_id from the first response — echo it back on every re-invocation>",
    phases=[phase_0, phase_1, phase_2],
)
```

---

## 7. JSON Node Definitions

### Phase node structure (each phase in the `phases` array)

```json
{
  "title": "<phase title>",
  "max_iterations": <int>,
  "execution": {
    "assignee": "<researcher | developer | debugger>",
    "title": "<execution card title>",
    "body": "<the worker instruction — what to do, the workspace, the hypothesis/repro, branch/worktree>",
    "skill": "<optional — e.g. 'developer-loop' for phase 1>"
  },
  "verifier": {
    "assignee": "verifier",
    "title": "<verifier card title>",
    "metric_type": "ground_truth",
    "body": "<the DoD — the definition-of-done checked by the independent verifier>"
  }
}
```

### The three phase definitions (canonical, from debug-loop SKILL.md)

#### Phase 0 — Reproduce + minimise

```json
{
  "title": "Reproduce + minimise <bug> (tight RED)",
  "max_iterations": 3,
  "execution": {
    "assignee": "researcher | developer",
    "title": "Build the tight RED repro for <bug>",
    "body": "<seeded with defect's repro_attempt, env, branch/worktree>"
  },
  "verifier": {
    "assignee": "verifier",
    "title": "Verify tight RED achieved for <bug>",
    "metric_type": "ground_truth",
    "body": "A reliable, minimal repro exists that goes RED on this bug and GREEN when fixed. Minimised to smallest scenario. Recorded on blackboard (ledger #0). If no repro possible → recommendation=escalate with gaps naming what's needed."
  }
}
```

#### Phase 1 — Hypothesise + fix + falsify (the converge loop)

```json
{
  "title": "Fix <bug> + falsify",
  "max_iterations": 5,
  "execution": {
    "assignee": "developer",
    "skill": "developer-loop",
    "title": "Ship minimal fix for <bug> + regression test",
    "body": "<ranked hypothesis + falsifiable prediction, repro from ledger #0, branch/worktree, instruction to write regression test before fix>"
  },
  "verifier": {
    "assignee": "verifier",
    "title": "Falsify + code-review the <bug> fix",
    "metric_type": "ground_truth",
    "body": "(1) Repro GREEN. (2) Regression test at correct seam. (3) Full suite green, no regression. (4) Falsify — break it another way. (5) Code-quality review (style, fix-logic, alternatives, no debt). dod_met=true/advance if all five; replan with cited gaps if symptom-fix/green-fail/quality-gap; escalate with 'no-correct-seam' or 'root-cause-spans-boundary' if design-flaw."
  }
}
```

#### Phase 2 — Converge / post-mortem (RCA)

```json
{
  "title": "Write the RCA / post-mortem for <bug-id>",
  "max_iterations": 2,
  "execution": {
    "assignee": "debugger",
    "title": "Author the post-mortem (RCA) at docs/postmortems/",
    "body": "<write RCA at docs/postmortems/<bug-id>-<slug>.md, 9arm structure, all four mandatory inputs, code-identifiers first-class>"
  },
  "verifier": {
    "assignee": "verifier",
    "title": "Verify the RCA has all four mandatory inputs + code-identifiers",
    "metric_type": "ground_truth",
    "body": "Post-mortem contains all four mandatory inputs (reliable repro + known root cause + identified fix + validated fix). Cites code-identifiers (function names, file paths, commit SHAs). Completion-contract metadata present. dod_met=true/advance if so; replan naming missing input otherwise."
  }
}
```

### The dod_verdict structure (verifier output, returned in `run.metadata`)

```json
{
  "dod_met": true | false,
  "recommendation": "advance | replan | escalate",
  "evidence": [
    {
      "claim": "<material claim>",
      "citations": [
        {
          "artifact_type": "file_line | test_output | commit_sha | probe_result",
          "locator": "<path:line | test name | sha | probe id>",
          "quote": "<what was found when re-opened>"
        }
      ]
    }
  ],
  "gaps": ["<named gap if replan/escalate>"]
}
```

### The full loop_engine call (assembling all nodes)

```json
{
  "strict_fact_basis": true,
  "goal": "<defect payload — byte-identical across calls for one bug>",
  "runner": "debugger",
  "loop_id": "<root_id from first response>",
  "phases": [
    {
      "title": "Reproduce + minimise (tight RED)",
      "max_iterations": 3,
      "execution": {"assignee": "researcher|developer", "title": "...", "body": "..."},
      "verifier": {"assignee": "verifier", "title": "...", "metric_type": "ground_truth", "body": "..."}
    },
    {
      "title": "Hypothesise + fix + falsify",
      "max_iterations": 5,
      "execution": {"assignee": "developer", "skill": "developer-loop", "title": "...", "body": "..."},
      "verifier": {"assignee": "verifier", "title": "...", "metric_type": "ground_truth", "body": "..."}
    },
    {
      "title": "Converge / post-mortem (RCA)",
      "max_iterations": 2,
      "execution": {"assignee": "debugger", "title": "...", "body": "..."},
      "verifier": {"assignee": "verifier", "title": "...", "metric_type": "ground_truth", "body": "..."}
    }
  ]
}
```

### Worked example — concrete phase bodies (from `scripts/drive_loop.py`)

The debugger profile ships a **worked re-invocation example** at `scripts/drive_loop.py` for bug `livetest-pipeline-g70` (ragged-row handling asymmetry). It demonstrates the full 3-phase plan with concrete execution + verifier bodies for a real localized bug, showing:
- Phase 0: researcher builds the RED repro test (`test_c14_ragged_row_short_fields_clean_error`).
- Phase 1: developer ships the sentinel-based fix (`_MISSING = object()` for `restval`), verifier runs 5 gates including 4 falsification probes.
- Phase 2: debugger authors the RCA at `docs/postmortems/livetest-pipeline-g70-ragged-short-row.md`.

---

## Appendix — Config Summary (config.yaml)

| Setting | Value | Rationale |
|---|---|---|
| `model.default` | `glm-5.2` | |
| `model.provider` | `zai` | |
| `model.context_length` | `1000000` | |
| `agent.reasoning_effort` | `xhigh` | Debugging is reasoning-heavy |
| `toolsets` | `hermes-cli`, `kanban`, `kanban_chains`, `loop_engine` | `loop_engine` REQUIRED — debugger is its first consumer |
| `plugins.enabled` | `kanban_chains`, `loop_engine`, `skill_enforcer` | |
| `skill_enforcer.mandatory` | `debug-loop` | The only mandatory skill |
| `skills.disabled` | (78 skills disabled — see config.yaml) | Pure orchestrator; only `debug-loop` + base meta enabled |
| `approvals.mode` | `off` | Autonomous orchestrator |
| `kanban.max_in_progress_per_profile` | `3` | Orchestrator parks on chains → low active concurrency |

### Enabled skills (everything NOT disabled)
- **`debug-loop`** (authored, mandatory) — the orchestration loop. Embeds the 9arm essentials (4 mantras + post-mortem structure) + the Matt Pocock 6-phase spine.
- Base meta (frozen): `transform`, `bundled-skills-opt-out`, `report-to-base`.

### Memory note (memories/MEMORY.md)
The debugger's memory records two operational gotchas for the interactive-CLI loop_engine re-invocation:
1. **Phase-0 re-run risk:** if `loop_state` shows `phase_index` not advancing after a verified-PASS terminal, STOP re-invoking `loop_engine` and dispatch the next phase's execution+verifier cards directly via `kanban_create` (poll terminal via sqlite).
2. **Park-failure is cosmetic:** cards/topology are created correctly; poll terminal card status, re-invoke with `loop_id=root_id` when done. Never set `HERMES_KANBAN_RUN_ID` to a stale value.
