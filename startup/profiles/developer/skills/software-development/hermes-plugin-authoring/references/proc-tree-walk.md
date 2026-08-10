# proc-tree-walk — killing a process AND all its descendants on Linux

When you kill a worker process, its grandchildren (grep, find, rustc, cargo,
codex, …) often survive as orphans reparented to init. This is because each
subprocess is spawned in its own session (`start_new_session=True`), so
`killpg(worker_pgid)` misses grandchildren in different process groups.

## The problem: process groups diverge from the process tree

```
gateway (pgid=A)
  └─ worker (pgid=B)           ← start_new_session=True
       └─ grep (pgid=C)        ← terminal tool ALSO start_new_session=True
       └─ find (pgid=D)        ← another terminal command, another pgid
       └─ rustc (pgid=E)
```

`killpg(B)` kills the worker but NOT grep/find/rustc — they're in different
process groups. Only PPID (parent PID) chains connect them, and those break
once the worker dies (descendants reparent to PID 1).

## The solution: PPID-walk BEFORE killing, then kill deepest-first

1. While the worker is still alive, walk `/proc/*/stat` following PPID chains
   to collect ALL descendants.
2. Kill deepest-first (grandchildren before children) so a dying process can't
   spawn a new child between the walk and the kill.
3. Tiered kill: SIGTERM → wait → SIGKILL for survivors.

## THE GOTCHA: os.kill(pid, 0) succeeds on zombies

This bit me during testing. After you SIGKILL a process, it becomes a
**zombie** if its parent hasn't reaped it. `os.kill(pid, 0)` returns success
(0) on zombies because they still occupy a PID table entry until reaped.
A naïve wait-loop `while os.kill(pid, 0): time.sleep(0.05)` will spin until
the timeout, falsely believing the process is alive.

**Fix:** read the state char from `/proc/<pid>/stat` and treat `Z` as dead.

IMPORTANT: `_read_ppid` and `_proc_state` both need the post-`comm` fields
from `/proc/<pid>/stat`. Do NOT duplicate the open/read/rindex/split logic
across both — extract ONE `_read_proc_stat_fields` helper and have each
call it (a code review flagged the duplication as the top smell; the
deduplicated version below is the verified pattern).

```python
def _read_proc_stat_fields(pid):
    """Read the post-comm fields from /proc/<pid>/stat.

    Format: <pid> (<comm>) <state> <ppid> <pgrp> ...
    comm can contain spaces and parens, so split from the LAST ')'.
    Returns [state, ppid, pgrp, ...] as bytes, or None if gone/unreadable.
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
    return data[close_paren + 2:].split()

def _read_ppid(pid):
    fields = _read_proc_stat_fields(pid)
    if fields is None:
        return None
    try:
        return int(fields[1])  # fields[0]=state, fields[1]=ppid
    except (IndexError, ValueError):
        return None

def _proc_state(pid):
    """Z = zombie (already dead, unreaped). None = gone."""
    fields = _read_proc_stat_fields(pid)
    if fields is None:
        return None
    try:
        return fields[0].decode("ascii", "replace")
    except (IndexError, UnicodeDecodeError):
        return None

def _pid_alive(pid):
    state = _proc_state(pid)
    if state is None:
        # /proc unavailable — fall back to kill(0) probe
        try:
            os.kill(pid, 0); return True
        except ProcessLookupError: return False
        except PermissionError: return True
    return state != "Z"
```

## The PPID walk (deepest-first)

`_read_ppid` is defined above (it calls the shared `_read_proc_stat_fields`).
The walk builds a PPID→children map of the whole `/proc` tree, then BFS from
the root to collect descendants sorted deepest-first:

```python
def _collect_descendants(root_pid):
    """All PIDs whose PPID chain leads to root_pid, deepest-first."""
    children = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == root_pid:
            continue
        ppid = _read_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)
    # BFS from root, tracking depth; sort deepest-first
    result = []
    queue = [(root_pid, 0)]
    while queue:
        parent, depth = queue.pop(0)
        for child in children.get(parent, []):
            result.append((depth + 1, child))
            queue.append((child, depth + 1))
    result.sort(key=lambda p: -p[0])  # highest depth first
    return [pid for _, pid in result]
```

## The tiered kill (mirrors tools/environments/local.py `_kill_process`)

```python
def _tiered_kill(pids, timeout=2.0, force=False):
    """SIGTERM → wait → SIGKILL. force=True skips straight to SIGKILL."""
    result = {"signaled": [], "sigkilled": [], "already_dead": [], "denied": []}
    if not pids:
        return result
    if not force:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM); result["signaled"].append(pid)
            except ProcessLookupError: result["already_dead"].append(pid)
            except PermissionError: result["denied"].append(pid)
        _wait_for_exit(result["signaled"], timeout)
    survivors = [p for p in pids if _pid_alive(p)]
    for pid in survivors:
        try:
            os.kill(pid, signal.SIGKILL); result["sigkilled"].append(pid)
        except (ProcessLookupError, OSError): pass
    _wait_for_exit(result["sigkilled"], timeout)
    return result
```

`_wait_for_exit` MUST use the state-aware `_pid_alive`, not `os.kill(pid, 0)`.

## Killing order: descendants first, worker LAST

Always kill descendants deepest-first, THEN the worker. If you kill the worker
first, its children reparent to init and the PPID chain breaks — the walk you
did becomes stale, and any process spawned after the walk is invisible.

## Why this is safe (no cross-worker kills)

Each process has exactly ONE PPID. The recursive walk only follows PPID
chains descending from the target worker. Two workers running rustc have
different PIDs and disjoint PPID chains — the walk finds only the target's
descendants.

## Edge case: worker already dead

If the worker is already dead (reparented to init), the PPID walk finds
nothing. Handle this: report `worker_alive: false` and that no descendants
could be reached. For this case you'd need the worker's process group stored
at spawn time, or systemd cgroups — but the walk-while-alive approach covers
the 99% case where the tool is called BEFORE the worker is externally killed.

## Verified working

This pattern was built and tested in the `kill_task` plugin (2026-08):
- 3-level process tree (bash → 2 bash → 2 sleep each) killed cleanly.
- Deepest-first ordering verified: grandchildren (depth 2) killed before
  their parent bash (depth 1).
- Zombie gotcha caught and fixed during testing — naïve `os.kill(pid,0)`
  loops would have spun on reaped children indefinitely.
