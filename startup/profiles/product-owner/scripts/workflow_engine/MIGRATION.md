# Workflow Engine Migration Plan

## Current State
- Old cron: `scripts/workflow-engine.py` (696 lines, 5 phases) running on PO's 1-min cron
- New engine: `scripts/workflow_engine/` package with 270 tests, proven against real kanban

## Migration Strategy: Phase by Phase

Each phase migrates ONE cron function to the new engine. The old cron keeps running.
When a phase is verified in production, disable it in the old cron.

### Phase 1: QA Trigger (lowest risk)
**Old cron function:** `phase_qa_trigger` (creates QA card when verifier PASSes)
**New engine template:** `templates/qa-loop.json` (already written)
**Migration steps:**
1. Add new engine tick to cron alongside old cron
2. Disable `phase_qa_trigger` in old cron
3. Monitor: QA cards should auto-trigger via new engine
**Rollback:** Re-enable `phase_qa_trigger` in old cron

### Phase 2: Bug Routing
**Old cron function:** `phase_bug_router` (routes QA-found bugs to debugger)
**New engine template:** `templates/bug-router.json` (to be written)
**Migration steps:**
1. Write bug-router.json template
2. Test on livetest board
3. Disable `phase_bug_router` in old cron

### Phase 3: Dispatch
**Old cron function:** `phase_dispatch` (creates bead→kanban cards)
**New engine template:** `templates/dev-dispatch.json` (to be written, uses bead_ready trigger)
**Migration steps:**
1. Write dev-dispatch.json with bead_ready trigger
2. Test on livetest board
3. Disable `phase_dispatch` in old cron

### Phase 4: Human Escalation
**Old cron function:** `phase_human_escalation` (flags blocked cards needing human input)
**New engine template:** `templates/escalation.json` (to be written)
**Migration steps:**
1. Write escalation.json template
2. Test
3. Disable in old cron

### Phase 5: Full Pipeline
**Final template:** `templates/dev-pipeline.json` — the complete PO→architect→dev↔verifier→merge→QA pipeline
**Migration steps:**
1. Write the full pipeline template
2. Run full livetest through new engine
3. Disable old cron entirely

## Cron Configuration

The new engine tick runs alongside the old cron:
```json
{
  "schedule": "every 1m",
  "command": "python3 scripts/workflow_engine/main.py tick",
  "deliver": "local"
}
```

Both old and new run on 1-min intervals. The old cron's phases that have been
migrated are disabled. The new engine picks up their work via JSON templates.

## Dynamic Workflow Support

The engine supports dynamic workflows through the kanban `blocked` status:

1. A node's card is dispatched to a profile (e.g., tech-lead)
2. The profile creates child cards via `kanban_chains` or `loop_engine`
3. The profile's card goes to `blocked` status while children run
4. The engine sees `blocked` and waits (does not advance the node)
5. When all children complete, the profile's card goes to `done`
6. The engine sees `done` and advances the node

This means the engine does NOT need to know about `kanban_chains` or
`loop_engine` internals — those are profile-managed. The engine only watches
the parent card's status. This is the "static-dynamic coexistence" pattern.

## Verification After Each Phase

1. Run the new engine tick manually: `python3 scripts/workflow_engine/main.py tick`
2. Check active instances: `python3 scripts/workflow_engine/main.py list`
3. Verify cards created on the correct board
4. Monitor for 1 hour of cron operation
5. If stable, proceed to next phase
