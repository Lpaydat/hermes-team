# Cleaning agent context for clean-slate tests

Agent sessions live in `<profile>/state.db` (SQLite with FTS5). The CLI (`hermes -p <profile> sessions`)
is the safe interface. Direct DB manipulation is the nuclear option when the CLI's time filters
don't catch what you need (timezone mismatches, archived sessions, FTS staleness).

## CLI approach (try first)

### Inspect
```bash
hermes -p <profile> sessions list --limit 50
hermes -p <profile> sessions stats
```

### Purge by time
```bash
# Duration-based (timezone-safe)
hermes -p <profile> sessions prune --older-than "2d" --yes
hermes -p <profile> sessions prune --before "2026-07-21 00:00" --yes

# Include archived sessions
hermes -p <profile> sessions prune --before "<date>" --include-archived --yes
```

### Delete specific sessions
```bash
hermes -p <profile> sessions delete <session-id> --yes
```

### Rebuild FTS after bulk changes
```bash
hermes -p <profile> sessions optimize
```

## Direct DB approach (when CLI isn't enough)

The session store is at: `~/.hermes-teams/startup/profiles/<profile>/state.db`

Tables: `sessions`, `messages`, `messages_fts` (FTS5 virtual), `messages_fts_trigram`,
plus session_model_usage, async_delegations, etc.

**CRITICAL:** Before any direct DB work:
1. Check for running workers: `ps aux | grep "hermes.*kanban task" | grep -v grep`
2. Identify real-work sessions by matching task IDs in session cwd/title
3. Back up the DB first: `cp state.db state.db.bak`

### Surgical purge (keep specific sessions, delete everything else)
```python
import sqlite3

db = sqlite3.connect('<path>/state.db')
cur = db.cursor()

# Sessions to KEEP (real work)
keep_ids = ('session_id_1', 'session_id_2', 'session_id_3')

# Delete messages for sessions we're removing
cur.execute(f"DELETE FROM messages WHERE session_id NOT IN {keep_ids}")
print(f"Messages deleted: {cur.rowcount}")

# Delete the sessions
cur.execute(f"DELETE FROM sessions WHERE id NOT IN {keep_ids}")
print(f"Sessions deleted: {cur.rowcount}")

db.commit()
db.close()
```

### After direct DB manipulation
```bash
hermes -p <profile> sessions optimize
```
This rebuilds the FTS5 index and VACUUMs. Without it, session_search may return stale
results pointing to deleted sessions.

## Memory cleanup

Check and clean the agent's MEMORY.md for references to test artifacts:
```bash
cat ~/.hermes-teams/startup/profiles/<profile>/memories/MEMORY.md
```

Remove lines referencing test runs, grill tests, or test board names. Use `patch` with
`cross_profile=True` since you're editing another profile's memory:
```
patch(path="<profile-path>/memories/MEMORY.md",
      mode="replace",
      old_string="<test-reference-line>",
      new_string="",
      cross_profile=True)
```

## Board cleanup

### List all boards
```bash
hermes kanban boards list
```

### Delete test boards
```bash
# Hard delete (gone forever)
hermes kanban boards rm --delete <test-slug>

# Archive (recoverable)
hermes kanban boards rm <test-slug>
```

### Find stray cards on wrong boards
If a card was created without `board=`, it landed on the "current" board. Check:
```bash
hermes kanban boards list    # look for the ● current marker
hermes kanban --board <slug> show <task-id>
```

## Verification checklist

- [ ] Test board created and confirmed in `boards list`
- [ ] All kanban calls used `board=<test-slug>` explicitly
- [ ] Agent sessions purged (only real-work sessions remain)
- [ ] Agent MEMORY.md cleaned of test references
- [ ] `sessions optimize` run after purges
- [ ] Card body includes explicit "do NOT search history" instruction
- [ ] Test subject is synthetic (not in any agent's prior context)
- [ ] Running real-work processes identified and excluded from cleanup
