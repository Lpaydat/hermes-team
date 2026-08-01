#!/usr/bin/env python3
"""Workflow Engine — tick loop entry point.

Runs as a cron job (every 1 minute). Each tick:
1. Loads all active workflow instances from state DB
2. Checks for completed node cards → reads outputs → resolves variables
3. Dispatches nodes whose dependencies are met
4. Checks triggers for new workflow starts

Usage:
    python3 -m workflow_engine.main           # Run one tick (for cron)
    python3 -m workflow_engine.main --loop    # Run continuously (for debugging)
    python3 -m workflow_engine.main --list    # List active instances
    python3 -m workflow_engine.main --render <workflow_id>  # Render mermaid graph
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Add scripts dir to path so `workflow_engine` resolves as package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflow_engine.runtime import Engine, STATE_DB
from workflow_engine.store import TemplateStore

TEMPLATES_DIR = Path.home() / ".hermes-teams/startup/scripts/workflow_engine/templates"


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_tick(args):
    """Run one engine tick."""
    engine = Engine(TEMPLATES_DIR)
    actions = engine.tick()
    for a in actions:
        print(a)
    if not actions:
        print("(no actions)")


def cmd_loop(args):
    """Run continuously, one tick per interval."""
    interval = args.interval
    engine = Engine(TEMPLATES_DIR)
    print(f"Running tick loop every {interval}s. Ctrl+C to stop.")
    while True:
        ts = time.strftime("%H:%M:%S")
        actions = engine.tick()
        if actions:
            print(f"\n=== {ts} tick ===")
            for a in actions:
                print(f"  {a}")
        time.sleep(interval)


def cmd_list(args):
    """List active workflow instances."""
    from workflow_engine.runtime import StateDB
    db = StateDB()
    instances = db.load_active_instances()
    if not instances:
        print("(no active instances)")
        return

    for inst in instances:
        done = sum(1 for ns in inst.node_states.values() if ns.status.value == "done")
        total = len(inst.node_states)
        print(f"  {inst.instance_id}")
        print(f"    workflow: {inst.workflow_id}")
        print(f"    board: {inst.board}")
        print(f"    nodes: {done}/{total} done")
        for node_id, ns in inst.node_states.items():
            card = f" → {ns.card_id}" if ns.card_id else ""
            print(f"      {ns.status.value:10s} {node_id}{card}")
        print()


def cmd_render(args):
    """Render a workflow as a mermaid graph."""
    store = TemplateStore(TEMPLATES_DIR)
    wf = store.load(args.workflow_id)
    if not wf:
        print(f"Workflow not found: {args.workflow_id}")
        sys.exit(1)
    print(wf.to_mermaid())


def cmd_start(args):
    """Manually start a workflow."""
    engine = Engine(TEMPLATES_DIR)
    context = {}
    if args.context:
        context = json.loads(args.context)
    # Inject trigger context (bare keys — context() adds the "trigger." prefix)
    context.setdefault("board", args.board)
    context.setdefault("source", "manual")
    if args.project_dir:
        context.setdefault("project_dir", args.project_dir)
    instance_id = engine.start_manual(
        workflow_id=args.workflow_id,
        board=args.board,
        project_dir=args.project_dir or "",
        context=context,
    )
    print(f"Started: {instance_id}")


def cmd_templates(args):
    """List available workflow templates."""
    store = TemplateStore(TEMPLATES_DIR)
    ids = store.list_ids()
    if not ids:
        print(f"(no templates found in {TEMPLATES_DIR})")
        return
    for wid in ids:
        wf = store.load(wid)
        nodes = len(wf.nodes) if wf else "?"
        trigger = wf.trigger.source if wf and wf.trigger else "manual"
        print(f"  {wid:30s} nodes={nodes} trigger={trigger}")


def cmd_log(args):
    """Query engine event log."""
    import sqlite3, json
    from datetime import datetime, timezone
    db_path = Path.home() / ".hermes-teams/startup/kanban/workflow-state.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM engine_events WHERE 1=1"
    params = []
    if args.instance:
        query += " AND instance_id = ?"
        params.append(args.instance)
    if args.type:
        query += " AND event_type = ?"
        params.append(args.type)
    if args.level:
        query += " AND level = ?"
        params.append(args.level)
    query += " ORDER BY timestamp DESC"
    if args.limit:
        query += f" LIMIT {int(args.limit)}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("(no events)")
        return

    for row in rows:
        ts = datetime.fromtimestamp(row["timestamp"], tz=timezone.utc).strftime("%H:%M:%S")
        level = row["level"]
        etype = row["event_type"]
        msg = row["message"][:120]
        inst = (row["instance_id"] or "")[:20]
        print(f"{ts} {level:5s} {etype:20s} {inst:20s} {msg}")


def main():
    parser = argparse.ArgumentParser(description="Workflow Engine")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("tick", help="Run one engine tick").set_defaults(func=cmd_tick)

    p_loop = sub.add_parser("loop", help="Run continuously")
    p_loop.add_argument("--interval", type=int, default=60)
    p_loop.set_defaults(func=cmd_loop)

    sub.add_parser("list", help="List active instances").set_defaults(func=cmd_list)

    p_render = sub.add_parser("render", help="Render workflow as mermaid")
    p_render.add_argument("workflow_id")
    p_render.set_defaults(func=cmd_render)

    p_start = sub.add_parser("start", help="Manually start a workflow")
    p_start.add_argument("workflow_id")
    p_start.add_argument("--board", required=True)
    p_start.add_argument("--project-dir", default="")
    p_start.add_argument("--context", default="")
    p_start.set_defaults(func=cmd_start)

    sub.add_parser("templates", help="List available templates").set_defaults(func=cmd_templates)

    p_log = sub.add_parser("log", help="Query engine event log")
    p_log.add_argument("--instance", default="", help="Filter by instance ID")
    p_log.add_argument("--type", default="", help="Filter by event type")
    p_log.add_argument("--level", default="", help="Filter by level (DEBUG/INFO/WARN/ERROR)")
    p_log.add_argument("--limit", default="50", help="Max rows (default 50)")
    p_log.set_defaults(func=cmd_log)

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.set_defaults(func=lambda a: parser.print_help())
    args = parser.parse_args()

    setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
