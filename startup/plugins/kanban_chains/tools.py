"""Tool handlers — the code that runs when the LLM calls kanban_chains.

Borrows the proven design from kanban_swarm.py: uses parents= in create_task
for ALL topology relationships (chain internal, fan-in, sequential). No
separate link_tasks calls for the topology — create_task handles linking
internally via _find_missing_parents. This eliminates the race condition
where link_tasks validates IDs that haven't committed yet.

The only explicit link_tasks call is for the CALLER (its card already exists,
so we can't pass it as a parent to create_task).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

BLACKBOARD_PREFIX = "[swarm:blackboard] "


# ── kanban_db bridge ──────────────────────────────────────────────────────────


def _board():
    return os.environ.get("HERMES_KANBAN_BOARD", "team")


def _kb():
    from hermes_cli import kanban_db
    return kanban_db


def _run_id():
    raw = os.environ.get("HERMES_KANBAN_RUN_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _my_card_id(**kwargs):
    tid = kwargs.get("task_id")
    if tid and isinstance(tid, str) and tid.startswith("t_"):
        return tid
    env_tid = os.environ.get("HERMES_KANBAN_TASK")
    if env_tid and env_tid.startswith("t_"):
        return env_tid
    return None


def _author(**kwargs):
    return kwargs.get("_profile") or "kanban_chains"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _container_section(image_tag, container_port, port, worker_num):
    return (
        f"\n\n## Container\n"
        f"Image: {image_tag}\n"
        f"Start: podman run -d --name qa-worker-{worker_num} "
        f"-p {port}:{container_port} {image_tag}\n"
        f"Port: {port}\n"
        f"Cleanup: podman rm -f qa-worker-{worker_num}\n"
    )


def _validate(args):
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

    Design borrowed from kanban_swarm.create_swarm: all topology relationships
    are expressed via parents= in create_task. No separate link_tasks calls
    for the topology — create_task validates and links parents atomically
    inside its own write_txn.
    """
    err = _validate(args)
    if err:
        return json.dumps({"error": err})

    my_card_id = _my_card_id(**kwargs)
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
    container_port = int(bb.get("container_port", 3000))
    base_port = int(bb.get("base_port", 18081))
    env_facts = (bb.get("env_facts") or "").strip()
    spec_path = (bb.get("spec_path") or "").strip()
    extra = bb.get("extra") or {}

    kb = _kb()
    run_id = _run_id()
    author = _author(**kwargs)

    with kb.connect_closing(board=_board()) as conn:

        # 1. Root card (shared blackboard).
        root_body = f"Chains root / shared blackboard.\nGoal: {goal}\n"
        if image_tag:
            root_body += f"Container image: {image_tag}\n"
            root_body += f"Container port: {container_port}\n"
        if env_facts:
            root_body += f"Env facts: {env_facts}\n"
        if spec_path:
            root_body += f"Spec: {spec_path}\n"

        root_id = kb.create_task(
            conn,
            title=f"Chains: {goal[:80]}",
            body=root_body,
            assignee=_board(),
            created_by=author,
        )

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
            kb.add_comment(conn, root_id, author,
                           f"{BLACKBOARD_PREFIX}{bb_payload}")

        kb.complete_task(
            conn, root_id,
            summary="Chains topology planned; root remains the shared blackboard.",
            metadata={"goal": goal, "chain_count": len(chains)},
        )

        # 2. Chains — each chain's steps run sequentially; chains are parallel.
        #    All linking done via parents= in create_task (same pattern as
        #    kanban_swarm.py: worker parents=[root], verifier parents=[all workers]).
        chains_created = []
        for ci, chain in enumerate(chains):
            chain_ids = []
            for si, step in enumerate(chain):
                parents = [root_id] if si == 0 else [chain_ids[-1]]
                body = step["body"]
                if si == 0 and image_tag:
                    port = base_port + ci
                    body = body + _container_section(
                        image_tag, container_port, port, ci + 1)
                skills = [step["skill"]] if step.get("skill") else None
                card_id = kb.create_task(
                    conn,
                    title=step["title"],
                    body=body,
                    assignee=step["assignee"],
                    created_by=author,
                    parents=parents,
                    skills=skills,
                    workspace_path=step.get("workspace_path"),
                    priority=step.get("priority", 0),
                )
                chain_ids.append(card_id)
            chains_created.append(chain_ids)

        chain_last_ids = [c[-1] for c in chains_created]

        # 3. After sequence (fan-in) — step[0] parented on ALL chain ends.
        #    Uses parents= (list) so create_task handles all fan-in links
        #    atomically in a single write_txn. No separate link_tasks calls.
        after_created = []
        if after:
            for si, step in enumerate(after):
                body = step.get("body") or step["title"]
                skills = [step["skill"]] if step.get("skill") else None
                parents = chain_last_ids if si == 0 else [after_created[-1]]
                card_id = kb.create_task(
                    conn,
                    title=step["title"],
                    body=body,
                    assignee=step["assignee"],
                    created_by=author,
                    parents=parents,
                    skills=skills,
                )
                after_created.append(card_id)

        # 4. Link caller to terminal card(s) and block.
        #    The caller card already exists — we can't use parents= here.
        #    This is the ONLY explicit link_tasks call, mirroring how
        #    `hermes kanban swarm` CLI links the caller after create_swarm.
        if after_created:
            terminal_ids = [after_created[-1]]
        else:
            terminal_ids = chain_last_ids

        for tid in terminal_ids:
            kb.link_tasks(conn, tid, my_card_id)

        reason = f"waiting_for_chains:{', '.join(terminal_ids)}"
        ok = kb.block_task(
            conn,
            my_card_id,
            reason=reason,
            kind="dependency",
            expected_run_id=run_id,
        )
        if not ok:
            logger.error("Block failed for %s (run_id=%s)", my_card_id, run_id)
            return json.dumps({
                "error": f"Block failed — card may not be in running/ready state, "
                         f"or run_id mismatch (expected {run_id}). "
                         f"Cards were created: root={root_id}",
                "root_id": root_id,
                "chains": chains_created,
                "after": after_created,
            })

    # 5. Return.
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
