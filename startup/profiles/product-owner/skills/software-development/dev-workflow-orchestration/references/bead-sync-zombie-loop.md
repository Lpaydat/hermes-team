# Bead-Sync Zombie Loop — Root Cause Analysis (Jul 2026)

When building `bead-sync.py` via the dev workflow, three compounding bugs caused
an infinite redispatch loop (48 failed spawns over ~2 hours). This document
traces the full causal chain so it can be prevented in the future.

## The causal chain (chronological)

```
1. PO creates bead-sync PRD (bead ead) → bead stays OPEN
   PO runs "bd close ead" but it doesn't persist (bd uses Dolt, not SQLite)

2. auto-dispatch scans bd ready → finds ead as OPEN → creates card t_5c6c0cac
   (card_exists() returned false — it can't see idempotency_key in the API)

3. PO realizes this is the wrong card (PRD bead, not a slice)
   → archives t_5c6c0cac via "hermes kanban archive"
   → does NOT remove the worktree at .worktrees/t_5c6c0cac/
   → does NOT delete the branch feature/test22-parallel-ead

4. auto-dispatch runs again (1-min cron)
   → card_exists() still returns false (API omits idempotency_key)
   → kanban create's DB-level dedup fails (previous card is archived = excluded)
   → creates card t_1d8fa921 (SECOND card for same bead)

5. Dispatcher tries to spawn t_1d8fa921
   → git worktree add fails: "feature/test22-parallel-ead is already used by
     worktree at .worktrees/t_5c6c0cac"
   → spawn_failed event logged

6. Board scanner sees spawn_failed
   → treats as transient (crash exhaustion pattern)
   → auto-unblocks after 2-min cooldown
   → dispatcher retries → same worktree failure → repeat

7. 48 iterations of spawn_failed → gave_up → unblock → spawn_failed...
   Each pair burns 2 dispatcher attempts and ~6 min of wall-clock time

8. PO manually archives t_1d8fa921
   → scanner unblocks again → auto-dispatch creates THIRD card (t_54a16a0f)
   → this one succeeds (different branch hash in worktree path)

9. Root cause identified: 3 independent bugs, each necessary for the loop
```

## Bug 1: `card_exists()` never works — API doesn't expose `idempotency_key`

**Severity: HIGH** — caused the duplicate dispatch in the first place

The `card_exists()` helper in `auto-dispatch.sh`:

```bash
card_exists() {
  local key="$1"
  local existing
  existing=$(hermes kanban --board "$BOARD" list --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for t in data:
        if t.get('idempotency_key') == '$key' and t.get('status') != 'archived':
            print('exists')
            break
except:
    pass
" 2>/dev/null)
  [ -n "$existing" ]
}
```

Tested: `hermes kanban list --json` returns 106 tasks, 0 have `idempotency_key` populated.
The field IS in the SQLite DB (`tasks.idempotency_key` with an index), but the JSON API omits it.

**Why Test 22 parallel test still worked:** `kanban create --idempotency-key` does its own
internal dedup at the DB level. So even though `card_exists()` was dead code, the create
command itself prevented duplicates — AS LONG AS the previous card wasn't archived.
Once I archived manually, the DB dedup stopped matching, and new cards were created.

**Fix:** Rewrite `card_exists()` to query SQLite directly:

```bash
KANBAN_DB="${HOME}/.hermes-teams/startup/kanban/boards/${BOARD}/kanban.db"

card_exists() {
  local key="$1"
  local existing
  existing=$(sqlite3 "$KANBAN_DB" \
    "SELECT 1 FROM tasks WHERE idempotency_key='$key' AND status!='archived' LIMIT 1;" 2>/dev/null)
  [ "$existing" = "1" ]
}
```

This is 4ms (faster than the API call) and reads the actual stored key.

## Bug 2: Zombie worktree blocks all future worktree creation for that branch

**Severity: HIGH** — turned a duplicate card into a 48-iteration failure loop

`hermes kanban archive <task-id>` does NOT clean up the worktree. It only changes
the task status in SQLite. The git worktree at `.worktrees/<task-id>/` persists,
and the branch stays checked out.

When auto-dispatch creates a new card for the same bead, it gets the same branch
name (`feature/<bead-id>`). `git worktree add` fails:

```
fatal: 'feature/test22-parallel-ead' is already used by worktree at
  '/home/lpaydat/dev-workflow-battle-tests/test22-parallel/.worktrees/t_5c6c0cac'
```

**Fix:** Always clean up worktrees when archiving:

```bash
git worktree remove .worktrees/<task-id> --force
git worktree prune
git branch -D feature/<bead-id>
```

The `card_exists()` SQLite fix (Bug 1) prevents the re-dispatch in the first place,
but cleanup-on-archive is still important hygiene for manual operations.

## Bug 3: Board scanner doesn't handle `dependency` block kind

**Severity: LOW** — stale battle test card stuck indefinitely

The board scanner (`board-scanner.py`) handles:
- `transient` → auto-unblock after 2-min cooldown
- `needs_input` → escalate to correct profile
- crash exhaustion (no `block_kind`, but `gave_up` events) → treat as transient

But tech-lead's self-inflicted `dependency_wait` blocks have:
- `block_kind: null` (not "transient", not "needs_input")
- No `gave_up` events (the task was deliberately blocked, not crashed)

The scanner's logic at line ~282:

```python
if not stuck_children and block_kind != "needs_input":
    continue  # skips dependency_wait blocks entirely
```

Since there are no stuck children (the dependency target completed long ago) and
the kind isn't `needs_input`, the scanner skips it. The card stays blocked forever.

**Fix:** The scanner should check if the block reason contains "dependency" and
either timeout (auto-unblock after N min — the dependency likely resolved) or
log explicitly that it's a dependency block being skipped. Not yet patched —
low severity (only affected stale test artifacts from hours-old battle tests).

## Why bead-sync.py would have prevented all three

1. **Bug 1 (card_exists):** If bead-sync set bead `ead` to `in_progress` when the
   first card was created, `bd ready` wouldn't show it → auto-dispatch wouldn't
   re-dispatch → no second card → no zombie worktree.

2. **Bug 2 (zombie worktree):** Direct consequence of Bug 1. No re-dispatch = no
   worktree collision.

3. **Bug 3 (scanner gap):** Unrelated to bead-sync, but the scanner is the system's
   safety net — if it doesn't catch a block type, that card is orphaned.

## Performance note: idempotency key in SQLite

The idempotency key IS stored correctly in the kanban SQLite DB:

```sql
sqlite3 kanban.db "SELECT id, status, idempotency_key FROM tasks WHERE idempotency_key LIKE 'bead-%';"
-- Returns all bead-linked cards with their keys
```

The DB has an index on it (`idx_tasks_idempotency ON tasks(idempotency_key)`).
The API just doesn't expose it. Any script that needs to check for existing cards
should query SQLite directly, not the API.
