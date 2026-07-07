# Cron Guard & Multi-Trigger Pattern

How to make scheduled agent tasks resilient to machine downtime while saving tokens.
Evolved from the daily research scout design.

## Problem
When a cron job runs on a local machine (not a server), the machine may be off at the
scheduled time. A single trigger means missed runs. But multiple triggers risk
re-running the same expensive workflow multiple times per day — wasting tokens.

## Solution: Guard script + multiple triggers

### 1. Guard script (runs before the agent loop)
The cron job's `script=` field points to a bash script that checks a marker file.
Its stdout is injected into the agent's prompt as context.

```bash
#!/bin/bash
# scout-guard.sh
TODAY=$(date +%Y-%m-%d)
MARKER="$HOME/vault/meta/.last-scout"

if [ -f "$MARKER" ]; then
    LAST_SCOUT=$(cat "$MARKER")
    if [ "$LAST_SCOUT" = "$TODAY" ]; then
        echo "STATUS:ALREADY_SCOUTED"
        echo "DATE:$TODAY"
        echo "ACTION:SKIP — Today's task already completed. Do nothing."
    else
        echo "STATUS:NEEDS_SCOUTING"
        echo "DATE:$TODAY"
        echo "LAST_SCOUT:$LAST_SCOUT"
        echo "ACTION:RUN — Last run was $LAST_SCOUT. Run today's full task."
    fi
else
    echo "STATUS:NEEDS_SCOUTING"
    echo "DATE:$TODAY"
    echo "LAST_SCOUT:never"
    echo "ACTION:RUN — No previous run found."
fi
```

### 2. Multiple daily triggers
Set the cron schedule with multiple hours:
```
schedule: "30 7,8,9,10 * * *"
```
This fires at :30 past 7, 8, 9, 10 AM. The first available trigger runs the task.
Subsequent triggers see `STATUS:ALREADY_SCOUTED` and exit immediately.

### 3. Agent prompt includes skip logic
The cron prompt must instruct the agent to check the guard output FIRST:

```
- If you see `STATUS:ALREADY_SCOUTED` → respond "Already done for [date]." and STOP.
  Do not run any tools. This saves tokens.
- If you see `STATUS:NEEDS_SCOUTING` → run the full workflow.
```

### 4. Marker write after completion
The agent writes the marker after successfully completing the task:
```bash
date +%Y-%m-%d > ~/vault/meta/.last-scout
```

## Token cost analysis
- **Skip path** (3 of 4 daily triggers): ~1 short response = a few hundred tokens
- **Full run** (1 of 4): the full workflow cost

This means 75% of triggers cost almost nothing, while ensuring the task runs every day
as long as the machine is on for at least one of the trigger windows.

## When to use this pattern
- Any cron job on a local/desktop machine (not a 24/7 server)
- Tasks where running once per day is the goal (not multiple times)
- Tasks with non-trivial token cost per run

## When NOT to use
- Server-side cron (machine is always on — single trigger is fine)
- Tasks that should run multiple times per day (e.g. hourly monitoring)
- Pure script-only cron jobs (`no_agent=True`) — the script can check the marker itself
  and return empty output to stay silent
