# Product-Owner Profile — Pipeline Role Diagnosis

> Generated 2026-07-31. Sources: `SOUL.md`, `config.yaml`, `cron/jobs.json`, `scripts/workflow-engine.py`, `scripts/hygiene-guard.sh`, and skills: `dev-planning`, `dev-dispatch`, `project-kickoff`, `project-promotion` (shared-skills), `project-discovery`, `task-hygiene-validator`, `project-lifecycle-routing`.

---

## 1. What PO Does

The Product Owner is the **single front door** of the pipeline. All ideas, bugs, feature requests, and questions come to PO first. PO owns the **WHAT**; tech-lead owns the **HOW**. PO never writes code, never creates dev/verifier cards, never touches the harness.

PO's functional responsibilities:

| Responsibility | How |
|---|---|
| **Intake & routing** | Receives user ideas, bugs, questions; routes to the right specialist (architect, tech-lead, builder, researcher). |
| **Spec authoring** | Writes PRDs, synthesizes specs from grill output (`to-spec`). Owns `<project-dir>/PRD.md`. |
| **Ticket decomposition** | Breaks PRD + architect design into **tracer-bullet beads** (end-to-end slices, not horizontal layers) via `to-tickets`. |
| **Dispatch** | When the workflow engine cron creates a dispatch card, PO creates minimal tech-lead cards from `bd ready` beads (one card per bead). |
| **Gate decisions** | Surfaces architect gate cards (hard-to-reverse design decisions) to the human for approval. Nothing dispatches without user approval. |
| **Backlog hygiene** | Runs `task-hygiene-validator` to auto-defer stale items, auto-tag orphans, batch kill-candidates for approval. |
| **Discovery / audit** | Runs `project-discovery` to scan active projects for work signals (failing tests, TODO density, stale PRs, tech debt, docs staleness, git velocity). |
| **Steering state** | Maintains `.driver/{goal,progress,decisions,gaps}.md` per project. |
| **Promotion handoff** | Receives promoted prototypes from builder; takes them to production (spec → architect → tickets → dispatch). |
| **Escalation sink** | The scanner's `ESCALATION_CHAIN` terminates at PO — `tech-lead → product-owner` is the last automated hop before a human. |
| **Weekly reporting** | Produces a weekly sprint briefing across all active projects (cron job). |

**Stance principles** (from SOUL.md): challenge assumptions before committing; nothing dispatches without user approval; state recommendations as decisions not menus; keep the loop moving.

---

## 2. What Triggers PO

PO is activated by three classes of trigger: **human input**, **cron jobs**, and **kanban cards from other agents/the engine**.

### 2.1 Human triggers (SOUL.md skill index)

| User says / does | PO loads skill |
|---|---|
| "promote this" / "ship it" (prototype → production) | `project-promotion` |
| New project idea, migration, "let's build X" | `project-kickoff` |
| Feature work on an existing project | `dev-planning` |
| "what should we work on", "audit this project", "what's missing" | `project-discovery` |
| "clean up the backlog", "audit tasks", "find orphan issues" | `task-hygiene-validator` |
| Builder calls PO as griller subagent | `grill-rpc` |

### 2.2 Cron triggers (the automation backbone)

| Cron job | Schedule | What wakes PO |
|---|---|---|
| **Dev Workflow Engine** (`workflow-engine.py`) | every minute (`* * * * *`) | Phase 2 (dispatch) creates a `[dispatch]` kanban card assigned to `product-owner` whenever `bd ready` has non-bug, non-wayfinder beads. PO then runs `dev-dispatch`. |
| **Task Hygiene Watchdog** (`hygiene-guard.sh`) | every 240 min | Guard script runs the zero-token scanner; if findings exist, wakes the agent to apply the auto-action policy (`task-hygiene-validator`). |
| **Weekly Sprint Report** | `0 19 * * 0` (Sun 19:00) | Agent wakes, loads `project-discovery`, produces sprint report. |

### 2.3 Card triggers (from other agents via the board)

| Trigger card | From | PO action |
|---|---|---|
| `[dispatch] N ready bead(s)` | workflow engine | Run `dev-dispatch` → create tech-lead cards |
| Promotion dispatch card (assignee=product-owner, board=`<slug>`) | builder (via `project-promotion`) | Load `dev-planning` to take prototype to production |
| `[ESCALATION] Resolve block on <task>` | board scanner (when tech-lead is blocked) | Investigate, resolve, or block `needs_input` |
| `[general]` decision task on `hermes-hq` | `project-discovery` (PO creating for itself) | Surface to user |

---

## 3. What PO Produces for Downstream

### 3.1 Artifacts (files in the project repo)

| Artifact | Skill that produces it | Consumed by |
|---|---|---|
| `<project-dir>/PRD.md` | `dev-planning` (step 2, via `to-spec`) | architect (design card input), tech-lead (reads via `cat PRD.md`) |
| PRD bead in bd (`ready-for-agent` label) | `dev-planning` | closed by PO after slice creation |
| Tracer-bullet beads (each with acceptance criteria + `ready-for-agent`) | `dev-planning` (step 4, via `to-tickets`) | workflow engine `bd ready` → dispatch → tech-lead |
| `.driver/{goal,progress,decisions,gaps}.md` | `project-discovery` / `task-hygiene-validator` | PO (future runs), user (sprint report) |
| `STATUS.md` (project dashboard) | `project-promotion` (template), PO maintains | user |
| Sprint report (`reports/sprint-{date}.md`) | Weekly Sprint Report cron | user |
| ADR stubs (when debugger finds design flaw) | implicit via `project-lifecycle-routing` feedback loop | architect gate |

### 3.2 Kanban cards created by PO

| Card | Skill | Assignee | Idempotency key |
|---|---|---|---|
| `[auto] <bead-title>` (minimal tech-lead card) | `dev-dispatch` | `tech-lead` | `bead-<bead-id>` |
| Architect design card | `architect-gate` (PO loads it) | `architect` | (skill-managed) |
| `[<project-tag>] <desc>` specialist routing | `project-discovery` | specialist profile | — |
| `[general] <decision>` | `project-discovery` | `default` | — |
| `[ESCALATION]` resolution (when PO receives one from tech-lead) | scanner | PO is the assignee, not creator | — |

### 3.3 What PO does NOT produce

- Dev/verifier/QA cards (tech-lead creates those via `kanban_chains`)
- Bug routing cards (engine routes bugs directly to `debugger` via `dispatch_bug_to_debugger`, bypassing PO)
- Wayfinder tickets (engine routes by label to `scout`/`ops`/`architect`, bypassing PO)
- QA cards (engine creates directly to `qa` via `qa-trigger` phase — now commented out / migrated to new engine)

---

## 4. Every Handoff to Other Profiles

```
                         ┌─────────────────────────────────────────┐
                         │              PRODUCT OWNER               │
                         └──────────────────┬──────────────────────┘
                                            │
          ┌─────────────────┬───────────────┼───────────────┬──────────────────┐
          ▼                 ▼               ▼               ▼                  ▼
   ┌─────────────┐  ┌─────────────┐  ┌────────────┐  ┌───────────┐    ┌──────────────┐
   │  ARCHITECT  │  │  TECH-LEAD  │  │  RESEARCHER│  │  BUILDER  │    │   OPERATOR   │
   │ (design     │  │ (dispatch   │  │ (wiki/     │  │ (prototype│    │ (human, via  │
   │  cards+ADRs)│  │  cards)     │  │  docs)     │  │  grilling)│    │  hq board)   │
   └─────────────┘  └─────────────┘  └────────────┘  └───────────┘    └──────────────┘
```

### Detailed handoff map

| # | Handoff to | Trigger | Mechanism | What crosses the boundary |
|---|---|---|---|---|
| 1 | **architect** | Design decisions that are expensive to reverse | `architect-gate` skill creates a design card assigned to `architect` | PRD + problem context; architect returns design doc + ADRs + gate cards |
| 2 | **tech-lead** | `bd ready` beads detected by workflow engine → PO dispatch card | `dev-dispatch` creates `[auto]` cards, assignee=`tech-lead`, `--workspace worktree:<project-dir>`, `--idempotency-key bead-<id>` | Minimal card: bead ID + pointer to PRD. Tech-lead reads bead, writes own contract, then `kanban_chains` dev+verifier |
| 3 | **tech-lead** (escalation) | Board scanner finds tech-lead blocked card with no active escalation | Scanner creates `[ESCALATION]` card assigned to `tech-lead`'s superior — which is **PO** | This is a handoff *to* PO, not from PO |
| 4 | **builder** (as griller) | Builder runs `grill-rpc` and calls PO as the griller subagent | File-based RPC | PO serves as adversarial griller of builder's prototype plan |
| 5 | **builder** (promotion) | User says "promote this" | `project-promotion` (runs as builder's skill initially, then dispatches a card to PO) | Builder → PO: "take this prototype to production." PO owns from here. |
| 6 | **researcher** | Research and documentation tasks | SOUL.md: "researcher owns the wiki; PO owns steering state" | Kanban card or delegation. PO retains steering state; researcher owns the knowledge artifacts |
| 7 | **operator / human** (escalation) | (a) Scanner reaches end of `ESCALATION_CHAIN` (PO is blocked, no higher profile) → `HUMAN_REQUIRED` comment. (b) `project-discovery` finds a decision needing user input → `[general]` card on `hermes-hq`. (c) Human-flagged beads → engine creates `[ESCALATION]` card on `hermes-hq` board (assignee=`default`) | Kanban card on `hermes-hq` board, or `kanban_block(reason=..., kind="needs_input")` | Decision request, summary of block |
| 8 | **debugger** (NOT via PO) | Bug beads | Engine `dispatch_bug_to_debugger()` routes directly | Bypasses PO entirely — noted for completeness |

**Escalation chain** (from `workflow-engine.py` `ESCALATION_CHAIN`):
```
developer → tech-lead
verifier  → tech-lead
debugger  → tech-lead
qa        → tech-lead
tech-lead → product-owner   ← PO is the terminal automated node
product-owner → None        ← HUMAN_REQUIRED (no higher profile)
```

---

## 5. Cron Phases

PO's profile runs **4 cron jobs** (from `cron/jobs.json`). The workflow engine itself runs **5 phases** per project per tick.

### 5.1 Cron jobs on the PO profile

| Job ID | Name | Schedule | Type | Status | Notes |
|---|---|---|---|---|---|
| `5838e048ae7f` | Dev Workflow Engine — bead-sync + dispatch + scanner | `* * * * *` (every min) | script (`workflow-engine.py`, `no_agent=true`) | ✅ enabled, last_status=ok, 31299 completions | The active backbone. Runs all 5 phases. |
| `94e735a11be6` | New Workflow Engine — tick | `* * * * *` (every min) | script (`startup/scripts/workflow_engine/main.py`, `no_agent=true`) | ❌ **ERRORING** — "Script not found", 389 completions | Dead job. Target script doesn't exist. Was intended as the declarative successor. |
| `5421d37938f5` | Task Hygiene Watchdog | every 240 min | script (`hygiene-guard.sh`, `no_agent=true`) | ✅ enabled, last_status=ok, 135 completions | Zero-token guard; only wakes agent on findings. |
| `adc76c798cd4` | Weekly Sprint Report | `0 19 * * 0` (Sun 19:00) | agent prompt, skill=`project-discovery` | ✅ enabled, last_status=ok, 4 completions | Writes `reports/sprint-{date}.md`. Deliver=local. |

### 5.2 Workflow engine phases (the 5-phase tick, per active project)

```
For each project in active-projects.json:
  1. bead-sync     — kanban card status → bd bead status
  2. dispatch      — bd ready → PO dispatch card (bugs → debugger directly)
  2b. human-escal  — human-flagged beads → operator HQ card
  3. scanner       — blocked tasks → escalate via ESCALATION_CHAIN
  4. qa-trigger    — [DISABLED — commented out, migrated to "new workflow engine" which is erroring]
```

#### Phase 1: bead-sync
- **Purpose:** Sync kanban card status → bd bead status.
- **Mechanism:** For each bead (excluding `gt:slot`), reads the kanban card with `idempotency_key = bead-<id>`. Maps card status to bead status via `STATUS_MAP` (`ready/running`→`in_progress`, `blocked`→`blocked`, `done`→`closed`, `archived`→`open`). Skips already-closed beads. Calls `bd update <id> -s <target>`.
- **PO involvement:** None (pure cron).

#### Phase 2: dispatch
- **Purpose:** Detect ready beads and create a PO dispatch card.
- **Mechanism:** Runs `bd ready --json`. For each ready bead:
  - Skip `gt:slot` labels, epics, and `WAYFINDER_SKIP` labels (`wayfinder:grilling`, `wayfinder:prototype`, `wayfinder:map`, `venture:brief`).
  - Skip if a card with `idempotency_key = bead-<id>` already exists.
  - **Bugs** (`issue_type == 'bug'` OR task with `bug` in labels) → `dispatch_bug_to_debugger()`: creates `[auto] bug:` card, assignee=`debugger`. **Bypasses PO.**
  - **Wayfinder tickets** (labels in `WAYFINDER_ROUTES`) → routed by type: `wayfinder:research`→`scout`, `wayfinder:task`→`ops`, `wayfinder:architecture`→`architect`. **Bypasses PO.**
  - **Everything else** → collected into `new_beads`.
  - If `has_active_po_dispatch_card(board)` is true → skip (only one PO dispatch card at a time).
  - Otherwise → creates `[dispatch] N ready bead(s)`, assignee=`product-owner`, priority=20, `--workspace dir:<project-dir>`, idempotency key `po-dispatch-<board>-<timestamp>`.
- **PO involvement:** This is what wakes PO. PO picks up the dispatch card and runs `dev-dispatch`.

#### Phase 2b: human-escal
- **Purpose:** Make human-flagged beads visible without relying on the escalating agent to ping.
- **Mechanism:** `bd list --all --label human`. For each non-closed flagged bead without an existing HQ card → creates `[ESCALATION] human answer needed:` card on `hermes-hq` board, assignee=`default`, priority=10, idempotency key `bead-human-<id>`.
- **PO involvement:** None directly (goes to operator).

#### Phase 3: scanner
- **Purpose:** Escalate blocked tasks to the next profile in the chain.
- **Mechanism:** Queries all `status='blocked'` tasks. Skips `default`/empty assignee and tasks with `HUMAN_REQUIRED` comments. Checks for a resolved escalation (a `[ESCALATION] %<task_id>%` card with `RESOLVED:` summary → unblocks). Otherwise creates `[ESCALATION] Resolve block on <task>` card assigned to `ESCALATION_CHAIN[assignee]`. If no target (PO blocked) → posts `HUMAN_REQUIRED` comment.
- **PO involvement:** PO is the escalation target for tech-lead blocks. PO receives `[ESCALATION]` cards.

#### Phase 4: qa-trigger (CURRENTLY DISABLED)
- **Purpose:** When a verifier/debugger card completes AND master advanced with code files, create a QA re-test card.
- **Mechanism:** Two-signal AND: (1) `git rev-parse HEAD` changed since last run (tracked in `qa-trigger-state.json` per board), (2) `git diff --name-only` shows code extensions (.py/.js/.ts/.rs/.go/etc.), (3) a verifier/debugger card completed in the last hour (excludes `[probe]` and `verify t_` cards). Dedup via `qa-merge-<sha>`. Creates `[qa] Re-test after merge:` card, assignee=`qa`.
- **Status:** **Commented out** in `main()` (lines 681-687). Comment says "now handled by new workflow engine (`templates/qa-loop.json` + `card_completed` trigger)."
- **Problem:** The "new workflow engine" job (`94e735a11be6`) is **erroring** — script not found. So QA triggering is currently **broken/in limbo**.

### 5.3 Hygiene watchdog guard (`hygiene-guard.sh`)
- **Gate:** Reads `active-projects.json`. Empty list → `{"wakeAgent": false}` → zero tokens.
- **Per project:** Checks `.beads/` exists, dedupes by `git remote` (worktree/clone skip), runs `scan_hygiene.py`.
- **Output:** All clean → `STATUS:ALL_CLEAN` + `{"wakeAgent": false}`. Findings → prints them (become agent context) and wakes agent.
- **Agent action:** Loads `task-hygiene-validator`, applies auto-action policy (defer stale, auto-tag orphans, report kill-candidates).

---

## 6. JSON Node Definitions for Each PO Task

These model each PO task as a workflow-graph node (per the declarative graph model referenced in `project-lifecycle-routing`). Each node is self-contained: trigger, inputs, PO action, outputs, handoff.

### Node: `po.project-kickoff`

```json
{
  "id": "po.project-kickoff",
  "title": "Project Kickoff (new project / migration)",
  "trigger": {
    "type": "human_input",
    "match": "user brings new project idea, migration, or says 'let's build X'"
  },
  "skill": "project-kickoff",
  "sub_skills": ["project-kickoff-grill", "project-kickoff-spec", "grill-with-docs", "to-spec", "architect-gate", "to-tickets"],
  "inputs": {
    "user_idea": "string",
    "project_slug": "string"
  },
  "steps": [
    {"step": 1, "name": "grill", "skill": "project-kickoff-grill", "output": "~/projects/<slug>/.driver/grill/decisions.md"},
    {"step": 2, "name": "spec", "skill": "project-kickoff-spec", "uses": ["grill decisions"], "output": "spec + ADRs"},
    {"step": 3, "name": "architect", "skill": "architect-gate", "output": "design doc + gate cards (surfaced to human)"},
    {"step": 4, "name": "tickets", "skill": "to-tickets", "output": "tracer-bullet beads with acceptance criteria + ready-for-agent label"},
    {"step": 5, "name": "infra", "action": "create project board, add to active-projects.json"}
  ],
  "outputs": {
    "artifacts": ["<project-dir>/PRD.md", "tracer-bullet beads in bd", ".driver/ steering state"],
    "downstream_trigger": "workflow engine detects bd ready → po.dispatch"
  },
  "handoffs": [
    {"to": "architect", "via": "design card", "when": "step 3"},
    {"to": "tech-lead", "via": "workflow engine dispatch (indirect)", "when": "beads become ready"}
  ]
}
```

### Node: `po.dev-planning`

```json
{
  "id": "po.dev-planning",
  "title": "Dev Planning (feature work on existing project)",
  "trigger": {
    "type": "human_input_or_card",
    "match": "feature work for an existing project, or promotion dispatch card from builder"
  },
  "skill": "dev-planning",
  "sub_skills": ["grill-with-docs", "to-spec", "architect-gate", "to-tickets"],
  "inputs": {
    "feature_request": "string",
    "project_dir": "path"
  },
  "steps": [
    {"step": 1, "name": "discuss", "skill": "grill-with-docs", "output": "problem/user/done in 2-3 sentences"},
    {"step": 2, "name": "prd", "skill": "to-spec", "output": "<project-dir>/PRD.md + PRD bead (ready-for-agent)"},
    {"step": 3, "name": "architect", "skill": "architect-gate", "output": "design doc + ADRs"},
    {"step": 4, "name": "decompose", "skill": "to-tickets", "output": "tracer-bullet beads (each cites ADRs), dependencies via bd link"},
    {"step": 5, "name": "close_prd", "action": "bd close <prd-bead-id>"}
  ],
  "rules": [
    "Create ALL beads in ONE session",
    "Each bead must have acceptance criteria",
    "Use bd link, not --deps",
    "Never create tech-lead/dev/verifier cards — dispatch happens via workflow engine cron",
    "Other party reviews after PRD, after architect, after beads"
  ],
  "outputs": {
    "artifacts": ["PRD.md", "tracer-bullet beads", "PRD bead closed"],
    "downstream_trigger": "workflow engine bd ready → po.dispatch"
  },
  "handoffs": [
    {"to": "architect", "via": "design card (architect-gate skill)", "when": "step 3"}
  ]
}
```

### Node: `po.dispatch`

```json
{
  "id": "po.dispatch",
  "title": "Dev Dispatch (create tech-lead cards from ready beads)",
  "trigger": {
    "type": "kanban_card",
    "match": "card with assignee=product-owner, title starts with '[dispatch]', created by workflow engine phase 2"
  },
  "skill": "dev-dispatch",
  "inputs": {
    "dispatch_card": "kanban card body lists ready bead IDs",
    "project_dir": "path (from card workspace)"
  },
  "steps": [
    {"step": 1, "name": "check_ready", "action": "bd ready --json, filter out gt:slot"},
    {"step": 2, "name": "create_cards", "loop": "for each ready bead", "body": "check existing card via SQL (idempotency_key=bead-<id>); if none, create [auto] card assignee=tech-lead, workspace=worktree:<project-dir>, idempotency_key=bead-<id>, priority=30"},
    {"step": 3, "name": "complete", "action": "kanban_complete with dispatch summary"}
  ],
  "card_template": {
    "title": "[auto] <bead-title>",
    "assignee": "tech-lead",
    "body": "Bead: `<id>` — <title>. Run `bd show <id>` + `cat PRD.md`. Execute loops-engineering doctrine. Close bead with `bd close <id>`.",
    "workspace": "worktree:<project-dir>",
    "idempotency_key": "bead-<bead-id>",
    "priority": 30
  },
  "rules": [
    "Card carries ONLY bead ID + PRD pointer — no contracts, no function signatures",
    "Never set skills on dispatch card (crashes tech-lead with 'Unknown skill(s)')",
    "Never create dev/verifier cards — tech-lead does via kanban_chains",
    "--idempotency-key bead-<id> is the dedup — always include"
  ],
  "outputs": {
    "cards_created": "N tech-lead cards (one per ready bead)",
    "downstream_trigger": "tech-lead picks up cards, runs kanban_chains(dev+verifier)"
  },
  "handoffs": [
    {"to": "tech-lead", "via": "[auto] kanban card per bead", "mechanism": "kanban create with worktree workspace"}
  ]
}
```

### Node: `po.project-discovery`

```json
{
  "id": "po.project-discovery",
  "title": "Project Discovery (scan for work signals + gaps)",
  "trigger": {
    "type": "multi",
    "sources": [
      {"type": "human_input", "match": "'what should we work on', 'audit this project', 'what's missing'"},
      {"type": "cron", "job": "Weekly Sprint Report (adc76c798cd4)"}
    ]
  },
  "skill": "project-discovery",
  "inputs": {
    "active_projects": "~/.hermes-teams/startup/active-projects.json (THE gatekeeper — empty = no scan)"
  },
  "steps": [
    {"step": 0, "name": "early_exit", "action": "check .driver/ exists; if no recent commits AND no new issues → skip (0 tokens)"},
    {"step": 0b, "name": "auto_init", "condition": ".driver/ missing", "action": "read AGENTS.md → README → CONTEXT.md → docs → beads; synthesize goal.md, progress.md, decisions.md, gaps.md"},
    {"step": 1, "name": "read_steering", "action": "read .driver/{goal,progress,decisions,gaps}.md"},
    {"step": 2, "name": "scan_signals", "checks": ["failing tests", "TODO/FIXME density", "stale PRs/branches", "tech debt (ponytail-audit)", "docs staleness", "git velocity"]},
    {"step": 3, "name": "cross_ref", "action": "git log vs PRD/ADRs; check implementation alignment"},
    {"step": 4, "name": "dedup_check", "action": "bd list --json; build existing issue inventory"},
    {"step": 5, "name": "file_and_update", "actions": ["bd create for concrete problems", "kanban_create [general] for decisions", "bd create -t chore for tech debt", "rewrite progress.md + gaps.md"]}
  ],
  "outputs": {
    "artifacts": [".driver/{goal,progress,decisions,gaps}.md", "reports/sprint-{date}.md (weekly)", "new bd issues"],
    "delivery": "gateway (Telegram/Discord) — project health summary, new issues, open decisions, proposed priorities"
  },
  "handoffs": [
    {"to": "specialist profiles", "via": "kanban_create [<project-tag>] card", "when": "finding warrants specialist action"},
    {"to": "operator/human", "via": "[general] kanban card on hermes-hq", "when": "decision needed"}
  ]
}
```

### Node: `po.task-hygiene`

```json
{
  "id": "po.task-hygiene",
  "title": "Task Hygiene Validator (backlog quality automation)",
  "trigger": {
    "type": "cron",
    "job": "Task Hygiene Watchdog (5421d37938f5)",
    "guard": "hygiene-guard.sh runs scan_hygiene.py first; wakes agent only on findings"
  },
  "skill": "task-hygiene-validator",
  "prerequisites": [".driver/goal.md must exist (else run project-discovery first)", "bd on PATH (~/.go/bin/bd)", ".beads/ directory"],
  "inputs": {
    "scanner_output": "JSON findings from scan_hygiene.py (orphan, unlabeled, stale, kill-candidate, duplicate-suspect)",
    "goal_context": ".driver/goal.md"
  },
  "checks": [
    {"check": 1, "name": "orphan_detection", "rule": "no parent epic and not epic itself (unless labeled chore/tech-debt/infra/docs)"},
    {"check": 2, "name": "missing_labels", "rule": "zero labels → needs type (bug/feature/chore/tech-debt/infra/docs) + priority (P0-P3)"},
    {"check": 3, "name": "goal_traceability", "rule": "trace orphan/unlabeled to goal area; if not traceable → kill-candidate"},
    {"check": 4, "name": "stale_detection", "rule": "14-29d untouched → auto-defer; 30d+ → kill-candidate"},
    {"check": 5, "name": "duplicate_detection", "rule": ">80% word overlap → duplicate-suspect"}
  ],
  "auto_actions": [
    {"action": "defer", "target": "stale 14-29d, not in_progress/blocked, no recent comments", "cmd": "bd update <id> --defer +30d", "reversible": true},
    {"action": "tag", "target": "orphans traceable to goal", "cmd": "bd label add <id> <label>; bd update <id> --parent <epic>", "reversible": true}
  ],
  "report_only": [
    {"action": "kill-candidate", "target": "30d+ untouched, no goal trace", "rule": "batch for one-click approval, NEVER close automatically"}
  ],
  "outputs": {
    "report": "hygiene report (only if findings) + .driver/gaps.md updated",
    "delivery": "gateway required (deliver=telegram/discord, NOT local)"
  },
  "handoffs": [
    {"to": "operator/human", "via": "hygiene report (kill-candidates batch)", "when": "irreversible decision needed"}
  ]
}
```

### Node: `po.project-promotion` (handoff receiver)

```json
{
  "id": "po.project-promotion",
  "title": "Project Promotion (prototype → production)",
  "trigger": {
    "type": "kanban_card",
    "match": "card from builder via project-promotion skill, assignee=product-owner, board=<slug>",
    "card_body": "Take this prototype to production. Read .context/grill/ for locked decisions..."
  },
  "skill": "dev-planning",
  "note": "project-promotion skill runs on BUILDER initially (creates structure, dispatches card to PO). PO receives the card and then runs dev-planning.",
  "inputs": {
    "project_dir": "~/projects/<slug>/",
    "context": [".context/dossier.md", ".context/grill/*.md", ".context/verification.md", "prototype/"]
  },
  "po_action": "Load dev-planning: write production spec → architect-gate (production architecture) → to-tickets (tracer-bullet beads) → dispatch via pipeline",
  "outputs": {
    "artifacts": ["PRD.md", "tracer-bullet beads", "STATUS.md (PO maintains)"],
    "downstream_trigger": "workflow engine bd ready → po.dispatch"
  },
  "handoffs": [
    {"from": "builder", "via": "promotion dispatch card", "what": "prototype + locked grill decisions"},
    {"to": "architect", "via": "design card (production architecture, not prototype stack)", "when": "dev-planning step 3"},
    {"to": "tech-lead", "via": "workflow engine dispatch (indirect)", "when": "beads ready"}
  ]
}
```

### Node: `po.escalation-sink`

```json
{
  "id": "po.escalation-sink",
  "title": "Escalation Sink (terminal node of ESCALATION_CHAIN)",
  "trigger": {
    "type": "kanban_card",
    "match": "card with title starting '[ESCALATION] Resolve block on', assignee=product-owner, created by workflow engine scanner phase"
  },
  "skill": "(none specific — general PO judgment)",
  "inputs": {
    "blocked_task_id": "string",
    "blocked_assignee": "tech-lead (always, since PO is tech-lead's escalation target)",
    "block_reason": "string (from task_events payload)"
  },
  "po_actions": [
    "kanban_show(blocked task) to understand the block",
    "Resolve → comment on blocked task → complete escalation card with 'RESOLVED: ...' (scanner auto-unblocks)",
    "Can't resolve → kanban_block(reason=..., kind='needs_input') to reach human"
  ],
  "outputs": {
    "resolution": "comment on blocked task + RESOLVED summary, OR needs_input block"
  },
  "handoffs": [
    {"to": "operator/human", "via": "kanban_block needs_input", "when": "PO cannot resolve"}
  ],
  "position_in_chain": "terminal — product-owner → None → HUMAN_REQUIRED"
}
```

### Node: `po.griller-rpc`

```json
{
  "id": "po.griller-rpc",
  "title": "Griller (adversarial interviewer for builder prototyping)",
  "trigger": {
    "type": "rpc",
    "match": "builder calls PO via grill-rpc file-based RPC"
  },
  "skill": "grill-rpc",
  "role": "PO serves as the griller subagent when builder is working the map",
  "inputs": {
    "builder_plan": "prototype plan or design from builder"
  },
  "po_action": "Relentless adversarial interview to sharpen the plan/design",
  "outputs": {
    "grill_decisions": "sharpened plan, surfaced assumptions, resolved ambiguities"
  },
  "handoffs": [
    {"to": "builder", "via": "RPC response", "what": "grill output feeds back to builder's prototype work"}
  ]
}
```

---

## Appendix: Config & Environment Facts

| Setting | Value | Source |
|---|---|---|
| Model | `glm-5.2` (zai) | config.yaml |
| Fallback provider | `deepseek` / `deepseek-v4-flash` | config.yaml |
| Context length | 1,000,000 | config.yaml |
| Reasoning effort | `ultra` (agent), `xhigh` (delegation) | config.yaml |
| Max turns | 200 (agent + delegation) | config.yaml |
| Rate limit delay | 30s | config.yaml |
| Max in-progress per profile | 3 | config.yaml |
| Dispatch stale timeout | 14,400s (4h) | config.yaml |
| Approvals mode | `off` | config.yaml |
| Enabled toolsets | hermes-cli, kanban, context_graph | config.yaml |
| Disabled toolsets | browser, delegation, web, kanban_chains | config.yaml |
| Enabled plugins | kanban_chains, context_graph, skill_enforcer | config.yaml |
| Mandatory skills (skill_enforcer) | claude-handoff, project-promotion | config.yaml |
| Active board (HQ) | `hermes-hq` | SOUL.md |

### Known issues / risks

1. **QA trigger is broken.** Phase 4 (`qa-trigger`) is commented out in the active `workflow-engine.py`. The replacement ("New Workflow Engine" job `94e735a11be6`) is erroring with "Script not found." **QA re-test cards are not being created automatically.** This is a live pipeline gap.
2. **`project-promotion` SKILL.md is not in the PO profile's skills dir.** It lives in `~/.hermes-teams/shared-skills/project-promotion/`. It's listed as mandatory by `skill_enforcer` and in the SOUL.md skill index, so it resolves via shared skills — but it's worth noting the location.
3. **Two workflow engine crons run every minute simultaneously.** The active one (`5838e048ae7f`) works; the new one (`94e735a11be6`) errors every tick (389 error completions). The erroring job should be disabled or the target script created.
4. **`delegation` toolset is disabled** in config but `kanban_chains` plugin is enabled with `allow_tool_override: false`. The `kanban_chains` tool is available to PO via the plugin despite the toolset being in `disabled_toolsets`.
