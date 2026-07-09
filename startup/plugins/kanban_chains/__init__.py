"""kanban_chains plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the kanban_chains schema to its handler."""
    ctx.register_tool(
        name="kanban_chains",
        toolset="kanban_chains",
        schema=schemas.KANBAN_CHAINS,
        handler=tools.kanban_chains,
    )
