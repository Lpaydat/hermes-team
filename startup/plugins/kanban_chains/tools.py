"""Tool handlers — the code that runs when the LLM calls kanban_chains.

Borrows the proven design from kanban_swarm.py: uses parents= in create_task
for ALL topology relationships (chain internal, fan-in, sequential). No
separate link_tasks calls for the topology — create_task handles linking
internally via _find_missing_parents. This eliminates the race condition
where link_tasks validates IDs that haven't committed yet.

The only explicit link_tasks call is for the CALLER (its card already exists,
so we can't pass it as a parent to create_task).

Swarm-parity robustness (mirrors kanban_swarm.create_swarm):
  * Idempotency — the root card is created with an idempotency_key derived from
    the caller + dispatch run. A retry/respawn returns the SAME root instead of
    building a duplicate graph. The full topology is recorded as a structured
    `[swarm:blackboard]` comment on the root ("topology" key); on re-invocation
    we recover terminal ids from it and just re-park the caller.
  * Shared blackboard context — every worker body gets a short pointer to the
    root/blackboard card, so workers can read shared spec/env/handoffs.
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# Mirrors hermes_cli.kanban_swarm.BLACKBOARD_PREFIX. Kept as a literal (not an
# import) so the plugin stays loadable/testable through its single _kb() seam
# without importing the swarm module. If swarm ever changes this, update here.
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


def _chains_context(root_id, goal):
    """Short pointer to the shared root/blackboard, appended to every worker
    body — mirrors kanban_swarm._swarm_context so chain workers can read the
    shared spec/env/handoffs and post machine-readable results."""
    return (
        f"\n\n## Chains protocol\n"
        f"- Shared blackboard / root card: `{root_id}`.\n"
        f"- Read parent/sibling handoffs from Kanban context before working.\n"
        f"- Put machine-readable results in your completion metadata.\n"
        f"- Overall goal: {goal.strip()}\n"
    )


def _idempotency_key(my_card_id, run_id, goal):
    """Stable dedup key for the root card. Keyed on the caller card + this
    dispatch's run so a retry/respawn WITHIN a dispatch recovers, while a fresh
    dispatch (new run_id) starts a new topology. Falls back to a goal hash when
    no run id is available."""
    if run_id is not None:
        salt = str(run_id)
    else:
        salt = hashlib.sha1(goal.encode("utf-8")).hexdigest()[:10]
    return f"chains:{my_card_id}:{salt}"


def _comment_body(c):
    body = getattr(c, "body", None)
    if body is None and isinstance(c, dict):
        body = c.get("body")
    return body or ""


def _read_topology(kb, conn, root_id):
    """Return the recorded topology dict from the root's blackboard, or None.

    Scans structured `[swarm:blackboard]` comments for the "topology" key
    (last write wins), exactly like kanban_swarm.latest_blackboard."""
    try:
        comments = kb.list_comments(conn, root_id)
    except Exception:  # kernel/mock without comments -> treat as first run
        return None
    topo = None
    for c in comments or []:
        body = _comment_body(c)
        if not body.startswith(BLACKBOARD_PREFIX):
            continue
        try:
            payload = json.loads(body[len(BLACKBOARD_PREFIX):])
        except (ValueError, TypeError):
            continue
        if payload.get("key") == "topology":
            topo = payload.get("value")  # later comment replaces earlier
    return topo


def _write_topology(kb, conn, root_id, author, chains_created, after_created,
                    terminal_ids, goal):
    """Record the full topology on the root blackboard so a re-invocation can
    recover it instead of rebuilding the graph."""
    payload = json.dumps({
        "key": "topology",
        "value": {
            "chains": chains_created,
            "after": after_created,
            "terminal_ids": terminal_ids,
            "goal": goal,
        },
    }, ensure_ascii=False)
    kb.add_comment(conn, root_id, author, f"{BLACKBOARD_PREFIX}{payload}")


def _park_caller(kb, conn, my_card_id, terminal_ids, run_id):
    """Link the caller as a child of every terminal card and move it into the
    dependency wait. Returns:

      'blocked'  — caller was running/ready and is now parked in `todo`
      'already'  — caller was already parked (idempotent recovery)
      'failed'   — caller is running/ready but block_task refused (bad run_id)
    """
    for tid in terminal_ids:
        try:
            kb.link_tasks(conn, tid, my_card_id)  # INSERT OR IGNORE — idempotent
        except ValueError:
            pass  # unknown/self/cycle guard — safe to skip on recovery
    reason = f"waiting_for_chains:{', '.join(terminal_ids)}"
    if kb.block_task(conn, my_card_id, reason=reason, kind="dependency",
                     expected_run_id=run_id):
        return "blocked"
    # block_task only fires from running/ready. A refusal usually means the
    # caller is ALREADY parked (todo/blocked from a prior successful call) —
    # recovery, not failure. Distinguish via the live status when available.
    try:
        st = getattr(kb.get_task(conn, my_card_id), "status", None)
        if st in ("todo", "blocked", "done"):
            return "already"
    except Exception:
        pass
    return "failed"


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
    caller as dependent on the terminal card(s), and park the caller in the
    dependency wait.

    Design borrowed from kanban_swarm.create_swarm: all topology relationships
    are expressed via parents= in create_task, the root is completed
    immediately, and the graph is idempotent — a retry recovers the existing
    topology from the root blackboard rather than duplicating it.
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

        # 1. Root card (shared blackboard) — idempotent on caller + dispatch.
        root_body = f"Chains root / shared blackboard.\nGoal: {goal}\n"
        if image_tag:
            root_body += f"Container image: {image_tag}\n"
            root_body += f"Container port: {container_port}\n"
        if env_facts:
            root_body += f"Env facts: {env_facts}\n"
        if spec_path:
            root_body += f"Spec: {spec_path}\n"

        idem_key = _idempotency_key(my_card_id, run_id, goal)
        root_id = kb.create_task(
            conn,
            title=f"Chains: {goal[:80]}",
            body=root_body,
            assignee=_board(),
            created_by=author,
            idempotency_key=idem_key,
        )

        # 1a. Idempotent recovery — if this root already carries a recorded
        #     topology, a prior call already built the graph. Do NOT rebuild;
        #     just make sure the caller is parked and return the same ids.
        topo = _read_topology(kb, conn, root_id)
        if topo and topo.get("terminal_ids"):
            terminal_ids = topo["terminal_ids"]
            state = _park_caller(kb, conn, my_card_id, terminal_ids, run_id)
            if state == "failed":
                return json.dumps({
                    "error": "Recovered existing chains topology but could not "
                             "park the caller — it is not in running/ready state "
                             f"or run_id mismatch (expected {run_id}).",
                    "root_id": root_id,
                    "terminal_ids": terminal_ids,
                })
            return json.dumps({
                "status": "blocked",
                "recovered": True,
                "root_id": root_id,
                "chains": topo.get("chains"),
                "after": topo.get("after"),
                "terminal_ids": terminal_ids,
                "message": (
                    "Recovered existing chains topology (idempotent "
                    "re-invocation); caller is parked in the dependency wait. "
                    "Do NOT call kanban_complete until re-dispatched."
                ),
            }, indent=2)

        # 1b. Optional shared-context blackboard for workers to read.
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

        context_suffix = _chains_context(root_id, goal)

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
                body = body + context_suffix
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
                body = (step.get("body") or step["title"]) + context_suffix
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

        # 4. Record topology on the root BEFORE parking the caller, so a retry
        #    (e.g. if the park below fails) can recover instead of rebuilding.
        if after_created:
            terminal_ids = [after_created[-1]]
        else:
            terminal_ids = chain_last_ids

        _write_topology(kb, conn, root_id, author,
                        chains_created, after_created, terminal_ids, goal)

        # 5. Link caller to terminal card(s) and park it in the dependency wait.
        #    The caller card already exists — we can't use parents= here.
        state = _park_caller(kb, conn, my_card_id, terminal_ids, run_id)
        if state == "failed":
            logger.error("Block failed for %s (run_id=%s)", my_card_id, run_id)
            return json.dumps({
                "error": f"Block failed — card may not be in running/ready state, "
                         f"or run_id mismatch (expected {run_id}). Retry is safe: "
                         f"the topology is recorded under an idempotency key, so "
                         f"re-invoking recovers it instead of duplicating.",
                "root_id": root_id,
                "chains": chains_created,
                "after": after_created,
                "terminal_ids": terminal_ids,
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
