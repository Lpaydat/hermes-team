# Engine Event Logging System

## Schema

```sql
CREATE TABLE engine_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    level TEXT NOT NULL,        -- DEBUG, INFO, WARN, ERROR
    event_type TEXT NOT NULL,   -- see below
    instance_id TEXT,
    workflow_id TEXT,
    node_id TEXT,
    board TEXT,
    card_id TEXT,
    message TEXT NOT NULL,
    metadata TEXT              -- JSON blob
);

CREATE INDEX idx_events_timestamp ON engine_events(timestamp);
CREATE INDEX idx_events_instance ON engine_events(instance_id);
CREATE INDEX idx_events_type ON engine_events(event_type);
```

## Event types

| event_type | level | When |
|------------|-------|------|
| `workflow_started` | INFO | Instance created (manual or trigger) |
| `workflow_completed` | INFO | All nodes reached terminal state |
| `command_run` | DEBUG | Command node executes (includes command string) |
| `node_dispatched` | INFO | Card created and assigned to agent |
| `node_done` | INFO | Card completed, node advanced |
| `node_failed` | ERROR | Command exited non-zero, or schema validation failed |
| `node_skipped` | INFO | Condition evaluated false, node skipped |
| `trigger_fired` | INFO | Card/bead matched a trigger condition |

## CLI

```bash
# Last 50 events
python3 main.py log

# Filter by instance
python3 main.py log --instance wf_1785527707_builder-grill-build_54bd4ac4

# Filter by type
python3 main.py log --type node_failed

# Filter by level
python3 main.py log --level ERROR

# Limit
python3 main.py log --limit 100
```

## How logging is wired

The `StateDB.log_event()` method writes to `engine_events`. It's called from:

1. `Engine.tick()` — after processing all instances, iterates `actions` list and logs each action string with inferred type/level
2. `Engine.start_manual()` — logs `workflow_started` event
3. `Engine._run_command_node()` — logs `command_run` (DEBUG) with command string

The action string parsing in tick() maps keywords to types:
- "COMPLETE" → workflow_completed
- "FAILED" → node_failed (ERROR)
- "DISPATCHED" → node_dispatched
- "DONE" → node_done
- "SKIPPED" → node_skipped
- "STARTED" → trigger_fired

## Use cases

- **Analyze failures**: `main.py log --type node_failed` to see all failures
- **Track a specific workflow**: `main.py log --instance <id>` for full lifecycle
- **Debug command execution**: `main.py log --type command_run` to see exact commands
- **Monitor throughput**: count events per minute to see processing rate
