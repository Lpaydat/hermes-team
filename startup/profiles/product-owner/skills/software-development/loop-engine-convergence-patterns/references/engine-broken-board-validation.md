# Engine Broken Board DB Validation

## Problem

`_boards_to_check()` returned ALL directories containing a `kanban.db` file,
regardless of whether the DB was valid. A single corrupt board (missing
`tasks` table, 0-byte file from interrupted init, locked DB) would crash
the entire `_check_triggers()` loop in `tick()`:

```
ERROR tick: no such table: tasks
```

The tick returns `["ERROR tick: ..."]` — ALL boards alphabetically after
the broken one never get processed. The workflow engine appears "stuck"
even though only one board is broken.

## Root Cause

`find_recent_completions(board, since)` in `kanban_adapter.py` executes:

```sql
SELECT t.id, t.title, ... FROM tasks t
JOIN task_runs r ON r.task_id = t.id ...
```

If the board DB lacks a `tasks` table, `sqlite3.OperationalError: no such
table: tasks` propagates up through `find_recent_completions` →
`_check_triggers` → `tick()` where it's caught by the broad `except
Exception` at runtime.py:986, returning an error and halting the tick.

## Fix (commit `cf9ffd1`)

`_boards_to_check()` in `runtime.py` now validates each board DB before
including it in the scan:

```python
for p in sorted(boards_dir.iterdir()):
    if not p.is_dir() or not (p / "kanban.db").exists():
        continue
    db_path = p / "kanban.db"
    # Skip 0-byte files (interrupted init)
    if db_path.stat().st_size == 0:
        log.warning("Board %r has 0-byte kanban.db; skipping", p.name)
        continue
    try:
        with _connect(db_path) as conn:
            conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone()
        valid_boards.append(p.name)
    except Exception as e:
        log.warning(
            "Board %r kanban.db unreadable (%s); skipping trigger scan. "
            "Run `hermes kanban boards delete %s` to remove if stale.",
            p.name, e, p.name,
        )
```

Three validation layers:
1. **0-byte check** — `db_path.stat().st_size == 0` catches interrupted init
2. **Schema probe** — `SELECT 1 FROM tasks LIMIT 1` catches missing tables
3. **Broad except** — catches locked DBs, corrupt WAL, etc.

Each skip logs at WARNING with:
- Board name
- The error
- Suggested cleanup command (`hermes kanban boards delete <name>`)

## Proof

Created two test boards:
- `broken-test-board` — DB with `junk` table but no `tasks` table
- `zero-byte-board` — 0-byte `kanban.db` file

Before fix: `python3 main.py tick` → `ERROR tick: no such table: tasks`

After fix: tick completed with zero crashes. Both broken boards logged:
```
WARNING Board 'broken-test-board' kanban.db unreadable (no such table: tasks); skipping trigger scan.
WARNING Board 'zero-byte-board' has 0-byte kanban.db; skipping
```

Ad-hoc verification: 5/5 checks passed (valid board included, 0-byte
excluded, no-tasks excluded, engine test suite 113 passed).

## Discovery Context

Found during the EXT-DBG2 subworkflow test. The `[merge-test]` card on
`ext-dbg` board was completed but the workflow trigger never fired. Root
cause: 34 broken boards from previous sessions (auto-created test boards
that were deleted before schema init completed). The engine crashed on
the first broken board in alphabetical order and never reached `ext-dbg`.

Detection script for manual cleanup (still useful):
```bash
for d in ~/.hermes-teams/startup/kanban/boards/*/; do
  b=$(basename "$d")
  r=$(sqlite3 "${d}kanban.db" "SELECT count(*) FROM tasks;" 2>&1)
  echo "$r" | grep -q "Error" && echo "BROKEN: $b"
done
```
