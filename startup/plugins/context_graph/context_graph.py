"""
Context Graph — a lightweight SQLite-backed graph for dynamic project context.

Replaces monolithic CONTEXT.md with a queryable graph:
- Nodes: decisions, facts, terms, artifacts (with status + content).
- Edges: blocks, relates_to, caused_by, supersedes, part_of, references (typed).
- Topics: many-to-many node↔topic tags (multi-topic decisions — the key feature).
- Queries: frontier (work queue), pull (topic subgraph), context (node neighborhood).

Usage:
    from context_graph import init_db, add_node, add_edge, resolve_node, frontier, pull, context
    init_db()
    d = add_node("decision", "Auth tokens in Redis?", source="VB", topics=["auth","data-store","security"])
    f = add_node("fact", "Redis supports TTL natively", source="lookup", topics=["data-store"])
    add_edge(f, d, "references")          # the fact informs the decision
    add_edge(d, root, "blocks")            # the decision blocks the root
    frontier()                             # → [d] (open, unblocked)
    pull("auth")                           # → {nodes: [d], edges: [...]}  (topic-focused)
    pull("data-store")                     # → {nodes: [d, f], edges: [...]}  (also gets d — multi-topic!)
    resolve_node(d, content="VB: Yes, Redis with TTL")
    frontier()                             # → [] (d resolved)
"""

import sqlite3
import uuid
from datetime import datetime

DB_PATH = None  # set by init_db; defaults to startup/context_graph.db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,           -- decision | fact | term | artifact | root
    status      TEXT DEFAULT 'open',     -- open | resolved | escalated
    title       TEXT NOT NULL,
    content     TEXT DEFAULT '',         -- the answer / definition / evidence
    source      TEXT DEFAULT '',         -- who provided it (VB, PO, lookup, etc.)
    created_at  TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_edges (
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL,           -- blocks | relates_to | caused_by | supersedes | part_of | references | answers
    created_at  TEXT,
    PRIMARY KEY (source_id, target_id, edge_type)
);

CREATE TABLE IF NOT EXISTS node_topics (
    node_id     TEXT NOT NULL,
    topic       TEXT NOT NULL,           -- e.g. "auth", "monetization", "architecture"
    PRIMARY KEY (node_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON graph_nodes(status);
CREATE INDEX IF NOT EXISTS idx_topics_topic ON node_topics(topic);
"""


def _get_db():
    import os
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "context_graph.db")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """Initialize the graph database (creates tables if not exist)."""
    global DB_PATH
    if db_path:
        DB_PATH = db_path
    conn = _get_db()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def add_node(node_type, title, content="", source="", topics=None):
    """Create a node. Returns the node id.

    Args:
        node_type: decision | fact | term | artifact | root
        title: short label
        content: the answer/definition/evidence (filled on creation or resolution)
        source: who provided the content (VB, PO, lookup)
        topics: list of topic strings (multi-topic — the key feature)
    Returns:
        node_id (e.g. "gn-a1b2c3d4")
    """
    node_id = f"gn-{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    conn = _get_db()
    conn.execute(
        "INSERT INTO graph_nodes (id, type, status, title, content, source, created_at) VALUES (?, ?, 'open', ?, ?, ?, ?)",
        (node_id, node_type, title, content, source, now)
    )
    if topics:
        for t in topics:
            conn.execute("INSERT OR IGNORE INTO node_topics (node_id, topic) VALUES (?, ?)", (node_id, t))
    conn.commit()
    conn.close()
    return node_id


def add_edge(source_id, target_id, edge_type):
    """Create a typed edge between two nodes.

    Edge types: blocks | relates_to | caused_by | supersedes | part_of | references | answers
    """
    now = datetime.now().isoformat()
    conn = _get_db()
    conn.execute(
        "INSERT OR IGNORE INTO graph_edges (source_id, target_id, edge_type, created_at) VALUES (?, ?, ?, ?)",
        (source_id, target_id, edge_type, now)
    )
    conn.commit()
    conn.close()


def resolve_node(node_id, content=None):
    """Mark a node resolved. Optionally update its content (the answer)."""
    now = datetime.now().isoformat()
    conn = _get_db()
    if content is not None:
        conn.execute(
            "UPDATE graph_nodes SET status='resolved', content=?, resolved_at=? WHERE id=?",
            (content, now, node_id)
        )
    else:
        conn.execute(
            "UPDATE graph_nodes SET status='resolved', resolved_at=? WHERE id=?",
            (now, node_id)
        )
    conn.commit()
    conn.close()


def frontier():
    """Return open decision/fact nodes with no open blockers (the work queue).

    A node is in the frontier if:
    - status = 'open'
    - type IN ('decision', 'fact')
    - no edge (source_id blocks node_id) where source is also 'open'
    """
    conn = _get_db()
    rows = conn.execute("""
        SELECT n.id, n.type, n.title, n.content, n.source, n.status
        FROM graph_nodes n
        WHERE n.status = 'open' AND n.type IN ('decision', 'fact')
        AND NOT EXISTS (
            SELECT 1 FROM graph_edges e
            WHERE e.target_id = n.id AND e.edge_type = 'blocks'
            AND EXISTS (SELECT 1 FROM graph_nodes b WHERE b.id = e.source_id AND b.status = 'open')
        )
        ORDER BY n.created_at
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pull(topic):
    """Retrieve all nodes tagged with a topic + their edges (topic subgraph).

    This is the KEY multi-topic query: a decision tagged "auth" AND "data-store"
    is retrieved by BOTH pull("auth") and pull("data-store"). No duplication —
    one node, multiple topic tags, retrieved by any matching topic.
    """
    conn = _get_db()
    nodes = conn.execute("""
        SELECT DISTINCT n.id, n.type, n.status, n.title, n.content, n.source
        FROM graph_nodes n
        JOIN node_topics t ON t.node_id = n.id
        WHERE t.topic = ?
        ORDER BY n.created_at
    """, (topic,)).fetchall()
    node_ids = [r['id'] for r in nodes]
    edges = []
    if node_ids:
        placeholders = ','.join('?' * len(node_ids))
        edges = conn.execute(f"""
            SELECT DISTINCT * FROM graph_edges
            WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
        """, node_ids + node_ids).fetchall()
    conn.close()
    return {"topic": topic, "nodes": [dict(r) for r in nodes], "edges": [dict(r) for r in edges]}


def context(node_id, hops=1):
    """Retrieve a node + its neighborhood (connected nodes + edges).

    Agents use this for focused context: "give me everything about THIS decision."
    Returns the node, its topics, its 1-hop neighbors, and the edges.
    """
    conn = _get_db()
    node = conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
    if not node:
        conn.close()
        return None
    neighbors = conn.execute("""
        SELECT DISTINCT n.id, n.type, n.status, n.title, n.content
        FROM graph_nodes n
        JOIN graph_edges e ON (
            (e.source_id = n.id AND e.target_id = ?) OR
            (e.target_id = n.id AND e.source_id = ?)
        )
        WHERE n.id != ?
    """, (node_id, node_id, node_id)).fetchall()
    edges = conn.execute("""
        SELECT * FROM graph_edges WHERE source_id = ? OR target_id = ?
    """, (node_id, node_id)).fetchall()
    topics = conn.execute("SELECT topic FROM node_topics WHERE node_id = ?", (node_id,)).fetchall()
    conn.close()
    return {
        "node": dict(node),
        "topics": [r['topic'] for r in topics],
        "neighbors": [dict(r) for r in neighbors],
        "edges": [dict(r) for r in edges]
    }


def tree(root_id):
    """Show the full dependency tree rooted at root_id (blocks edges, recursive)."""
    conn = _get_db()
    # recursive CTE for the blocks-tree
    rows = conn.execute("""
        WITH RECURSIVE tree_cte AS (
            SELECT n.id, n.type, n.status, n.title, n.content, 0 AS depth
            FROM graph_nodes n WHERE n.id = ?
            UNION ALL
            SELECT n.id, n.type, n.status, n.title, n.content, t.depth + 1
            FROM graph_nodes n
            JOIN graph_edges e ON e.source_id = n.id AND e.edge_type = 'blocks'
            JOIN tree_cte t ON e.target_id = t.id
            WHERE t.depth < 20
        )
        SELECT * FROM tree_cte ORDER BY depth, title
    """, (root_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats():
    """Quick stats: node counts by type + status."""
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) AS n FROM graph_nodes").fetchone()['n']
    by_type = conn.execute("SELECT type, COUNT(*) AS n FROM graph_nodes GROUP BY type").fetchall()
    by_status = conn.execute("SELECT status, COUNT(*) AS n FROM graph_nodes GROUP BY status").fetchall()
    edges = conn.execute("SELECT COUNT(*) AS n FROM graph_edges").fetchone()['n']
    topics = conn.execute("SELECT COUNT(DISTINCT topic) AS n FROM node_topics").fetchone()['n']
    conn.close()
    return {"total_nodes": total, "by_type": {r['type']: r['n'] for r in by_type},
            "by_status": {r['status']: r['n'] for r in by_status},
            "total_edges": edges, "total_topics": topics}
