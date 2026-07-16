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

# Sessions that touched the context_graph toolset during their lifetime.
# Populated by the post_tool_call hook (_on_post_tool_call) on every graph_*
# tool call and drained by on_session_end. Hermes' on_session_end kwargs do
# NOT carry the session's tool-call list, so "touched the graph" is observed
# here over the session's lifetime instead. (Mirrors the shipped disk-cleanup
# plugin's track-in-post_tool_call / drain-in-on_session_end pattern.)
_GRAPH_TOUCHED_SESSIONS: set = set()
_GRAPH_TOOL_PREFIX = "graph_"


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
    ctx.register_hook("post_tool_call", _on_post_tool_call)

    logger.info("context_graph plugin registered (%d tools)", len(tools_to_register))


def _on_post_tool_call(tool_name: str = "", session_id: str = "", **_) -> None:
    """Track whether this session touched the context_graph toolset.

    Hermes fires post_tool_call for every tool call with ``tool_name`` +
    ``session_id``. A grill session makes graph_* calls; we record the
    session_id so the on_session_end hook can distinguish grill sessions from
    unrelated ones (chart sessions, PO work that never touched the graph).
    """
    if session_id and tool_name.startswith(_GRAPH_TOOL_PREFIX):
        _GRAPH_TOUCHED_SESSIONS.add(session_id)


def is_grill_session(session_id: str) -> bool:
    """B2 detection: is ``session_id`` a mid-grill session?

    True iff BOTH:
      1. the session touched the graph (made >=1 graph_* tool call), AND
      2. an open grill root exists (type='root' AND status='open') — a grill
         in progress. A grill that is GRILL COMPLETE has its root resolved,
         so there is no open root and this returns False.

    Detection only — B3/B4 consume a True result to drive transitions.
    """
    if not session_id or session_id not in _GRAPH_TOUCHED_SESSIONS:
        return False
    try:
        return cg.has_open_root()
    except Exception:
        logger.debug("has_open_root check failed", exc_info=True)
        return False


def _on_session_end(session_id: str = "", **kw) -> None:
    """Session-end lifecycle hook (B2: grill-session detection).

    Detects whether the ended session was a mid-grill session (touched the
    graph AND an open grill root exists). Non-grill sessions are a no-op.
    DETECTION ONLY — B3/B4 will act on a detected grill session (transitions /
    card creation); this hook decides grill-or-not, logs it, and returns None.

    Hermes fires on_session_end with kwargs {session_id, completed,
    interrupted, model, platform, reason, and sometimes task_id / turn_id /
    api_request_id}. None of those carry the session's tool-call list, so
    "touched the graph" is read from the post_tool_call tracker
    (_GRAPH_TOUCHED_SESSIONS) populated over the session's lifetime.
    """
    grill = is_grill_session(session_id)
    if grill:
        logger.info(
            "context_graph: grill session detected (session_id=%s) — mid-grill, "
            "open root exists",
            session_id,
        )
    else:
        logger.debug(
            "context_graph: session %s not a mid-grill session (touched_graph=%s)",
            session_id,
            session_id in _GRAPH_TOUCHED_SESSIONS,
        )
    # Drain the per-session tracker either way (mirrors disk-cleanup's bucket
    # drain) so it never leaks across sessions.
    _GRAPH_TOUCHED_SESSIONS.discard(session_id)
    return None
