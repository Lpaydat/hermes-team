# Hermes Startup Team — Architecture

> How 12 specialized agent profiles coordinate to take a project from idea to shipped artifact.

## Profiles

| Profile | Role | One-liner |
|---------|------|-----------|
| **product-owner** | Front door | Single entry point. Routes work, files issues, contracts the user for decisions. |
| **builder** | Prototyper | Takes raw ideas, grills them, builds prototypes, presents for promotion. |
| **architect** | Design partner + gatekeeper | Owns irreversible decisions. Runs design-council, produces ADRs. |
| **tech-lead** | Construction orchestrator | Designs coding loops, delegates to developer + verifier via kanban_delegate. |
| **developer** | Harness wrapper | Thin governance around vendor coding harnesses (Claude Code, Codex). Generates code. |
| **verifier** | Adversarial evaluator + merge-owner | Reviews output (not reasoning), fans out probes, owns the merge gate. Zero-findings = PASS. |
| **debugger** | Diagnosis orchestrator | Reproduce → hypothesize → falsify → converge. Dispatches fixes, never writes code. |
| **qa** | Last gate before shipping | Tests the assembled, running artifact. Builds it, runs it, breaks it. No code reading. |
| **researcher** | Deep knowledge engineer | Depth-first research, Obsidian wiki curation, cited synthesis. |
| **scout** | Fast trend scanner | Breadth-first AI frontier scanning, daily digest, files deep-research tasks. |
| **ops** | Platform engineer | Owns the dev environment — tools, configs, infrastructure. |
| **advisor** | Strategic sparring partner | YC-level startup advisor. Pressure-tests strategy, fundraising, GTM. |

## The Three Orchestrators

Three profiles can initiate work chains via `kanban_chains` or `loop_engine`:

- **Architect** — design fan-out (researcher + peer perspectives → ADR)
- **Tech-lead** — construction fan-out (developer + verifier → merged feature)
- **Debugger** — diagnosis fan-out (developer fix + verifier falsify → proven fix)

The rest are workers or single-session agents.

---

## The Full Production Pipeline

```mermaid
flowchart TD
    %% ── Planning Phase ──
    User([User])
    PO[Product Owner]
    Grill[Grill<br/>adversarial interview]
    Spec[Spec<br/>to-spec synthesis]
    Arch[Architect<br/>design-council → ADRs]
    Tickets[to-tickets<br/>tracer-bullet slices]
    Approval{{User approval gate}}

    User -->|"idea / promote / feature request"| PO
    PO --> Grill
    Grill --> Spec
    Spec --> Arch
    Arch -->|"design doc + ADRs"| Tickets
    Tickets --> Approval
    Approval -->|"approved"| Beads[(Beads DB)]

    %% ── Dispatch Phase ──
    Engine[Workflow Engine<br/>cron * * * * *]
    Dispatch[dev-dispatch<br/>PO creates tech-lead cards]

    Beads -->|"bd ready"| Engine
    Engine -->|"[dispatch] card → PO"| Dispatch
    Dispatch -->|"tech-lead card"| TL

    %% ── Construction Phase ──
    TL[Tech Lead<br/>construction orchestrator]
    Dev[Developer<br/>harness wrapper]
    Ver[Verifier<br/>adversarial reviewer]
    Merge[Merge to master<br/>verifier owns this]

    TL -->|"kanban_delegate<br/>(atomic)"| Dev
    TL -->|"kanban_delegate<br/>(atomic)"| Ver
    Dev -->|"code on branch"| Ver
    Ver -->|"FAIL: findings<br/>→ fix card"| Dev
    Ver -->|"PASS: zero findings"| Merge

    %% ── Escalation from construction ──
    Ver -->|"iter ≥3: ESCALATE"| TL
    TL -->|"hard bug → ESCALATE"| DBG

    %% ── QA Phase ──
    QA[QA Engineer<br/>live artifact tester]

    Merge -->|"merged feature"| QA
    QA -->|"PASS: test report"| Done([ACTUAL DONE])

    %% ── QA Failure Triage ──
    QA -->|"FAIL: files beads"| Triage{QA Triage}
    Triage -->|"bug: code is wrong"| DBG
    Triage -->|"non-bug: behavior wrong"| TL
    Triage -->|"spec: spec is wrong"| PO

    %% ── Debugger Loop ──
    DBG[Debugger<br/>diagnosis orchestrator]
    Repro[Reproduce]
    Hypo[Hypothesize + Fix<br/>→ developer card]
    Falsify[Falsify<br/>→ verifier card]
    Converge{Converge?}

    DBG --> Repro
    Repro --> Hypo
    Hypo --> Falsify
    Falsify --> Converge
    Converge -->|"not yet"| Repro
    Converge -->|"localized bug<br/>EXIT A"| RCA_A[RCA + fix + regression test]
    Converge -->|"design flaw<br/>EXIT B"| RCA_B[RCA + ADR stub]

    %% ── Debugger exits ──
    RCA_A -->|"re-verify"| QA
    RCA_B -->|"re-enter gate"| Arch

    %% ── Architect Gate (incremental) ──
    Arch -->|"T0: wave through"| Tickets
    Arch -->|"T1-T3: ADR required"| Tickets

    %% ── Styling ──
    classDef user fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    classDef orchestrator fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef worker fill:#e8f5e9,stroke:#388e3c,stroke-width:1px
    classDef gate fill:#fce4ec,stroke:#c62828,stroke-width:2px
    classDef store fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1px
    classDef done fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px

    class User user
    class PO,TL,DBG,Arch orchestrator
    class Dev,Ver,QA,Grill,Spec,Tickets,Dispatch,Engine worker
    class Approval,Triage,Converge gate
    class Beads store
    class Done done
```

---

## Phase-by-phase detail

### 1. Planning (Product Owner)

The PO is the front door. The skill index in the PO's SOUL.md routes incoming requests:

| Trigger | Skill loaded | What happens |
|---------|-------------|--------------|
| New project idea / migration | `project-kickoff` | Routes to `project-kickoff-grill` then `project-kickoff-spec` |
| Prototype promotion | `project-promotion` | Creates project structure, board, bd epic. Dispatches to PO. |
| Feature work on existing project | `dev-planning` | Discuss → `to-spec` → `to-tickets` |
| Workflow engine dispatch card | `dev-dispatch` | Creates tech-lead cards from ready beads |
| Discovery cron | `project-discovery` | Scans projects, updates steering state |

**Enforcement point:** The PO's SOUL.md is identity-only (charter). It contains zero inlined procedures. The skill index points to skills that own the process. This prevents the PO from improvising beads via `bd create` without loading `to-tickets`.

### 2. Grill → Spec → Architect → Tickets

```mermaid
flowchart LR
    Grill[Grill<br/>adversarial interview<br/>N decisions locked] --> Spec[to-spec<br/>synthesize PRD]
    Spec --> Arch[Architect<br/>design-council]
    Arch -->|design doc + ADRs| Tickets[to-tickets<br/>tracer-bullet slices<br/>citing ADRs]
    Tickets --> Gate{{User approval}}
    Gate -->|approved| Beads[(Beads)]
```

**Architect two modes:**
- **Design partner** (new project): PO creates a design card. Architect runs `design-council` via `loop_engine` — researcher + peer-architect fan-out through `kanban_chains`, PO interview gate, ADR recording. Output: design doc + ADR series.
- **Gatekeeper** (incremental change): T0-T3 blast-radius triage. T0 = wave through. T1+ = ADR via `design-council`.

**to-tickets:** Breaks the spec into vertical tracer-bullet slices — each cuts through every layer (schema, API, logic, tests) and is independently demoable. Each ticket cites the relevant ADRs. The skill quizzes the user for approval before publishing.

### 3. Workflow Engine (cron, zero-token)

Runs every minute via `workflow-engine.py` on the product-owner profile:

```mermaid
flowchart TD
    subgraph "Workflow Engine — every 60s"
        P1[Phase 1: bead-sync<br/>card status → bd bead status]
        P2[Phase 2: dispatch<br/>bd ready → PO dispatch card]
        P3[Phase 3: scanner<br/>blocked tasks → escalation]
        P1 --> P2 --> P3
    end
```

Reads `active-projects.json` to know which projects to scan. Empty list = silent exit, zero tokens.

### 4. Construction (Tech-lead → Developer → Verifier)

```mermaid
flowchart TD
    TL[Tech Lead<br/>receives bead card]
    TL -->|"kanban_delegate plugin<br/>(atomic: creates both, links, blocks self)"| Dev
    TL -->|"kanban_delegate plugin"| Ver

    Dev[Developer<br/>invokes coding harness<br/>in isolated worktree]
    Dev -->|"gates green<br/>commit to branch"| Ver

    Ver[Verifier<br/>3-stage adversarial review]
    Ver -->|"Stage 1: execute + fast-fail<br/>Stage 2: fan out probes<br/>Stage 3: synthesize"| Verdict{Verdict}

    Verdict -->|"FAIL<br/>findings → fix card"| Dev
    Verdict -->|"iter ≥3"| Esc[ESCALATE → Tech Lead]
    Verdict -->|"PASS<br/>zero findings at ANY severity"| Merge[Merge to master<br/>serialized, post-rebase test]

    Merge --> QA
```

**Role separation (load-bearing):**
- Developer = the Generator. Never reviews, scores, or approves its own work.
- Verifier = the Checker. Never writes code. Reviews output, not reasoning (trace-blind by default).
- This separation is what makes adversarial verification meaningful — if the same agent graded its own work, the review would be compromised.

**Verifier merge gate:** The verifier owns the merge. It acquires the merge slot (`bd merge-slot`), rebases onto main, re-runs the full test suite on the rebased candidate, then merges. Serialized — one slot holder at a time.

**Inner FAIL loop (runs without tech-lead):** Verifier files findings as a `REVIEW-ITERATION` comment on the developer card, creates a fix card (developer warm-resumes the prior harness session), and a fresh review card. The developer and verifier iterate without tech-lead involvement until PASS or iteration ≥3.

### 5. QA (last gate — tests the running artifact)

```mermaid
flowchart TD
    M[Merge to master] --> QA
    QA[QA Engineer<br/>builds, runs, uses the artifact]
    QA -->|happy path + edge cases| Result{Result}
    Result -->|PASS| Done([ACTUAL DONE])
    Result -->|FAIL| Triage{Triage by type}
    Triage -->|bug: code is wrong| DBG[Debugger]
    Triage -->|non-bug: behavior wrong| TL[Tech Lead]
    Triage -->|spec: spec is wrong| PO[Product Owner]
```

QA does NOT read code. QA tests the assembled, running artifact — the actual thing a user would interact with. "The unit tests passed" means nothing to QA; it trusts only what it personally observed by running the thing.

### 6. Debugger (diagnosis orchestrator)

```mermaid
flowchart TD
    subgraph "Inbound"
        QA[QA triage<br/>confirmed bug]
        TL[Tech-lead ESCALATE<br/>hard bug at iter ≥3]
    end

    QA --> DBG
    TL --> DBG

    DBG[Debugger<br/>loop_engine: reproduce → hypothesize → falsify → converge]
    DBG -->|fix card| Dev[Developer]
    DBG -->|falsify card| Ver[Verifier]
    DBG -->|archaeology card| Res[Researcher]

    Dev --> DBG
    Ver --> DBG
    Res --> DBG

    DBG --> ExitA{Converge}
    ExitA -->|EXIT A<br/>localized bug| Fix[Proven fix<br/>+ regression test<br/>+ post-mortem RCA]
    ExitA -->|EXIT B<br/>design flaw| ADR[ADR stub<br/>+ post-mortem RCA]

    Fix -->|re-verify| QA
    ADR -->|re-enter gate| Arch[Architect]
```

The debugger is the third orchestrator. It never writes code — it dispatches developer cards for fixes, verifier cards for falsification, researcher cards for environment/log archaeology. It holds the breadcrumb ledger (repro, ranked hypotheses, instrument results) on the root card's blackboard.

**Two exits:**
- **EXIT A (localized bug):** Proven minimal fix + regression test + post-mortem (RCA). Handed back to QA/originator for re-verification. The loop closes.
- **EXIT B (design flaw):** Root cause is architectural — no correct test seam exists, or the bug spans a boundary. RCA + ADR stub re-enters the architect gate. The bug becomes an architecture decision.

---

## Escalation Chain

```mermaid
flowchart TD
    Dev[Developer<br/>blocked] -->|scanner| TL[Tech Lead]
    Ver[Verifier<br/>blocked] -->|scanner| TL
    TL -->|scanner| PO[Product Owner]
    PO -->|scanner| Human[Human<br/>HUMAN_REQUIRED]

    TL -->|hard bug iter ≥3| DBG[Debugger]
    Ver -->|iter ≥3| TL
    QA -->|bug triage| DBG
    DBG -->|design flaw| Arch[Architect]
```

The board scanner (workflow engine Phase 3) detects blocked tasks and escalates to the next-level profile on the same board. Blocked tasks with a `HUMAN_REQUIRED` comment are skipped — they need a human, not an escalation card.

---

## Board Model

One board per project. All profiles work on all boards (n-to-n).

```
~/.hermes-teams/startup/kanban/boards/
├── crr-pos/          ← CRR POS v2
├── domainguard/      ← DomainGuard
├── team/             ← cross-project ops
└── hermes-hq/        ← HQ / default
```

`active-projects.json` maps projects to boards. The workflow engine only scans registered projects. Adding a project: create the board, add the entry, the engine picks it up on the next tick.

---

## SOUL.md Architecture

Each profile has a SOUL.md with two sections:

1. **Base identity** (above SPECIALTY block) — shared across all profiles. Constitution, bootstrap protocol, team coordination footer.
2. **SPECIALTY block** (between `<!-- SPECIALTY:BEGIN -->` and `<!-- SPECIALTY:END -->`) — identity-only charter: role, stance, handoffs, skill index.

The SPECIALTY block follows the `writing-great-soul` skill principles:
- **No inlined procedures** — if a procedure lives in the charter, it becomes a stale duplicate of the skill
- **No rosters** — each charter states only its own ownership, not teammates'
- **No rule lists** — collapsed to stance-level principles
- **Skill index** — trigger conditions pointing to skills, zero procedural content

---

## Component Map

| Component | Location | Purpose |
|-----------|----------|---------|
| `workflow-engine.py` | `product-owner/scripts/` | Combined cron: bead-sync + dispatch + scanner |
| `kanban_delegate` plugin | `tech-lead/plugins/dev_workflow/` | Creates dev+verifier cards atomically |
| `loop_engine` | architect/debugger tool | Converge-loop driver for design-council and debug-loop |
| `hygiene-guard.sh` | `product-owner/scripts/` | Scans for stale/orphan beads |
| `active-projects.json` | `startup/` | Project → board registry (workflow engine reads this) |
| `writing-great-soul` | `shared-skills/` | Reference skill for SOUL.md editing |
| `writing-great-skills` | `shared-skills/mattpocock/` | Reference for skill authoring |
