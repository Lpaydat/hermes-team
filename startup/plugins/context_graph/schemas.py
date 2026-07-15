"""JSON schemas for context_graph tools (what the agent sees)."""

GRAPH_FRONTIER = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

GRAPH_PULL = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "Topic tag to retrieve (e.g. 'auth', 'monetization')"},
    },
    "required": ["topic"],
    "additionalProperties": False,
}

GRAPH_CONTEXT = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string", "description": "The graph node id (e.g. 'gn-a1b2c3d4')"},
    },
    "required": ["node_id"],
    "additionalProperties": False,
}

GRAPH_ADD_NODE = {
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
}

GRAPH_ADD_EDGE = {
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
}

GRAPH_RESOLVE_NODE = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string"},
        "content": {"type": "string", "description": "The resolved answer/definition"},
    },
    "required": ["node_id"],
    "additionalProperties": False,
}

GRAPH_TREE = {
    "type": "object",
    "properties": {
        "root_id": {"type": "string", "description": "The root node id"},
    },
    "required": ["root_id"],
    "additionalProperties": False,
}

GRAPH_STATS = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
