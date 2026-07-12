"""Tool handlers — the code that runs when the LLM calls loop_engine.

Runs in the loop-driver's WORKER process and drives ONE iteration of the outer
phase-loop per invocation. T1 spine: ONE phase, ONE iteration.

Mirrors the proven conventions from kanban_chains/tools.py:
  * _kb() lazy-imports hermes_cli.kanban_db (keeps the plugin loadable/testable
    through its single _kb() seam).
  * BLACKBOARD_PREFIX is a literal (not an import) for the same reason.
  * _my_card_id/_run_id resolve the worker env (HERMES_KANBAN_TASK /
    HERMES_KANBAN_RUN_ID).
  * The root is create_task'd with an idempotency_key on every call; the DB
    dedups. loop_state on the root blackboard distinguishes first-invocation
    from re-invocation (the kanban_chains recovery pattern).

Two paths:
  * FIRST invocation (no loop_state yet): build root + ONE execution card,
    complete root, write loop_state, dependency-park the driver, return
    status=blocked. The worker session ends; the dispatcher re-spawns the
    driver when recompute_ready promotes it (execution card -> done).
  * RE-INVOCATION (driver promoted): read loop_state, read the execution
    card's latest run, stub-decide at hard cap 1 -> status=complete.

The engine is TOOL-driven, not hook-driven: it reads board state on its own
promotion, so the verified recompute_ready ordering hazard (dependents promote
BEFORE the kanban_task_completed hook fires) is irrelevant here. The observer
hook registered in __init__.py is telemetry-only.
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# Mirrors hermes_cli.kanban_db / kanban_swarm BLACKBOARD_PREFIX. Kept as a
# literal (not an import) so the plugin stays loadable/testable through its
# single _kb() seam without importing the DB module. If the upstream constant
# changes, update here.
BLACKBOARD_PREFIX = "[swarm:blackboard] "

# T1: one phase, one iteration. The hard cap is the layered-exit backstop; the
# real DoD + verifier arrive in later beads.
MAX_PHASE_STEPS = 1


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
    return kwargs.get("_profile") or "loop_engine"


def _idempotency_key(my_card_id, run_id, goal):
    """Stable dedup key for the root card (mirrors kanban_chains).

    Keyed on the driver card + this dispatch's run, so a retry WITHIN a
    dispatch recovers the same root, while a fresh dispatch starts fresh.
    Falls back to a goal hash when no run id is available.
    """
    if run_id is not None:
        salt = str(run_id)
    else:
        salt = hashlib.sha1(goal.encode("utf-8")).hexdigest()[:10]
    return f"loop:{my_card_id}:{salt}"


# ── Blackboard helpers (last-write-wins per key — the kanban_chains pattern) ───


def _comment_body(c):
    body = getattr(c, "body", None)
    if body is None and isinstance(c, dict):
        body = c.get("body")
    return body or ""


def _read_blackboard(kb, conn, root_id, key):
    """Return the last `value` written under `key` on root's blackboard, or None."""
    try:
        comments = kb.list_comments(conn, root_id)
    except Exception:  # kernel/mock without comments -> treat as first run
        return None
    value = None
    for c in comments or []:
        body = _comment_body(c)
        if not body.startswith(BLACKBOARD_PREFIX):
            continue
        try:
            payload = json.loads(body[len(BLACKBOARD_PREFIX):])
        except (ValueError, TypeError):
            continue
        if payload.get("key") == key:
            value = payload.get("value")  # last write wins
    return value


def _write_blackboard(kb, conn, root_id, author, key, value):
    payload = json.dumps({"key": key, "value": value}, ensure_ascii=False)
    kb.add_comment(conn, root_id, author, f"{BLACKBOARD_PREFIX}{payload}")


# ── Validation ────────────────────────────────────────────────────────────────


def _validate(args):
    goal = args.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return "goal is required and must be a non-empty string"
    execution = args.get("execution")
    if not isinstance(execution, dict):
        return "execution is required and must be an object"
    for field in ("assignee", "title", "body"):
        val = execution.get(field)
        if not isinstance(val, str) or not val.strip():
            return (f"execution.{field} is required and must be a "
                    f"non-empty string")
    return None


# ── Dependency-park (mirrors kanban_chains._park_caller, single terminal) ─────


def _park_driver(kb, conn, my_card_id, terminal_id, run_id):
    """Link the driver as a child of the execution card and dependency-park it.

    kind="dependency" routes the driver to `todo` and lets recompute_ready
    auto-promote it when the execution card completes — WITHOUT tripping
    block_recurrences (that counter only counts needs_input/capability/
    transient re-blocks). Safe to re-invoke every iteration. See SPEC.md
    §Constraints respected.
    """
    try:
        kb.link_tasks(conn, terminal_id, my_card_id)  # INSERT OR IGNORE
    except ValueError:
        pass  # already linked, or self/cycle guard — safe to skip on recovery
    reason = f"waiting_for_execution:{terminal_id}"
    if kb.block_task(conn, my_card_id, reason=reason, kind="dependency",
                     expected_run_id=run_id):
        return "blocked"
    return "failed"


# ── Handler ───────────────────────────────────────────────────────────────────


def loop_engine(args: dict, **kwargs) -> str:
    """Drive ONE iteration of the outer phase-loop.

    First invocation -> build the spine + dependency-park (status=blocked).
    Re-invocation   -> read the result + stub-decide at hard cap 1
                       (status=complete; no verifier/DoD in T1).
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
    execution = args["execution"]
    author = _author(**kwargs)

    kb = _kb()
    run_id = _run_id()

    with kb.connect_closing(board=_board()) as conn:

        # 1. Root card (shared blackboard) — idempotent on driver + dispatch.
        idem_key = _idempotency_key(my_card_id, run_id, goal)
        root_id = kb.create_task(
            conn,
            title=f"Loop: {goal[:80]}",
            body=f"Loop-engine root / shared blackboard.\nGoal: {goal}\n",
            assignee=_board(),
            created_by=author,
            idempotency_key=idem_key,
        )

        # 2. First invocation vs re-invocation: loop_state on the blackboard is
        #    the single source of truth (the driver is stateless between
        #    promotions).
        loop_state = _read_blackboard(kb, conn, root_id, "loop_state")

        if loop_state is None:
            return _first_invocation(
                kb, conn, root_id, goal, execution, author,
                my_card_id, run_id,
            )

        return _reinvoke(kb, conn, root_id, loop_state, author, run_id)


def _first_invocation(kb, conn, root_id, goal, execution, author,
                      my_card_id, run_id):
    """Build root + ONE execution card, write loop_state, dependency-park."""
    # Complete the root FIRST so the execution card is `ready` immediately
    # (mirrors kanban_chains: complete root, then create children).
    kb.complete_task(
        conn, root_id,
        summary="Loop topology planned; root is the shared blackboard.",
        metadata={"goal": goal},
    )

    skills = [execution["skill"]] if execution.get("skill") else None
    exec_id = kb.create_task(
        conn,
        title=execution["title"],
        body=execution["body"],
        assignee=execution["assignee"],
        created_by=author,
        parents=[root_id],
        skills=skills,
    )

    # Persist loop_state (last-write-wins). terminal_ids is the fan-in barrier;
    # re-invocation re-reads it to locate the execution card.
    _write_blackboard(kb, conn, root_id, author, "loop_state", {
        "phase_index": 0,
        "iteration_counter": 0,
        "terminal_ids": [exec_id],
        "execution_card": exec_id,
    })

    state = _park_driver(kb, conn, my_card_id, exec_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s (run_id=%s)",
                     my_card_id, run_id)
        return json.dumps({
            "error": f"Block failed — driver not in running/ready state, "
                     f"or run_id mismatch (expected {run_id}). Retry is safe: "
                     f"loop_state is recorded on the root blackboard.",
            "root_id": root_id,
            "execution_card": exec_id,
            "terminal_ids": [exec_id],
        })

    return json.dumps({
        "status": "blocked",
        "root_id": root_id,
        "execution_card": exec_id,
        "terminal_ids": [exec_id],
        "iteration": 0,
        "message": (
            "Loop spine built: root + one execution card. Driver "
            "dependency-parked on the execution card; auto-promotes when it "
            "completes. Do NOT call kanban_complete until re-dispatched."
        ),
    }, indent=2)


def _reinvoke(kb, conn, root_id, loop_state, author, run_id):
    """Read the execution result and stub-decide at the T1 hard cap of 1."""
    exec_id = loop_state.get("execution_card")
    if not exec_id:
        terminal_ids = loop_state.get("terminal_ids") or []
        exec_id = terminal_ids[0] if terminal_ids else None

    iteration_counter = int(loop_state.get("iteration_counter", 0)) + 1

    # Read the execution card's closing run for its structured handoff.
    run = kb.latest_run(conn, exec_id) if exec_id else None
    result = {
        "summary": getattr(run, "summary", None),
        "metadata": getattr(run, "metadata", None),
        "outcome": getattr(run, "outcome", None),
    }

    # Persist the advanced counter (durable across a session boundary).
    loop_state["iteration_counter"] = iteration_counter
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    # T1 stub-decide: hard cap = 1 -> report the result, terminate. Later beads
    # add the real verifier / DoD + advance/replan/escalate layered exits.
    return json.dumps({
        "status": "complete",
        "root_id": root_id,
        "execution_card": exec_id,
        "iteration": iteration_counter,
        "decision": "hard_cap_reached",
        "result": result,
        "message": (
            f"Stub-decided at hard cap {MAX_PHASE_STEPS}: reporting the "
            f"execution result (no verifier/DoD in T1). Loop complete."
        ),
    }, indent=2)
