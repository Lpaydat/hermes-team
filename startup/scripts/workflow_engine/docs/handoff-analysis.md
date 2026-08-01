# Inter-Profile Handoff Analysis — Full Pipeline Mapping

> **Generated:** 2026-07-31
> **Sources:** 8 profile diagnoses (`docs/profile-diagnoses/`), old cron `workflow-engine.py`, `docs/pipeline-diagnosis.md`
> **Purpose:** Identify every inter-profile handoff in the current system, classify each as engine-managed / profile-managed / cron-managed / manual, and define the boundary data each carries.

---

## Quick-Reference: Classification Categories

| Category | Definition | Engine Visibility |
|----------|-----------|-------------------|
| **Engine-managed** | Explicit edge or trigger between workflow nodes — the engine itself creates the downstream card, advances the graph, or fires a trigger condition. | Full — engine owns the transition |
| **Profile-managed** | A single orchestrator profile uses `kanban_chains` / `loop_engine` to spawn sub-cards. The engine sees only the parent card go `blocked`→`done`; internal trees are invisible. | Opaque — engine sees status only |
| **Cron-managed** | A cron job (currently `workflow-engine.py` or ops scripts) runs on a schedule, queries state, and creates cards/route work. No workflow-graph edge exists. | None — cron is outside the graph |
| **Manual** | Requires a human decision — cannot be automated. The system surfaces the need (blocked card, HQ escalation) but a human must act. | Signal only — human acts |

---

## Master Handoff Inventory (28 handoffs)

| # | Handoff | Source → Target | Current | Proposed | Category |
|---|---------|----------------|---------|----------|----------|
| H01 | Design card | PO → Architect | Profile skill (`architect-gate`) | **Engine edge** (design phase node) | Engine |
| H02 | Design doc return | Architect → PO | Card completion metadata | **Engine edge** (phase→done) | Engine |
| H03 | Architect consult RPC | Architect → PO (file-based RPC) | `design-consult-rpc` skill — spawn PO session | **Manual** (needs real-time human-quality judgment) | Manual |
| H04 | Research fan-out | Architect → Researcher | `kanban_chains` inside design-council | **Profile-managed** (stays as-is) | Profile |
| H05 | Peer-architect fan-out | Architect → Architect (peer) | `kanban_chains` inside design-council | **Profile-managed** (stays as-is) | Profile |
| H06 | DoD verdict | Architect → Verifier | `loop_engine` verifier phase | **Profile-managed** (stays as-is) | Profile |
| H07 | Bead dispatch (default) | Engine/Cron → PO → Tech-Lead | Cron `workflow-engine.py` Phase 2 | **Engine trigger** (`bead_ready`) | Engine |
| H08 | Bug dispatch | Engine/Cron → Debugger | Cron `dispatch_bug_to_debugger()` | **Engine trigger** (`bead_ready` + `type=bug`) | Engine |
| H09 | Wayfinder routing | Engine/Cron → Scout/Ops/Architect | Cron label-based routing | **Engine trigger** (`bead_ready` + label conditions) | Engine |
| H10 | Dev card creation | Tech-Lead → Developer | `kanban_chains` (tech-lead orchestrates) | **Profile-managed** (stays as-is) | Profile |
| H11 | Verifier card creation | Tech-Lead → Verifier | `kanban_chains` (auto-child of dev card) | **Profile-managed** (stays as-is) | Profile |
| H12 | Dev→Verify promotion | Developer → Verifier | Card completion auto-promotes child | **Profile-managed** (kanban native) | Profile |
| H13 | FAIL fix card | Verifier → Developer | Verifier creates `kanban_create` fix card | **Profile-managed** (inside dev loop) | Profile |
| H14 | ESCALATE | Verifier → Tech-Lead | `kanban_block(needs_input)` + escalation card | **Profile-managed** + scanner backup | Profile |
| H15 | Contract-vs-intent | Verifier/Tech-Lead → PO | `kanban_block(needs_input)` → PO owns beads | **Manual** (spec judgment) | Manual |
| H16 | QA trigger | Verifier/Debugger → QA | Cron Phase 4 (DISABLED) / new engine (BROKEN) | **Engine trigger** (`card_completed`) | Engine |
| H17 | QA bug filing | QA → Debugger | `bd create --type=bug` → engine routes | **Engine trigger** (`bead_ready` + `type=bug`) | Engine |
| H18 | QA triage report | QA → Tech-Lead | Synthesizer card completion → tech-lead | **Profile-managed** (QA orchestrates) | Profile |
| H19 | QA spec findings | QA → PO | `bd create` with spec-ambiguity label | **Engine trigger** (bead label routing) | Engine |
| H20 | Debugger fix dispatch | Debugger → Developer | `loop_engine` phase execution card | **Profile-managed** (inside debug loop) | Profile |
| H21 | Debugger falsify | Debugger → Verifier | `loop_engine` phase verifier card | **Profile-managed** (inside debug loop) | Profile |
| H22 | Debugger merge gate | Debugger → Verifier | Verifier card for bug branch review+merge | **Profile-managed** (inside debug loop) | Profile |
| H23 | Debugger exit B | Debugger → Architect | Gate card (blocked + routed) | **Manual** (architect T2/T3 gate) | Manual |
| H24 | Debugger re-verify | Debugger → QA/Originator | Completion-contract `verdict=fixed` | **Engine trigger** (merge→QA) | Engine |
| H25 | Scanner escalation | Any → Next-in-chain | Cron Phase 3 `ESCALATION_CHAIN` | **Cron** (stays as safety net) | Cron |
| H26 | Human-flagged bead | Any → Operator | Cron Phase 2b HQ card | **Engine trigger** (`bead_ready` + `label=human`) | Engine |
| H27 | Scout→Researcher | Scout → Researcher | `kanban_create(assignee=researcher)` | **Profile-managed** (scout owns filing) | Profile |
| H28 | Ops platform | Ops → All profiles | Cron scripts (no_agent) | **Cron** (stays — infra ops) | Cron |

---

## Detailed Handoff Analysis

### H01: PO → Architect (Design Card)

| Field | Detail |
|-------|--------|
| **Current mechanism** | PO loads `architect-gate` skill, which creates a design kanban card assigned to `architect`. Card body is self-contained: spec link + context summary + settled decisions + open questions + stakes tier (low/standard/high). Card promotes to architect via dispatcher. |
| **Proposed mechanism** | **Engine-managed edge.** Model as a workflow node with a design-phase trigger: when PO completes the spec-authoring node, the engine fires a `card_created` trigger that creates the architect design card. The `stakes` field on the card metadata drives the `loop_engine` phase configuration (2-phase low / 3-phase standard / 3-phase-high-with-ensemble). |
| **Boundary data** | `spec_path` (PRD.md), `context_summary`, `settled_decisions[]`, `open_questions[]`, `stakes` (low\|standard\|high), `project_slug`, `card_topic` (for kanban-comment targeting) |
| **Engine can handle?** | **Yes** — this is a clean "phase complete → spawn specialist card" edge. The trigger condition is `po.spec_node.status == done`. No human judgment needed at the transition point itself. |

### H02: Architect → PO (Design Doc Return)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Architect completes the design card with structured metadata: `design_doc`, `design_version_ref`, `adr` (path), open questions for PO. PO reads this metadata via `kanban_show` before running `to-tickets`. |
| **Proposed mechanism** | **Engine-managed edge.** When the architect's `loop_engine` workflow completes (all phases done, DoD met), the engine marks the design node as done. A downstream `po.tickets_node` auto-advances. The completion metadata (`design_doc`, `adr`, `open_questions`) is the boundary payload injected into the PO's `to-tickets` context. |
| **Boundary data** | `design_doc` (slug), `design_version_ref`, `adr` (file path), `open_questions[]`, `tech_stack_decisions[]`, `data_model_decisions[]` |
| **Engine can handle?** | **Yes** — clean card-completion → graph advancement. |

### H03: Architect → PO (Design Consult RPC)

| Field | Detail |
|-------|--------|
| **Current mechanism** | During the `loop_engine` converge phase (T2 standard/high), architect has product-ambiguous trade-off questions. It launches a file-based RPC: `hermes -p product-owner --skills design-consult-rpc -z "<question>"` (with `HERMES_KANBAN_*` unset so PO doesn't pick up the architect's card context). PO answers in `<A>` tags. On timeout, architect calls `kanban_block(kind="needs_input")`. |
| **Proposed mechanism** | **Manual / hybrid.** The RPC itself can be modeled as an engine "interview" node (a blocking sub-phase that waits for PO response), but the *content* of PO's answer requires human-quality product judgment. The engine can manage the *mechanics* (spawn PO consult card, block until answered, inject response) but cannot *produce* the answer. Recommendation: keep as a `loop_engine` re-entrant interview phase (current model is already correct). |
| **Boundary data** | `question` (string), `context_citations[]`, `stakes`. Returns: `answer` (string), `citations[]` |
| **Engine can handle?** | **Mechanics yes, content no.** The engine manages the blocking/unblocking lifecycle. The actual answer requires PO's product judgment (human-level reasoning). |

### H04: Architect → Researcher (Research Fan-Out)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Inside the `design-council` skill's converge phase, architect calls `kanban_chains` with researcher cards: `[{"assignee": "researcher", "skill": "deep-research"}]` or `["docs-verification"]` for auth/security topics. Each researcher card carries a focused sub-topic and returns findings + citations to the root blackboard. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** This is an internal fan-out within the architect's `loop_engine` workflow. The engine sees the architect's root card go `blocked`→`done`; the researcher sub-cards are invisible. This is the correct abstraction — the architect owns the research decomposition. |
| **Boundary data** | `sub_topic`, `research_depth` (scout/deep/verification), `context_brief`. Returns: `findings[]`, `citations[]` posted to `[swarm:blackboard]` |
| **Engine can handle?** | **No — and shouldn't.** This is architect-internal orchestration. Moving it to the engine would break the design-council convergence loop. |

### H05: Architect → Architect-Peer (Peer Review Fan-Out)

| Field | Detail |
|-------|--------|
| **Current mechanism** | `kanban_chains` fan-out with independent peer-architect cards. Each peer reviews independently — explicit "do NOT read sibling perspectives" to prevent anchoring. Returns independent design-doc version or critique. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** Same rationale as H04: this is architect-internal convergence orchestration. |
| **Boundary data** | `design_doc_draft`, `decision_focus`. Returns: independent `perspective`, `alternatives[]`, `critique` |
| **Engine can handle?** | **No — and shouldn't.** Peer independence is the load-bearing property. |

### H06: Architect → Verifier (DoD Verdict)

| Field | Detail |
|-------|--------|
| **Current mechanism** | `loop_engine` verifier phase: after architect synthesizes a design-doc version, a verifier card (skill: `dod-verdict`) evaluates against the DoD contract. Returns `dod_verdict` JSON: `behaviors[]`, `defect_traces[]`, `dod_met`, `score`, `items{}`, `gaps[]`, `evidence[]`, `recommendation`. On high stakes, spawns 3-judge ensemble. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** The verifier is the DoD-checker inside the `loop_engine` phase structure. The engine sees the architect's root card lifecycle only. |
| **Boundary data** | `design_doc` (slug), `dod_contract_ref`. Returns: `dod_verdict` (full structured object — see §6.5 of architect diagnosis) |
| **Engine can handle?** | **No — and shouldn't.** The `loop_engine` plugin already manages this convergence. The workflow engine should not duplicate DoD logic. |

### H07: Bead Dispatch (Default Path) — Engine/Cron → PO → Tech-Lead

| Field | Detail |
|-------|--------|
| **Current mechanism** | Cron `workflow-engine.py` Phase 2: `bd ready --json` → filters (skip gt:slot, epics, wayfinder:skip labels) → checks `has_active_po_dispatch_card()` (one-at-a-time guard) → creates `[dispatch] N ready bead(s)` card, assignee=`product-owner`. PO picks it up, runs `dev-dispatch` skill → creates `[auto] <bead-title>` cards, assignee=`tech-lead`, `--idempotency-key bead-<id>`, `--workspace worktree:<project-dir>`. |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready`).** Replace the cron poll with an engine trigger that fires when `bd ready` returns new beads. The trigger node creates the PO dispatch card (or directly creates tech-lead cards if the PO step is deemed redundant). Must preserve: one-at-a-time dispatch guard, idempotency key `bead-<id>`, worktree workspace. |
| **Boundary data** | `bead_id`, `bead_title`, `project_dir`, `board`, `idempotency_key` (`bead-<bead_id>`). Tech-lead card body: `"Bead: <id> — <title>. Run bd show <id> + cat PRD.md."` |
| **Engine can handle?** | **Yes — high priority.** This is the most fundamental pipeline trigger. The cron currently does it well; the engine's advantage is event-driven timing (immediate vs every-60s poll) and graph visibility. **Key constraint:** the one-active-dispatch-card guard must be preserved. |

### H08: Bug Dispatch — Engine/Cron → Debugger

| Field | Detail |
|-------|--------|
| **Current mechanism** | Cron Phase 2: if `bead.issue_type == 'bug'` (or task with `bug` in labels), calls `dispatch_bug_to_debugger()` → creates `[auto] bug:` card, assignee=`debugger`, `--idempotency-key bead-<id>`, `--workspace dir:<project-dir>`. **Bypasses PO entirely.** |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready` + `type=bug` condition).** A trigger node with condition `bead.issue_type == 'bug'` routes directly to debugger. Preserves the PO bypass (bugs don't need product judgment — they need diagnosis). |
| **Boundary data** | `bead_id`, `bug_title`, `description`, `project_dir`, `resolve_protocol` (run loops-engineering doctrine). Card body includes bead ID + description + "Run your loops-engineering doctrine." |
| **Engine can handle?** | **Yes — high priority.** Clean type-based routing. |

### H09: Wayfinder Routing — Engine/Cron → Scout/Ops/Architect

| Field | Detail |
|-------|--------|
| **Current mechanism** | Cron Phase 2: checks bead labels against `WAYFINDER_ROUTES` dict: `wayfinder:research`→scout, `wayfinder:task`→ops, `wayfinder:architecture`→architect. Creates routed card with resolve-protocol body (including ADR instructions for architect). Skip labels: `wayfinder:grilling`, `wayfinder:prototype`, `wayfinder:map`, `venture:brief` (HITL-substitute work, never headless-dispatched). |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready` + label conditions).** Multiple trigger nodes, one per wayfinder label, each with a `condition` matching the label and a distinct `assignee`. The resolve-protocol body can be a template in the engine config. |
| **Boundary data** | `bead_id`, `map_id` (parent), `question` (bead description), `project_dir`. For architect: also `adr_convention_path`, `resolve_protocol` (weigh alternatives, record ADR, cite by number). |
| **Engine can handle?** | **Yes — medium priority.** Label-based routing is mechanical. The architect variant's resolve-protocol body is complex but template-able. |

### H10: Tech-Lead → Developer (Dev Card)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Tech-lead calls `kanban_chains` atomically: creates dev card (assignee=`developer`) + verifier card (child of dev card) + links tech-lead as child of verifier + blocks tech-lead `kind=dependency`. Dev card body: full contract (ACs, `evals_cmd`, `bead_id`, `contract_ref`, Size, Harness, constraints). Workspace: `dir:<project path>`. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** The tech-lead's `kanban_chains` call is the canonical pattern. The workflow engine sees the tech-lead's root card go `blocked`→`done`; the dev+verifier tree is internal. This is exactly the "dynamic workflow" pattern the engine supports. |
| **Boundary data** | `bead_id`, `contract_ref` (path to contract.md), `evals_cmd`, `Size` (small\|medium\|large), `Harness` (claude\|codex\|opencode\|pi), `constraints`, `context_plan`. |
| **Engine can handle?** | **No — and shouldn't.** `kanban_chains` is the atomic primitive. Moving dev-card creation to the engine would break role separation (tech-lead owns HOW, including contract authoring). |

### H11: Tech-Lead → Verifier (Verifier Card)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Auto-child of dev card, created atomically by `kanban_chains`. Body: `contract_ref`, `evals_cmd`, `bead_id`, review axes. Trace-blind by default. Promotes to verifier when dev card completes. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** Same as H10 — part of the `kanban_chains` atomic creation. |
| **Boundary data** | `contract_ref`, `evals_cmd`, `base_sha`, `branch_name` (auto-injected from dev card completion metadata), `bead_id`, review axes. |
| **Engine can handle?** | **No — and shouldn't.** |

### H12: Developer → Verifier (Promotion)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Developer completes card with structured metadata (`branch_name`, `worktree_path`, `harness_session_id`, `transcript_path`, `total_cost_usd`, `changed_files`, `chain_root`) + completion report comment (AC evidence mapping). The child verifier card auto-promotes to `ready` and is dispatched to the verifier profile. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** This is native kanban parent→child promotion. The engine doesn't need to intervene. |
| **Boundary data** | Metadata: `harness_session_id`, `transcript_path`, `total_cost_usd`, `num_turns`, `changed_files[]`, `branch_name`, `worktree_path`, `chain_root`. Report: AC evidence mappings, test evidence, approach, key decisions, deviations, dead ends. |
| **Engine can handle?** | **No — and shouldn't.** Kanban handles this natively. |

### H13: Verifier → Developer (FAIL Fix Card)

| Field | Detail |
|-------|--------|
| **Current mechanism** | On FAIL verdict, verifier creates a fix card via `kanban_create(assignee="developer", parents=[review_card], workspace_kind="dir", workspace_path=<dev's worktree>)`. Body carries: `Review-Iteration: <N+1>`, `Chain-Root`, `Resume-Session`, `Branch`, `Worktree`, findings pointer, same `contract_ref`/`evals_cmd`. A fresh review card is created as the fix card's child (next verification iteration). |
| **Proposed mechanism** | **Profile-managed — stays as-is.** The FAIL→fix→re-verify loop is verifier-internal orchestration. The engine sees the tech-lead root card stay blocked until the loop converges. |
| **Boundary data** | `Review-Iteration`, `Chain-Root`, `Resume-Session` (harness session for warm resume), `Branch`, `Worktree`, findings comment pointer, `contract_ref`, `evals_cmd`. |
| **Engine can handle?** | **No — and shouldn't.** The fix loop is the verifier's core responsibility. |

### H14: Verifier → Tech-Lead (ESCALATE)

| Field | Detail |
|-------|--------|
| **Current mechanism** | When iteration ≥ 3 OR spec gap, verifier blocks own review card `kanban_block(kind="needs_input", reason="ESCALATE: ...")`. Creates a tech-lead escalation card linking the chain root + all review cards. Tech-lead reads accumulated comments + trace ledger, then classifies: defect→debugger, contract gap→re-contract, harness ceiling→switch model, wrong slice→abandon. |
| **Proposed mechanism** | **Profile-managed (primary) + cron scanner (backup).** The verifier's ESCALATE block is the primary mechanism. The cron scanner (H25) serves as a safety net for blocks that sit too long without resolution. Keep both. |
| **Boundary data** | Escalation card: `chain_root_id`, `review_card_ids[]`, `iteration_count`, `block_reason`, accumulated findings, trace ledger path. |
| **Engine can handle?** | **Partially.** The engine could detect `status=blocked` + `reason starts with ESCALATE:` and create the tech-lead escalation card automatically. But the classification (defect vs contract gap vs harness) requires tech-lead's judgment. Recommend: engine creates the escalation card; tech-lead classifies. |

### H15: Verifier/Tech-Lead → PO (Contract-vs-Intent Gap)

| Field | Detail |
|-------|--------|
| **Current mechanism** | If the bead promises the wrong thing (contract matches code but intent is wrong), tech-lead routes to PO via `kanban_block(kind="needs_input")` or creates a card. PO owns bead content and can amend the bead/PRD. |
| **Proposed mechanism** | **Manual.** Spec-vs-intent judgment is inherently human-product-level reasoning. The engine can route the blocked card to PO, but PO's decision (amend spec? change acceptance criteria? re-scope?) requires judgment. |
| **Boundary data** | `bead_id`, `contract_ref`, `intent_gap_description`, `evidence` (what the contract says vs what was intended). |
| **Engine can handle?** | **Routing yes, decision no.** The engine can detect the block and surface it, but the resolution is a human-product judgment. |

### H16: Verifier/Debugger → QA (Merge Trigger)

| Field | Detail |
|-------|--------|
| **Current mechanism** | **BROKEN.** Cron Phase 4 (`phase_qa_trigger`) is commented out. It was replaced by the "new workflow engine" (`qa-loop.json` template + `card_completed` trigger), but that engine's script path doesn't exist (`startup/scripts/workflow_engine/main.py` → "Script not found"). So QA triggering is currently **non-functional**. The old logic: two-signal AND — (1) master HEAD changed with code files, (2) verifier/debugger card completed in last hour. Dedup via `qa-merge-<sha>`. |
| **Proposed mechanism** | **Engine-managed trigger (`card_completed`).** This is the highest-priority migration target. A trigger node fires when: `card.assignee IN ('verifier', 'debugger') AND card.status == 'done' AND card.metadata.verdict == 'PASS' AND git HEAD advanced`. Creates `[qa] Re-test after merge` card, assignee=`qa`, `--idempotency-key qa-merge-<sha>`. The `qa-loop.json` template already exists — the engine script just needs to be fixed/deployed. |
| **Boundary data** | `merged_sha`, `source_card_id`, `source_assignee` (verifier\|debugger), `source_title`, `completion_summary`, `project_dir`, `feature_scope`. |
| **Engine can handle?** | **Yes — critical priority.** This is currently broken and blocking the QA pipeline. |

### H17: QA → Debugger (Bug Filing)

| Field | Detail |
|-------|--------|
| **Current mechanism** | QA files bugs as beads: `bd create --type=bug --priority=<P-level> --title=... --description=...`. The workflow engine's Phase 2 dispatch then picks up the bug bead via `bd ready` and routes to debugger via `dispatch_bug_to_debugger()`. The chain: QA → bd → cron poll → debugger card. |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready` + `type=bug`).** Same as H08 — the engine already handles this routing. QA just files the bead; the engine trigger fires when the bead becomes `ready` and creates the debugger card. No change needed to QA's filing behavior. |
| **Boundary data** | Bug bead: `bead_id`, `title`, `description` (symptom, repro, environment, severity), `priority` (P0–P4), `epic_link`. |
| **Engine can handle?** | **Yes** — already handled by H08 mechanism. The bead is the boundary artifact. |

### H18: QA → Tech-Lead (Triage Report)

| Field | Detail |
|-------|--------|
| **Current mechanism** | For medium/large artifacts, the QA synthesizer (a QA role in the `kanban_chains` swarm) deduplicates worker findings by root cause and files ONE combined triage report card to tech-lead. Tech-lead then creates dev+verifier fix pairs via `kanban_chains`. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** The QA swarm is internal to the QA orchestrator's `kanban_chains` call. The engine sees the QA root card lifecycle. The triage report card to tech-lead is a standard `kanban_create` from the synthesizer's completion. |
| **Boundary data** | `verdict`, `findings_count`, `root_causes[]`, `claims_tested`, `claims_proven`, findings detail (per root cause: claim, severity, reproduction, evidence). |
| **Engine can handle?** | **No — and shouldn't.** QA's swarm orchestration is internal. |

### H19: QA → PO (Spec Findings)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Spec-level findings (ambiguity, missing requirements) route to PO via beads (`bd create` with spec-ambiguity context). The verdict summary on the QA card completion is readable by anyone via `kanban_show`. |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready` + label routing).** QA files a bead tagged appropriately; the engine's bead-dispatch trigger routes it. If the spec finding is filed as a standard feature bead, it goes through the normal PO dispatch path (H07). |
| **Boundary data** | `bead_id`, `spec_issue_description`, `ambiguity_evidence`, `affected_requirements[]`. |
| **Engine can handle?** | **Yes** — same mechanism as H07/H09. Bead-label-based routing. |

### H20: Debugger → Developer (Fix Dispatch)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Inside the `loop_engine` converge loop (Phase 1: hypothesise+fix+falsify), the debugger dispatches developer cards via the execution phase node. Body: ranked hypothesis + falsifiable prediction, repro from ledger #0, branch/worktree (`debug/<bug-id>-<slug>`), instruction to write regression test before fix. High-stakes: N parallel hypothesis cards, each its own `hypo-N` worktree. |
| **Proposed mechanism** | **Profile-managed — stays as-is.** The debug loop is a `loop_engine` workflow. The engine sees the debugger's root card go `blocked`→`done`. Internal phase cards (developer fix, verifier falsify) are invisible. |
| **Boundary data** | `hypothesis`, `falsifiable_prediction`, `repro` (from ledger #0), `branch_name`, `worktree_path`, `regression_test_instruction`, `bug_id`. |
| **Engine can handle?** | **No — and shouldn't.** The `loop_engine` convergence loop is debugger-internal. |

### H21: Debugger → Verifier (Falsify)

| Field | Detail |
|-------|--------|
| **Current mechanism** | `loop_engine` Phase 1 verifier node: after developer ships a fix, a verifier card evaluates 5 gates: (1) repro GREEN, (2) regression test at correct seam, (3) full suite green, (4) falsify (break it another way), (5) code-quality review. Returns `dod_verdict` with `recommendation` (advance\|replan\|escalate). |
| **Proposed mechanism** | **Profile-managed — stays as-is.** Part of the debug `loop_engine` convergence loop. |
| **Boundary data** | `fix_branch`, `repro`, `dod_contract` (5 gates). Returns: `dod_verdict` (structured — see debugger diagnosis §7). |
| **Engine can handle?** | **No — and shouldn't.** |

### H22: Debugger → Verifier (Merge Gate)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Debugger NEVER merges. On convergence (fix validated), debugger creates a verifier card for the bug branch: `assignee=verifier`, body includes branch reference + what was fixed + how to verify merge. Verifier reviews, merges to main via `merge-protocol` (slot acquire, rebase, re-run evals, merge, release slot). Workflow engine then auto-creates QA re-test card (H16). |
| **Proposed mechanism** | **Profile-managed (card creation) + engine trigger (QA card).** The debugger's verifier card is a `kanban_create` from inside the debug loop. The downstream QA trigger (H16) is engine-managed. |
| **Boundary data** | `bug_branch` (`debug/<bug-id>-<slug>`), `what_was_fixed`, `merge_verification_steps`, `bug_id`, `postmortem_path`. |
| **Engine can handle?** | **Card creation no (profile-managed), QA trigger yes (engine).** The merge→QA edge (H16) is engine-managed. |

### H23: Debugger → Architect (Exit B — Design Flaw)

| Field | Detail |
|-------|--------|
| **Current mechanism** | When root cause has no correct test seam or spans a boundary (exit B), debugger writes RCA + ADR stub at `docs/adr/<bug-id>-<slug>.md`, then creates an architect gate card (blocked + routed). Architect processes via T2/T3 gate path. Debugger's completion-contract `verdict = escalated-design`. |
| **Proposed mechanism** | **Manual.** The architect gate is a human-judgment ceremony (weigh ≥2 alternatives, record ADR, async human approval for T2). The engine can create the gate card automatically (trigger: `debugger.metadata.verdict == 'escalated-design'`), but the architect's *decision* requires the design-council convergence loop + potentially human approval. |
| **Boundary data** | `rca_path`, `adr_stub_path`, `bug_id`, `design_flaw_summary`, `boundary_description`, `proposed_alternatives[]`. |
| **Engine can handle?** | **Card creation yes, decision no.** The engine can detect `verdict=escalated-design` and create the architect gate card. The architect's T2/T3 gate process (design-council, human approval) is manual. |

### H24: Debugger → QA/Originator (Re-Verify)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Debugger completes with `verdict=fixed` and completion-contract metadata. The fix is shipped on the bug branch, merged by verifier. The workflow engine's QA trigger (H16) detects the merge and creates a QA re-test card. QA re-tests the running artifact (delta re-test + regression check). |
| **Proposed mechanism** | **Engine-managed trigger (same as H16).** The merge→QA trigger fires when the verifier merges the bug fix branch. The QA card carries the bug context for delta re-testing. |
| **Boundary data** | `verdict` (`fixed`), `bug_id`, `regression_test` (path or "no-seam"), `postmortem_path`, `root_cause_summary`. |
| **Engine can handle?** | **Yes** — this is H16 with debugger as the source instead of verifier. |

### H25: Scanner Escalation (Blocked Task → Next-in-Chain)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Cron Phase 3 (`scan_board`): queries all `status='blocked'` tasks per board. For each: skip `default`/empty assignee, skip `HUMAN_REQUIRED`-commented tasks. Check if escalation resolved (done task with `[ESCALATION] %{task_id}%` + `RESOLVED:` summary → unblock). Check if escalation already exists (skip if active). Create `[ESCALATION] Resolve block on <task>` card assigned to `ESCALATION_CHAIN[assignee]`. Chain: developer→tech-lead, verifier→tech-lead, debugger→tech-lead, qa→tech-lead, tech-lead→PO, PO→None (HUMAN_REQUIRED comment). |
| **Proposed mechanism** | **Cron — stays as safety net.** The scanner is a cross-cutting concern that monitors ALL boards for stuck cards. It's not a workflow-graph edge — it's a watchdog. The engine could theoretically model blocked-task detection as a trigger, but the scanner's value is its simplicity and universality (one script, all boards, no per-workflow configuration). Keep as cron. |
| **Boundary data** | `task_id`, `assignee`, `title`, `block_reason` (from task_events payload), `target_assignee` (from ESCALATION_CHAIN). |
| **Engine can handle?** | **Theoretically yes, practically no.** The scanner is a universal safety net. Modeling it as engine triggers would require every workflow to declare escalation edges. The cron approach is simpler and catches edge cases the engine wouldn't know about. |

### H26: Human-Flagged Bead → Operator (HQ Card)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Cron Phase 2b (`phase_human_escalations`): `bd list --all --label human`. For each non-closed flagged bead without existing HQ card → creates `[ESCALATION] human answer needed:` card on `hermes-hq` board, assignee=`default`, priority=10, idempotency key `bead-human-<id>`. Response mechanism: `bd human respond <bead_id>`. |
| **Proposed mechanism** | **Engine-managed trigger (`bead_ready` + `label=human`).** A trigger node that fires when a bead is tagged `human` and is not closed. Creates the HQ card on `hermes-hq`. This is cleaner than the cron poll and more responsive (immediate vs every-60s). |
| **Boundary data** | `bead_id`, `bead_title`, `description`, `respond_command` (`bd human respond <bead_id>`), `project_dir`, `board`. |
| **Engine can handle?** | **Yes — medium priority.** Label-based trigger, clean routing. |

### H27: Scout → Researcher (Deep Research Filing)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Scout runs daily cron (8×/day). In Phase 4 (file), if a source is classified as `deep-research` (≥2 of: landscape-changing, T1, high signal, core to agentic/gen AI), scout calls `kanban_create(title="Deep research: ...", assignee="researcher", body=...)`. Dispatcher picks up, researcher does deep research, writes wiki note, completes. **Currently broken** — scout cron fails (`RuntimeError: No usable credentials found for provider 'deepseek'`). |
| **Proposed mechanism** | **Profile-managed — stays as-is (but fix the scout cron).** The scout→researcher handoff is a `kanban_create` from inside the scout's workflow. The engine doesn't need to manage this — scout owns the discovery and filing decision. The fix needed is the DeepSeek API key, not an architecture change. |
| **Boundary data** | `research_topic`, `source_urls[]`, `source_tier`, `why_deep_research` (rationale), `related_wiki_notes[]` (for cross-referencing). |
| **Engine can handle?** | **No — and shouldn't.** The filing decision (is this deep-research-worthy?) is scout's editorial judgment. |

### H28: Ops → All Profiles (Platform Operations)

| Field | Detail |
|-------|--------|
| **Current mechanism** | Three `no_agent` cron scripts on the ops profile: (1) `healthcheck.sh` every 5 min — checks tools, gateways, disk, Z.AI auth; silent when healthy, reports findings when broken. (2) `cron-store-backup.sh` every 6h — backs up all profiles' `jobs.json`. (3) `session-archiver.py` every 6h — archives kanban sessions >3 days old. All are zero-token watchdog scripts. |
| **Proposed mechanism** | **Cron — stays as-is.** These are infrastructure operations, not workflow handoffs. They don't create cards or route work between profiles. They maintain the platform. Moving them to the workflow engine would add complexity without benefit. |
| **Boundary data** | N/A — these are system health checks, not inter-profile data flows. |
| **Engine can handle?** | **No — and shouldn't.** Infrastructure ops belong in cron, not the workflow engine. |

---

## Cross-Cutting Patterns

### Pattern 1: Bead as Universal Boundary Artifact

Multiple handoffs (H07, H08, H09, H17, H19, H26) use **beads** as the boundary artifact. The pattern is:

```
Source profile → bd create (files bead with type/label) → engine/cron detects bd ready → creates target card
```

This means the **bead is the contract** between profiles for work routing. The engine's `bead_ready` trigger is the universal bridge. Migration recommendation: implement one robust `bead_ready` trigger with condition-based routing (by `issue_type`, `labels`), replacing the cron's Phase 2 dispatch entirely.

### Pattern 2: `kanban_chains` as Profile-Internal Orchestration

Three orchestrator profiles (tech-lead, debugger, QA) use `kanban_chains` to spawn internal card trees:
- **Tech-lead**: dev + verifier pair (H10, H11)
- **Debugger**: researcher + developer + verifier converge loop (H20, H21, H22)
- **QA**: functional + security + exploratory workers + synthesizer (H18)

The engine sees only the parent card's `blocked`→`done` transition. This is the **correct abstraction** — the engine should not peer inside these trees. Moving any of these to engine-managed edges would break the orchestrator's control over convergence logic, fan-out sizing, and iteration caps.

### Pattern 3: Merge as the Cross-Phase Boundary

The verifier's merge is the boundary between the dev loop and the QA phase:
- **Before merge**: tech-lead/debugger orchestrates dev+verifier cards (profile-managed)
- **After merge**: engine creates QA card (engine-managed trigger)

The merge event (`git HEAD advanced` + `verifier/debugger card completed`) is the signal. Currently broken (H16). This is the single most critical migration target.

### Pattern 4: Escalation as Safety Net, Not Primary Path

The scanner (H25) is a **watchdog**, not a workflow edge. It catches cards that are stuck because the primary handoff mechanism failed (verifier didn't create escalation card, tech-lead didn't classify, etc.). Keeping it as cron is correct — it needs to be universal and board-agnostic.

### Pattern 5: Spec Judgment is Always Manual

Three handoffs involve spec/product judgment:
- H03 (architect consult RPC) — product-ambiguous trade-offs
- H15 (contract-vs-intent gap) — bead promises wrong thing
- H23 (debugger exit B) — architectural root cause

The engine can route the cards, but the **decisions** require human-level product/architectural reasoning. These should surface as blocked cards (`needs_input`) and wait for human or PO/architect judgment.

---

## Migration Priority Matrix

| Priority | Handoff | Action | Effort | Risk |
|----------|---------|--------|--------|------|
| **P0 — Critical** | H16 (QA trigger) | Fix broken engine script; deploy `qa-loop.json` trigger | Low (template exists) | High (QA pipeline down) |
| **P1 — High** | H07 (bead dispatch) | Implement `bead_ready` trigger replacing cron Phase 2 | Medium | Medium (one-at-a-time guard) |
| **P1 — High** | H08 (bug dispatch) | Add `type=bug` condition to `bead_ready` trigger | Low (subset of H07) | Low |
| **P2 — Medium** | H09 (wayfinder routing) | Add label-based conditions to `bead_ready` trigger | Medium | Low |
| **P2 — Medium** | H26 (human-flagged bead) | Add `label=human` condition to `bead_ready` trigger | Low | Low |
| **P3 — Low** | H01, H02 (design card) | Model as engine edge (PO spec → architect design → PO tickets) | Medium | Low |
| **Keep** | H10–H13 (dev loop) | Profile-managed via `kanban_chains` — no change | — | — |
| **Keep** | H20–H22 (debug loop) | Profile-managed via `loop_engine` — no change | — | — |
| **Keep** | H18 (QA triage) | Profile-managed via QA swarm — no change | — | — |
| **Keep** | H25 (scanner) | Cron safety net — no change | — | — |
| **Keep** | H28 (ops cron) | Infrastructure cron — no change | — | — |
| **Manual** | H03, H15, H23 | Engine routes card; human/PO/architect decides | — | — |

---

## Summary Statistics

| Category | Count | Handoffs |
|----------|-------|----------|
| **Engine-managed** (proposed) | 8 | H01, H02, H07, H08, H09, H16, H19, H24, H26 |
| **Profile-managed** (stays) | 11 | H04, H05, H06, H10, H11, H12, H13, H14, H18, H20, H21, H22, H27 |
| **Cron-managed** (stays) | 2 | H25, H28 |
| **Manual** (human decision) | 3 | H03, H15, H23 |

> **Note:** Some handoffs span categories (e.g., H14 is profile-managed primary + cron backup; H22 is profile-managed card creation + engine QA trigger). Counts above reflect the *primary* mechanism.

---

## Key Constraints for Engine Migration

1. **One PO dispatch card at a time** — the `has_active_po_dispatch_card()` guard must be preserved in any `bead_ready` trigger implementation.

2. **Bug routing bypasses PO** — bugs go directly to debugger. The trigger must check `issue_type == 'bug'` before the default PO dispatch path.

3. **Wayfinder skip labels** — `wayfinder:grilling`, `wayfinder:prototype`, `wayfinder:map`, `venture:brief` must NEVER be headless-dispatched. These are HITL-substitute work.

4. **Merge serialization** — verifier holds a `bd merge-slot`. Only one merge at a time. The engine must NOT try to parallelize merges or create multiple QA cards for concurrent merges.

5. **Idempotency keys are load-bearing** — `bead-<id>` for bead-dispatched cards, `qa-merge-<sha>` for QA triggers, `bead-human-<id>` for HQ escalations. These prevent duplicate card creation across engine restarts or re-ticks.

6. **`kanban_chains` atomicity** — the engine must never interfere with an in-flight `kanban_chains` call. The parent card's `blocked` status is the signal that internal orchestration is running.

7. **Scanner as universal safety net** — even after engine migration, the cron scanner must continue running to catch cards that fall through the cracks (engine bugs, missed triggers, edge cases).

8. **Profile configs must agree on caps** — `max_in_progress_per_profile` is read by the lock-holding gateway at boot. All profile configs must agree for a cap change to take effect regardless of which gateway dispatches.
