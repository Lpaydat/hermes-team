"""Tool handlers — the code that runs when the LLM calls kanban_chains."""

import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

BLACKBOARD_PREFIX = "[swarm:blackboard] "


# ── Shared helpers ────────────────────────────────────────────────────────────


def _get_board():
    """Return the kanban board from env (default 'team')."""
    return os.environ.get("HERMES_KANBAN_BOARD", "team")


def _run_kanban(args_list):
    """Run `hermes kanban --board <board> <args>`, return (success, output_text)."""
    cmd = ["hermes", "kanban", "--board", _get_board()] + args_list
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=os.environ.copy())
    return result.returncode == 0, result.stdout.strip()


def _run_kanban_json(args_list):
    """Run a kanban command with --json, return parsed JSON or None."""
    cmd = ["hermes", "kanban", "--board", _get_board()] + args_list + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=os.environ.copy())
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _get_my_card_id(**kwargs):
    """Get the current task ID from kwargs or env."""
    return kwargs.get("task_id") or os.environ.get("HERMES_KANBAN_TASK")


def _create_card(title, assignee, body, skill=None, workspace_path=None,
                 parent_id=None, priority=None):
    """Create a kanban card via --json and return its id, or None on failure."""
    args = ["create", title, "--assignee", assignee, "--body", body]
    if skill:
        args += ["--skill", skill]
    if workspace_path:
        args += ["--workspace", f"dir:{workspace_path}"]
    if parent_id:
        args += ["--parent", parent_id]
    if priority is not None:
        args += ["--priority", str(priority)]
    result = _run_kanban_json(args)
    if not result or "id" not in result:
        return None
    return result["id"]


def _container_section(image_tag, container_port, port, worker_num):
    """Container setup block appended to a worker step body (mirrors qa_swarm)."""
    return (
        f"\n\n## Container\n"
        f"Image: {image_tag}\n"
        f"Start: podman run -d --name qa-worker-{worker_num} "
        f"-p {port}:{container_port} {image_tag}\n"
        f"Port: {port}\n"
        f"Cleanup: podman rm -f qa-worker-{worker_num}\n"
    )


def _validate(args):
    """Validate args BEFORE any card creation. Return an error string, or None if valid."""
    goal = args.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return "goal is required and must be a non-empty string"

    chains = args.get("chains")
    if not isinstance(chains, list) or not chains:
        return "chains is required and must be a non-empty list"
    for ci, chain in enumerate(chains):
        if not isinstance(chain, list) or not chain:
            return f"chain {ci + 1} must be a non-empty list"
        for si, step in enumerate(chain):
            if not isinstance(step, dict):
                return f"chain {ci + 1} step {si + 1} must be an object"
            for field in ("assignee", "title", "body"):
                val = step.get(field)
                if not isinstance(val, str) or not val.strip():
                    return (f"chain {ci + 1} step {si + 1}: "
                            f"{field} is required and must be a non-empty string")

    after = args.get("after")
    if after is not None:
        if not isinstance(after, list) or not after:
            return "after must be a non-empty list if provided"
        for si, step in enumerate(after):
            if not isinstance(step, dict):
                return f"after step {si + 1} must be an object"
            for field in ("assignee", "title"):
                val = step.get(field)
                if not isinstance(val, str) or not val.strip():
                    return (f"after step {si + 1}: "
                            f"{field} is required and must be a non-empty string")
    return None


# ── Handler ───────────────────────────────────────────────────────────────────


def kanban_chains(args: dict, **kwargs) -> str:
    """
    Create a parallel-chains + optional sequential-synthesis topology, link the
    caller as dependent on the terminal card(s), and block the caller.
    Returns JSON describing the created topology.
    """
    # 0. Validate BEFORE any card creation — no partial topologies.
    err = _validate(args)
    if err:
        return json.dumps({"error": err})

    my_card_id = _get_my_card_id(**kwargs)
    if not my_card_id:
        return json.dumps({
            "error": "Cannot determine current task ID. "
                     "Set HERMES_KANBAN_TASK or pass task_id.",
        })

    goal = args["goal"].strip()
    chains = args["chains"]
    after = args.get("after")
    bb = args.get("blackboard") or {}
    image_tag = (bb.get("image_tag") or "").strip()
    container_port = bb.get("container_port", 3000)
    base_port = bb.get("base_port", 18081)
    env_facts = (bb.get("env_facts") or "").strip()
    spec_path = (bb.get("spec_path") or "").strip()
    extra = bb.get("extra") or {}

    # 1. Root card (shared blackboard).
    root_body = f"Chains root / shared blackboard.\nGoal: {goal}\n"
    if image_tag:
        root_body += f"Container image: {image_tag}\n"
        root_body += f"Container port: {container_port}\n"
    if env_facts:
        root_body += f"Env facts: {env_facts}\n"
    if spec_path:
        root_body += f"Spec: {spec_path}\n"

    root_id = _create_card(f"Chains: {goal[:80]}", _get_board(), root_body)
    if not root_id:
        return json.dumps({"error": "Failed to create root card"})

    # Post the blackboard comment only when the blackboard param was provided.
    if args.get("blackboard"):
        bb_payload = json.dumps({
            "key": "swarm_context",
            "value": {
                "image_tag": image_tag,
                "container_port": container_port,
                "base_port": base_port,
                "env_facts": env_facts,
                "spec_path": spec_path,
                "extra": extra,
            },
        }, ensure_ascii=False)
        _run_kanban(["comment", root_id, f"{BLACKBOARD_PREFIX}{bb_payload}"])

    # Complete the root immediately so children can promote when ready.
    _run_kanban(["complete", root_id])

    # 2. Chains — each chain's steps run sequentially (parent->child); chains are parallel.
    chains_created = []
    for ci, chain in enumerate(chains):
        chain_ids = []
        for si, step in enumerate(chain):
            parent_id = root_id if si == 0 else chain_ids[-1]
            body = step["body"]
            # First step of each chain is the worker that owns a container/port.
            if si == 0 and image_tag:
                port = base_port + ci
                body = body + _container_section(image_tag, container_port, port, ci + 1)
            card_id = _create_card(
                title=step["title"],
                assignee=step["assignee"],
                body=body,
                skill=step.get("skill"),
                workspace_path=step.get("workspace_path"),
                parent_id=parent_id,
                priority=step.get("priority"),
            )
            if not card_id:
                return json.dumps({
                    "error": f"Failed to create chain {ci + 1} step {si + 1}",
                    "root_id": root_id,
                    "chains": chains_created,
                })
            chain_ids.append(card_id)
        chains_created.append(chain_ids)

    chain_last_ids = [c[-1] for c in chains_created]

    # 3. After sequence (fan-in) — runs after ALL chains complete.
    after_created = []
    if after:
        for si, step in enumerate(after):
            body = step.get("body") or step["title"]
            if si == 0:
                # Parented on the last step of EVERY chain: create unparented,
                # then link each chain's last step as a parent.
                card_id = _create_card(
                    title=step["title"],
                    assignee=step["assignee"],
                    body=body,
                    skill=step.get("skill"),
                )
            else:
                card_id = _create_card(
                    title=step["title"],
                    assignee=step["assignee"],
                    body=body,
                    skill=step.get("skill"),
                    parent_id=after_created[-1],
                )
            if not card_id:
                return json.dumps({
                    "error": f"Failed to create after step {si + 1}",
                    "root_id": root_id,
                    "chains": chains_created,
                    "after": after_created,
                })
            if si == 0:
                for last_id in chain_last_ids:
                    _run_kanban(["link", last_id, card_id])
            after_created.append(card_id)

    # 4. Caller linking — block on the terminal card(s).
    if after_created:
        terminal_ids = [after_created[-1]]
    else:
        terminal_ids = chain_last_ids
    for tid in terminal_ids:
        _run_kanban(["link", tid, my_card_id])

    # 5. Block caller (kind=dependency) and verify it took effect.
    reason = f"waiting_for_chains:{', '.join(terminal_ids)}"
    ok, block_out = _run_kanban(["block", my_card_id, reason, "--kind", "dependency"])
    if not ok:
        logger.error("Block command failed for %s: %s", my_card_id, block_out)
        return json.dumps({
            "error": f"Block command failed: {block_out}",
            "root_id": root_id,
            "chains": chains_created,
            "after": after_created,
        })

    verify = _run_kanban_json(["show", my_card_id])
    actual_status = None
    if verify:
        t = verify.get("task", verify)
        actual_status = t.get("status")
    if actual_status != "todo":
        return json.dumps({
            "error": f"Block did not take effect: status={actual_status} (expected todo)",
            "root_id": root_id,
            "chains": chains_created,
            "after": after_created,
        })

    # 6. Return.
    result = {
        "status": "blocked",
        "root_id": root_id,
        "chains": chains_created,
    }
    if after_created:
        result["after"] = after_created
    result["terminal_ids"] = terminal_ids
    tail = f" + {len(after_created)} after step(s)" if after_created else ""
    result["message"] = (
        f"Created {len(chains_created)} chain(s){tail}. "
        f"Blocked (dependency) on {len(terminal_ids)} terminal card(s). "
        f"Auto-promotes when all complete. Do NOT call kanban_complete until then."
    )
    return json.dumps(result, indent=2)
