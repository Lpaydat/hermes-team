#!/bin/bash
# Pipeline guard — runs BEFORE the agent.
# Checks if the last pipeline cycle was within the cooldown window.
# Output is injected into the agent's prompt as context.
#
# If RECENT: agent exits immediately (minimal tokens).
# If DUE: agent runs the full pipeline cycle.
#
# Also checks for URGENT conditions that override the cooldown:
#   - A product build just completed on the kanban board (needs review ping)
#   - Gate feedback was received that needs processing

NOW_EPOCH=$(date +%s)
COOLDOWN_DAYS=3
COOLDOWN_SECONDS=$((COOLDOWN_DAYS * 86400))
MARKER="$HOME/vault/ventures/.last-pipeline"

if [ -f "$MARKER" ]; then
    LAST_EPOCH=$(cat "$MARKER")
    ELAPSED=$((NOW_EPOCH - LAST_EPOCH))
    ELAPSED_DAYS=$((ELAPSED / 86400))

    if [ "$ELAPSED" -lt "$COOLDOWN_SECONDS" ]; then
        # Cooldown active — check for urgent conditions (board activity since last run)
        URGENT=""
        BOARD_JSON=$(hermes kanban list --json 2>/dev/null)
        if [ $? -ne 0 ] || [ -z "$BOARD_JSON" ]; then
            URGENT="kanban-cli-unavailable (fail-open)"
        else
            LAST_ISO=$(date -d "@$LAST_EPOCH" +%Y-%m-%dT%H:%M:%S 2>/dev/null || echo "1970-01-01T00:00:00")
            URGENT=$(echo "$BOARD_JSON" | python3 -c "
import json, sys
last = '$LAST_ISO'
try:
    tasks = json.load(sys.stdin)
    if isinstance(tasks, dict): tasks = tasks.get('tasks', [])
    hits = []
    for t in tasks:
        upd = (t.get('updated_at') or t.get('completed_at') or '')[:19]
        if upd > last and t.get('status') in ('done', 'review', 'blocked'):
            hits.append(f\"{t.get('id')}:{t.get('status')}:{(t.get('title') or '')[:40]}\")
    print('; '.join(hits))
except Exception as e:
    print(f'parse-error:{e} (fail-open)')
")
        fi
        if [ -n "$URGENT" ]; then
            echo "STATUS:RECENT_BUT_URGENT"
            echo "LAST_PIPELINE_EPOCH:$LAST_EPOCH"
            echo "ELAPSED:${ELAPSED_DAYS}d"
            echo "URGENT:$URGENT"
            echo "ACTION:RUN — cooldown active but board activity since last pipeline. Process the urgent items above."
        else
            echo "STATUS:RECENT"
            echo "ELAPSED:${ELAPSED_DAYS}d of ${COOLDOWN_DAYS}d cooldown, no board activity since last run."
            echo '{"wakeAgent": false}'
        fi
    else
        echo "STATUS:DUE"
        echo "LAST_PIPELINE_EPOCH:$LAST_EPOCH"
        echo "ELAPSED:${ELAPSED_DAYS}d"
        echo "COOLDOWN:${COOLDOWN_DAYS}d"
        echo "ACTION:RUN — Last pipeline was ${ELAPSED_DAYS}d ago (> ${COOLDOWN_DAYS}d cooldown). Run the full pipeline cycle."
    fi
else
    echo "STATUS:DUE"
    echo "LAST_PIPELINE_EPOCH:never"
    echo "ELAPSED:never"
    echo "COOLDOWN:${COOLDOWN_DAYS}d"
    echo "ACTION:RUN — No previous pipeline run found. Run the full pipeline cycle."
fi
