"""Tool handlers — the code that runs when the LLM calls kanban_delegate."""

import json
import logging
import sqlite3
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

BOARD = None  # resolved at call time from env


def _get_board():
    import os
    return os.environ.get("HERMES_KANBAN_BOARD", "startup")


def _run_kanban(args_list):
    """Run a hermes kanban command, return (success, output_text)."""
    import os
    board = _get_board()
    cmd = ["hermes", "kanban", "--board", board] + args_list
    # Inherit HERMES_KANBAN_TASK and HERMES_KANBAN_RUN_ID from parent env
    # so the CLI can authenticate as the worker that owns the task claim.
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
    task_id = kwargs.get("task_id") or os.environ.get("HERMES_KANBAN_TASK")
    return task_id


def kanban_delegate(args: dict, **kwargs) -> str:
    """
    Create N dev→verifier pairs, link caller as dependent on all verifiers,
    and block caller with kind=dependency.

    Returns JSON with created card IDs and status.
    """
    contracts = args.get("contracts", [])
    if not contracts:
        return json.dumps({"error": "No contracts provided"})

    my_card_id = _get_my_card_id(**kwargs)
    if not my_card_id:
        return json.dumps({"error": "Cannot determine current task ID. Set HERMES_KANBAN_TASK or pass task_id."})

    created = []
    verifier_ids = []

    for i, contract in enumerate(contracts):
        title = contract.get("title", f"Build contract {i+1}")
        body = contract.get("body", "")
        workspace_path = contract.get("workspace_path", "")

        if not body or not workspace_path:
            created.append({"error": f"Contract {i+1}: missing body or workspace_path"})
            continue

        # Step 1: Create developer card
        dev_result = _run_kanban_json([
            "create", f"[dev] {title}",
            "--assignee", "developer",
            "--body", body,
            "--workspace", f"dir:{workspace_path}",
        ])

        if not dev_result or "id" not in dev_result:
            created.append({"error": f"Failed to create developer card for '{title}'"})
            continue

        dev_id = dev_result["id"]

        # Step 2: Create verifier card (parented on developer)
        ver_result = _run_kanban_json([
            "create", f"[verify] {title}",
            "--assignee", "verifier",
            "--parent", dev_id,
            "--body", f"Verify developer card {dev_id}. Contract:\\n{body}",
        ])

        if not ver_result or "id" not in ver_result:
            created.append({"error": f"Failed to create verifier card for '{title}'", "dev_id": dev_id})
            continue

        ver_id = ver_result["id"]
        verifier_ids.append(ver_id)
        created.append({"dev_id": dev_id, "verifier_id": ver_id, "title": title})

    if not verifier_ids:
        return json.dumps({"error": "No verifier cards created", "details": created})

    # Step 3: Link caller as child of ALL verifiers
    for ver_id in verifier_ids:
        ok, out = _run_kanban(["link", ver_id, my_card_id])
        if not ok:
            logger.warning("Failed to link %s as parent of %s: %s", ver_id, my_card_id, out)

    # Step 4: Block caller with kind=dependency
    # Note: reason must come BEFORE --kind (argparse parsing quirk)
    ver_list = ", ".join(verifier_ids)
    reason = f"waiting_for_{len(verifier_ids)}_verifiers:{ver_list}"
    import os as _os
    _debug_env = {
        "task": _os.environ.get("HERMES_KANBAN_TASK", "MISSING"),
        "run_id": _os.environ.get("HERMES_KANBAN_RUN_ID", "MISSING"),
    }
    ok, block_out = _run_kanban([
        "block", my_card_id, reason, "--kind", "dependency",
    ])
    if not ok:
        logger.error("Block command failed for %s: %s (env=%s)", my_card_id, block_out, _debug_env)
        return json.dumps({"error": f"Block command failed: {block_out}", "created": created, "debug_env": _debug_env})

    # Verify the block actually took effect
    verify_status = _run_kanban_json(["show", my_card_id])
    actual_status = None
    if verify_status:
        t = verify_status.get("task", verify_status)
        actual_status = t.get("status")
    if actual_status != "todo":
        logger.error("Block verification failed: %s status=%s (expected todo)", my_card_id, actual_status)
        return json.dumps({"error": f"Block did not take effect: status={actual_status} (expected todo)", "created": created, "debug_env": _debug_env, "block_output": block_out})

    return json.dumps({
        "status": "blocked",
        "verifiers": verifier_ids,
        "created": created,
        "message": (
            f"Created {len(verifier_ids)} dev→verifier pair(s). "
            f"You are now blocked (dependency) on {len(verifier_ids)} verifier(s). "
            f"Auto-promotes when ALL complete. Do NOT call kanban_complete until then."
        ),
    }, indent=2)
