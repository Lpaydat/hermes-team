"""Tool handlers for context_graph — thin wrappers over the core module.

Each handler runs in the WORKER process when an agent calls the tool.
Returns JSON strings the agent can consume.

Two contract requirements:
1. Handler signature: ``def handler(args: dict, **kw)`` — the registry
   dispatches ``handler(args, **kwargs)`` where ``args`` is the full JSON
   arguments dict the model sent. Extract named params from it.
2. Return type: ``str`` — the registry normalizes handler results and
   rejects plain dicts (only accepts ``str`` or multimodal envelopes).
   Always ``json.dumps()`` the result.

Input validation: handlers reject malformed input with a clear JSON error
rather than silently creating garbage (e.g. a node with empty type/title is
invisible to graph_frontier → fake-completion risk). The schema's required/
enum constraints are NOT enforced at dispatch, so each handler validates its
own required fields + enums.
"""

import json
from . import context_graph as cg

_VALID_NODE_TYPES = {"root", "decision", "fact", "term", "artifact"}
_VALID_EDGE_TYPES = {"blocks", "relates_to", "caused_by", "supersedes", "part_of", "references", "answers"}


def _err(msg):
    return json.dumps({"error": msg})


def graph_frontier(args: dict, **_kw):
    """Return open decision/fact nodes with no open blockers (the work queue)."""
    items = cg.frontier()
    return json.dumps({"count": len(items), "frontier": items})


def graph_remaining(args: dict, **_kw):
    """Return ALL open decision/fact nodes — the grill backlog (what's left).

    Distinct from graph_frontier: this is the FULL unresolved set (including
    blocked nodes), so an empty result is the mechanical done-check (grill
    complete). Handler signature ``def fn(args: dict, **kw) -> str`` returning
    json.dumps — the registry dispatches ``handler(args, **kwargs)``.
    """
    items = cg.graph_remaining()
    return json.dumps({"count": len(items), "remaining": items})


def graph_pull(args: dict, **_kw):
    """Retrieve all nodes + edges for a topic (multi-topic subgraph)."""
    topic = (args.get("topic") or "").strip()
    if not topic:
        return _err("graph_pull requires a non-empty 'topic'")
    return json.dumps(cg.pull(topic))


def graph_context(args: dict, **_kw):
    """Retrieve a node + its neighborhood (focused context)."""
    node_id = (args.get("node_id") or "").strip()
    if not node_id:
        return _err("graph_context requires a non-empty 'node_id'")
    result = cg.context(node_id)
    if result is None:
        return _err(f"node {node_id} not found")
    return json.dumps(result)


def graph_add_node(args: dict, **_kw):
    """Create a graph node with optional multi-topic tags. Returns the node id."""
    node_type = (args.get("node_type") or "").strip()
    title = (args.get("title") or "").strip()
    if node_type not in _VALID_NODE_TYPES:
        return _err(f"graph_add_node 'node_type' must be one of {sorted(_VALID_NODE_TYPES)}, got {node_type!r}")
    if not title:
        return _err("graph_add_node requires a non-empty 'title'")
    content = args.get("content") or ""
    source = args.get("source") or ""
    topics = args.get("topics")
    if topics is not None and not isinstance(topics, list):
        return _err("graph_add_node 'topics' must be a list of strings")
    node_id = cg.add_node(node_type, title, content=content, source=source, topics=topics)
    return json.dumps({"node_id": node_id, "created": True})


def graph_add_edge(args: dict, **_kw):
    """Create a typed edge between two nodes."""
    source_id = (args.get("source_id") or "").strip()
    target_id = (args.get("target_id") or "").strip()
    edge_type = (args.get("edge_type") or "").strip()
    if not source_id or not target_id:
        return _err("graph_add_edge requires non-empty 'source_id' and 'target_id'")
    if edge_type not in _VALID_EDGE_TYPES:
        return _err(f"graph_add_edge 'edge_type' must be one of {sorted(_VALID_EDGE_TYPES)}, got {edge_type!r}")
    cg.add_edge(source_id, target_id, edge_type)
    return json.dumps({"edge": f"{source_id} --{edge_type}--> {target_id}", "created": True})


def graph_resolve_node(args: dict, **_kw):
    """Mark a node resolved with the answer/definition."""
    node_id = (args.get("node_id") or "").strip()
    if not node_id:
        return _err("graph_resolve_node requires a non-empty 'node_id'")
    content = args.get("content")
    cg.resolve_node(node_id, content=content)
    return json.dumps({"node_id": node_id, "resolved": True})


def graph_tree(args: dict, **_kw):
    """Show the full dependency tree rooted at root_id."""
    root_id = (args.get("root_id") or "").strip()
    if not root_id:
        return _err("graph_tree requires a non-empty 'root_id'")
    return json.dumps({"tree": cg.tree(root_id)})


def graph_stats(args: dict, **_kw):
    """Quick stats: node/edge/topic counts."""
    return json.dumps(cg.stats())
