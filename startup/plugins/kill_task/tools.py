"""Tool handlers — kill_task: process-tree-safe worker termination.

When a kanban worker is killed, its terminal-spawned grandchildren (grep,
find, rustc, cargo, codex, ...) survive as orphans because every subprocess
is launched in its own session (``start_new_session=True``). ``killpg`` on
the worker's process group misses them. This tool walks ``/proc/*/stat``
following PPID chains to find the FULL descendant tree while the worker is
still alive, then kills deepest-first.
"""

import json
import logging
import os
import signal
import subprocess
import time

logger = logging.getLogger(__name__)

# /proc is only meaningful on Linux. The plugin manifest and tool description
# already document "local backend only", but this guard prevents confusing
# errors on macOS/Windows dev machines where someone enables the plugin.
_IS_LINUX = os.path.exists("/proc") and os.path.isdir("/proc/1")


# ─── helpers: board / PID resolution ──────────────────────────────────────

def _get_board(args: dict) -> str:
    """Resolve the board slug from args or env (same pattern as kanban_chains)."""
    return (args.get("board") or "").strip() or os.environ.get(
        "HERMES_KANBAN_BOARD", "startup"
    )


def _run_kanban_json(args_list, board):
    """Run a ``hermes kanban`` command with --json, return parsed JSON or None."""
    cmd = ["hermes", "kanban", "--board", board] + args_list + ["--json"]
    env = os.environ.copy()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=env
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _extract_pid(value):
    """Coerce a payload value to int PID, or None if not a valid PID."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_worker_pid(payload):
    """Extract the worker PID from a ``kanban show --json`` payload.

    Priority (per the handoff spec, L23): the 'spawned' event's ``{"pid": N}``
    is the primary source; the latest run's ``worker_pid`` is a fallback for
    builds/rows where the spawn event isn't present. Returns None if no PID
    can be found.
    """
    # 1. Latest 'spawned' event carrying {"pid": N}.
    events = payload.get("events") or []
    for ev in reversed(events):
        if ev.get("kind") == "spawned":
            pid = _extract_pid((ev.get("payload") or {}).get("pid"))
            if pid is not None:
                return pid

    # 2. Fallback: latest run with a non-null worker_pid.
    runs = payload.get("runs") or []
    for run in reversed(runs):
        pid = _extract_pid(run.get("worker_pid"))
        if pid is not None:
            return pid
    return None


# ─── helpers: /proc PPID walk ─────────────────────────────────────────────

def _read_proc_stat_fields(pid):
    """Read the post-``comm`` fields from /proc/<pid>/stat.

    /proc/<pid>/stat format:  ``<pid> (<comm>) <state> <ppid> <pgrp> ...``
    ``comm`` can contain spaces and parentheses, so we split from the LAST
    ``)`` rather than naively tokenising the whole line.

    Returns the list of byte-fields after the closing paren
    (``[state, ppid, pgrp, session, ...]``), or None if the process is gone
    or unreadable. Both ``_read_ppid`` and ``_proc_state`` share this single
    read so the /proc parsing logic lives in exactly one place.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    try:
        close_paren = data.rindex(b")")
    except ValueError:
        return None
    # After the closing paren: b" S <ppid> <pgrp> <session> ..."
    return data[close_paren + 2:].split()


def _read_ppid(pid):
    """Read the PPID of ``pid`` from /proc/<pid>/stat, or None if gone."""
    fields = _read_proc_stat_fields(pid)
    if fields is None:
        return None
    try:
        return int(fields[1])  # fields[0]=state, fields[1]=ppid
    except (IndexError, ValueError):
        return None


def _collect_descendants(root_pid):
    """Return all PIDs whose PPID chain leads to ``root_pid`` (exclusive).

    Sorted deepest-first so we kill grandchildren before children, avoiding
    races where a child spawns a new process between the walk and the kill.
    Does NOT include ``root_pid`` itself.
    """
    # Build ppid -> [child_pids] for every process in /proc.
    children = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == root_pid:
            continue
        ppid = _read_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)

    # BFS from root_pid to collect descendants with their depth.
    result = []  # (depth, pid)
    queue = [(root_pid, 0)]
    while queue:
        parent, depth = queue.pop(0)
        for child in children.get(parent, []):
            result.append((depth + 1, child))
            queue.append((child, depth + 1))

    # Deepest-first: highest depth sorts first.
    result.sort(key=lambda pair: -pair[0])
    return [pid for _, pid in result]


def _proc_state(pid):
    """Return the single-letter state from /proc/<pid>/stat, or None if gone.

    States: R S D Z T t W X x K W P. ``Z`` = zombie (already dead, just
    unreaped). ``None`` = no such process / unreadable.
    """
    fields = _read_proc_stat_fields(pid)
    if fields is None:
        return None
    # fields[0] is the state char; decode defensively.
    try:
        return fields[0].decode("ascii", "replace")
    except (IndexError, UnicodeDecodeError):
        return None


def _pid_alive(pid):
    """True if ``pid`` exists AND is not a zombie.

    ``os.kill(pid, 0)`` succeeds on zombies (they still have a PID table
    entry until reaped), which would make us loop waiting for processes
    that are already dead. We read /proc state and treat ``Z`` as dead.
    """
    state = _proc_state(pid)
    if state is None:
        # No /proc entry — either truly gone, or /proc unavailable. Fall
        # back to the kill(0) probe so the function is still correct on
        # non-/proc systems (and for PIDs that vanished between the stat
        # read and now).
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    return state != "Z"


# ─── helpers: tiered kill ─────────────────────────────────────────────────

def _signal_many(pids, sig):
    """Send ``sig`` to every PID in ``pids``. Returns (signaled, already_dead, denied)."""
    signaled, already_dead, denied = [], [], []
    for pid in pids:
        try:
            os.kill(pid, sig)
            signaled.append(pid)
        except ProcessLookupError:
            already_dead.append(pid)
        except PermissionError:
            denied.append(pid)
        except OSError:
            already_dead.append(pid)
    return signaled, already_dead, denied


def _wait_for_exit(pids, timeout):
    """Poll until none of ``pids`` are alive or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_pid_alive(p) for p in pids):
            return True
        time.sleep(0.05)
    return not any(_pid_alive(p) for p in pids)


def _empty_kill_result():
    """A fresh tiered-kill result dict — one shape, reused everywhere."""
    return {"signaled": [], "sigkilled": [], "already_dead": [], "permission_denied": []}


def _tiered_kill(pids, timeout, force=False):
    """SIGTERM -> wait -> SIGKILL for a list of PIDs.

    Mirrors the terminal tool's ``_kill_process`` semantics
    (tools/environments/local.py:1556): graceful SIGTERM, brief grace period,
    then SIGKILL for survivors. With ``force=True`` the SIGTERM phase is
    skipped and we go straight to SIGKILL.

    Returns a dict: {signaled, sigkilled, already_dead, permission_denied}
    (each a list of PIDs).
    """
    result = _empty_kill_result()
    if not pids:
        return result

    if not force:
        term_sent, dead, denied = _signal_many(pids, signal.SIGTERM)
        result["signaled"] = term_sent
        result["already_dead"] = dead
        result["permission_denied"] = denied
        _wait_for_exit(term_sent, timeout)

    # Whatever is still alive gets SIGKILL.
    survivors = [p for p in pids if _pid_alive(p)]
    if survivors:
        kill_sent, kill_dead, kill_denied = _signal_many(survivors, signal.SIGKILL)
        result["sigkilled"] = kill_sent
        result["already_dead"] += kill_dead
        result["permission_denied"] += kill_denied
        _wait_for_exit(kill_sent, timeout)

    return result


def _merge_kill_results(*results):
    """Merge multiple _tiered_kill result dicts into one.

    Used instead of shuttling four parallel lists around (the data-clump
    smell): each _tiered_kill already returns the natural type, so we
    accumulate the dicts directly.
    """
    merged = _empty_kill_result()
    for r in results:
        for key in merged:
            merged[key] += r.get(key, [])
    return merged


# ─── tool entry point ────────────────────────────────────────────────────

def kill_task(args: dict, **kwargs) -> str:
    """Kill a kanban worker and its entire process tree (PPID-walked)."""
    task_id = (args.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required"})

    dry_run = bool(args.get("dry_run", False))
    force = bool(args.get("force", False))
    timeout = float(args.get("timeout_seconds", 2.0))
    board = _get_board(args)

    if not _IS_LINUX:
        return json.dumps({
            "error": "kill_task only works on Linux (reads /proc). "
                     "This host does not have /proc.",
            "task_id": task_id,
        })

    # 1. Resolve the worker PID from the board.
    payload = _run_kanban_json(["show", task_id], board)
    if not payload:
        return json.dumps({
            "error": f"Could not read task {task_id} from board '{board}'. "
                     "Is the task id correct and is `hermes kanban` available?",
            "task_id": task_id,
            "board": board,
        })

    worker_pid = _resolve_worker_pid(payload)
    if not worker_pid:
        return json.dumps({
            "error": f"No worker PID found for task {task_id}. The task may "
                     "never have been dispatched, or the worker already exited "
                     "and its PID was cleared.",
            "task_id": task_id,
            "board": board,
        })

    # Guard against self-kill: the tool process IS the worker.
    if worker_pid == os.getpid():
        return json.dumps({
            "error": f"Refusing to kill self (pid {worker_pid}). The target "
                     "task's worker PID resolves to this process.",
            "task_id": task_id,
            "worker_pid": worker_pid,
        })

    worker_alive = _pid_alive(worker_pid)

    # 2. Walk /proc to collect descendants WHILE the worker is alive.
    descendants = _collect_descendants(worker_pid) if worker_alive else []

    if dry_run:
        return json.dumps({
            "dry_run": True,
            "task_id": task_id,
            "worker_pid": worker_pid,
            "worker_alive": worker_alive,
            "descendants": descendants,
            "would_kill": descendants + ([worker_pid] if worker_alive else []),
            "message": (
                f"Would kill {len(descendants)} descendant(s) + worker "
                f"pid {worker_pid}."
            ) if worker_alive else (
                f"Worker pid {worker_pid} is NOT alive — no descendants "
                f"to walk (tree already reparented to init)."
            ),
        }, indent=2)

    # 3. Kill descendants deepest-first, then the worker last. Each tiered
    #    kill returns the natural result dict; merge them rather than
    #    unpacking into parallel lists.
    kill_results = []
    if descendants:
        kill_results.append(_tiered_kill(descendants, timeout, force=force))
    if worker_alive:
        kill_results.append(_tiered_kill([worker_pid], timeout, force=force))
    totals = _merge_kill_results(*kill_results)

    killed_pids = sorted(set(totals["signaled"] + totals["sigkilled"]))
    already_dead = sorted(set(totals["already_dead"]))
    permission_denied = sorted(set(totals["permission_denied"]))
    return json.dumps({
        "task_id": task_id,
        "worker_pid": worker_pid,
        # Spec-required contract field (handoff L53): killed_pids.
        "killed_pids": killed_pids,
        # Diagnostics — stable, caller-facing but not part of the contract.
        "worker_was_alive": worker_alive,
        "descendants_found": descendants,
        "already_dead": already_dead,
        "permission_denied": permission_denied,
        "message": (
            f"Killed {len(killed_pids)} process(es): worker {worker_pid}"
            + (f" + {len(descendants)} descendant(s)" if descendants else "")
            + (f". {len(permission_denied)} denied (permission)." if permission_denied else "")
        ),
    }, indent=2)
