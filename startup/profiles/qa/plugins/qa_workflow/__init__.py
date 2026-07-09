"""QA workflow plugin — registration."""

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire schemas to handlers."""
    ctx.register_tool(
        name="qa_swarm",
        toolset="qa_workflow",
        schema=schemas.QA_SWARM,
        handler=tools.qa_swarm,
    )
