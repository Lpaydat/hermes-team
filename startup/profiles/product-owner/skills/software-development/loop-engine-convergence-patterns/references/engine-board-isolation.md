# Engine Board Isolation via active-projects.json

## Problem

`_boards_to_check()` scanned ALL board directories under `KANBAN_HOME`.
During development/testing, 29 boards accumulated on disk but only a few
were active. Every tick, the engine checked all 29 for triggers. A
`[spec]` card completing on ANY board would fire dev-dispatch —
cross-board contamination.

## Fix (commit `06f03c9`)

`_boards_to_check()` in `runtime.py` now calls `_active_project_boards()`
which reads `active-projects.json` and returns the allowlist. Only boards
in that list are candidate boards for trigger scanning.

### Path resolution

`active-projects.json` lives at `~/.hermes-teams/startup/active-projects.json`.

`KANBAN_HOME` = `~/.hermes-teams/startup/kanban/boards/`

The file is TWO parent levels up from KANBAN_HOME:
```python
startup_dir = KANBAN_HOME.parent.parent  # startup/kanban/boards → startup
projects_file = startup_dir / "active-projects.json"
```

Getting this wrong (one level up = `startup/kanban/active-projects.json`)
silently returns None and disables isolation entirely.

### Both formats supported

```json
// Format 1: active_projects array
{
  "active_projects": [
    {"board": "my-project", "repo": "/path/to/repo"}
  ]
}

// Format 2: legacy flat dict
{
  "my-project": "/path/to/repo"
}
```

### Backward compat / test mode

If `active-projects.json` doesn't exist → returns None → engine scans ALL
boards (original behavior). This is critical for engine tests: the
FakeWorld creates a temp KANBAN_HOME without `active-projects.json`, so
tests pass without modification.

### Relationship to broken-board validation

Board isolation is a LAYER on top of the existing broken-board
validation (commit `cf9ffd1`). The order is:

1. `_active_project_boards()` → returns allowlist (or None for fallback)
2. Candidate boards filtered to allowlist only
3. Each candidate validated: 0-byte check + `SELECT 1 FROM tasks` probe
4. Valid boards returned for trigger scanning

## Verification

- 113 engine tests pass (tests use temp dir without active-projects.json)
- Cross-board test passes (FakeWorld has no allowlist file → fallback to all)
- Production: 29 boards on disk, 5 in allowlist → 24 skipped every tick
