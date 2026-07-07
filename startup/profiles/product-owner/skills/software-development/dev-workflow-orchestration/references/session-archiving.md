# Session Archiving — Kanban Worker Session Cleanup

## The Problem

Every kanban task dispatch spawns a new session. After a few workflow cycles,
the session list is dominated by "work kanban task t_xxx" entries — making it
hard to find real conversations. A 5-bead test run produces 20+ sessions across
tech-lead, developer, and verifier profiles.

## The Official API (NOT raw SQL)

Hermes has two paths to soft-archive a session:

### Path 1: Python API (RECOMMENDED — works from cron scripts)

Import `SessionDB` from `hermes_state.py` directly. No HTTP auth needed.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes-teams" / "startup" / "hermes-agent"))
from hermes_state import SessionDB

store = SessionDB(Path("~/.hermes-teams/startup/profiles/tech-lead/state.db").expanduser())
store.set_session_archived(session_id, True)  # Returns True on success
store.close()
```

**Important**: `SessionDB` expects a `Path` object, not a string. Passing a string
raises `'str' object has no attribute 'parent'`.

### Path 2: HTTP PATCH API (requires dashboard auth token)

The web dashboard exposes `PATCH /api/sessions/{session_id}` but requires a
`HERMES_DASHBOARD_SESSION_TOKEN` that is generated at runtime. Not practical
for cron scripts.

- Archived sessions are **hidden** from the default session list (`archived=exclude`)
- Archived sessions are **still searchable** via `session_search` (preserves debug value)
- The `sessions` table has an `archived` INTEGER column (0/1)
- `db.set_session_archived(sid, True)` is the documented function call

**Do NOT set `archived=1` via raw SQL** — use the `SessionDB` Python API instead.

## How to Identify Kanban Worker Sessions

Kanban worker sessions have `source = "cli"` (the dispatcher spawns via CLI).
The first user message is always "work kanban task t_xxx".

```sql
-- Find kanban worker sessions older than 3 days on a profile
SELECT s.id, s.started_at
FROM sessions s
WHERE s.source = 'cli'
  AND s.started_at < <cutoff_epoch>
  AND s.id IN (
    SELECT m.session_id FROM messages m
    WHERE m.role = 'user'
      AND m.content LIKE 'work kanban task %'
      AND m.id = (SELECT MIN(id) FROM messages m2 WHERE m2.session_id = m.session_id)
  )
```

## CLI Alternatives

| Command | What it does | Limitation |
|---|---|---|
| `hermes sessions prune --older-than N --source cli` | Deletes sessions older than N days | Too broad — deletes ALL cli sessions, not just kanban workers |
| `hermes sessions delete <id>` | Deletes one session | Destructive — can't recover |
| `hermes sessions rename <id> <title>` | Renames a session | No bulk operation |

There is **no CLI command for archiving** — only the PATCH API endpoint.

## Recommended Approach

Archive kanban worker sessions older than 3 days via the PATCH API.
Could be added as Phase 4 of the workflow engine or a separate ops cron.
Keep it as a separate concern — session hygiene is not workflow orchestration.

## Session Counts (Jul 2026 baseline)

| Profile | Total sessions | Kanban worker sessions | Older than 3 days |
|---|---|---|---|
| tech-lead | 202 | 195 | 10 |
| developer | 104 | 104 | 0 |
| verifier | 168 | 74 | 2 |
| product-owner | 36 | 7 | 2 |
