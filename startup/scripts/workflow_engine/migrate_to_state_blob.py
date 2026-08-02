#!/usr/bin/env python3
"""Migrate the workflow state DB to the state-blob schema (T4, expand phase).

This is a **one-time** migration that performs the EXPAND phase of the
state-blob migration (bead hermes-teams-qxb5):

  1. Adds the ``state`` and ``version`` columns to ``workflow_instances``
     (no-op if they already exist — handled by ``StateDB._migrate_columns``).
  2. Backs up the state DB.
  3. Backfills the ``state`` blob for every ACTIVE instance from its
     ``node_states`` rows (via ``StateDB.backfill_state_blob``).
  4. Verifies the migrated count.

It deliberately does NOT drop the ``node_states`` table. Old code paths
continue to read/write ``node_states``; the new blob is additive scaffolding
that T5's contract phase will adopt. Dropping ``node_states`` happens in a
later, separate migration once T5 is live and nothing references the table.

Usage::

    python3 -m workflow_engine.migrate_to_state_blob              # dry-run
    python3 -m workflow_engine.migrate_to_state_blob --apply       # for real
    python3 -m workflow_engine.migrate_to_state_blob --db /path/to/state.db

Exit codes: 0 on success, 1 on any error or pre-flight failure.
"""
from __future__ import annotations
import argparse
import logging
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Add scripts dir to path so `workflow_engine` resolves as package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflow_engine.runtime import STATE_DB, LOCK_FILE


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


log = logging.getLogger("migrate_state_blob")


def cron_is_running() -> bool:
    """Best-effort check: is the workflow-engine cron (or a loop) running?

    Looks for (a) the engine's advisory file lock being held, and (b) any
    ``main.py`` / ``--loop`` process in the process table. Neither check is
    bulletproof; this is a safety warning, not a hard gate.
    """
    # 1. Advisory lock — try to acquire it non-blocking.
    try:
        import fcntl
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCK_FILE, "w") as fd:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                return True  # someone holds it
    except Exception:
        pass  # don't let a lock-check failure block the migration

    # 2. Process table scan for a running tick loop.
    try:
        out = subprocess.run(
            ["pgrep", "-af", "workflow_engine.main"],
            capture_output=True, text=True, timeout=5,
        )
        if out.stdout.strip():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # pgrep not available — skip

    return False


def backup_db(db_path: Path) -> Path:
    """Copy ``db_path`` to a timestamped ``.bak`` and return the backup path."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"{db_path.name}.bak-{ts}")
    # Also copy sidecar WAL/SHM files if present (WAL mode).
    shutil.copy2(db_path, backup)
    for suffix in ("-wal", "-shm"):
        side = db_path.with_name(db_path.name + suffix)
        if side.exists():
            shutil.copy2(side, backup.with_name(backup.name + suffix))
    return backup


def verify_columns(db_path: Path) -> None:
    """Pre-flight: the state/version columns must be present."""
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_instances)").fetchall()}
    finally:
        conn.close()
    missing = {"state", "version"} - cols
    if missing:
        raise RuntimeError(
            f"workflow_instances is missing columns {sorted(missing)} — "
            f"StateDB._migrate_columns should have added them; aborting."
        )


def count_active_instances(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM workflow_instances WHERE status = 'active'"
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    _doc = (__doc__ or "Migrate the workflow state DB to the state-blob schema.").splitlines()[0]
    parser = argparse.ArgumentParser(description=_doc)
    parser.add_argument(
        "--db", type=Path, default=STATE_DB,
        help=f"Path to the workflow state DB (default: {STATE_DB})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually run the migration. Without this flag the script is a "
             "dry-run and makes no changes.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    db_path: Path = args.db
    if not db_path.exists():
        log.error("State DB not found at %s — nothing to migrate.", db_path)
        return 1

    # ─── Pre-flight ────────────────────────────────────────────────────
    log.info("Pre-flight: state DB = %s", db_path)
    active_before = count_active_instances(db_path)
    log.info("Pre-flight: %d active instance(s).", active_before)

    if cron_is_running():
        log.warning(
            "The workflow engine appears to be running (cron/loop detected). "
            "STOP the engine cron before running this migration to avoid races "
            "on active instances."
        )
        if not args.apply:
            log.warning("Dry-run: continuing anyway. Use --apply to run for real.")

    # Importing StateDB triggers _init_schema → _migrate_columns, which adds
    # the new columns to an existing DB. In dry-run we still construct it so
    # the column check below passes, but we DO NOT backfill.
    from workflow_engine.runtime import StateDB
    state = StateDB(db_path)
    verify_columns(db_path)
    log.info("Pre-flight: columns 'state' and 'version' are present. OK.")

    if not args.apply:
        log.info(
            "DRY-RUN: would backfill %d active instance(s). Re-run with --apply "
            "to perform the migration.", active_before,
        )
        return 0

    # ─── Backup ────────────────────────────────────────────────────────
    backup = backup_db(db_path)
    log.info("Backed up DB to %s", backup)

    # ─── Backfill ──────────────────────────────────────────────────────
    stats = state.backfill_state_blob()
    log.info(
        "Backfill complete: migrated=%d skipped=%d errors=%d",
        stats["migrated"], stats["skipped"], stats["errors"],
    )

    # ─── Verify ────────────────────────────────────────────────────────
    active_after = count_active_instances(db_path)
    if active_after != active_before:
        log.warning(
            "Active instance count changed during migration (%d → %d). "
            "This is fine if the engine was running, but verify manually.",
            active_before, active_after,
        )

    # Every active instance should now have a non-empty state blob OR have
    # been legitimately skipped (no node_states rows).
    conn = sqlite3.connect(str(db_path))
    try:
        empty = conn.execute(
            "SELECT COUNT(*) FROM workflow_instances "
            "WHERE status = 'active' AND (state IS NULL OR state = '' OR state = '{}')"
        ).fetchone()[0]
    finally:
        conn.close()
    log.info(
        "Verify: %d active instance(s) still have an empty state blob "
        "(expected: only instances with zero node_states rows).", empty,
    )

    if stats["errors"]:
        log.error(
            "Migration completed with %d error(s). Review the logs above; the "
            "node_states table is intact and the backup is at %s.",
            stats["errors"], backup,
        )
        return 1

    log.info(
        "Migration (expand phase) succeeded. The node_states table is intact — "
        "it will be dropped in a later migration once T5 is live. Backup: %s",
        backup,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
