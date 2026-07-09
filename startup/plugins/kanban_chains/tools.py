"""Tool handlers — kanban_chains: unified parallel-chains + optional synthesis topology."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

BLACKBOARD_PREFIX = "[swarm:blackboard] "


def _get_board():
    import os
    return os.environ.get("HERMES_KANBAN_BOARD", "startup")


def _run_kanban(args_list):
    """Run a hermes kanban command, return (success, output_text)."""
    import os
    board = _get_board()
    cmd = ["hermes", "kanban", "--board", board] + args_list
    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    return result.returncode == 0, result.stdout.strip()


def _run_kanban_json(args_list):
    """Run a hermes kanban command with --json, return parsed JSON or None."""
    import os
    board = _get_board()
    cmd = ["hermes", "kanban", "--board", board] + args_list + ["--json"]
    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _get_my_card_id(**kwargs):
    """Get the current task ID from kwargs or env."""
    import os
    return kwargs.get("task_id") or os.environ.get("HERMES_KANBAN_TASK")


def _container_block(image_tag, port, container_port, n):
    return (
        f"\n## Container\n"
        f"Image: {image_tag}\n"
        f"Start: podman run -d --name qa-worker-{n} -p {port}:{container_port} {image_tag}\n"
        f"Port: {port}\n"
        f"Cleanup: podman rm -f qa-worker-{n}\n"
    )


def _validate(args):
    """Return an error string if args are invalid, else None."""
    goal = (args.get("goal") or "").strip()
    if not goal:
        return "goal is required"
    chains = args.get("chains")
    if not chains or not isinstance(chains, list):
        return "chains is required and must be a non-empty list"
    for ci, chain in enumerate(chains):
        if not isinstance(chain, list) or len(chain) == 0:
            return f"chain {ci} must be a non-empty list of steps"
        for si, step in enumerate(chain):
            if not isinstance(step, dict):
                return f"chain {ci} step {si} must be an object"
            if not (step.get("assignee") or "").strip():
                return f"chain {ci} step {si}: assignee is required"
            if not (step.get("title") or "").strip():
                return f"chain {ci} step {si}: title is required"
            if not (step.get("body") or "").strip():
                return f"chain {ci} step {si}: body is required"
    after = args.get("after") or []
    for ki, step in enumerate(after):
        if not isinstance(step, dict):
            return f"after step {ki} must be an object"
        if not (step.get("assignee") or "").strip():
            return f"after step {ki}: assignee is required"
        if not (step.get("title") or "").strip():
            return f"after step {ki}: title is required"
    return None


def kanban_chains(args: dict, **kwargs) -> str:
    """
    Create a parallel-chains + optional synthesis topology.

    Root card (blackboard) → N parallel chains (each sequential) → optional `after`
    fan-in tail. Caller is linked as child of the terminal card(s) and blocked
    (kind=dependency) until they complete.
    """
    err = _validate(args)
    if err:
        return json.dumps({"error": err})

    goal = (args.get("goal") or "").strip()
    chains = args.get("chains")
    after = args.get("after") or []
    blackboard = args.get("blackboard") or {}
    idempotency_key = (args.get("idempotency_key") or "").strip()

    my_card_id = _get_my_card_id(**kwargs)
    if not my_card_id:
        return json.dumps({"error": "Cannot determine current task ID. Set HERMES_KANBAN_TASK or pass task_id."})

    bb = blackboard or {}
    image_tag = (bb.get("image_tag") or "").strip()
    container_port = bb.get("container_port", 3000)
    base_port = bb.get("base_port", 18081)
    env_facts = (bb.get("env_facts") or "").strip()
    spec_path = (bb.get("spec_path") or "").strip()
    extra = bb.get("extra") or {}

    first_assignee = chains[0][0]["assignee"]

    # 1. Root card (blackboard anchor)
    root_body = f"Matrix root / shared blackboard.\nGoal: {goal}\n"
    if image_tag:
        root_body += f"Image: {image_tag}\nContainer port: {container_port}\nBase port: {base_port}\n"
    if env_facts:
        root_body += f"Env facts: {env_facts}\n"
    if spec_path:
        root_body += f"Spec: {spec_path}\n"

    root_create_args = ["create", goal[:80], "--assignee", first_assignee, "--body", root_body]
    if idempotency_key:
        root_create_args += ["--idempotency-key", idempotency_key]
    root_result = _run_kanban_json(root_create_args)
    if not root_result or "id" not in root_result:
        return json.dumps({"error": "Failed to create root card"})
    root_id = root_result["id"]

    # 2. Complete root immediately — it is just a blackboard anchor
    _run_kanban(["complete", root_id, "--result", "Matrix root anchor — blackboard only"])

    # 3. Blackboard comment (only when a blackboard was provided)
    if blackboard:
        bb_payload = json.dumps({
            "key": "matrix_context",
            "value": {
                "goal": goal,
                "image_tag": image_tag,
                "container_port": container_port,
                "base_port": base_port,
                "env_facts": env_facts,
                "spec_path": spec_path,
                "extra": extra,
            },
        }, ensure_ascii=False)
        _run_kanban(["comment", root_id, f"{BLACKBOARD_PREFIX}{bb_payload}"])

    # 4. Chains — step[0] parented on root, step[n] on step[n-1]
    chain_ids = []
    for i, chain in enumerate(chains):
        ids = []
        prev = None
        for j, step in enumerate(chain):
            parent = root_id if j == 0 else prev
            body = step.get("body", "")
            if image_tag and j == 0:
                port = base_port + i
                body = body + _container_block(image_tag, port, container_port, i + 1)
            create_args = [
                "create", step["title"],
                "--assignee", step["assignee"],
                "--body", body,
                "--parent", parent,
            ]
            if step.get("skill"):
                create_args += ["--skill", step["skill"]]
            if step.get("workspace_path"):
                create_args += ["--workspace", f"dir:{step['workspace_path']}"]
            if step.get("priority") is not None:
                create_args += ["--priority", str(step["priority"])]
            res = _run_kanban_json(create_args)
            if not res or "id" not in res:
                return json.dumps({
                    "error": f"Failed to create chain {i} step {j}",
                    "root_id": root_id, "chains": chain_ids,
                })
            cid = res["id"]
            ids.append(cid)
            prev = cid
        chain_ids.append(ids)

    terminal_ids = [ids[-1] for ids in chain_ids]

    # 5. After sequence — after[0] fans in from the last step of EVERY chain
    after_ids = []
    if after:
        prev = None
        for k, step in enumerate(after):
            create_args = ["create", step["title"], "--assignee", step["assignee"]]
            body = step.get("body", "")
            if body:
                create_args += ["--body", body]
            if k > 0:
                create_args += ["--parent", prev]
            if step.get("skill"):
                create_args += ["--skill", step["skill"]]
            if step.get("priority") is not None:
                create_args += ["--priority", str(step["priority"])]
            res = _run_kanban_json(create_args)
            if not res or "id" not in res:
                return json.dumps({
                    "error": f"Failed to create after step {k}",
                    "root_id": root_id, "chains": chain_ids, "after": after_ids,
                })
            aid = res["id"]
            if k == 0:
                # fan-in: link the last step of EVERY chain as a parent of after[0]
                for tid in terminal_ids:
                    _run_kanban(["link", tid, aid])
            after_ids.append(aid)
            prev = aid
        terminal_ids = [after_ids[-1]]

    # 6. Link caller as child of the terminal card(s)
    if after:
        _run_kanban(["link", after_ids[-1], my_card_id])
    else:
        for ids in chain_ids:
            _run_kanban(["link", ids[-1], my_card_id])

    # 7. Block caller with kind=dependency
    reason = f"waiting_for_matrix:{','.join(terminal_ids)}"
    ok, block_out = _run_kanban(["block", my_card_id, reason, "--kind", "dependency"])
    if not ok:
        return json.dumps({
            "error": f"Block command failed: {block_out}",
            "root_id": root_id, "chains": chain_ids, "after": after_ids,
        })

    # 8. Verify the block took effect (caller should now be status=todo)
    verify = _run_kanban_json(["show", my_card_id])
    actual_status = None
    if verify:
        t = verify.get("task", verify)
        actual_status = t.get("status")
    block_verified = (actual_status == "todo")
    if not block_verified:
        return json.dumps({
            "error": f"Block did not take effect: status={actual_status} (expected todo)",
            "root_id": root_id,
            "chains": chain_ids,
            "after": after_ids,
            "terminal_ids": terminal_ids,
            "block_verified": False,
        })

    tail = f", {len(after)} after step(s)" if after else ""
    return json.dumps({
        "status": "blocked",
        "root_id": root_id,
        "chains": chain_ids,
        "after": after_ids,
        "terminal_ids": terminal_ids,
        "block_verified": True,
        "message": (
            f"Created matrix: {len(chains)} chain(s){tail}. "
            f"Root {root_id}. Blocked (dependency) on {','.join(terminal_ids)}. "
            f"Auto-promotes when terminal(s) complete. Do NOT kanban_complete until re-dispatched."
        ),
    }, indent=2)
