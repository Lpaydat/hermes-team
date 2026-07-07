#!/bin/bash
# Daily scout guard script — runs BEFORE the agent loop.
# Injected into the agent's prompt as context by the cron scheduler.
# Checks if today's scout already completed to avoid duplicate runs (saves tokens).
#
# Usage: called automatically by the cron job (script field).
# The cron triggers at multiple times (e.g. 7:30, 8:30, 9:30, 10:30) to catch
# machine downtime. This guard ensures only the FIRST trigger runs the full scout;
# subsequent triggers see STATUS:ALREADY_SCOUTED and the agent exits immediately.

TODAY=$(date +%Y-%m-%d)
MARKER="$HOME/vault/meta/.last-scout"

if [ -f "$MARKER" ]; then
    LAST_SCOUT=$(cat "$MARKER")
    if [ "$LAST_SCOUT" = "$TODAY" ]; then
        echo "STATUS:ALREADY_SCOUTED"
        echo "DATE:$TODAY"
        echo "ACTION:SKIP — Today's scout already completed. Do nothing. Return 'Already scouted for $TODAY.' and stop."
        echo '{"wakeAgent": false}'
    else
        echo "STATUS:NEEDS_SCOUTING"
        echo "DATE:$TODAY"
        echo "LAST_SCOUT:$LAST_SCOUT"
        echo "ACTION:RUN — Last scout was $LAST_SCOUT. Run today's full scout."
    fi
else
    echo "STATUS:NEEDS_SCOUTING"
    echo "DATE:$TODAY"
    echo "LAST_SCOUT:never"
    echo "ACTION:RUN — No previous scout found. Run today's full scout."
fi
