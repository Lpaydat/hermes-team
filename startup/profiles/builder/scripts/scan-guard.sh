#!/bin/bash
# Daily scan guard — runs BEFORE the agent.
# Checks if today's demand signal scan already completed.
# Output is injected into the agent's prompt as context.
#
# If ALREADY_SCANNED: agent sees this and exits immediately (minimal tokens).
# If NEEDS_SCANNING: agent runs the full scan.

TODAY=$(date +%Y-%m-%d)
MARKER="$HOME/vault/ventures/.last-scan"

if [ -f "$MARKER" ]; then
    LAST_SCAN=$(cat "$MARKER")
    if [ "$LAST_SCAN" = "$TODAY" ]; then
        echo "STATUS:ALREADY_SCANNED"
        echo "DATE:$TODAY"
        echo "ACTION:SKIP — Today's scan already completed. Do nothing. Return 'Already scanned for $TODAY.' and stop."
        echo '{"wakeAgent": false}'
    else
        echo "STATUS:NEEDS_SCANNING"
        echo "DATE:$TODAY"
        echo "LAST_SCAN:$LAST_SCAN"
        echo "ACTION:RUN — Last scan was $LAST_SCAN. Run today's demand signal scan."
    fi
else
    echo "STATUS:NEEDS_SCANNING"
    echo "DATE:$TODAY"
    echo "LAST_SCAN:never"
    echo "ACTION:RUN — No previous scan found. Run today's demand signal scan."
fi
