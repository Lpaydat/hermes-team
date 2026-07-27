#!/usr/bin/env python3
"""Graph state manager for grill sessions.

Wraps the context_graph plugin to provide a simple CLI for:
- init: create grill root node
- lock: add a locked decision
- open: add an open question
- resolve: resolve an open question
- status: print one-liner state for PO injection
- done: resolve the grill root
- is-done: check if grill is complete (exit 0 = done)
- export: dump all nodes for SUMMARY.md

Usage:
    graph_state.py init <topic> "<idea>"
    graph_state.py lock <topic> "<title>" "<content>"
    graph_state.py status <topic>
    graph_state.py done <topic>
    graph_state.py is-done <topic>
    graph_state.py export <topic>
"""

import sys
import os

# Import context_graph from the plugin
PLUGINS_DIR = os.path.expanduser("~/.hermes-teams/startup/plugins")
sys.path.insert(0, PLUGINS_DIR)
from context_graph import context_graph as cg  # noqa: E402


def cmd_init(topic, idea):
    """Create grill root node. Idempotent — if root exists for topic, reuse it."""
    # Check if root already exists for this topic
    result = cg.pull(topic)
    roots = [n for n in result["nodes"] if n["type"] == "root"]
    if roots:
        root_id = roots[0]["id"]
        print(f"Root exists: {root_id} (topic={topic})")
        return root_id

    root_id = cg.add_node("root", title=f"Grill: {idea}", topics=[topic])
    print(root_id)
    return root_id


def cmd_lock(topic, title, content=""):
    """Add a locked (resolved) decision node linked to root."""
    result = cg.pull(topic)
    root_id = None
    for n in result["nodes"]:
        if n["type"] == "root":
            root_id = n["id"]
            break

    node_id = cg.add_node("decision", title=title, content=content,
                          source="builder", topics=[topic])
    # Immediately resolve — locked decisions are done
    cg.resolve_node(node_id, content=content)
    if root_id:
        cg.add_edge(node_id, root_id, "part_of")
    print(node_id)
    return node_id


def cmd_resolve(topic, node_id, content=""):
    """Resolve an open question node."""
    cg.resolve_node(node_id, content=content)
    print(f"Resolved: {node_id}")
    return node_id


def cmd_status(topic):
    """Print one-liner state: [STATE: LOCKED(N): D1=..., OPEN(M): Q1=...]"""
    result = cg.pull(topic)
    locked = [n for n in result["nodes"]
              if n["type"] == "decision" and n["status"] == "resolved"]
    open_items = [n for n in result["nodes"]
                  if n["type"] in ("decision", "fact") and n["status"] == "open"]

    parts = []
    if locked:
        lock_strs = [f"{n['title']}" for n in locked]
        parts.append(f"LOCKED({len(locked)}): {', '.join(lock_strs)}")
    if open_items:
        open_strs = [f"{n['title']}" for n in open_items]
        parts.append(f"OPEN({len(open_items)}): {', '.join(open_strs)}")

    state = " | ".join(parts) if parts else "EMPTY"
    print(f"[STATE: {state}]")
    return state


def cmd_done(topic):
    """Resolve the grill root — marks grill complete."""
    result = cg.pull(topic)
    for n in result["nodes"]:
        if n["type"] == "root":
            cg.resolve_node(n["id"])
            print(f"Grill done: {n['id']}")
            return
    print("ERROR: No root found for topic", file=sys.stderr)
    sys.exit(1)


def cmd_is_done(topic):
    """Exit 0 if grill root is resolved, exit 1 if still open."""
    result = cg.pull(topic)
    for n in result["nodes"]:
        if n["type"] == "root":
            if n["status"] == "resolved":
                sys.exit(0)
            else:
                sys.exit(1)
    # No root at all = not initialized
    sys.exit(1)


def cmd_export(topic):
    """Dump all nodes for SUMMARY.md generation."""
    result = cg.pull(topic)
    nodes = result["nodes"]
    edges = result["edges"]

    root_nodes = [n for n in nodes if n["type"] == "root"]
    decisions = [n for n in nodes if n["type"] == "decision"]
    facts = [n for n in nodes if n["type"] == "fact"]

    print(f"# Grill Export — {topic}")
    print(f"\n**{len(decisions)} decisions locked, {len(facts)} facts recorded.**\n")

    if root_nodes:
        print(f"## Root: {root_nodes[0]['title']}\n")

    print("## Decisions\n")
    for i, d in enumerate(decisions, 1):
        status = "LOCKED" if d["status"] == "resolved" else "OPEN"
        print(f"### D{i}: {d['title']} [{status}]")
        if d["content"]:
            print(f"{d['content']}\n")

    if edges:
        print("\n## Relationships\n")
        for e in edges:
            print(f"- {e['source_id']} --{e['edge_type']}--> {e['target_id']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: graph_state.py <command> [args]", file=sys.stderr)
        print("Commands: init, lock, resolve, status, done, is-done, export",
              file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    cg.init_db()

    if cmd == "init":
        topic, idea = sys.argv[2], sys.argv[3]
        cmd_init(topic, idea)
    elif cmd == "lock":
        topic, title = sys.argv[2], sys.argv[3]
        content = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_lock(topic, title, content)
    elif cmd == "resolve":
        topic, node_id = sys.argv[2], sys.argv[3]
        content = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_resolve(topic, node_id, content)
    elif cmd == "status":
        topic = sys.argv[2]
        cmd_status(topic)
    elif cmd == "done":
        topic = sys.argv[2]
        cmd_done(topic)
    elif cmd == "is-done":
        topic = sys.argv[2]
        cmd_is_done(topic)
    elif cmd == "export":
        topic = sys.argv[2]
        cmd_export(topic)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
