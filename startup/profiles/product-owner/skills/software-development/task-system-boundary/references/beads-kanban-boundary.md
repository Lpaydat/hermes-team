# Beads vs Kanban: Failure/Recovery & Internal Mechanics

Detailed evidence from reading `kanban_db.py` (9,584 lines) and the beads (`bd` CLI)
configuration in a live workspace. The SKILL.md has the principles; this file has
the proof.

## Failure/Recovery Matrix

| Scenario | Beads | Kanban | Winner |
|---|---|---|---|
| Board corrupted/deleted | Git-remote sync + Dolt backup | Local-only; corrupt-DB quarantine but no off-machine recovery | **Beads** |
| Agent crash before complete | Uncommitted working-set changes may be lost (auto-commit default off) | Card always survives; 5-layer reclaim/retry/circuit-breaker self-heals | **Kanban** |
| Production bug trace-back | Full Dolt commit history with `bd diff` between arbitrary points | Append-only `task_events` log; no state-diff capability | **Beads** |
| Two agents same item (race) | `bd update --claim` (Dolt SQL transaction, idempotent) | CAS: `UPDATE ... WHERE status='ready' AND claim_lock IS NULL` | **Tie** |
| Machine crash | Survives on git remote; needs manual `bd dolt pull` to recover | Auto-recovers: PID liveness check, TTL reclaim, heartbeat backstop | **Split** |
| Double dispatch | No dispatch loop (N/A) | 7 mechanisms (see below) | **Kanban** |

## Kanban's Double-Dispatch Prevention (7 layers)

All seven live in `hermes_cli/kanban_db.py`. Reading the source is the fastest way
to understand them.

1. **CAS claim** (`claim_task`, line ~3818):
   ```sql
   UPDATE tasks SET status='running', claim_lock=?, claim_expires=?
   WHERE id=? AND status='ready' AND claim_lock IS NULL
   ```
   SQLite WAL serializes writers, exactly one claimer gets `rowcount == 1`.

2. **`_dispatch_tick_lock`** (line ~1424): board-scoped cross-process file lock.
   The losing dispatcher returns `DispatchResult(skipped_locked=True)` and does
   zero DB writes. Prevents orphaned gateway + service gateway from racing on
   WAL frames.

3. **Worker survival check** (`_terminate_reclaimed_worker` + `_defer_reclaim_for_live_worker`,
   line ~6584/6662): before reclaiming a stale claim, tries SIGTERM → SIGKILL on
   the old PID. If the worker survives termination, the claim is **deferred**
   (`claim_expires` extended) not released — prevents a duplicate spawn alongside
   a surviving worker.

4. **Respawn guard** (`check_respawn_guard`): skips re-spawn if the task:
   - completed successfully within `_RESPAWN_GUARD_SUCCESS_WINDOW` (1 hour)
   - has a GitHub PR URL in recent comments (`_RESPAWN_GUARD_PR_WINDOW` = 24h)
   - has a quota/auth blocker in `last_failure_error` (`_RESPAWN_BLOCKER_RE`)

5. **Rate-limit sentinel** (`KANBAN_RATE_LIMIT_EXIT_CODE = 75`): exit code
   `EX_TEMPFAIL` means "rate limited, not failed." Task goes to `ready` without
   counting a failure; respawn deferred by `DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS`
   (5 min). The circuit breaker never trips on a transient throttle.

6. **Idempotency key** (`create_task`, line ~2721): `idempotency_key` parameter
   checks for an existing non-archived task with the same key before inserting.
   Prevents webhook/automation double-writes. Note: the check is BEFORE the
   `write_txn` (line ~2874), so two concurrent creators with the same key can
   both insert — the comment acknowledges this race as acceptable.

7. **Protocol-violation streak** (`_protocol_violation_streak`, line ~7064):
   clean exit (rc=0) without `kanban_complete`/`kanban_block` gets a bounded
   retry budget (`_PROTOCOL_VIOLATION_FAILURE_LIMIT`, separate from the unified
   `consecutive_failures` counter) before tripping the breaker. Empirically ~96%
   complete on a later run, so immediate blocking just churned them.

## Kanban's Crash Recovery Chain

The dispatch tick (`_dispatch_once_locked`, line ~7843) runs this sequence every
60 seconds:

```
dispatch tick
  ├─ reap_worker_zombies        — non-blocking waitpid on all children
  ├─ release_stale_claims       — TTL expired? reclaim (or extend if PID alive & heartbeat fresh)
  ├─ detect_stale_running       — heartbeat stale >1h? reclaim (catches wedged logic loops)
  ├─ detect_crashed_workers     — PID not alive? reclaim + classify exit (crashed/rate_limited/protocol_violation)
  ├─ enforce_max_runtime        — exceeded max_runtime_seconds? SIGTERM→SIGKILL + requeue
  ├─ recompute_ready            — promote todo→ready where all parents done
  └─ spawn ready tasks          — CAS claim + spawn_fn, respecting max_in_progress + per-profile caps
```

**Circuit breaker:** after `DEFAULT_FAILURE_LIMIT` (2) consecutive non-successes,
the task is auto-blocked with a `gave_up` event for human review. Prevents retry
storms on unfixable tasks. Rate-limited requeues do NOT count toward this limit.

**Claim TTL:** `DEFAULT_CLAIM_TTL_SECONDS` = 15 min (configurable via
`HERMES_KANBAN_CLAIM_TTL_SECONDS`). Workers that outlive this should call
`heartbeat_claim` / `kanban_heartbeat` periodically.

**Heartbeat backstop:** `DEFAULT_CLAIM_HEARTBEAT_MAX_STALE_SECONDS` = 1 hour.
If the PID is alive but `last_heartbeat_at` is older than this, the worker is
considered wedged (logic loop) and reclaimed anyway.

## Kanban's Corruption Handling

All in `_guard_existing_db_is_healthy` (line ~1815) and `_backup_corrupt_db`
(line ~1672).

- **`PRAGMA integrity_check`** runs on every connect. Cached per-path per-process.
- **Index-only corruption** (`_repairable_index_names`, line ~1753): if every
  integrity_check message is an index-scoped error ("wrong # of entries in index
  X" / "row N missing from index X"), the table b-trees are intact. Auto-REINDEX
  rebuilds the damaged indexes losslessly. Pre-repair backup taken first.
- **Non-index corruption** (page damage, "database disk image is malformed"):
  fail-closed. Quarantines DB to `<db>.corrupt.<sha256>.bak` (content-addressed,
  capped at 10 via `_prune_corrupt_backups`), raises `KanbanDbCorruptError`.
  No silent schema recreation on damaged DB.
- **`repair_db`** (line ~1933): CLI-callable probe that applies the same narrow
  REINDEX repair. Returns `RepairResult` with status ok/repaired/corrupt/missing.
- **No remote backup.** Disk failure = board gone unless operator backed up manually.

## Beads' Recovery Mechanisms

- **Dolt remotes:** `bd dolt push` / `bd dolt pull` sync via `refs/dolt/data` on
  the git remote (separate from `refs/heads/*` where code lives).
- **Dolt-native backup:** `bd backup init <path>` + `bd backup sync` — full
  database backup (tables, branches, commit history, working-set). Configurable
  for auto-backup with interval.
- **Version history:** `bd history <id>` shows every commit that touched an issue.
  `bd diff <ref1> <ref2>` shows issue changes between any two points.
- **JSONL export:** `bd export` writes issue records to `.beads/issues.jsonl`
  (passive export, not the wire protocol, but usable as a tertiary fallback).
- **Weakness:** default `dolt-auto-commit` is `off`. Uncommitted working-set
  changes can be lost on crash. SIGTERM/SIGHUP flush pending batch commits, but
  a hard crash loses them. The `.beads/backup/` directory holds periodic Dolt
  backups (`backup_state.json` tracks `last_dolt_commit`).

## Kanban Schema (for reference)

Seven tables, all in one SQLite file per board:

| Table | Purpose |
|---|---|
| `tasks` | Core task rows (id, title, body, assignee, status, claim_lock, etc.) |
| `task_links` | Parent-child dependency edges |
| `task_comments` | Threaded discussion per task |
| `task_events` | Append-only audit log (created, claimed, spawned, crashed, completed, etc.) |
| `task_runs` | Historical dispatch attempts (one row per claim, with outcome/summary/error) |
| `task_attachments` | File attachments metadata (blob on disk under `attachments_root(board)/`) |
| `kanban_notify_subs` | Gateway subscriptions (push events to chat platforms) |

The `task_runs` table is the key traceability mechanism: every dispatch attempt
gets a row with `started_at`, `ended_at`, `outcome` (completed/blocked/crashed/
timed_out/spawn_failed/gave_up/reclaimed), `summary`, `metadata` (JSON), and
`error`. The `task_events` table is the finer-grained event stream (heartbeats,
claim extensions, protocol violations, etc.).

## The Critical Gap

**Kanban has no off-machine backup or remote sync.** This is the single most
important architectural constraint. The corruption handling is excellent for
local crash-consistency (WAL + integrity_check + REINDEX + quarantine), but
provides zero disaster recovery.

Beads covers this gap via git-remote sync and Dolt backup. The bead-sync phase
in the workflow engine is the bridge that keeps the two systems aligned. If
bead-sync is running correctly, the kanban board is always reconstructable from
beads — making the board's lack of off-machine backup acceptable.
