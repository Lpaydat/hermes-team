# Pipeline Diagnosis Methodology — Mapping a Multi-Profile Team to Workflow Templates

## Context

On 2026-07-31, 8 parallel subagents diagnosed every profile in the Hermes team
to map the full dev pipeline for workflow engine migration. This file captures
the methodology so future sessions can repeat it.

## The 8-Profile Diagnosis

| Subagent | Profile(s) | Key Finding |
|----------|-----------|-------------|
| 1 | product-owner | Single front door, owns WHAT, 5 cron phases (bead-sync, dispatch, human-escal, scanner, qa-trigger) |
| 2 | architect | Two-mode: design partner (new projects) + gatekeeper (incremental T0-T3 triage) |
| 3 | tech-lead | Autonomous planner, uses kanban_chains for dev+verifier, never writes code |
| 4 | developer | Thin governance wrapper around vendor harnesses (Claude Code, Codex) |
| 5 | verifier | Dual role: adversarial reviewer + merge gate owner. PASS→merge, FAIL→fix, ESCALATE→TL |
| 6 | debugger | Pure diagnosis orchestrator using loop_engine converge pattern |
| 7 | qa | Last gate, tests running artifact, files bug beads for debugger |
| 8 | ops + scout | Platform management (healthcheck/backup cron), research scanner (broken: missing API key) |

## The Pipeline Map (Happy Path)

```
User → PO → Architect (design) → PO (tickets/beads)
  → Tech-Lead (plan + kanban_chains)
    → Developer (code via harness)
    ↔ Verifier (review + merge gate)
  → QA (test running artifact)
  → Debugger (bugs: reproduce → fix → falsify → converge)
```

## 9 Handoffs Documented

Each handoff was mapped with: trigger, mechanism, what crosses the boundary, what returns.

1. PO → Architect (design card + PRD)
2. PO → Tech-Lead (dispatch card from bd ready beads)
3. Tech-Lead → Developer (kanban_chains coding card)
4. Tech-Lead → Verifier (kanban_chains review card)
5. Verifier → QA (on PASS: trigger creates QA card)
6. Verifier → Developer (on FAIL: fix card with findings)
7. QA → Debugger (bug beads auto-routed by type)
8. Debugger → Developer (fix via loop_engine converge)
9. Debugger → Verifier (re-verify card for the fix)

## Migration Priorities

| Cron Phase | Migration Target | Engine Feature | Priority |
|-----------|-----------------|----------------|----------|
| qa-trigger | qa-loop.json template | card_completed trigger | **DONE** (Phase 1) |
| bug routing | bug-router.json template | card_completed trigger + type=bug condition | High |
| dispatch | dev-dispatch.json template | bead_ready trigger | High |
| scanner | escalation.json template | card_completed + time check | Medium |
| human-escal | hq-escalation.json template | bead_ready + human flag | Medium |
| bead-sync | Dedicated sync tick | Not a workflow (state sync) | Low |

## JSON Node Definition Pattern

Each task produces a JSON node definition for the workflow engine:

```json
{
  "id": "qa_trigger",
  "trigger": {
    "source": "card_completed",
    "condition": {"assignee": "verifier", "metadata.verdict": "PASS"}
  },
  "nodes": [
    {
      "id": "qa_retest",
      "profile": "qa",
      "skill": "live-testing",
      "body_template": "Re-test the merged feature",
      "output": {
        "schema": {
          "required": ["verdict"],
          "properties": {"verdict": {"enum": ["PASS", "FAIL", "BLOCK"]}}
        }
      }
    }
  ]
}
```

## Key Constraints Discovered

1. **One PO dispatch card at a time** — the old cron checks `has_active_po_dispatch_card()`
2. **Bug routing bypasses PO** — bugs go directly to debugger via type=bug condition
3. **Wayfinder routing** — beads route by label to different profiles
4. **Sequential dispatch** — beads dispatch one at a time (tech-lead processes sequentially)
5. **Merge serialization** — verifier holds a merge slot (only one merge at a time)
6. **Escalation chain terminal** — PO is the last automated node, after that = HUMAN_REQUIRED

## Dynamic Workflows (Profile-Managed)

The engine supports workflows where profiles manage their own card trees:

- **Tech-lead**: Uses `kanban_chains` to create parent→child dev+verifier cards
- **Debugger**: Uses `loop_engine` converge pattern (reproduce→fix→falsify→converge)
- **QA**: Uses `kanban_chains` for medium/large test sessions (fan-out + synthesizer)

The engine watches only the parent card's status. When it goes `done`, the node advances.
The internal card trees are invisible to the engine. This is the "static-dynamic coexistence" pattern.
