#!/bin/bash
# Daily scout guard script — runs BEFORE the agent.
# Checks if today's scout already completed.
# Output is injected into the agent's prompt as context.
#
# If ALREADY_SCOUTED: agent sees this and exits immediately (minimal tokens).
# If NEEDS_SCOUTING: agent runs the full workflow.
# If MACHINE_WAS_OFF: agent knows it's catching up on missed days.

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
