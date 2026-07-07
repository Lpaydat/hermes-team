#!/usr/bin/env python3
"""
Session Archiver — archive old kanban worker sessions.

Kanban worker sessions (first user message: "work kanban task t_xxx") pollute
the session list, hiding real conversations. This script archives them after
a configurable age (default: 3 days).

Uses the official SessionStore.set_session_archived() API — not raw SQL.
Archived sessions are hidden from the default list but remain searchable
via session_search.

Runs as a zero-token cron on the ops profile.
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

# Add hermes-agent to path for imports
HERMES_AGENT = Path.home() / ".hermes-teams" / "startup" / "hermes-agent"
sys.path.insert(0, str(HERMES_AGENT))

try:
    from hermes_state import SessionDB
except ImportError:
    print("[session-archiver] ERROR: cannot import SessionDB from hermes_state")
    sys.exit(0)

# Config
OLDER_THAN_DAYS = 3
PROFILES = ["tech-lead", "developer", "verifier", "product-owner", "scout", "venture-builder", "ops"]
PROFILES_DIR = Path.home() / ".hermes-teams" / "startup" / "profiles"

CUTOFF = time.time() - (OLDER_THAN_DAYS * 86400)


def get_kanban_sessions(db_path, cutoff_ts):
    """
    Find sessions that are:
    - source = 'cli' (dispatcher spawns workers via CLI)
    - started_at < cutoff
    - first user message starts with 'work kanban task'
    - not already archived

    Returns list of session IDs.
    """
    if not Path(db_path).exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find sessions where the first user message is a kanban task
    rows = conn.execute("""
        SELECT s.id
        FROM sessions s
        WHERE s.source = 'cli'
          AND s.started_at < ?
          AND s.archived = 0
          AND EXISTS (
            SELECT 1 FROM messages m
            WHERE m.session_id = s.id
              AND m.role = 'user'
              AND m.content LIKE 'work kanban task %'
              AND m.id = (
                SELECT MIN(m2.id) FROM messages m2 WHERE m2.session_id = s.id
              )
          )
    """, (cutoff_ts,)).fetchall()

    conn.close()
    return [r["id"] for r in rows]


def archive_sessions_for_profile(profile_name):
    """Archive old kanban sessions for one profile."""
    state_db = PROFILES_DIR / profile_name / "state.db"
    if not state_db.exists():
        return 0

    session_ids = get_kanban_sessions(str(state_db), CUTOFF)
    if not session_ids:
        return 0

    # Use the official SessionDB API
    store = SessionDB(state_db)  # Pass Path object, not string
    archived = 0
    for sid in session_ids:
        try:
            if store.set_session_archived(sid, True):
                archived += 1
        except Exception as e:
            print(f"[session-archiver] WARNING: failed to archive {sid} on {profile_name}: {e}")

    store.close()
    return archived


def main():
    total = 0
    for profile in PROFILES:
        count = archive_sessions_for_profile(profile)
        if count > 0:
            print(f"[session-archiver] {profile}: archived {count} kanban session(s) older than {OLDER_THAN_DAYS}d")
            total += count

    if total > 0:
        print(f"[session-archiver] Total: {total} session(s) archived")
    # Silent when nothing to archive


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[session-archiver ERROR] {e}", file=sys.stderr)
        sys.exit(0)
