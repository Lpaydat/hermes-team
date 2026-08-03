# Live Testing Workflow Templates — Field Guide

Hard-won lessons from deploying and testing the dev-dispatch template on real boards.

## Test board setup

1. Create a dedicated test board: `hermes kanban boards create wf-<name>-test`
2. Add to `active-projects.json` with a temp path: `{"name": "<Name>", "path": "/tmp/<dir>", "board": "<slug>"}`
3. `mkdir -p /tmp/<dir>` (the engine needs the path to exist)
4. **Never put test cards on production boards.** Use dedicated test boards only.

## Creating spec cards with metadata

The engine reads metadata from `task_runs`, not `tasks`. To create a card that triggers a `card_completed` workflow:

```python
import sqlite3, json, time

conn = sqlite3.connect(str(board_db))
now = int(time.time())
conn.execute(
    "INSERT INTO tasks (id, title, assignee, status, idempotency_key, created_at, completed_at, body) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (card_id, title, assignee, 'done', f'manual-{card_id}', now, now, 'body')
)
conn.execute(
    "INSERT INTO task_runs (task_id, profile, status, started_at, ended_at, outcome, summary, metadata) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (card_id, assignee, 'done', now, now, 'completed', title, json.dumps(metadata))
)
conn.commit()
```

Or use `hermes kanban --board <slug> create ...` then `hermes kanban --board <slug> complete <id> --metadata '<json>'`.

## Running engine ticks manually

The cron may not be running (no daemon process). Run ticks manually:

```bash
cd ~/.hermes-teams/startup/scripts
python3 workflow_engine/main.py tick
```

Tick 1: trigger fires + entry node runs.
Tick 2: routing edges fire + task cards created.

## Corrupt board guard

The engine's `_boards_to_check()` skips boards with no `tasks` table. But leftover board directories with corrupt empty DBs can still appear (recreated by daemons). If `tick failed: no such table: tasks` appears, check for corrupt boards:

```bash
for d in ~/.hermes-teams/startup/kanban/boards/*/; do
  b=$(basename "$d")
  if [ -f "$d/kanban.db" ]; then
    tables=$(sqlite3 "$d/kanban.db" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='tasks'" 2>/dev/null)
    [ "$tables" != "1" ] && echo "CORRUPT: $b"
  fi
done
```

## Condition engine behavior

The merged engine supports AND/OR compound conditions. The OLD engine (pre-merge) did NOT — it silently evaluated only the first clause. If a routing diamond with `!= 'X' AND != 'Y'` routes everything to the default, the condition engine is the likely culprit. Verify:

```python
from workflow_engine.model import evaluate_condition
evaluate_condition("${trigger.type} != 'bug' AND ${trigger.type} != 'ops'", {"trigger.type": "ops"})
# Should be False. If True, the condition engine is broken.
```

## Cross-workflow handoff chain

The full pipeline chains via `card_completed` triggers (no explicit wiring):

```
[spec] PO card done → dev-dispatch triggers
  → routes to tech-lead/debugger/scout/etc
  → tech-lead card done → qa-loop triggers (assignee=verifier, verdict=PASS)
  → QA card done → bug-fix triggers (assignee=qa, verdict=FAIL)
```

Each workflow is independent — the trigger conditions ARE the chain.

## Cleaning up

```bash
hermes kanban boards delete <slug>
rm -f ~/.hermes-teams/startup/kanban/<slug>-state.db  # engine state DB
```

Clear `active-projects.json` to `[]` when done testing.
