"""context_graph plugin — a SQLite-backed graph for dynamic project context.

Replaces monolithic CONTEXT.md with a queryable graph:
- Nodes: decisions, facts, terms, artifacts (with status + content + multi-topic tags).
- Edges: blocks, relates_to, caused_by, supersedes, part_of, references (typed).
- Queries: frontier (work queue), pull (topic subgraph), context (node neighborhood).

Multi-topic: one decision tagged auth+data-store+security → retrieved by ALL three
pull() queries. No duplication. No "which file?" ambiguity.

Tools registered:
  graph_frontier     — open decision/fact nodes with no open blockers
  graph_pull         — topic subgraph (multi-topic retrieval)
  graph_context      — node + its neighborhood (focused context)
  graph_add_node     — create a node (with optional multi-topic tags)
  graph_add_edge     — create a typed edge
  graph_resolve_node — mark resolved + record the answer
  graph_tree         — recursive dependency tree
  graph_stats        — node/edge/topic counts
  graph_remaining    — ALL open decision/fact nodes (the grill backlog; empty == done)
"""

import logging

from . import schemas, tools
from . import context_graph as cg

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire the context_graph tools."""
    # initialize the DB on first load
    cg.init_db()

    tools_to_register = [
        ("graph_frontier",     schemas.GRAPH_FRONTIER,     tools.graph_frontier),
        ("graph_pull",         schemas.GRAPH_PULL,         tools.graph_pull),
        ("graph_context",      schemas.GRAPH_CONTEXT,      tools.graph_context),
        ("graph_add_node",     schemas.GRAPH_ADD_NODE,     tools.graph_add_node),
        ("graph_add_edge",     schemas.GRAPH_ADD_EDGE,     tools.graph_add_edge),
        ("graph_resolve_node", schemas.GRAPH_RESOLVE_NODE, tools.graph_resolve_node),
        ("graph_tree",         schemas.GRAPH_TREE,         tools.graph_tree),
        ("graph_stats",        schemas.GRAPH_STATS,        tools.graph_stats),
        ("graph_remaining",    schemas.GRAPH_REMAINING,    tools.graph_remaining),
    ]

    for name, schema, handler in tools_to_register:
        ctx.register_tool(
            name=name,
            toolset="context_graph",
            schema=schema,
            handler=handler,
        )

    ctx.register_hook("on_session_end", _on_session_end)

    logger.info("context_graph plugin registered (%d tools)", len(tools_to_register))


def _on_session_end(**kw) -> None:
    """Session-end lifecycle hook (B1 scaffolding).

    Registered so grill-session detection + state transitions (tickets B2/B3/B4)
    have a firing point. For B1 this is intentionally a no-op: it must be
    registered, callable, and crash-proof — nothing more. Accepts arbitrary
    kwargs (Hermes passes session_id/profile_name/etc. at session-end) and
    returns None.
    """
    logger.debug("context_graph on_session_end fired (kwargs=%s)", sorted(kw))
    return None
