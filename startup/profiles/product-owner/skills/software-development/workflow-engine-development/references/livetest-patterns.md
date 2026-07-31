# Livetest Patterns — What Constitutes a Real Test

## The user's hard line on livetests

> "this is not livetest I imagine. I don't see the builder work or grill or build even a second."

A livetest is NOT:
- Creating cards and immediately deleting them
- Verifying card titles are correct
- Running the engine tick and seeing "DISPATCHED" in the log
- Starting a workflow and checking the board shows cards

A livetest IS:
- Starting the workflow
- Letting the dispatcher pick up cards (~60s)
- Letting the real agent gateway claim and process the card
- Watching the agent actually do the work (minutes to hours)
- Seeing the card complete with real metadata
- Seeing the engine detect completion and advance to the next node
- The full E2E cycle: create → dispatch → agent works → complete → engine advances → next node

## How to run a real builder livetest

1. **Create a dedicated test board**: `hermes kanban boards create builder-livetest`
2. **Ensure the builder gateway is running**: check `ps aux | grep "hermes.*gateway.*builder"`
3. **Start the workflow**: `main.py start builder-grill-build --board builder-livetest --project-dir <path>`
4. **Run engine tick**: `main.py tick` (parse runs, cards created)
5. **WAIT** — the builder gateway claims cards on its dispatch cycle (~60s), then processes for 20-30 minutes per grill
6. **Monitor**: check board status, engine log, card details every 5-10 minutes
7. **Verify completion**: card goes `ready → running → done`, engine tick shows "DONE node grill", next node dispatches

## Increasing concurrency

Edit the profile's `config.yaml`:
```yaml
kanban:
  max_in_progress: 5
  max_in_progress_per_profile: 5
```

Requires gateway restart to take effect (kill + restart, or use the `gateways` fish function).

## Monitoring commands

```bash
# Board status
hermes kanban --board builder-livetest list

# Engine events
python3 main.py log --limit 20

# Specific instance
python3 workflow_engine/main.py log --instance <id>

# Active instances
python3 workflow_engine/main.py list
```

## Time expectations

- Parse (command node): instant
- Grill cards dispatched: instant after tick
- Builder claims cards: ~60s (dispatch cycle)
- Grill session (builder + PO): 20-30 minutes per idea
- Build session (builder + loop_engine): 20-30 minutes per idea
- Total for 10 ideas at 5 concurrent: ~1-2 hours for grills, then ~1-2 hours for builds

## Cleanup after livetest

```bash
# Archive all test cards
hermes kanban --board builder-livetest list --json | python3 -c "import json,sys; [print(t['id']) for t in json.load(sys.stdin)]" | xargs -I{} hermes kanban --board builder-livetest archive {}

# Delete test board
hermes kanban boards delete builder-livetest

# Clean engine state
python3 -c "
import sqlite3; from pathlib import Path
db = Path.home() / '.hermes-teams/startup/kanban/workflow-state.db'
conn = sqlite3.connect(str(db))
conn.execute(\"DELETE FROM node_states WHERE instance_id IN (SELECT instance_id FROM workflow_instances WHERE workflow_id='builder-grill-build')\")
conn.execute(\"DELETE FROM workflow_instances WHERE workflow_id='builder-grill-build'\")
conn.commit(); conn.close()
"
```
