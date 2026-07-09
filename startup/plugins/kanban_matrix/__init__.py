"""kanban_matrix plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the kanban_matrix schema to its handler."""
    ctx.register_tool(
        name="kanban_matrix",
        toolset="kanban_matrix",
        schema=schemas.KANBAN_MATRIX,
        handler=tools.kanban_matrix,
    )
