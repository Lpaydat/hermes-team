#!/usr/bin/env bash
# sqlite3 guard — blocks direct writes to kanban/workflow databases.
# Forces use of hermes kanban / kanban_* tools instead.
# READ access always allowed.

REAL_SQLITE3="/usr/bin/sqlite3-real"

DB_PATH=""
for arg in "$@"; do
    case "$arg" in
        -*) continue ;;
    esac
    if [ -z "$DB_PATH" ]; then
        DB_PATH="$arg"
        break
    fi
done

IS_PROTECTED=false
case "$DB_PATH" in
    *kanban*.db|*workflow-state.db|*workflow_state.db)
        IS_PROTECTED=true
        ;;
esac

if [ "$IS_PROTECTED" = "false" ]; then
    exec "$REAL_SQLITE3" "$@"
fi

ALL_ARGS="$*"
case "$ALL_ARGS" in
    *[[:space:]]INSERT[[:space:]]*|\
    *[[:space:]]UPDATE[[:space:]]*|\
    *[[:space:]]DELETE[[:space:]]*|\
    *[[:space:]]DROP[[:space:]]*|\
    *[[:space:]]ALTER[[:space:]]*|\
    *[[:space:]]CREATE[[:space:]]*|\
    *[[:space:]]REPLACE[[:space:]]*|\
    *[[:space:]]ATTACH[[:space:]]*|\
    *[[:space:]]DETACH[[:space:]]*|\
    *[[:space:]].import[[:space:]]*|\
    *[[:space:]].restore[[:space:]]*|\
    *[[:space:]].backup[[:space:]]*|\
    *[[:space:]].save[[:space:]]*)
        echo "sqlite3-guard: BLOCKED — direct write to protected database: $DB_PATH" >&2
        echo "sqlite3-guard: Use hermes kanban / kanban_* tools instead." >&2
        echo "sqlite3-guard: They run recompute_ready, event emission, and claim locks." >&2
        exit 1
        ;;
esac

exec "$REAL_SQLITE3" "$@"
