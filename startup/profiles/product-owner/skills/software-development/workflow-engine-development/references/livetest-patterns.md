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

Edit the **global** `startup/config.yaml` (NOT the per-profile config — the dispatcher reads global config):

```yaml
kanban:
  max_in_progress: 10              # global cap across all profiles
  max_in_progress_per_profile: 5   # per-profile cap (tighter)
```

- `max_in_progress` — total cards running on the board
- `max_in_progress_per_profile` — max cards per single profile

Requires gateway restart to take effect (kill + restart with `terminal(background=true)`).

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

## Where concurrency config lives

The gateway reads config from the **GLOBAL** `~/.hermes-teams/startup/config.yaml`, NOT the per-profile `profiles/builder/config.yaml`. Both have a `kanban:` section, but the global one wins.

```yaml
# ~/.hermes-teams/startup/config.yaml  ← THIS ONE
kanban:
  max_in_progress: 10              # global cap across all profiles
  max_in_progress_per_profile: 5   # per-profile cap
```

If you change per-profile config and see no effect, check the global config. Gateway restart required after any change.

## Cleanup after livetest

### For foreach subworkflow (parent + children)

```bash
# Archive all test cards
hermes kanban --board builder-livetest list --json | python3 -c "import json,sys; [print(t['id']) for t in json.load(sys.stdin)]" | xargs -I{} hermes kanban --board builder-livetest archive {}

# Clean engine state — parent + ALL child instances
python3 -c "
import sqlite3; from pathlib import Path
db = Path.home() / '.hermes-teams/startup/kanban/workflow-state.db'
conn = sqlite3.connect(str(db))
# Delete all child instances (builder-single)
conn.execute(\"DELETE FROM node_states WHERE instance_id IN (SELECT instance_id FROM workflow_instances WHERE workflow_id='builder-single')\")
conn.execute(\"DELETE FROM workflow_instances WHERE workflow_id='builder-single'\")
# Delete parent instance (builder-grill-build)
conn.execute(\"DELETE FROM node_states WHERE instance_id IN (SELECT instance_id FROM workflow_instances WHERE workflow_id='builder-grill-build')\")
conn.execute(\"DELETE FROM workflow_instances WHERE workflow_id='builder-grill-build'\")
conn.commit(); conn.close()
print('Cleaned')
"
```

### Canceling specific child workflows mid-run

If you archive a card to remove an idea from a running pipeline, the engine treats archived as terminal and ADVANCES the pipeline. To truly cancel:
```python
# Mark the child instance as completed directly
conn.execute("UPDATE workflow_instances SET status = 'completed' WHERE instance_id = ?", (child_id,))
```

## A/B testing prompt strategies

When a card body instruction is being ignored by the agent (e.g., "build with loop_engine" → builder skips it), run a prompt A/B test:

1. **Create a dedicated board**: `hermes kanban boards create ab-<topic>-test`
2. **Design 10-20 prompt variants** across groups (prose, tool-invocation, constraint, skill-injection, example, threat, combo, minimal)
3. **Create one card per variant** with the SAME task but different body text
4. **Let the builder process them all** (5 concurrent, ~10-15 min each)
5. **Check results** by tracing child cards via idempotency keys: `loop:<parent_card_id>:...`
6. **Winning pattern**: constraint-framing ("You may NOT write files directly without loop_engine") outperforms tool-invocation and explicit examples

### Tracking loop_engine usage per card

```python
# loop_engine creates child cards with idempotency key: loop:<parent_card_id>:<hash>
# Query:
SELECT id, title, idempotency_key FROM tasks WHERE title LIKE 'Loop:%'
# Extract parent from key.split(':')[1]
```

### Restarting the builder gateway after config changes

The dispatcher reads global config at startup. After changing `max_in_progress`:
```bash
# Kill old gateway
kill $(ps aux | grep "python.*hermes_cli.*--profile builder gateway run" | grep -v grep | awk '{print $2}')

# Start new gateway (use terminal background=true, NOT nohup)
# terminal(background=true): cd ~/.hermes-teams/startup && hermes --profile builder gateway run
```
