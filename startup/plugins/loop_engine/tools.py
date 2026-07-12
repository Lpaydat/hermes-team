"""Tool handlers — the code that runs when the LLM calls loop_engine.

Runs in the loop-driver's WORKER process and drives ONE iteration of the outer
phase-loop per invocation.

Two modes, selected by whether the caller supplies a ``verifier`` spec:
  * T1 spine (no verifier): ONE phase, ONE iteration, execute-and-read.
  * T2 verifier-gated converge loop (verifier present): after the execution card
    completes, an independent verifier card evaluates the phase output against
    the DoD and completes with a ``dod_verdict`` in ``run.metadata``
    (``{dod_met, score, gaps, recommendation}``). On promotion the driver reads
    the verdict (latest_run direct read) and decides: DoD met /
    recommendation="advance" -> phase complete; dod_met=false / "replan" (under
    the hard cap) -> replan (fresh execution + verifier, dependency-park again);
    hard cap reached without DoD met -> terminate.

Mirrors the proven conventions from kanban_chains/tools.py:
  * _kb() lazy-imports hermes_cli.kanban_db (keeps the plugin loadable/testable
    through its single _kb() seam).
  * BLACKBOARD_PREFIX is a literal (not an import) for the same reason.
  * _my_card_id/_run_id resolve the worker env (HERMES_KANBAN_TASK /
    HERMES_KANBAN_RUN_ID).
  * The root is create_task'd with an idempotency_key on every call; the DB
    dedups. loop_state on the root blackboard distinguishes first-invocation
    from re-invocation (the kanban_chains recovery pattern).

Two paths (T1, when no verifier is supplied):
  * FIRST invocation (no loop_state yet): build root + ONE execution card,
    complete root, write loop_state, dependency-park the driver, return
    status=blocked. The worker session ends; the dispatcher re-spawns the
    driver when recompute_ready promotes it (execution card -> done).
  * RE-INVOCATION (driver promoted): read loop_state, read the execution
    card's latest run, stub-decide at hard cap 1 -> status=complete.

T2 (verifier supplied) adds the verifier card + verdict-gated decide/replan
loop on top of the same substrate, gated on loop_state.verifier_card so the T1
path is byte-for-byte unchanged when no verifier is configured.

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

# T1: one phase, one iteration. The hard cap is the layered-exit backstop.
MAX_PHASE_STEPS = 1

# T2: default hard iteration cap for the verifier-gated converge loop. A caller
# can override per-call via the `max_iterations` argument. Loop engineering's
# core tenet is that termination must not depend on the model; the cap is the
# deterministic backstop that bounds the loop even when the DoD is never met.
DEFAULT_MAX_ITERATIONS = 5


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
    verifier = args.get("verifier")
    if verifier is not None:
        if not isinstance(verifier, dict):
            return "verifier must be an object"
        for field in ("assignee", "title", "body"):
            val = verifier.get(field)
            if not isinstance(val, str) or not val.strip():
                return (f"verifier.{field} is required and must be a "
                        f"non-empty string")
    max_iter = args.get("max_iterations")
    if max_iter is not None:
        # bool is a subclass of int — reject it explicitly.
        if isinstance(max_iter, bool) or not isinstance(max_iter, int) \
                or max_iter < 1:
            return "max_iterations must be a positive integer"
    return None


# ── Dependency-park (mirrors kanban_chains._park_caller, single terminal) ─────


def _park_driver(kb, conn, my_card_id, terminal_id, run_id):
    """Link the driver as a child of the terminal card and dependency-park it.

    kind="dependency" routes the driver to `todo` and lets recompute_ready
    auto-promote it when the terminal completes — WITHOUT tripping
    block_recurrences (that counter only counts needs_input/capability/
    transient re-blocks). Safe to re-invoke every iteration (the re-park on
    replan links a NEW terminal and re-blocks). See SPEC.md §Constraints
    respected.
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


# ── T2: verifier verdict + card factories ─────────────────────────────────────


def _extract_verdict(run):
    """Pull the structured dod_verdict from a verifier card's closing run.

    The verifier writes ``{dod_met, score, gaps, recommendation}`` into
    ``run.metadata["dod_verdict"]`` via ``kanban_complete(metadata=...)``. The
    driver reads it back through the latest_run direct-read path (the same
    path T1 used for the execution result). Returns None when no verdict is
    present (verifier not yet completed, or completed without a verdict).
    """
    if run is None:
        return None
    meta = getattr(run, "metadata", None) or {}
    verdict = meta.get("dod_verdict") if isinstance(meta, dict) else None
    return verdict if isinstance(verdict, dict) else None


def _create_execution_card(kb, conn, root_id, execution, author):
    """Execution card parented on the root (ready immediately; the root is
    completed first). Shared by the first invocation and every replan."""
    skills = [execution["skill"]] if execution.get("skill") else None
    return kb.create_task(
        conn,
        title=execution["title"],
        body=execution["body"],
        assignee=execution["assignee"],
        created_by=author,
        parents=[root_id],
        skills=skills,
    )


def _create_verifier_card(kb, conn, exec_id, verifier, author):
    """Verifier card parented on the execution card.

    Parenting on the execution card (not the root) does two things:
      1. the verifier becomes `ready` only once the execution card completes
         (the execution -> verifier -> driver chain);
      2. build_worker_context injects the execution card's run.metadata into the
         verifier, so the verifier sees the phase output it must evaluate.

    The driver in turn dependency-parks on the verifier, so the verifier's
    completion promotes the driver (the verifier is the terminal parent).
    """
    skills = [verifier["skill"]] if verifier.get("skill") else None
    return kb.create_task(
        conn,
        title=verifier["title"],
        body=verifier["body"],
        assignee=verifier["assignee"],
        created_by=author,
        parents=[exec_id],
        skills=skills,
    )


def _park_failure(root_id, exec_id, verifier_id, terminal_id, run_id):
    body = {
        "error": f"Block failed — driver not in running/ready state, "
                 f"or run_id mismatch (expected {run_id}). Retry is safe: "
                 f"loop_state is recorded on the root blackboard.",
        "root_id": root_id,
        "execution_card": exec_id,
        "terminal_ids": [terminal_id],
    }
    if verifier_id is not None:
        body["verifier_card"] = verifier_id
    return json.dumps(body)


# ── Handler ───────────────────────────────────────────────────────────────────


def loop_engine(args: dict, **kwargs) -> str:
    """Drive ONE iteration of the outer phase-loop.

    Without `verifier`: T1 — first invocation builds the spine +
    dependency-parks (status=blocked); re-invocation stub-decides at hard cap 1
    (status=complete).
    With `verifier`: T2 — verifier-gated converge loop (advance / replan /
    hard-cap), see module docstring.
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
    verifier = args.get("verifier")
    max_iterations = args.get("max_iterations")
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
                my_card_id, run_id, verifier, max_iterations,
            )

        return _reinvoke(
            kb, conn, root_id, loop_state, author, run_id,
            my_card_id, execution, verifier,
        )


def _first_invocation(kb, conn, root_id, goal, execution, author,
                      my_card_id, run_id, verifier, max_iterations):
    """Build root + execution (+ optional verifier), write loop_state, park."""
    # Complete the root FIRST so the execution card is `ready` immediately
    # (mirrors kanban_chains: complete root, then create children).
    kb.complete_task(
        conn, root_id,
        summary="Loop topology planned; root is the shared blackboard.",
        metadata={"goal": goal},
    )

    exec_id = _create_execution_card(kb, conn, root_id, execution, author)

    if verifier is None:
        # T1 spine: one execution card, park on it.
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
            return _park_failure(root_id, exec_id, None, exec_id, run_id)

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

    # T2 verifier-gated converge loop.
    verifier_id = _create_verifier_card(kb, conn, exec_id, verifier, author)
    cap = max_iterations or DEFAULT_MAX_ITERATIONS

    _write_blackboard(kb, conn, root_id, author, "loop_state", {
        "phase_index": 0,
        "iteration_counter": 1,
        "terminal_ids": [verifier_id],
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "max_iterations": cap,
    })

    state = _park_driver(kb, conn, my_card_id, verifier_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s (run_id=%s)",
                     my_card_id, run_id)
        return _park_failure(root_id, exec_id, verifier_id, verifier_id, run_id)

    return json.dumps({
        "status": "blocked",
        "root_id": root_id,
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "terminal_ids": [verifier_id],
        "iteration": 1,
        "max_iterations": cap,
        "message": (
            "Verifier-gated loop: execution + verifier cards dispatched. "
            "Driver dependency-parked on the verifier card; auto-promotes when "
            "the verifier completes. Re-dispatch then reads the dod_verdict and "
            "decides advance / replan / hard-cap."
        ),
    }, indent=2)


def _reinvoke(kb, conn, root_id, loop_state, author, run_id,
              my_card_id, execution, verifier):
    """Read the terminal result and decide.

    T1 path (no verifier_card in loop_state): stub-decide at the T1 hard cap.
    T2 path (verifier_card present): verdict-gated advance / replan / hard cap.
    """
    if "verifier_card" not in loop_state:
        return _reinvoke_t1(kb, conn, root_id, loop_state, author, run_id)
    return _reinvoke_verifier(kb, conn, root_id, loop_state, author, run_id,
                              my_card_id, execution, verifier)


def _reinvoke_t1(kb, conn, root_id, loop_state, author, run_id):
    """T1: read the execution result and stub-decide at the hard cap of 1."""
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


def _reinvoke_verifier(kb, conn, root_id, loop_state, author, run_id,
                       my_card_id, execution, verifier):
    """T2: read the verifier's dod_verdict and decide advance / replan / hard cap.

    The verifier is the terminal parent the driver parked on; its completion
    promoted the driver. The driver reads the verdict via latest_run (direct
    read), not the injected _metadata_ line — the same clean path T1 used.
    """
    verifier_id = loop_state.get("verifier_card")
    exec_id = loop_state.get("execution_card")
    cap = int(loop_state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    iteration_counter = int(loop_state.get("iteration_counter", 1))

    run = kb.latest_run(conn, verifier_id) if verifier_id else None
    verdict = _extract_verdict(run)

    dod_met = bool(verdict and verdict.get("dod_met"))
    recommendation = verdict.get("recommendation") if verdict else None

    # Advance: DoD met (or the verifier explicitly recommends advancing).
    if dod_met or recommendation == "advance":
        return json.dumps({
            "status": "complete",
            "decision": "advance",
            "root_id": root_id,
            "execution_card": exec_id,
            "verifier_card": verifier_id,
            "iteration": iteration_counter,
            "verdict": verdict,
            "message": (
                f"DoD met on iteration {iteration_counter} "
                f"(verifier dod_met={dod_met}); verifier-gated phase complete."
            ),
        }, indent=2)

    # Escalate: the verifier explicitly asked for a human (deferred as a later
    # SPEC refinement — for now we surface it so the caller can act).
    if recommendation == "escalate":
        return json.dumps({
            "status": "escalate",
            "decision": "escalate",
            "root_id": root_id,
            "execution_card": exec_id,
            "verifier_card": verifier_id,
            "iteration": iteration_counter,
            "verdict": verdict,
            "message": (
                "Verifier recommends escalation to a human; pausing the "
                "verifier-gated loop."
            ),
        }, indent=2)

    # Replan while the iteration count is under the hard cap; otherwise the
    # deterministic cap terminates the loop (termination must not depend on the
    # model — loop engineering core tenet).
    if iteration_counter < cap:
        return _replan(kb, conn, root_id, loop_state, author, run_id,
                       my_card_id, execution, verifier,
                       iteration_counter, cap, verdict)

    return json.dumps({
        "status": "complete",
        "decision": "hard_cap_reached",
        "root_id": root_id,
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "iteration": iteration_counter,
        "verdict": verdict,
        "message": (
            f"Hard cap {cap} reached without DoD met; terminating the "
            f"verifier-gated loop."
        ),
    }, indent=2)


def _replan(kb, conn, root_id, loop_state, author, run_id,
            my_card_id, execution, verifier,
            iteration_counter, cap, verdict):
    """Dispatch a fresh execution + verifier card and re-park the driver.

    Each iteration mints new cards because completed cards cannot re-run. The
    re-park links the driver to the NEW verifier terminal and dependency-blocks
    again (kind="dependency" does not trip block_recurrences, so re-parking
    every iteration is safe — SPEC §Constraints respected).
    """
    next_iter = iteration_counter + 1

    exec_id = _create_execution_card(kb, conn, root_id, execution, author)
    verifier_id = _create_verifier_card(kb, conn, exec_id, verifier, author)

    loop_state["iteration_counter"] = next_iter
    loop_state["execution_card"] = exec_id
    loop_state["verifier_card"] = verifier_id
    loop_state["terminal_ids"] = [verifier_id]
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, verifier_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s during replan (run_id=%s)",
                     my_card_id, run_id)
        return _park_failure(root_id, exec_id, verifier_id, verifier_id, run_id)

    return json.dumps({
        "status": "blocked",
        "decision": "replan",
        "root_id": root_id,
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "terminal_ids": [verifier_id],
        "iteration": next_iter,
        "max_iterations": cap,
        "verdict": verdict,
        "message": (
            f"DoD not met (recommendation={verdict.get('recommendation') if verdict else None}); "
            f"replanning iteration {next_iter}/{cap}. Driver re-parked on the "
            f"new verifier card."
        ),
    }, indent=2)
