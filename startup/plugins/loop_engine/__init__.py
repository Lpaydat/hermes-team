"""loop_engine plugin — registration.

The FIRST plugin to register BOTH a control tool and an observer hook.
The engine is tool-driven (the driver reads board state on its own promotion);
the hook is observer-only telemetry, so it is unaffected by the verified
recompute_ready ordering hazard (dependents promote BEFORE the
kanban_task_completed hook fires). See SPEC.md §Implementation Decisions.
"""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the loop_engine control tool + an observer telemetry hook."""
    ctx.register_tool(
        name="loop_engine",
        toolset="loop_engine",
        schema=schemas.LOOP_ENGINE,
        handler=tools.loop_engine,
    )
    ctx.register_hook("kanban_task_completed", _on_task_completed)


def _on_task_completed(task_id=None, board=None, assignee=None,
                       run_id=None, profile_name=None, summary=None, **_kw):
    """Observer-only telemetry hook (T1 stub).

    Fired by hermes_cli.kanban_db in the WORKER process AFTER the state change
    is committed. Return value is ignored by the host. The engine never reads
    loop progress through this hook — it re-reads the board on its own
    promotion — so this only records a debug log.
    """
    logger.debug(
        "loop_engine observer: task %s completed (board=%s run_id=%s)",
        task_id, board, run_id,
    )
