"""kill_task plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the kill_task schema to its handler."""
    ctx.register_tool(
        name="kill_task",
        toolset="kill_task",
        schema=schemas.KILL_TASK,
        handler=tools.kill_task,
    )
