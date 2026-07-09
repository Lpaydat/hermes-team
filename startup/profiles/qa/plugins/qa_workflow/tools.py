"""Tool handlers — the code that runs when the LLM calls qa_swarm."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# Artifact type → default worker set (the model can override)
ARTIFACT_DEFAULTS = {
    "cli": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "library": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "api_server": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-security", "title": "Security + non-functional"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "daemon": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-security", "title": "Security + non-functional"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "webapp": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-journeys", "title": "User journeys"},
        {"skill": "qa-security", "title": "Security + non-functional"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "mobile": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-journeys", "title": "User journeys"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "blockchain": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-security", "title": "Security + non-functional"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "tui": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
    "mixed": [
        {"skill": "qa-functional", "title": "Functional claims"},
        {"skill": "qa-journeys", "title": "User journeys"},
        {"skill": "qa-security", "title": "Security + non-functional"},
        {"skill": "qa-exploratory", "title": "Exploratory"},
    ],
}

BLACKBOARD_PREFIX = "[swarm:blackboard] "


def _get_board():
    import os
    return os.environ.get("HERMES_KANBAN_BOARD", "team")


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


def qa_swarm(args: dict, **kwargs) -> str:
    """
    Create a QA test swarm: root (blackboard) + workers + verifier + synthesizer.
    Each worker gets a tailored card body with its specific checklist.
    Auto-allocates ports, links dependencies, blocks caller on synthesizer.
    """
    goal = args.get("goal", "").strip()
    artifact_type = args.get("artifact_type", "mixed")
    image_tag = args.get("image_tag", "").strip()
    container_port = args.get("container_port", 3000)
    base_port = args.get("base_port", 18081)
    env_facts = args.get("env_facts", "").strip()
    spec_path = args.get("spec_path", "").strip()
    workers_input = args.get("workers", [])

    if not goal:
        return json.dumps({"error": "goal is required"})
    if not image_tag:
        return json.dumps({"error": "image_tag is required"})
    if not workers_input:
        return json.dumps({"error": "workers is required — pass at least one worker"})

    my_card_id = _get_my_card_id(**kwargs)
    if not my_card_id:
        return json.dumps({"error": "Cannot determine current task ID. Set HERMES_KANBAN_TASK or pass task_id."})

    # Step 1: Create root card (blackboard)
    blackboard_body = (
        f"QA Swarm root / shared blackboard.\n"
        f"Goal: {goal}\n"
        f"Artifact type: {artifact_type}\n"
        f"Container image: {image_tag}\n"
        f"Container port: {container_port}\n"
    )
    if env_facts:
        blackboard_body += f"Env facts: {env_facts}\n"
    if spec_path:
        blackboard_body += f"Spec: {spec_path}\n"

    root_result = _run_kanban_json([
        "create", f"QA Swarm: {goal[:80]}",
        "--assignee", "qa",
        "--body", blackboard_body,
    ])
    if not root_result or "id" not in root_result:
        return json.dumps({"error": "Failed to create root card"})

    root_id = root_result["id"]

    # Post structured blackboard with image + env info
    bb_payload = json.dumps({
        "key": "swarm_context",
        "value": {
            "image_tag": image_tag,
            "container_port": container_port,
            "artifact_type": artifact_type,
            "env_facts": env_facts,
            "spec_path": spec_path,
        }
    }, ensure_ascii=False)
    _run_kanban(["comment", root_id, f"{BLACKBOARD_PREFIX}{bb_payload}"])

    # Step 2: Create worker cards with tailored bodies
    worker_ids = []
    created = []

    for i, w in enumerate(workers_input):
        title = w.get("title", f"Worker {i+1}")
        skill = w.get("skill", "qa-functional")
        body_content = w.get("body", "")

        port = base_port + i

        # Build the worker card body — this is what the worker sees as its task
        worker_body = (
            f"{title}\n\n"
            f"## Your assignment\n"
            f"{body_content}\n\n"
            f"## Container\n"
            f"- Image: `{image_tag}`\n"
            f"- Start: `podman run -d --name qa-worker-{i+1} --memory=1g --cpus=1 -p {port}:{container_port} {image_tag}`\n"
            f"- Your port: {port}\n"
            f"- Health check: `curl -sf http://localhost:{port}/` (adapt for your artifact type)\n"
            f"- Cleanup: `podman rm -f qa-worker-{i+1}` after testing\n\n"
            f"## Swarm protocol\n"
            f"- Swarm root / shared blackboard: `{root_id}`\n"
            f"- Post results to the blackboard using structured comments.\n"
            f"- Complete with metadata: {{verdicts/findings, checks_run, claims_tested, claims_proven}}.\n"
            f"- Goal: {goal}\n"
        )

        if env_facts:
            worker_body += f"\n## Environment (CRITICAL)\n{env_facts}\n"
        if spec_path:
            worker_body += f"\n## Spec\nRead claims from: `{spec_path}`\n"

        worker_result = _run_kanban_json([
            "create", f"[QA] {title}",
            "--assignee", "qa",
            "--parent", root_id,
            "--body", worker_body,
            "--skills", skill,
        ])

        if not worker_result or "id" not in worker_result:
            created.append({"error": f"Failed to create worker '{title}'"})
            continue

        worker_id = worker_result["id"]
        worker_ids.append(worker_id)
        created.append({"worker_id": worker_id, "title": title, "skill": skill, "port": port})

    if not worker_ids:
        return json.dumps({"error": "No worker cards created", "details": created})

    # Step 3: Create verifier card (parented on ALL workers)
    verifier_body = (
        "Verify QA swarm outputs. Read the root card's blackboard. "
        "Check that ALL workers posted results. Complete with metadata {\"gate\": \"pass\"} "
        "when evidence is sufficient. Block with missing work if any worker is incomplete.\n\n"
        f"Swarm root: `{root_id}`\n"
        f"Workers: {', '.join(worker_ids)}\n"
    )
    ver_result = _run_kanban_json([
        "create", "[QA] Verify swarm outputs",
        "--assignee", "qa",
        "--body", verifier_body,
    ])
    if not ver_result or "id" not in ver_result:
        return json.dumps({"error": "Failed to create verifier card", "workers": created})

    verifier_id = ver_result["id"]
    # Link verifier as child of each worker
    for wid in worker_ids:
        _run_kanban(["link", wid, verifier_id])

    # Step 4: Create synthesizer card (parented on verifier)
    synth_body = (
        "Synthesize QA swarm outputs into final verdict. Read the root card's blackboard "
        "and all worker completions. File Critical findings (P0/P1) using the `kanban_delegate` "
        "tool — it atomically creates a developer card WITH a verifier child, so the fix is "
        "independently verified. Do NOT use `kanban_create` to file developer cards; that "
        "bypasses the dev→verifier pairing. "
        "Complete with metadata {verdict, findings_count, claims_tested, claims_proven}.\n\n"
        f"Swarm root: `{root_id}`\n"
    )
    synth_result = _run_kanban_json([
        "create", "[QA] Synthesize verdict",
        "--assignee", "qa",
        "--body", synth_body,
    ])
    if not synth_result or "id" not in synth_result:
        return json.dumps({"error": "Failed to create synthesizer card", "workers": created})

    synthesizer_id = synth_result["id"]
    # Link synthesizer as child of verifier
    _run_kanban(["link", verifier_id, synthesizer_id])

    # Step 5: Link caller as child of synthesizer
    ok, out = _run_kanban(["link", synthesizer_id, my_card_id])
    if not ok:
        logger.warning("Failed to link synthesizer %s as parent of %s: %s", synthesizer_id, my_card_id, out)

    # Step 6: Block caller with kind=dependency
    reason = f"waiting_for_qa_synthesizer:{synthesizer_id}"
    ok, block_out = _run_kanban(["block", my_card_id, reason, "--kind", "dependency"])
    if not ok:
        logger.error("Block command failed for %s: %s", my_card_id, block_out)
        return json.dumps({"error": f"Block command failed: {block_out}", "created": created})

    # Verify the block took effect
    verify_status = _run_kanban_json(["show", my_card_id])
    actual_status = None
    if verify_status:
        t = verify_status.get("task", verify_status)
        actual_status = t.get("status")
    if actual_status != "todo":
        return json.dumps({
            "error": f"Block did not take effect: status={actual_status} (expected todo)",
            "created": created,
        })

    return json.dumps({
        "status": "blocked",
        "root_id": root_id,
        "worker_ids": worker_ids,
        "verifier_id": verifier_id,
        "synthesizer_id": synthesizer_id,
        "created": created,
        "message": (
            f"Created QA swarm: {len(worker_ids)} workers + verifier + synthesizer. "
            f"You are now blocked (dependency) on synthesizer {synthesizer_id}. "
            f"Auto-promotes when synthesis completes. Do NOT call kanban_complete until then."
        ),
    }, indent=2)
