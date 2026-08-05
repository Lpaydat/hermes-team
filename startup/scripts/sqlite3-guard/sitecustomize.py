"""sqlite3 guard — blocks direct writes to kanban/workflow databases via Python.

Patches sqlite3.Connection.execute to refuse writes on protected DBs.
Reads (SELECT, PRAGMA) are always allowed.
"""
import sqlite3 as _sqlite3
import os as _os

_REAL_CONNECT = _sqlite3.connect
_REAL_EXECUTE = _sqlite3.Connection.execute
_REAL_EXECUTEMANY = _sqlite3.Connection.executemany
_REAL_COMMIT = _sqlite3.Connection.commit

_WRITE_KEYWORDS = ('insert', 'update', 'delete', 'drop', 'alter', 'create', 'replace', 'attach', 'detach')
_REAL_KANBAN_HOME = _os.path.expanduser("~/.hermes-teams/startup/kanban")

def _is_protected_path(db_path):
    if not db_path or db_path == ':memory:':
        return False
    p = str(db_path)
    # Only protect the REAL kanban/workflow databases under the hermes home.
    # Test databases in /tmp or other locations are not protected.
    if _REAL_KANBAN_HOME not in p:
        return False
    p_lower = p.lower()
    return ('kanban' in p_lower or 'workflow-state' in p_lower or 'workflow_state' in p_lower)

class _GuardedConnection(_sqlite3.Connection):
    _protected = False

    def _check_write(self, sql):
        if not self._protected:
            return
        sql_stripped = sql.lstrip().lower() if isinstance(sql, str) else ''
        for kw in _WRITE_KEYWORDS:
            if sql_stripped.startswith(kw):
                raise _sqlite3.OperationalError(
                    f"sqlite3-guard: BLOCKED — direct write to protected kanban/workflow database. "
                    f"Use hermes kanban / kanban_* tools instead (they run recompute_ready, "
                    f"event emission, and claim locks properly)."
                )

    def execute(self, sql, *args, **kwargs):
        self._check_write(sql)
        return _REAL_EXECUTE(self, sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        self._check_write(sql)
        return _REAL_EXECUTEMANY(self, sql, *args, **kwargs)

def _guarded_connect(database, *args, **kwargs):
    kwargs.setdefault('factory', _GuardedConnection)
    conn = _REAL_CONNECT(database, *args, **kwargs)
    conn._protected = _is_protected_path(database)
    return conn

_sqlite3.connect = _guarded_connect
