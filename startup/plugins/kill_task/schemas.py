"""Tool schema — what the LLM sees for kill_task."""

KILL_TASK = {
    "name": "kill_task",
    "description": (
        "Kill a kanban worker process AND every descendant it spawned.\n\n"
        "WHY: kanban workers are spawned with start_new_session=True, and each "
        "terminal command the worker runs is ALSO in its own process group. "
        "A plain kill(worker_pid) or killpg(worker_pgid) leaves grandchildren "
        "(grep, find, rustc, cargo, codex, …) alive as orphans reparented to "
        "init, where they burn CPU forever.\n\n"
        "WHAT THIS DOES:\n"
        "1. Resolves the worker PID for the task (from the latest run's "
        "worker_pid, falling back to the 'spawned' event payload).\n"
        "2. While the worker is still alive, walks /proc/*/stat following PPID "
        "chains to collect the ENTIRE descendant tree.\n"
        "3. Kills deepest-first: SIGTERM every descendant, wait up to "
        "timeout_seconds, then SIGKILL survivors.\n"
        "4. Finally SIGTERM→SIGKILL the worker PID itself.\n\n"
        "Call this BEFORE externally killing the worker — the PPID walk only "
        "finds descendants while the worker is alive (once it dies, descendants "
        "reparent to init and the chain breaks).\n\n"
        "This tool does NOT block/archive the task — the dispatcher may respawn "
        "it. To prevent respawn, stop the gateway first or block the task. "
        "Local backend only; docker/ssh workers have different process isolation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The kanban task whose worker (and descendants) to kill.",
            },
            "board": {
                "type": "string",
                "description": "Board slug. Defaults to HERMES_KANBAN_BOARD env var.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, walk the tree and report what WOULD be killed without sending any signal. Safe to inspect.",
                "default": False,
            },
            "force": {
                "type": "boolean",
                "description": "If true, skip the SIGTERM grace period and SIGKILL immediately (for stuck/unresponsive processes).",
                "default": False,
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Seconds to wait after SIGTERM before escalating to SIGKILL. Default 2.0.",
                "default": 2.0,
            },
        },
        "required": ["task_id"],
    },
}
