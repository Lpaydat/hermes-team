"""JSON schemas for context_graph tools (what the agent sees).

ENVELOPE FORMAT: each schema is {name, description, parameters:{<json-schema>}}.
This is the shape register_tool / get_tool_definitions expects — the model API
reads `function.parameters.properties` for the params it must fill. A raw
JSON-Schema (type/properties/required at top level, no `parameters` key) leaves
the model-facing parameters.properties EMPTY, so the model has no params to fill
and sends empty args (the R24/R28 empty-args bug). Match kanban_chains's format.
"""

GRAPH_FRONTIER = {
    "name": "graph_frontier",
    "description": "Return open decision/fact nodes with no open blockers (the work queue).",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

GRAPH_PULL = {
    "name": "graph_pull",
    "description": "Retrieve all nodes + edges tagged with a topic (multi-topic subgraph).",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic tag to retrieve (e.g. 'auth', 'monetization')"},
        },
        "required": ["topic"],
        "additionalProperties": False,
    },
}

GRAPH_CONTEXT = {
    "name": "graph_context",
    "description": "Retrieve a node + its neighborhood (focused context).",
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "The graph node id (e.g. 'gn-a1b2c3d4')"},
        },
        "required": ["node_id"],
        "additionalProperties": False,
    },
}

GRAPH_ADD_NODE = {
    "name": "graph_add_node",
    "description": "Create a graph node with optional multi-topic tags. Returns the node id.",
    "parameters": {
        "type": "object",
        "properties": {
            "node_type": {"type": "string", "enum": ["decision", "fact", "term", "artifact", "root"],
                          "description": "Node type"},
            "title": {"type": "string", "description": "Short label for the node"},
            "content": {"type": "string", "default": "", "description": "Answer/definition/evidence"},
            "source": {"type": "string", "default": "", "description": "Who provided it (VB, PO, lookup)"},
            "topics": {"type": "array", "items": {"type": "string"}, "description": "Topic tags (multi-topic allowed)"},
        },
        "required": ["node_type", "title"],
        "additionalProperties": False,
    },
}

GRAPH_ADD_EDGE = {
    "name": "graph_add_edge",
    "description": "Create a typed edge between two nodes.",
    "parameters": {
        "type": "object",
        "properties": {
            "source_id": {"type": "string"},
            "target_id": {"type": "string"},
            "edge_type": {"type": "string",
                          "enum": ["blocks", "relates_to", "caused_by", "supersedes", "part_of", "references", "answers"],
                          "description": "Relationship type"},
        },
        "required": ["source_id", "target_id", "edge_type"],
        "additionalProperties": False,
    },
}

GRAPH_RESOLVE_NODE = {
    "name": "graph_resolve_node",
    "description": "Mark a node resolved with the answer/definition.",
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {"type": "string"},
            "content": {"type": "string", "description": "The resolved answer/definition"},
        },
        "required": ["node_id"],
        "additionalProperties": False,
    },
}

GRAPH_TREE = {
    "name": "graph_tree",
    "description": "Show the full dependency tree rooted at root_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "root_id": {"type": "string", "description": "The root node id"},
        },
        "required": ["root_id"],
        "additionalProperties": False,
    },
}

GRAPH_STATS = {
    "name": "graph_stats",
    "description": "Quick stats: node/edge/topic counts.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

GRAPH_REMAINING = {
    "name": "graph_remaining",
    "description": "Return ALL open decision/fact nodes — the grill backlog (what's left). Empty == grill complete.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}
