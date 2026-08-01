# Comprehensive Per-Profile Migration Plan

> **Generated:** 2026-07-31
> **Sources:** 8 profile diagnoses (`docs/profile-diagnoses/`), `MIGRATION.md`, `README.md`, `profiles/product-owner/scripts/workflow-engine.py`
> **Goal:** Migrate orchestration (cron/script/manual) into declarative engine JSON templates while preserving skills as agent behavior.

---

## 0. The Core Principle (read this first)

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│            SKILLS (stay)            │        ENGINE TEMPLATES (move)       │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ What an agent does INSIDE a card    │ Which cards get created, in what    │
│ (behavior, judgment, craft)         │ order, with what conditions         │
│                                     │ (orchestration)                     │
│                                     │                                     │
│ project-kickoff, dev-dispatch,      │ bead_ready → dispatch card,          │
│ adversarial-review, live-testing,   │ card_completed(PASS) → QA card,      │
│ debug-loop, healthcheck, etc.       │ blocked → escalation card            │
│                                     │                                     │
│ Loaded into the agent's context     │ Runs on the 1-min engine tick        │
│ when the card arrives               │ before any agent runs                │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

**The test:** If the logic decides *which card to create next* or *which profile to wake*, it's engine orchestration. If the logic decides *how to do the work once woken*, it's a skill.

**The exception:** Skills that call `kanban_create`/`kanban_chains` internally (e.g., `dev-dispatch`, `qa-protocol`, `loop_engine`-driven skills) are doing *profile-managed dynamic orchestration*. These stay as skills — the engine handles them via the **static-dynamic coexistence pattern** (engine dispatches a parent card; the profile creates children via its skill; the engine waits for the parent to reach `done`).

---

## 1. Migration Overview — All Tasks Classified

Legend: ✅ migrate to engine | 🔄 profile-managed (dynamic, stays in skill) | 📝 stays as agent skill | ⚙️ stays as cron script (no_agent) | ❌ cannot migrate (requires human judgment) | 🔴 broken — must fix before/during migration

### Product Owner (PO)

| Task | Current mechanism | Target | Template/Phase |
|------|-------------------|--------|----------------|
| Bead-sync (kanban→bd status) | `phase_bead_sync` cron | ⚙️ keep as script | — |
| Dispatch ready beads → PO card | `phase_dispatch` cron | ✅ engine | `bead-dispatch.json` |
| Bug bead → debugger (bypass PO) | `phase_dispatch` (inline) | ✅ engine | `bug-router.json` |
| Wayfinder bead → specialist routing | `phase_dispatch` (inline) | ✅ engine | `wayfinder-router.json` |
| Human-flagged bead → HQ card | `phase_human_escalations` cron | ✅ engine | `human-escalation.json` |
| Blocked-task scanner → escalation | `scan_board` cron | ✅ engine | `blocked-escalation.json` |
| QA trigger (verifier PASS → QA card) | `phase_qa_trigger` (DISABLED) | ✅ engine | `qa-loop.json` *(already exists)* |
| Dev-dispatch (bead→tech-lead cards) | `dev-dispatch` skill inside card | 🔄 profile-managed | — |
| Project-kickoff | `project-kickoff` skill | 📝 skill | — |
| Dev-planning | `dev-planning` skill | 📝 skill | — |
| Project-discovery | `project-discovery` skill | 📝 skill | — |
| Task-hygiene-validator | `task-hygiene-validator` skill | 📝 skill | — |
| Project-promotion | `project-promotion` skill | 📝 skill | — |
| Weekly sprint report | cron (agent prompt) | 📝 skill (triggered by cron) | — |
| Griller RPC | `grill-rpc` skill | 📝 skill | — |
| Escalation sink (resolve tech-lead blocks) | PO judgment inside ESCALATION card | 📝 skill | — |

### Architect

| Task | Current mechanism | Target |
|------|-------------------|--------|
| Design-council converge loop | `design-council` skill + `loop_engine` plugin | 🔄 profile-managed (loop_engine) |
| ADR authorship | `design-council` / `architect-gate` skill | 📝 skill |
| Triage (T0-T3) | `architect-gate` skill | 📝 skill |
| Design consult RPC (PO questions) | `design-consult-rpc` skill | 📝 skill |
| Researcher/peer fan-out | `loop_engine` internal `kanban_chains` | 🔄 profile-managed |
| Gate cards to human (T2 approval) | `design-council` skill blocks card | 🔄 profile-managed |

**No engine migration needed for architect.** The architect is triggered by kanban cards created by PO (via `architect-gate` skill) and operates entirely within its card using `loop_engine`. The engine only needs to observe the parent card status.

### Tech-Lead

| Task | Current mechanism | Target |
|------|-------------------|--------|
| beads-watchdog.sh (bead-ready → TL card) | 🔴 NOT scheduled cron script | ✅ engine (replaces dormant watchdog) |
| Discover phase | `loops-engineering` skill | 📝 skill |
| Plan phase (grill → PRD → contract → beads) | `loops-engineering` skill | 📝 skill |
| Execute phase (`kanban_chains` dev+verifier) | `loops-engineering` skill | 🔄 profile-managed |
| Validate phase (wait for verifier) | `loops-engineering` skill | 🔄 profile-managed |
| Iterate phase (ESCALATE routing) | `loops-engineering` skill | 📝 skill |
| Completion (bd close, journal, reflection) | `loops-engineering` skill | 📝 skill |
| beads-watchdog.sh (zero-token bridge) | dormant cron script | ✅ engine (or retire — PO dev-dispatch covers this) |

**Note:** The PO's `dev-dispatch` skill already creates tech-lead cards from ready beads. The `beads-watchdog.sh` was a redundant second bridge that is **not scheduled**. Migration decision: **retire the watchdog**, let PO's dispatch (now engine-driven) be the single bridge.

### Developer

| Task | Current mechanism | Target |
|------|-------------------|--------|
| Cold start → harness invocation → gates → trace → complete | `developer-loop` skill | 📝 skill |
| Harness recipe selection | `developer-loop` skill | 📝 skill |
| Warm resume on fix cards | `developer-loop` skill | 📝 skill |
| Budget enforcement | `developer-loop` skill | 📝 skill |
| Block on transient/needs_input | `developer-loop` skill | 📝 skill |

**No engine migration needed for developer.** The developer is purely card-driven with zero orchestration logic — it executes whatever card arrives and returns metadata. All orchestration (creating dev cards) belongs to tech-lead.

### Verifier

| Task | Current mechanism | Target |
|------|-------------------|--------|
| Adversarial review (3-stage pipeline) | `adversarial-review` skill | 📝 skill |
| `[probe]` fan-out (Stage 2) | `kanban_chains` inside skill | 🔄 profile-managed |
| FAIL → fix card creation | `kanban_create` inside skill | 🔄 profile-managed |
| Merge protocol (slot/rebase/rerun/merge) | `merge-protocol.md` reference | 📝 skill |
| DoD verdict (for loop_engine) | `dod-verdict` skill | 📝 skill |
| Verdict stamping (PASS/FAIL/ESCALATE) | `adversarial-review` skill | 📝 skill |

**No engine migration needed for verifier.** The verifier's fan-out and fix-card creation are profile-managed dynamic orchestration. The engine observes the parent review card status.

### Debugger

| Task | Current mechanism | Target |
|------|-------------------|--------|
| Debug converge loop (3-phase) | `debug-loop` skill + `loop_engine` | 🔄 profile-managed |
| Reproduce → hypothesize → falsify → converge | `loop_engine` phases | 🔄 profile-managed |
| Exit B (architect gate escalation) | `debug-loop` skill creates card | 🔄 profile-managed |
| HITL block (no repro) | `debug-loop` skill blocks card | 🔄 profile-managed |
| Merge gate handoff (→ verifier card) | `debug-loop` skill creates card | 🔄 profile-managed |

**No engine migration needed for debugger.** The debugger uses `loop_engine` for its entire converge loop. All child-card creation is profile-managed. Engine observes the parent debugger card.

### QA

| Task | Current mechanism | Target |
|------|-------------------|--------|
| QA card auto-created on verifier/debugger merge | `phase_qa_trigger` (DISABLED) / `qa-loop.json` | ✅ engine |
| 8-phase test execution | `live-testing` skill | 📝 skill |
| Swarm creation (medium/large) | `qa-protocol` skill + `kanban_chains` | 🔄 profile-managed |
| Triage report → tech-lead | `qa-protocol` skill creates card | 🔄 profile-managed |
| Bug bead filing | `live-testing` skill | 📝 skill |
| Verdict + report | `live-testing` skill | 📝 skill |
| Critical findings → block | `qa-protocol` skill blocks card | 🔄 profile-managed |
| Re-test loop (fixes merge) | `live-testing` skill | 📝 skill |

**Engine migration:** The QA trigger (verifier PASS → QA card) is the one engine migration. Already migrated via `qa-loop.json`. **BUT** it's currently broken because the engine cron job (`94e735a11be6`) points to a non-existent script. See §6 Broken Systems.

### Ops / Scout / Researcher

| Task | Current mechanism | Target |
|------|-------------------|--------|
| Ops healthcheck (4 checks) | `healthcheck.sh` no_agent cron | ⚙️ keep as script |
| Cron store backup | `cron-store-backup.sh` no_agent cron | ⚙️ keep as script |
| Session archiver | `session-archiver.py` no_agent cron | ⚙️ keep as script |
| Env drift repair | `dev-env-setup` skill | 📝 skill |
| Tool evaluation | `dev-env-setup` skill | 📝 skill |
| Scout daily scan (8×/day) | `scout-guard.sh` → agent → `research-scout` skill | 🔴 broken (DeepSeek key missing) — keep as cron+skill, FIX |
| Scout Telegram delivery | `research-scout` skill | 🔴 broken — FIX in skill |
| Scout → researcher task filing | `kanban_create` inside skill | 🔄 profile-managed |
| Deep research (wiki note writing) | `deep-research` / researcher skills | 📝 skill (skills currently DISABLED — FIX) |

**No engine migration needed for ops/scout/researcher.** The ops cron jobs are zero-token watchdog scripts — they should stay as cron scripts (the engine is a kanban orchestrator, not a system monitor). The scout is broken due to credentials/config, not architecture — fixing it is an ops task, not an engine migration.

---

## 2. Summary: What Actually Migrates

Only **6 engine templates** are needed. Five replace `workflow-engine.py` phases; the QA loop already exists.

| # | Template | Replaces | Engine trigger | Status |
|---|----------|----------|----------------|--------|
| 1 | `qa-loop.json` | `phase_qa_trigger` | `card_completed` (verifier, PASS) | ✅ Written, ⚠️ engine cron broken |
| 2 | `bead-dispatch.json` | `phase_dispatch` (feature beads) | `bead_ready` (type=feature/task) | 🔲 To write |
| 3 | `bug-router.json` | `phase_dispatch` (bug routing) | `bead_ready` (type=bug) | 🔲 To write |
| 4 | `wayfinder-router.json` | `phase_dispatch` (wayfinder labels) | `bead_ready` (label=wayfinder:*) | 🔲 To write |
| 5 | `human-escalation.json` | `phase_human_escalations` | `bead_ready` (label=human) | 🔲 To write |
| 6 | `blocked-escalation.json` | `scan_board` | `card_completed` (status=blocked) or manual | 🔲 To write |

**Templates that are NOT needed** (would be anti-patterns):
- Developer, verifier, debugger, architect templates — these profiles are card-driven; their internal orchestration (`kanban_chains`, `loop_engine`) is profile-managed dynamic work. The engine observes parent card status only.
- Tech-lead template — tech-lead cards are created by PO's `dev-dispatch` skill, not the engine directly. Once the engine creates the dispatch card, PO's skill handles the rest.
- QA swarm template — the QA swarm is created by `qa-protocol` skill via `kanban_chains`, not the engine.
- Ops healthcheck template — system monitoring is not kanban orchestration.

---

## 3. Exact JSON Templates

### 3.1 `bead-dispatch.json` — Ready beads → PO dispatch card

**Replaces:** `phase_dispatch()` — the feature/task bead path (bugs and wayfinder excluded, handled by separate templates).

**Logic migrated:** Filter ready beads → skip `gt:slot`, epics, wayfinder labels → check for existing card (`bead-<id>`) → if no active PO dispatch card → create one `[dispatch]` card.

```json
{
  "id": "bead-dispatch",
  "name": "Bead Dispatch — ready feature/task beads → PO dispatch card",
  "description": "When bd ready returns feature/task beads (excluding bugs, wayfinder, gt:slot), create a single PO dispatch card listing all ready beads. PO then runs dev-dispatch to create tech-lead cards. One active dispatch card per board.",
  "trigger": {
    "source": "bead_ready",
    "condition": {
      "type": "feature",
      "not_labels": ["gt:slot", "wayfinder:grilling", "wayfinder:prototype", "wayfinder:map", "venture:brief", "wayfinder:research", "wayfinder:task", "wayfinder:architecture", "human"]
    }
  },
  "nodes": [
    {
      "id": "po_dispatch",
      "profile": "product-owner",
      "skill": "dev-dispatch",
      "priority": 20,
      "body_template": "## Ready beads to dispatch\n\nThe following beads are ready for tech-lead cards:\n\n- Bead: `${trigger.bead_id}` — ${trigger.bead_title}\n\nRun `dev-dispatch` skill to create tech-lead cards (one per bead). Card carries ONLY bead ID + PRD pointer. Use `--idempotency-key bead-${trigger.bead_id}` for dedup. Never set skills on dispatch card. Never create dev/verifier cards — tech-lead does via kanban_chains.",
      "input": {
        "schema": {
          "required": ["bead_id"]
        },
        "sources": {
          "bead_id": "${trigger.bead_id}",
          "bead_title": "${trigger.bead_title}"
        }
      },
      "output": {
        "schema": {
          "type": "object",
          "properties": {
            "cards_created": {"type": "integer"},
            "bead_ids": {"type": "array", "items": {"type": "string"}}
          }
        }
      }
    }
  ]
}
```

**Notes:**
- The `not_labels` condition filters out bugs (handled by `bug-router.json`), wayfinder tickets (handled by `wayfinder-router.json`), and human-flagged beads (handled by `human-escalation.json`).
- The old cron collected ALL ready beads into one `[dispatch] N ready bead(s)` card. The engine's `bead_ready` trigger fires per-bead. **Design choice:** each bead creates its own dispatch card with `--idempotency-key bead-<id>`, which is exactly what `dev-dispatch` does internally. This is MORE correct — PO gets one card per bead, not a batch that must be processed atomically.
- **Engine enhancement needed:** The `bead_ready` trigger condition needs `not_labels` support to exclude beads by label. If the engine doesn't support `not_labels` yet, the filtering must happen in the trigger condition or be added as a feature.

---

### 3.2 `bug-router.json` — Bug beads → debugger (bypasses PO)

**Replaces:** `dispatch_bug_to_debugger()` inside `phase_dispatch`.

**Logic migrated:** Ready beads with `issue_type=bug` or `bug` in labels → create `[auto] bug:` card assigned to debugger, skipping PO entirely.

```json
{
  "id": "bug-router",
  "name": "Bug Router — bug beads → debugger (bypasses PO)",
  "description": "When bd ready returns a bug bead, route it directly to the debugger profile. Bugs never go through PO dispatch or tech-lead — they go straight to diagnosis. Idempotent per bead.",
  "trigger": {
    "source": "bead_ready",
    "condition": {
      "type": "bug",
      "or_labels_contains": "bug"
    }
  },
  "nodes": [
    {
      "id": "dispatch_bug",
      "profile": "debugger",
      "skill": "debug-loop",
      "priority": 30,
      "body_template": "## Bug ${trigger.bead_id} — ${trigger.bead_title}\n\n${trigger.bead_description}\n\n## Resolve protocol\n\nRun your `debug-loop` doctrine (loops-engineering). Diagnose the root cause, ship a minimal fix via developer cards, falsify via verifier, converge with a post-mortem (RCA). Close the bead with `bd close ${trigger.bead_id}` when done.\n\n**Bead ID:** `${trigger.bead_id}`\n**Project:** `${trigger.project_dir}`",
      "idempotency_key_template": "bead-${trigger.bead_id}",
      "input": {
        "schema": {
          "required": ["bead_id", "bead_title"]
        },
        "sources": {
          "bead_id": "${trigger.bead_id}",
          "bead_title": "${trigger.bead_title}",
          "bead_description": "${trigger.bead_description}",
          "project_dir": "${trigger.project_dir}"
        }
      },
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {
            "verdict": {"type": "string", "enum": ["fixed", "escalated-design", "blocked-hitl"]},
            "bug_id": {"type": "string"},
            "branch_name": {"type": "string"},
            "worktree_path": {"type": "string"},
            "regression_test": {"type": "string"},
            "postmortem_path": {"type": "string"},
            "root_cause_summary": {"type": "string"}
          }
        }
      }
    }
  ]
}
```

**Notes:**
- The `or_labels_contains` condition catches beads where `issue_type=task` but `bug` appears in labels (a known bd quirk). If the engine doesn't support OR-label matching, a simpler approach: trigger on `type=bug` only, and add a second template for `label=bug` with the same node.
- Dedup via `idempotency_key_template: "bead-${trigger.bead_id}"` — this is the same key the old cron used, ensuring no duplicate cards during transition.

---

### 3.3 `wayfinder-router.json` — Wayfinder beads → specialist by label

**Replaces:** `dispatch_wayfinder_ticket()` inside `phase_dispatch`.

**Logic migrated:** Ready beads with wayfinder labels → route by label: `wayfinder:research`→scout, `wayfinder:task`→ops, `wayfinder:architecture`→architect. Skip `wayfinder:grilling`, `wayfinder:prototype`, `wayfinder:map`, `venture:brief`.

This template uses **explicit edges** with label conditions to route to the correct specialist:

```json
{
  "id": "wayfinder-router",
  "name": "Wayfinder Router — wayfinder beads → specialist by label type",
  "description": "Routes wayfinder tickets directly to the specialist that can resolve them. wayfinder:research → scout, wayfinder:task → ops, wayfinder:architecture → architect. Skips HITL-substitute types (grilling, prototype, map, venture:brief).",
  "trigger": {
    "source": "bead_ready",
    "condition": {
      "label_any": ["wayfinder:research", "wayfinder:task", "wayfinder:architecture"]
    }
  },
  "nodes": [
    {
      "id": "route_research",
      "profile": "scout",
      "skill": "research-scout",
      "body_template": "## Wayfinder ticket ${trigger.bead_id} — ${trigger.bead_title}\n\nMap: `${trigger.bead_parent}` (the venture's wayfinding map).\n\n${trigger.bead_description}\n\n## Resolve protocol (run bd from ${trigger.project_dir})\n\n1. Investigate (AFK). Long artifacts go to a file; link them.\n2. Record resolution: `bd comment ${trigger.bead_id} \"<answer + citation>\"`\n3. Append to map's Decisions-so-far index via `bd update`.\n4. Complete card with answer as summary. Do NOT `bd close` — bead-sync closes it.",
      "condition": "${trigger.bead_label} == 'wayfinder:research'",
      "idempotency_key_template": "bead-${trigger.bead_id}"
    },
    {
      "id": "route_task",
      "profile": "ops",
      "skill": "dev-env-setup",
      "body_template": "## Wayfinder ticket ${trigger.bead_id} — ${trigger.bead_title}\n\nMap: `${trigger.bead_parent}`\n\n${trigger.bead_description}\n\n## Resolve protocol (run bd from ${trigger.project_dir})\n\n1. Investigate and fix the environment issue.\n2. Record resolution: `bd comment ${trigger.bead_id} \"<answer>\"`\n3. Append to map's Decisions-so-far index.\n4. Complete card with answer as summary.",
      "condition": "${trigger.bead_label} == 'wayfinder:task'",
      "idempotency_key_template": "bead-${trigger.bead_id}"
    },
    {
      "id": "route_architecture",
      "profile": "architect",
      "skill": "architect-gate",
      "body_template": "## Wayfinder ticket ${trigger.bead_id} — ${trigger.bead_title}\n\nMap: `${trigger.bead_parent}`\n\n${trigger.bead_description}\n\n## Resolve protocol — architecture (run bd from ${trigger.project_dir})\n\n1. Answer in gate posture: weigh alternatives before deciding.\n2. Record as ADR in `${trigger.project_dir}/docs/adr/` per adr-convention.md.\n3. Resolution: `bd comment ${trigger.bead_id} \"RESOLVED: <gist> — see ADR-NNN\"`\n4. Append to map's Decisions-so-far index.\n5. Complete with metadata {\"adr\": \"ADR-NNN\", \"posture\": \"gate\"}. Do NOT `bd close`.",
      "condition": "${trigger.bead_label} == 'wayfinder:architecture'",
      "idempotency_key_template": "bead-${trigger.bead_id}"
    }
  ],
  "edges": [
    {"from": "route_research", "to": null},
    {"from": "route_task", "to": null},
    {"from": "route_architecture", "to": null}
  ]
}
```

**Notes:**
- The three routing nodes are mutually exclusive (only one label matches per bead). Each has a `condition` checking the label. Only one will fire; the other two will be SKIPPED.
- The `idempotency_key_template` is shared (`bead-<id>`) across all three nodes — but since only one node fires per trigger, there's no conflict.
- **Engine enhancement needed:** The `trigger.condition.label_any` matches any of the listed labels. The node-level `condition` then checks which specific label matched. The engine needs to expose `trigger.bead_label` in the context for this to work.

---

### 3.4 `human-escalation.json` — Human-flagged beads → HQ card

**Replaces:** `phase_human_escalations()`.

**Logic migrated:** Beads with `human` label that aren't closed → create `[ESCALATION] human answer needed:` card on `hermes-hq` board, assignee=default, idempotent per bead.

```json
{
  "id": "human-escalation",
  "name": "Human Escalation — human-flagged beads → operator HQ card",
  "description": "When a bead is tagged 'human' (set by any agent that escalates), create a card on the hermes-hq board for the human operator. One card per bead, idempotent. Response via `bd human respond <bead_id>`.",
  "trigger": {
    "source": "bead_ready",
    "condition": {
      "label": "human",
      "status_not": "closed"
    }
  },
  "nodes": [
    {
      "id": "create_hq_card",
      "profile": "default",
      "board": "hermes-hq",
      "priority": 10,
      "body_template": "## Human-flagged bead: ${trigger.bead_id}\n\n${trigger.bead_description}\n\nAnswer with: `bd human respond ${trigger.bead_id}` (comments + closes the bead) from ${trigger.project_dir}. Board: ${trigger.board}.",
      "idempotency_key_template": "bead-human-${trigger.bead_id}",
      "input": {
        "schema": {
          "required": ["bead_id"]
        },
        "sources": {
          "bead_id": "${trigger.bead_id}",
          "bead_description": "${trigger.bead_description}",
          "project_dir": "${trigger.project_dir}",
          "board": "${trigger.board}"
        }
      },
      "output": {
        "schema": {
          "type": "object",
          "properties": {
            "resolution": {"type": "string"}
          }
        }
      }
    }
  ]
}
```

**Notes:**
- The `board` field on the node overrides the default board — this card must go to `hermes-hq`, not the project board.
- **Engine enhancement needed:** `bead_ready` trigger needs to fire for beads with the `human` label even if they're not "ready" in the bd sense (they may be `open` status). The `status_not` condition filters out already-closed beads.
- The old cron ran `bd list --all --label human` — it scanned ALL beads, not just ready ones. The engine's `bead_ready` trigger may need a variant `bead_labeled` or `bead_scan` that matches by label regardless of ready status.

---

### 3.5 `blocked-escalation.json` — Blocked tasks → escalation chain

**Replaces:** `scan_board()`.

**Logic migrated:** Tasks with `status=blocked` → check for HUMAN_REQUIRED comment → check for resolved escalation → check for existing active escalation → create `[ESCALATION] Resolve block on <task>` card assigned to `ESCALATION_CHAIN[assignee]`, or post `HUMAN_REQUIRED` comment if no higher profile.

```json
{
  "id": "blocked-escalation",
  "name": "Blocked Task Escalation — escalate blocked tasks up the chain",
  "description": "Scans all project boards for blocked tasks. For each: skip if assignee=default/empty, skip if HUMAN_REQUIRED comment exists, check if escalation resolved (unblock), check if escalation already active (skip), else create escalation card to the next profile in the chain. Terminal profiles (PO) → HUMAN_REQUIRED comment.",
  "trigger": {
    "source": "task_blocked",
    "condition": {
      "assignee_not": ["default", ""],
      "no_comment_contains": "HUMAN_REQUIRED"
    }
  },
  "nodes": [
    {
      "id": "check_resolved",
      "type": "task",
      "profile": "_engine_internal",
      "body_template": "Check if a done task with title '[ESCALATION] %{trigger.task_id}%' exists with run summary starting 'RESOLVED:'. If yes → unblock the original task. If no → proceed to route_escalation.",
      "description": "Internal check — does NOT create a card. Engine evaluates SQL: SELECT 1 FROM tasks WHERE title LIKE '[ESCALATION] %{task_id}%' AND status='done' AND run.summary LIKE 'RESOLVED:%'"
    },
    {
      "id": "route_escalation",
      "type": "task",
      "body_template": "Route based on assignee:\n- developer/verifier/debugger/qa → tech-lead\n- tech-lead → product-owner\n- product-owner → HUMAN_REQUIRED comment (no card)",
      "depends_on": ["check_resolved"],
      "condition": "${nodes.check_resolved.output.resolved} == false"
    },
    {
      "id": "escalate_to_techlead",
      "profile": "tech-lead",
      "priority": 10,
      "body_template": "## Blocked: ${trigger.task_id}\n\n**Assignee**: ${trigger.task_assignee}\n**Reason**: ${trigger.block_reason}\n\n1. `kanban_show(task_id=\"${trigger.task_id}\")`\n2. Resolve → comment on blocked task → complete with `RESOLVED: ...`\n3. Can't resolve → block this card (needs_input)",
      "depends_on": ["route_escalation"],
      "condition": "${trigger.task_assignee} in ['developer', 'verifier', 'debugger', 'qa']"
    },
    {
      "id": "escalate_to_po",
      "profile": "product-owner",
      "priority": 10,
      "body_template": "## Blocked: ${trigger.task_id}\n\n**Assignee**: ${trigger.task_assignee}\n**Reason**: ${trigger.block_reason}\n\n1. `kanban_show(task_id=\"${trigger.task_id}\")`\n2. Resolve → comment on blocked task → complete with `RESOLVED: ...`\n3. Can't resolve → block this card (needs_input). PO is terminal — this reaches the human.",
      "depends_on": ["route_escalation"],
      "condition": "${trigger.task_assignee} == 'tech-lead'"
    },
    {
      "id": "human_required",
      "type": "task",
      "profile": "_engine_internal",
      "body_template": "Post comment on task: HUMAN_REQUIRED: No higher profile for ${trigger.task_assignee}. Author: board-scanner.",
      "depends_on": ["route_escalation"],
      "condition": "${trigger.task_assignee} == 'product-owner'"
    }
  ]
}
```

**Notes:**
- **This is the most complex migration.** The old scanner runs sophisticated SQL queries (resolved-escalation detection, existing-escalation dedup, block-reason extraction). 
- **Engine enhancement needed:** A new trigger source `task_blocked` (fires when a task transitions to `blocked` status). The existing `card_completed` trigger fires on `done`; this needs the inverse.
- The `check_resolved` and `human_required` nodes are marked `profile: "_engine_internal"` — these are SQL operations the engine performs directly (unblocking, commenting) without waking an agent. If the engine doesn't support internal action nodes, these must be implemented as engine extensions or kept as a residual cron script.
- **Fallback:** If the trigger model proves too complex, this phase can remain a cron script. The scanner is pure SQL + kanban CLI calls — it's well-suited to staying as a `no_agent` script.

---

### 3.6 `qa-loop.json` — Already written (verify correctness)

**Replaces:** `phase_qa_trigger()` (DISABLED in old cron).

**Status:** Template exists at `templates/qa-loop.json`. Content verified correct against the old cron logic. The trigger matches:
- `assignee: "verifier"` 
- `metadata.verdict: "PASS"`
- `title_not_prefix: "[probe]"` (excludes probe cards)
- Excludes `verify t_` sub-review cards

**Issue:** The old cron had a **two-signal AND gate** (verifier PASS AND git HEAD changed AND code files in diff). The engine template only checks the verdict. This means the engine may fire QA cards on verifier PASS even when no merge occurred (e.g., verifier reviewed but didn't merge). **Recommendation:** Add `metadata.merged: true` to the trigger condition, set by the verifier when it actually merges. This is a verifier skill update, not an engine change.

---

## 4. What Cannot Be Migrated (and Why)

| Task | Profile | Why it stays |
|------|---------|--------------|
| `project-kickoff` (grill → spec → architect → tickets) | PO | Human-in-the-loop planning. Requires interactive dialogue with the user. Not triggered by system state. |
| `dev-planning` (feature discussion → PRD → architect → beads) | PO | Same — interactive human dialogue. |
| `project-discovery` (scan for signals, file findings) | PO | Requires agent judgment to cross-reference git log vs PRD, assess TODO density, file nuanced findings. Too subjective for template. |
| `task-hygiene-validator` (orphan/stale/duplicate detection) | PO | The scanner (`scan_hygiene.py`) could be engine-triggered, but the *actions* (defer, tag, batch kill-candidates) require judgment. The zero-token guard (`hygiene-guard.sh`) stays as cron. |
| `architect-gate` design decisions | Architect | Requires deep reasoning, alternative comparison, ADR authorship. Triggered by PO's `dev-planning` skill, not system state. |
| `loops-engineering` (discover → plan → execute → validate → iterate) | Tech-lead | The full 5-phase loop is profile-managed dynamic orchestration. `loop_engine` handles the converge loop; `kanban_chains` handles dev+verifier dispatch. The engine only needs to see the parent card reach `done`. |
| `developer-loop` (harness invocation, gates, trace) | Developer | Pure execution. No orchestration decisions. |
| `adversarial-review` (3-stage fan-out, merge) | Verifier | Profile-managed dynamic orchestration (`kanban_chains` for probes, fix-card creation, merge protocol). |
| `debug-loop` (reproduce → hypothesize → falsify → converge) | Debugger | `loop_engine`-driven. All child-card creation is profile-managed. |
| `live-testing` (8-phase test spine) | QA | Pure execution. Swarm creation is profile-managed via `qa-protocol`. |
| `healthcheck.sh` / `cron-store-backup.sh` / `session-archiver.py` | Ops | Zero-token system monitoring scripts. Not kanban orchestration. Correct as `no_agent` cron. |
| `research-scout` daily scan | Scout | Scheduled content scanning + editorial judgment. Not kanban-triggered. Stays as cron + skill (must FIX credentials). |
| Deep research / wiki note writing | Researcher | Requires agent to read sources, synthesize knowledge. Task-driven via kanban, not cron. |
| `grill-rpc` / `design-consult-rpc` | PO / Architect | File-based RPC between profiles. Adversarial interview requires agent reasoning. |
| Escalation resolution (when PO receives ESCALATION card) | PO | Requires judgment to investigate the block, resolve or escalate to human. |

---

## 5. Dependency Graph

```
                    ┌──────────────────────────┐
                    │  FIX BROKEN ENGINE CRON   │ ← PREREQUISITE (§6)
                    │  (job 94e735a11be6)       │
                    └─────────────┬────────────┘
                                  │
                    ┌─────────────▼────────────┐
                    │  FIX ENGINE TICK SCRIPT   │
                    │  (main.py path correct)   │
                    └─────────────┬────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
    ┌─────────────────┐ ┌──────────────────┐ ┌────────────────┐
    │ PHASE 1: QA     │ │ PHASE 2: Bug      │ │ PHASE 3:        │
    │ (qa-loop.json)  │ │ Router            │ │ Wayfinder       │
    │ LOWEST RISK     │ │ LOW RISK          │ │ Router          │
    │ (already        │ │ (simple trigger)  │ │ LOW RISK        │
    │  written)       │ │                   │ │                 │
    └────────┬────────┘ └────────┬──────────┘ └────────┬────────┘
             │                   │                     │
             └───────────────────┼─────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  PHASE 4: Bead Dispatch   │ ← depends on 2,3
                    │  (bead-dispatch.json)     │   (routing templates
                    │  MEDIUM RISK              │    must exist first
                    └────────────┬────────────┘    so non-feature beads
                                 │                  are filtered out)
                    ┌────────────▼────────────┐
                    │  PHASE 5: Human           │ ← independent of 4,
                    │  Escalation               │   but lower priority
                    │  MEDIUM RISK              │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  PHASE 6: Blocked         │ ← HIGHEST RISK
                    │  Escalation               │   (most complex logic,
                    │  HIGH RISK                │    may stay as cron)
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  PHASE 7: Retire Old      │ ← after ALL phases
                    │  Cron (workflow-engine.py)│   verified in prod
                    │  for 30+ days             │
                    └─────────────────────────┘

INDEPENDENT (no dependency on engine migration):
  - FIX scout cron (DeepSeek key + Telegram config) — ops task
  - FIX researcher skills (enable disabled skills) — config task
  - RETIRE beads-watchdog.sh (PO dispatch covers it) — cleanup task
```

### Dependency Details

| Phase | Depends on | Why |
|-------|-----------|-----|
| Phase 1 (QA loop) | Fix engine cron | The template exists but the engine isn't running |
| Phase 2 (Bug router) | Fix engine cron | All templates need the engine running |
| Phase 3 (Wayfinder router) | Fix engine cron | Same |
| Phase 4 (Bead dispatch) | Phases 2 + 3 | The dispatch trigger must exclude bugs and wayfinder beads. If those routing templates don't exist yet, the dispatch template would catch ALL beads including bugs — causing double-routing. **Mitigation:** the `not_labels` filter in the trigger handles this, so technically independent. But deploying in order reduces confusion. |
| Phase 5 (Human escalation) | None (independent) | This is a separate trigger (`label=human`) |
| Phase 6 (Blocked escalation) | Phases 1-5 stable | Highest complexity. Only migrate after the engine has proven stable for simpler templates. |
| Phase 7 (Retire old cron) | ALL phases verified | Keep old cron running as backup during transition. Only retire after 30+ days of stable engine operation. |

---

## 6. Broken Systems (Must Fix Before Migration)

These must be resolved BEFORE or DURING the migration. They block specific phases.

### 6.1 Engine cron job broken — `94e735a11be6`

| Field | Value |
|-------|-------|
| **Job** | "New Workflow Engine — tick" |
| **Schedule** | `* * * * *` (every min) |
| **Script** | `startup/scripts/workflow_engine/main.py` |
| **Error** | "Script not found" |
| **Status** | 389 completions, then started erroring |
| **Impact** | ALL engine templates are dead. `qa-loop.json` exists but never fires. |

**Fix:** The cron job points to a path that doesn't resolve. The engine lives at `~/.hermes-teams/startup/scripts/workflow_engine/main.py` relative to the home directory, but the cron's working directory or path resolution is wrong.

**Resolution:** Fix the cron job's `command` to use the absolute path:
```bash
python3 ~/.hermes-teams/startup/scripts/workflow_engine/main.py tick
```

**Risk:** LOW. This is a path fix, not a logic change.

---

### 6.2 Scout cron broken — DeepSeek API key missing

| Field | Value |
|-------|-------|
| **Job** | scout-guard.sh → agent prompt |
| **Error** | `RuntimeError: No usable credentials found for provider 'deepseek'` |
| **Impact** | No AI frontier scanning. No deep-research tasks filed for researcher. |

**Fix:** Either set `DEEPSEEK_API_KEY` in the environment, or switch the scout cron to use `glm-5.2` (zai) which is the config default and has working credentials.

**Not blocked by engine migration.** This is an ops/credentials task.

---

### 6.3 Scout Telegram delivery broken

| Field | Value |
|-------|-------|
| **Error** | `platform 'telegram' not configured/enabled` |
| **Impact** | Even if scout ran, digests wouldn't deliver. |

**Fix:** Configure Telegram in the gateway settings, or switch delivery to a working channel.

**Not blocked by engine migration.** Ops/config task.

---

### 6.4 Researcher skills disabled

| Field | Value |
|-------|-------|
| **Disabled skills** | `deep-research`, `llm-wiki`, `obsidian`, `obsidian-vault` |
| **Impact** | SOUL.md describes writing Obsidian wiki notes, but enabling skills are off. Researcher can't do its core job. |

**Fix:** Re-enable the disabled skills in researcher's `config.yaml`.

**Not blocked by engine migration.** Config task.

---

## 7. Risk Assessment & Rollback Strategy

### Per-Template Risk Matrix

| Template | Risk | Reason | Rollback |
|----------|------|--------|----------|
| `qa-loop.json` | **LOW** | Single-node template, trigger is well-defined (verifier PASS), already written and tested. The old cron equivalent was simple. | Re-enable `phase_qa_trigger` in old cron (uncomment lines 684-687). |
| `bug-router.json` | **LOW** | Simple trigger (bead type=bug), single node, idempotent key matches old cron. Bugs currently route correctly via old cron. | Old cron's `dispatch_bug_to_debugger()` continues running. |
| `wayfinder-router.json` | **LOW-MEDIUM** | Multi-node conditional routing (3 paths). Slightly more complex but each path is simple. The label-matching condition needs engine support. | Old cron's `dispatch_wayfinder_ticket()` continues running. |
| `bead-dispatch.json` | **MEDIUM** | Replaces the core dispatch loop. If this breaks, no new work enters the pipeline. The trigger condition (`not_labels`) must correctly exclude bugs/wayfinder/human beads, or PO gets cards for bugs that should go to debugger. | Old cron's `phase_dispatch()` continues running. The idempotency keys match (`bead-<id>`), so there's no double-dispatch risk during transition. |
| `human-escalation.json` | **MEDIUM** | Requires the engine to scan beads by label, not just `bd ready`. The old cron ran `bd list --all --label human`. If the engine's `bead_ready` trigger doesn't support label-only scanning (regardless of ready status), this needs a new trigger type. | Old cron's `phase_human_escalations()` continues running. |
| `blocked-escalation.json` | **HIGH** | Most complex logic: SQL queries for resolved-escalation detection, existing-escalation dedup, block-reason extraction from `task_events`, conditional routing based on assignee. Requires new trigger type (`task_blocked`). Internal action nodes (unblock, comment) may not be engine-supported. | Old cron's `scan_board()` continues running. **Recommendation:** This template may never fully migrate — consider keeping the scanner as a cron script indefinitely. |

### General Rollback Strategy

**During transition:** Both old cron (`workflow-engine.py`) and new engine run simultaneously. The old cron's migrated phases are **commented out one at a time**. To rollback:

1. **Immediate rollback (seconds):** Re-enable the commented-out phase in `workflow-engine.py`. The idempotency keys match (`bead-<id>`, `qa-merge-<sha>`, etc.), so there's **zero risk of duplicate cards** — the engine and old cron use the same dedup keys.
2. **Disable the engine template:** Rename `templates/<name>.json` to `templates/<name>.json.disabled`. The engine won't load it on the next tick.
3. **Verify:** Watch for 1 hour. Old cron resumes full operation.

**After old cron is retired (Phase 7):**
1. The old cron script remains in git history.
2. Re-add the old cron job to `cron/jobs.json` with the original schedule.
3. Re-enable all phases in `workflow-engine.py`.
4. Disable the engine cron job.

### Transition Coexistence Guarantee

The old cron and new engine can run **simultaneously without conflict** because:

| Mechanism | Old cron key | New engine key | Match? |
|-----------|-------------|----------------|--------|
| Bug routing | `bead-<bead_id>` | `wf:<instance>:<node_id>` (card), `bead-<bead_id>` (idempotency) | ⚠️ **Different!** The engine's card idempotency key is `wf:...`, but the **task** idempotency key must be `bead-<id>` to match. **Template specifies `idempotency_key_template`** to override the default `wf:` prefix. |
| PO dispatch | `po-dispatch-<board>-<timestamp>` | `wf:...` | Different — no conflict, but the old cron's timestamp-based key won't dedup with the engine. **Safe** — if old cron is disabled, no issue. |
| QA trigger | `qa-merge-<sha>` | `wf:...` (card), trigger dedup via `trigger_keys` table | Different dedup mechanisms. **Safe** — if both run, old cron creates the card first (matching key), engine's trigger fires but finds the card already exists. |
| Human escalation | `bead-human-<bead_id>` | `bead-human-<bead_id>` (via template) | Match — coexistence safe. |
| Blocked escalation | `[ESCALATION] %<task_id>%` (title match) | `wf:...` | Different. Old cron checks for existing `[ESCALATION]` cards by title pattern. Engine creates cards with `wf:` idempotency. **Risk:** double-escalation if both run. **Mitigation:** disable old cron's scanner when migrating this phase. |

**Critical:** The `idempotency_key_template` field in templates is **load-bearing** for coexistence. Without it, the engine would create cards with `wf:` keys that don't match the old cron's dedup, causing duplicates.

---

## 8. Implementation Checklist

### Phase 0: Fix Prerequisites (before any migration)

- [ ] Fix engine cron job `94e735a11be6` — correct the script path to absolute
- [ ] Verify engine runs: `python3 ~/.hermes-teams/startup/scripts/workflow_engine/main.py tick`
- [ ] Verify `python3 ~/.hermes-teams/startup/scripts/workflow_engine/main.py templates` lists `qa-loop`
- [ ] Add `idempotency_key_template` support to the engine (if not already present)
- [ ] Add `not_labels` / `label_any` / `or_labels_contains` to `bead_ready` trigger conditions
- [ ] Add `board` override support on nodes (for `human-escalation.json` → `hermes-hq`)
- [ ] (Optional) Fix scout cron (DeepSeek key or switch to zai) — independent
- [ ] (Optional) Re-enable researcher skills — independent

### Phase 1: QA Loop (lowest risk, already written)

- [ ] Verify `qa-loop.json` trigger condition matches old cron logic
- [ ] Add `metadata.merged: true` to trigger (or verify verifier stamps it)
- [ ] Disable old cron's `phase_qa_trigger` (already done — lines 681-687 commented)
- [ ] Monitor: `python3 .../main.py list` — check qa-loop instances appear
- [ ] Monitor: QA cards appear on project boards after verifier PASS
- [ ] Watch for 1 hour of cron operation
- [ ] **Rollback ready:** Uncomment lines 681-687 in `workflow-engine.py`

### Phase 2: Bug Router

- [ ] Write `templates/bug-router.json` (§3.2 above)
- [ ] Test manually: `python3 .../main.py start bug-router --board <test-board> --project-dir <dir>`
- [ ] Create a test bug bead, verify card routes to debugger
- [ ] Modify old cron: remove `dispatch_bug_to_debugger()` call from `phase_dispatch`
- [ ] Monitor for 1 hour
- [ ] **Rollback ready:** Re-add bug routing to `phase_dispatch`

### Phase 3: Wayfinder Router

- [ ] Write `templates/wayfinder-router.json` (§3.3 above)
- [ ] Test each routing path (research→scout, task→ops, architecture→architect)
- [ ] Modify old cron: remove `dispatch_wayfinder_ticket()` from `phase_dispatch`
- [ ] Monitor for 1 hour
- [ ] **Rollback ready:** Re-add wayfinder routing to `phase_dispatch`

### Phase 4: Bead Dispatch (core pipeline)

- [ ] Write `templates/bead-dispatch.json` (§3.1 above)
- [ ] **CRITICAL:** Verify `not_labels` correctly excludes all bugs, wayfinder, human beads
- [ ] Test: create a feature bead, verify dispatch card created for PO
- [ ] Test: create a bug bead, verify it does NOT create a dispatch card (goes to bug-router)
- [ ] Modify old cron: disable `phase_dispatch` entirely (comment out in `main()`)
- [ ] Monitor for 24 hours — this is the core pipeline entry point
- [ ] **Rollback ready:** Re-enable `phase_dispatch`

### Phase 5: Human Escalation

- [ ] Write `templates/human-escalation.json` (§3.4 above)
- [ ] Verify engine can scan beads by label (not just `bd ready`)
- [ ] Test: tag a bead `human`, verify HQ card created on `hermes-hq`
- [ ] Modify old cron: disable `phase_human_escalations`
- [ ] Monitor for 1 hour
- [ ] **Rollback ready:** Re-enable `phase_human_escalations`

### Phase 6: Blocked Escalation (highest risk — may defer)

- [ ] Evaluate: is a new trigger type (`task_blocked`) feasible?
- [ ] Evaluate: can internal action nodes (SQL unblock, comment) be engine-supported?
- [ ] If YES: write `templates/blocked-escalation.json` (§3.5 above)
- [ ] If NO: **keep `scan_board()` as a cron script** — it works, it's pure SQL, and it's low-maintenance
- [ ] Test extensively on a staging board
- [ ] Modify old cron: disable `scan_board`
- [ ] Monitor for 48 hours
- [ ] **Rollback ready:** Re-enable `scan_board`

### Phase 7: Retire Old Cron

- [ ] All phases verified stable for 30+ days
- [ ] Disable old cron job `5838e048ae7f` in `cron/jobs.json`
- [ ] Keep `workflow-engine.py` in git for historical reference
- [ ] Remove `bead-sync` note: **bead-sync is NOT migrated** — see §8.1 below
- [ ] Document the new architecture in README.md

### 8.1 Bead-Sync — Special Case

`phase_bead_sync` syncs kanban card status → bd bead status. This is **NOT** an engine template — it's a data synchronization task, not a card-creation orchestration. The engine's design decision was "kanban-only, no beads" (README §Design Decisions). 

**Recommendation:** Keep `bead-sync` as a standalone cron script. Either:
- Extract it from `workflow-engine.py` into its own `bead-sync.py` script with its own cron job, OR
- Leave it in `workflow-engine.py` (which becomes just the bead-sync script after all other phases are migrated).

---

## 9. Per-Profile Migration Summary Cards

### Product Owner

```
STAYS AS SKILL:          project-kickoff, dev-planning, dev-dispatch,
                         project-discovery, task-hygiene-validator,
                         project-promotion, grill-rpc, escalation resolution

MOVES TO ENGINE:         bead-dispatch.json, bug-router.json,
                         wayfinder-router.json, human-escalation.json,
                         blocked-escalation.json, qa-loop.json

STAYS AS CRON SCRIPT:    bead-sync (data sync, not orchestration)
                         hygiene-guard.sh (zero-token guard)
                         weekly sprint report (agent prompt cron)

CANNOT MIGRATE:          project-kickoff/dev-planning (interactive dialogue)
                         project-discovery (judgment-heavy scanning)
                         task-hygiene actions (judgment)

DEPENDENCIES:            Engine cron must be fixed first (§6.1)
RISK:                    MEDIUM overall — core pipeline entry point
ROLLBACK:                Re-enable phases in workflow-engine.py (idempotency keys match)
```

### Architect

```
STAYS AS SKILL:          design-council (loop_engine-driven), architect-gate,
                         design-consult-rpc

MOVES TO ENGINE:         Nothing

PROFILE-MANAGED:         loop_engine phases (converge, interview, ADR)
                         researcher/peer fan-out via kanban_chains

CANNOT MIGRATE:          Design decisions require deep reasoning + alternatives

DEPENDENCIES:            None — architect is triggered by PO-created cards
RISK:                    N/A — no migration
ROLLBACK:                N/A
```

### Tech-Lead

```
STAYS AS SKILL:          loops-engineering (all 5 phases: discover, plan,
                         execute, validate, iterate)

MOVES TO ENGINE:         beads-watchdog.sh → RETIRED (PO dispatch covers it)

PROFILE-MANAGED:         kanban_chains (dev+verifier card creation)
                         dynamic blocking on verifier completion

CANNOT MIGRATE:          Planning, grilling, contracting, routing decisions

DEPENDENCIES:            Depends on PO dispatch working (bead-dispatch.json)
RISK:                    LOW — retiring dormant watchdog is safe
ROLLBACK:                Re-schedule beads-watchdog.sh if needed
```

### Developer

```
STAYS AS SKILL:          developer-loop (6-phase lifecycle)

MOVES TO ENGINE:         Nothing

CANNOT MIGRATE:          Harness invocation, mechanical gates, trace capture

DEPENDENCIES:            Depends on tech-lead creating cards (via kanban_chains)
RISK:                    N/A — no migration
ROLLBACK:                N/A
```

### Verifier

```
STAYS AS SKILL:          adversarial-review (3-stage pipeline),
                         dod-verdict, merge-protocol

MOVES TO ENGINE:         Nothing (qa-loop.json triggers ON verifier output,
                         doesn't change verifier behavior)

PROFILE-MANAGED:         probe fan-out via kanban_chains
                         fix-card creation on FAIL
                         merge protocol (slot/rebase/rerun/merge)

CANNOT MIGRATE:          Adversarial review requires independent judgment

DEPENDENCIES:            qa-loop.json reads verifier metadata.verdict
RISK:                    N/A — no migration of verifier itself
ROLLBACK:                N/A
```

### Debugger

```
STAYS AS SKILL:          debug-loop (3-phase converge loop)

MOVES TO ENGINE:         Nothing (bug-router.json creates the initial card,
                         doesn't change debugger behavior)

PROFILE-MANAGED:         loop_engine phases (reproduce, hypothesize+fix,
                         converge)
                         developer/verifier card creation within loop

CANNOT MIGRATE:          Diagnosis requires reasoning, hypothesis ranking

DEPENDENCIES:            bug-router.json routes bugs to debugger
RISK:                    N/A — no migration of debugger itself
ROLLBACK:                N/A
```

### QA

```
STAYS AS SKILL:          live-testing (8-phase spine), qa-protocol
                         (swarm orchestrator)

MOVES TO ENGINE:         qa-loop.json (trigger: verifier PASS → QA card)
                         ✅ ALREADY WRITTEN

PROFILE-MANAGED:         swarm creation via kanban_chains
                         triage report → tech-lead

CANNOT MIGRATE:          Test execution, finding filing, verdict

DEPENDENCIES:            Engine cron must be fixed (§6.1)
RISK:                    LOW — single-node template, already tested
ROLLBACK:                Re-enable phase_qa_trigger in old cron
```

### Ops / Scout / Researcher

```
STAYS AS CRON SCRIPT:    healthcheck.sh, cron-store-backup.sh,
                         session-archiver.py (zero-token watchdogs)

STAYS AS SKILL:          dev-env-setup, healthcheck, team-observability,
                         research-scout, deep-research

MOVES TO ENGINE:         Nothing

BROKEN (FIX INDEPENDENTLY):
                         Scout cron (DeepSeek key missing)
                         Scout Telegram (not configured)
                         Researcher skills (disabled in config)

CANNOT MIGRATE:          System monitoring (not kanban orchestration)
                         Content scanning + editorial judgment (scout)
                         Knowledge synthesis (researcher)

DEPENDENCIES:            None — independent of engine migration
RISK:                    N/A — no migration
ROLLBACK:                N/A
```

---

## 10. Appendix: Old Cron Phase → Engine Template Mapping

| Old cron function | Lines in workflow-engine.py | Engine template | Status |
|---|---|---|---|
| `phase_bead_sync()` | 78-128 | N/A (keep as script) | Stays |
| `phase_dispatch()` — feature beads | 271-330 | `bead-dispatch.json` | 🔲 To migrate |
| `dispatch_bug_to_debugger()` | 243-269 | `bug-router.json` | 🔲 To migrate |
| `dispatch_wayfinder_ticket()` | 175-241 | `wayfinder-router.json` | 🔲 To migrate |
| `phase_human_escalations()` | 353-391 | `human-escalation.json` | 🔲 To migrate |
| `scan_board()` | 406-493 | `blocked-escalation.json` | 🔲 To migrate (HIGH risk) |
| `phase_qa_trigger()` | 499-639 | `qa-loop.json` | ✅ Written, ⚠️ engine broken |

### Old cron's `main()` (lines 645-693):

```python
def main():
    for project in projects:
        phase_bead_sync(board, path)      # → KEEP AS SCRIPT
        phase_dispatch(board, path)        # → ENGINE (3 templates)
        phase_human_escalations(board, path)  # → ENGINE
        scan_board(board)                  # → ENGINE (HIGH risk)
        # phase_qa_trigger(board, path)    # → ENGINE (already disabled)
```

After migration, `main()` reduces to:
```python
def main():
    for project in projects:
        phase_bead_sync(board, path)  # the only remaining phase
```

Or `bead-sync` is extracted to its own script and `workflow-engine.py` is retired entirely.

---

*End of Migration Plan*
