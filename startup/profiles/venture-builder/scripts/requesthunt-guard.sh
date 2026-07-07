#!/bin/bash
# RequestHunt guard — runs BEFORE the script.
# Checks if this week's requesthunt deep scan already completed.
# Output is injected into context.
#
# If ALREADY_SCANNED: skip (zero credits spent).
# If NEEDS_SCANNING: run the requesthunt script.

WEEK=$(date +%Y-W%V)
MARKER="$HOME/vault/ventures/.last-requesthunt"

if [ -f "$MARKER" ]; then
    LAST_RH=$(cat "$MARKER")
    if [ "$LAST_RH" = "$WEEK" ]; then
        echo "STATUS:ALREADY_SCANNED"
        echo "WEEK:$WEEK"
        echo "ACTION:SKIP — This week's requesthunt scan already completed. Do nothing."
    else
        echo "STATUS:NEEDS_SCANNING"
        echo "WEEK:$WEEK"
        echo "LAST_RH:$LAST_RH"
        echo "ACTION:RUN — Last requesthunt scan was $LAST_RH. Run this week's deep scan."
    fi
else
    echo "STATUS:NEEDS_SCANNING"
    echo "WEEK:$WEEK"
    echo "LAST_RH:never"
    echo "ACTION:RUN — No previous requesthunt scan found. Run this week's deep scan."
fi
