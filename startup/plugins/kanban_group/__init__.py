"""kanban_group plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the group_cards schema to its handler."""
    ctx.register_tool(
        name="group_cards",
        toolset="kanban_group",
        schema=schemas.GROUP_CARDS,
        handler=tools.group_cards,
    )
