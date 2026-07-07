"""Dev workflow plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire schemas to handlers."""
    ctx.register_tool(
        name="kanban_delegate",
        toolset="dev_workflow",
        schema=schemas.KANBAN_DELEGATE,
        handler=tools.kanban_delegate,
    )
