#!/usr/bin/env python3
"""Detached scanner-creator — spawned non-blocking by grill_followup's hook.

Reads the venture's CONTEXT.md, decides the next grill question (or terminates),
and creates the next [grill] kanban card. Decoupled from the worker's
kanban_complete so the scanner's latency under ZAI load can't stall the worker
or hit max-runtime before the next card is created (the synchronous-in-hook
failure mode that prevented iter-3+ on grilllive46/47/48).

Invoked with HERMES_ASYNC_TITLE / HERMES_ASYNC_BODY / HERMES_ASYNC_SLUG env vars
(set by spawn_async_chain in __init__.py)."""
import os
import sys
import subprocess

_PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
# add the PARENT (plugins/) so `import grill_followup` resolves the package,
# not just this script's own dir.
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))
sys.path.insert(0, _PLUGIN_DIR)
import grill_followup as g  # noqa: E402


def main() -> None:
    title = os.environ.get("HERMES_ASYNC_TITLE", "")
    body = os.environ.get("HERMES_ASYNC_BODY", "")
    if not body:
        return
    env = dict(os.environ)
    if g._REPO_ROOT:
        env["HERMES_HOME"] = os.path.join(g._REPO_ROOT, "startup")
    slug = g._extract_slug(body)
    # count existing grill cards for this venture (per-iter unique key + cap-5)
    existing = 0
    try:
        import json as _json
        _r = subprocess.run(
            ["hermes", "kanban", "--board", "hermes-hq", "list", "--json"],
            capture_output=True, text=True, env=env, cwd=g._REPO_ROOT, timeout=30,
        )
        existing = len([
            c for c in _json.loads(_r.stdout or "[]")
            if slug in (c.get("body") or "") and c.get("assignee") == "product-owner"
            and "[grill]" in (c.get("title") or "")
        ])
    except Exception:
        pass
    if existing >= 5:
        return  # CAP: don't spawn past iter 5
    open_qs = g.decide_carryover(title, body)
    if not open_qs:
        return
    spec = g.build_next_spec(task_title=title, task_body=body, open_questions=open_qs)
    spec["idempotency_key"] = f"venture-grill-iter{existing + 1}-{slug}" if slug else None
    cmd = [
        "hermes", "kanban", "--board", "hermes-hq", "create", spec["title"],
        "--assignee", spec["assignee"], "--body", spec["body"],
    ]
    if spec.get("idempotency_key"):
        cmd += ["--idempotency-key", spec["idempotency_key"]]
    for sk in spec.get("skills", []):
        cmd += ["--skill", sk]
    try:
        subprocess.run(
            cmd, cwd=g._REPO_ROOT or None, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
