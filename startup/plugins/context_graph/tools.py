"""Tool handlers for context_graph — thin wrappers over the core module.

Each handler runs in the WORKER process when an agent calls the tool.
Returns dicts/strings the agent can consume.
"""

import json
from . import context_graph as cg


def graph_frontier(**_kw):
    """Return open decision/fact nodes with no open blockers (the work queue)."""
    items = cg.frontier()
    return {"count": len(items), "frontier": items}


def graph_pull(topic, **_kw):
    """Retrieve all nodes + edges for a topic (multi-topic subgraph)."""
    return cg.pull(topic)


def graph_context(node_id, **_kw):
    """Retrieve a node + its neighborhood (focused context)."""
    result = cg.context(node_id)
    if result is None:
        return {"error": f"node {node_id} not found"}
    return result


def graph_add_node(node_type, title, content="", source="", topics=None, **_kw):
    """Create a graph node with optional multi-topic tags. Returns the node id."""
    node_id = cg.add_node(node_type, title, content=content, source=source, topics=topics)
    return {"node_id": node_id, "created": True}


def graph_add_edge(source_id, target_id, edge_type, **_kw):
    """Create a typed edge between two nodes."""
    cg.add_edge(source_id, target_id, edge_type)
    return {"edge": f"{source_id} --{edge_type}--> {target_id}", "created": True}


def graph_resolve_node(node_id, content=None, **_kw):
    """Mark a node resolved with the answer/definition."""
    cg.resolve_node(node_id, content=content)
    return {"node_id": node_id, "resolved": True}


def graph_tree(root_id, **_kw):
    """Show the full dependency tree rooted at root_id."""
    return {"tree": cg.tree(root_id)}


def graph_stats(**_kw):
    """Quick stats: node/edge/topic counts."""
    return cg.stats()
