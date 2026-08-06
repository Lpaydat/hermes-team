"""Kanban adapter — the engine's interface to the board.

This is a thin wrapper around `hermes kanban` CLI + direct SQLite reads.
The engine never talks to the board without going through this layer.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import contextlib
import json
import sqlite3
import subprocess
import time
import logging

log = logging.getLogger(__name__)

KANBAN_HOME = Path.home() / ".hermes-teams/startup/kanban/boards"


@dataclass
class CardInfo:
    """Minimal card representation for the engine."""
    id: str
    title: str
    assignee: str
    status: str  # todo, ready, running, blocked, done, archived
    idempotency_key: str | None = None
    metadata: dict | None = None
    completed_at: int | None = None
    summary: str | None = None


def board_db_path(board: str) -> Path:
    return KANBAN_HOME / board / "kanban.db"


@contextlib.contextmanager
def _connect(db: Path):
    """Context manager for opening a board DB with Row factory.

    Handles the connect → row_factory → close pattern shared by all board
    read functions. Yields the connection, closes it on exit.
    """
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def run_kanban(board: str, args: list[str]) -> tuple[bool, str]:
    """Run a hermes kanban command. Returns (success, output)."""
    cmd = ["hermes", "kanban", "--board", board] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.error("kanban cmd failed: %s\nstderr: %s", " ".join(cmd), result.stderr[:200])
            return False, result.stderr
        return True, result.stdout
    except subprocess.TimeoutExpired:
        log.error("kanban cmd timed out: %s", " ".join(cmd))
        return False, "timeout"
    except FileNotFoundError:
        log.error("hermes CLI not found on PATH")
        return False, "hermes not found"


def create_card(
    board: str,
    title: str,
    assignee: str,
    body: str = "",
    idempotency_key: str | None = None,
    priority: int | None = None,
    workspace: str | None = None,
    parent: str | None = None,
) -> tuple[bool, str]:
    """Create a kanban card. Returns (success, card_id_or_error)."""
    args = ["create", title, "--assignee", assignee]
    if body:
        args += ["--body", body]
    if idempotency_key:
        args += ["--idempotency-key", idempotency_key]
    if priority is not None:
        args += ["--priority", str(priority)]
    if workspace:
        args += ["--workspace", workspace]
    if parent:
        args += ["--parent", parent]
    args += ["--json"]
    return run_kanban(board, args)


def get_card(board: str, card_id: str) -> CardInfo | None:
    """Get a card by ID from the board's SQLite DB."""
    db = board_db_path(board)
    if not db.exists():
        return None

    with _connect(db) as conn:
        row = conn.execute(
            """SELECT id, title, assignee, status, idempotency_key, completed_at
               FROM tasks WHERE id = ?""",
            (card_id,),
        ).fetchone()
        if not row:
            return None
        return CardInfo(
            id=row["id"],
            title=row["title"],
            assignee=row["assignee"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            completed_at=row["completed_at"],
        )


def _parse_metadata(raw: str | None) -> dict:
    """Parse a JSON metadata string, returning {} on any error."""
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def get_card_metadata(board: str, card_id: str) -> dict:
    """Get the latest run metadata for a card."""
    db = board_db_path(board)
    if not db.exists():
        return {}

    with _connect(db) as conn:
        row = conn.execute(
            """SELECT metadata, summary FROM task_runs
               WHERE task_id = ? AND outcome = 'completed'
               ORDER BY id DESC LIMIT 1""",
            (card_id,),
        ).fetchone()
        if not row:
            return {}
        return {"metadata": _parse_metadata(row["metadata"]), "summary": row["summary"] or ""}


def find_cards_by_idempotency_key(board: str, key: str) -> list[CardInfo]:
    """Find cards matching an idempotency key."""
    db = board_db_path(board)
    if not db.exists():
        return []

    with _connect(db) as conn:
        rows = conn.execute(
            """SELECT id, title, assignee, status, idempotency_key, completed_at
               FROM tasks WHERE idempotency_key = ?""",
            (key,),
        ).fetchall()
        return [
            CardInfo(
                id=r["id"],
                title=r["title"],
                assignee=r["assignee"],
                status=r["status"],
                idempotency_key=r["idempotency_key"],
                completed_at=r["completed_at"],
            )
            for r in rows
        ]


def find_recent_completions(board: str, since_ts: int) -> list[CardInfo]:
    """Find cards completed since a timestamp (Unix epoch seconds)."""
    db = board_db_path(board)
    if not db.exists():
        return []

    try:
        with _connect(db) as conn:
            rows = conn.execute(
                """SELECT t.id, t.title, t.assignee, t.status, t.idempotency_key,
                          t.completed_at, r.metadata, r.summary
                   FROM tasks t
                   JOIN task_runs r ON r.task_id = t.id AND r.outcome = 'completed'
                   WHERE t.status = 'done' AND t.completed_at > ?
                   ORDER BY t.completed_at DESC
                   LIMIT 200""",
                (since_ts,),
            ).fetchall()
    except sqlite3.OperationalError as e:
        # A board DB may exist but be corrupt or uninitialized (e.g. an empty
        # 4 KB file left when init was interrupted, lacking the `tasks` table).
        # The trigger scan iterates ALL boards; one unreadable board must not
        # crash the whole tick. Treat it as having no completions.
        log.warning("Board %r DB unreadable (%s); skipping trigger scan", board, e)
        return []

    cards = []
    for r in rows:
        meta = _parse_metadata(r["metadata"])
        cards.append(
            CardInfo(
                id=r["id"],
                title=r["title"],
                assignee=r["assignee"],
                status=r["status"],
                idempotency_key=r["idempotency_key"],
                completed_at=r["completed_at"],
                metadata=meta,
                summary=r["summary"] or "",
            )
        )
    return cards


def validate_against_schema(instance: dict, schema: dict) -> tuple[bool, str]:
    """Validate a dict against a JSON Schema.

    Uses jsonschema if available, otherwise falls back to a minimal
    required-field check. Returns (valid, error_message).

    Shared by validate_output (board card metadata) and subworkflow
    completion (in-memory mapped_output).
    """
    try:
        from jsonschema import validate
        validate(instance=instance, schema=schema)
        return True, ""
    except ImportError:
        # jsonschema not installed — do a minimal required-field check
        for key in schema.get("required", []):
            if key not in instance:
                return False, f"Missing required field: {key}"
        return True, ""
    except Exception as e:
        return False, str(e)


def validate_output(board: str, card_id: str, schema: dict) -> tuple[bool, str]:
    """Validate a card's output metadata against a JSON Schema.

    Returns (valid, error_message).
    """
    info = get_card_metadata(board, card_id)
    metadata = info.get("metadata", {})
    return validate_against_schema(metadata, schema)
