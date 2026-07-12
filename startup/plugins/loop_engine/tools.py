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

T5 — runner profile config + fallback. A workflow may declare a ``runner``
profile (e.g. ``debugger``) — the profile that should drive the loop and that
execution/verifier cards default to when they do not name their own assignee.
A single resolver (:func:`_resolve_runner`) implements the resolution order
**configured runner -> worker -> default** and is the ONLY assignee-resolution
path. The resolved runner is stored in ``loop_state`` (durable across replans /
phase advances) and applied to every card via :func:`_resolve_assignee`; a card
that sets its own ``assignee`` overrides the runner default.

Driver-card bootstrap: this tool runs *inside* the driver's worker, so the
driver card is created by the bootstrap CALLER (not by this tool). The caller
sets the driver card's assignee using the SAME resolver
(``_resolve_runner(runner, known_profiles=_known_profiles())``) so the driver
matches the workflow's runner — the engine does not (cannot) set it after the
fact.
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

# T4: layered-exit guards. The hard cap (max_iterations) is the deterministic
# backstop; budget + no-progress are additional early-break exits. ALL THREE
# route to a sticky HITL block (block_task kind=needs_input) — termination must
# not depend on the model (loop-engineering core tenet; SPEC §Termination is
# safety-critical, therefore deterministic). No loop runs unbounded, even in
# stop-condition-optional / non-stop mode.
DEFAULT_BUDGET = None              # None = no budget guard (hard cap still bounds).
DEFAULT_ITERATION_COST = 1         # cost units consumed per completed iteration.
DEFAULT_NO_PROGRESS_THRESHOLD = 2  # N consecutive identical verdict hashes.

# T5: runner profile resolution. A workflow may declare a `runner` profile
# (e.g. "debugger") — the profile that should drive the loop and that
# execution/verifier cards default to when they do not name their own assignee.
# Resolution order: configured runner -> worker -> default. ``worker`` and
# ``default`` are LOGICAL fallback names (not necessarily real profile dirs);
# a deployment steers the fallback by declaring its known-profile set.
DEFAULT_RUNNER = "worker"   # the first fallback when no runner is configured.
RUNNER_FALLBACK = "default"  # the unconditional last resort.


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


# ── T5: runner profile resolution ─────────────────────────────────────────────


def _known_profiles():
    """Return the set of profile names this deployment recognizes, or None.

    When None, :func:`_resolve_runner` accepts any non-empty candidate, so the
    effective chain is ``runner -> worker`` (``default`` is the unconditional
    last resort). Set the ``HERMES_KNOWN_PROFILES`` env var (comma-separated
    profile names) to restrict the set so an unknown configured runner falls
    back to ``worker``, and an unknown ``worker`` falls back to ``default``.
    Returns None when unset / blank / unparseable.

    This is the deployment-configurable seam for the fallback chain; tests and
    deployments may also call :func:`_resolve_runner` with ``known_profiles``
    directly.
    """
    raw = os.environ.get("HERMES_KNOWN_PROFILES")
    if not raw or not raw.strip():
        return None
    names = {p.strip() for p in raw.split(",") if p.strip()}
    return names or None


def _resolve_runner(runner=None, known_profiles=None):
    """Resolve the workflow's runner profile — the default card assignee.

    T5. This is the SINGLE resolver used for every card the engine creates.
    Resolution order (first AVAILABLE candidate wins):

        configured runner  ->  worker  ->  default

    A candidate is *available* when it is a non-empty string AND
    (``known_profiles is None`` OR ``known_profiles`` contains it). When
    ``known_profiles`` is None every non-empty candidate is accepted, so the
    effective chain is ``runner -> worker``. Supply a known-profile set (the
    deployment's real profile names) so an unknown configured runner falls back
    to ``worker``, and an unknown ``worker`` falls back to ``default``.

    ``default`` is the unconditional last resort: if no candidate is available
    it is returned regardless, so a card is never created without an assignee.

    Driver-card bootstrap: the engine tool runs *inside* the driver's worker,
    so the driver card is created by the bootstrap CALLER (not by this tool).
    The caller should use this same resolver to set the driver card's assignee
    so the driver matches the workflow's runner (SPEC §Implementation
    Decisions, "Runner assignment").
    """
    chain = []
    if runner and isinstance(runner, str) and runner.strip():
        chain.append(runner.strip())
    chain.append(DEFAULT_RUNNER)
    for candidate in chain:
        if candidate and (known_profiles is None or candidate in known_profiles):
            return candidate
    return RUNNER_FALLBACK


def _resolve_assignee(spec, resolved_runner):
    """Per-card assignee: an explicit card assignee wins; else the resolved runner.

    A card (execution or verifier spec) may omit ``assignee`` to inherit the
    workflow's resolved runner (T5). An explicit, non-empty assignee always
    overrides the runner default — so a phase that needs a different profile
    (e.g. verifier on the ``verifier`` profile) just names it.
    """
    explicit = spec.get("assignee") if isinstance(spec, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    return resolved_runner


def _idempotency_key(my_card_id, run_id, goal):
    """Stable dedup key for the root card.

    Keyed on the driver card + the goal so the root (and its loop_state
    blackboard) is RECOVERED across re-dispatches of the same workflow. The
    converge loop's durability model requires the root to be stable across
    runs: ``block_task(kind="dependency")`` closes the current run, so a
    re-promoted driver is re-claimed into a NEW run with a different run_id.
    A run-based key would orphan loop_state on every re-invoke; the goal hash
    keeps the root stable (the driver is stateless between promotions; SPEC
    §State). Different goals yield different hashes, and a driver runs one
    workflow at a time, so there is no collision risk. ``run_id`` is accepted
    for signature compatibility but does not participate in the key.
    """
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


def _validate_phases(phases):
    """Validate the T3 multi-phase `phases` list.

    T5: ``assignee`` is OPTIONAL on each execution/verifier spec — the resolved
    runner (configured -> worker -> default) fills it in at card-creation time.
    When ``assignee`` IS supplied it must be a non-empty string.
    """
    if not isinstance(phases, list) or len(phases) < 1:
        return "phases must be a non-empty array"
    for i, phase in enumerate(phases):
        if not isinstance(phase, dict):
            return f"phases[{i}] must be an object"
        pexec = phase.get("execution")
        if not isinstance(pexec, dict):
            return (f"phases[{i}].execution is required and must be "
                    f"an object")
        for field in ("title", "body"):
            val = pexec.get(field)
            if not isinstance(val, str) or not val.strip():
                return (f"phases[{i}].execution.{field} is required and "
                        f"must be a non-empty string")
        err = _validate_optional_assignee(
            pexec.get("assignee"), f"phases[{i}].execution.assignee")
        if err:
            return err
        pver = phase.get("verifier")
        if pver is not None:
            if not isinstance(pver, dict):
                return f"phases[{i}].verifier must be an object"
            for field in ("title", "body"):
                val = pver.get(field)
                if not isinstance(val, str) or not val.strip():
                    return (f"phases[{i}].verifier.{field} is required "
                            f"and must be a non-empty string")
            err = _validate_optional_assignee(
                pver.get("assignee"), f"phases[{i}].verifier.assignee")
            if err:
                return err
        pmax = phase.get("max_iterations")
        if pmax is not None:
            if isinstance(pmax, bool) or not isinstance(pmax, int) \
                    or pmax < 1:
                return (f"phases[{i}].max_iterations must be a positive "
                        f"integer")
    return None


def _validate_optional_assignee(value, label):
    """assignee is optional (T5: defaults to the resolved runner). When present
    it must be a non-empty string."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty string"
    return None


def _validate(args):
    goal = args.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return "goal is required and must be a non-empty string"
    # T5: optional workflow runner profile (defaults to worker -> default).
    runner = args.get("runner")
    if runner is not None:
        if not isinstance(runner, str) or not runner.strip():
            return ("runner must be a non-empty string (the profile that "
                    "drives the loop)")
    phases = args.get("phases")
    if phases is not None:
        return _validate_phases(phases)
    execution = args.get("execution")
    if not isinstance(execution, dict):
        return "execution is required and must be an object"
    for field in ("title", "body"):
        val = execution.get(field)
        if not isinstance(val, str) or not val.strip():
            return (f"execution.{field} is required and must be a "
                    f"non-empty string")
    # T5: assignee is optional — defaults to the resolved runner.
    err = _validate_optional_assignee(
        execution.get("assignee"), "execution.assignee")
    if err:
        return err
    verifier = args.get("verifier")
    if verifier is not None:
        if not isinstance(verifier, dict):
            return "verifier must be an object"
        for field in ("title", "body"):
            val = verifier.get(field)
            if not isinstance(val, str) or not val.strip():
                return (f"verifier.{field} is required and must be a "
                        f"non-empty string")
        err = _validate_optional_assignee(
            verifier.get("assignee"), "verifier.assignee")
        if err:
            return err
    max_iter = args.get("max_iterations")
    if max_iter is not None:
        # bool is a subclass of int — reject it explicitly.
        if isinstance(max_iter, bool) or not isinstance(max_iter, int) \
                or max_iter < 1:
            return "max_iterations must be a positive integer"
    budget = args.get("budget")
    if budget is not None:
        if isinstance(budget, bool) or not isinstance(budget, int) \
                or budget < 1:
            return "budget must be a positive integer"
    threshold = args.get("no_progress_threshold")
    if threshold is not None:
        if isinstance(threshold, bool) or not isinstance(threshold, int) \
                or threshold < 1:
            return "no_progress_threshold must be a positive integer"
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


def _create_execution_card(kb, conn, root_id, execution, author,
                           resolved_runner):
    """Execution card parented on the root (ready immediately; the root is
    completed first). Shared by the first invocation and every replan.

    T5: the card's assignee is :func:`_resolve_assignee` — an explicit
    ``execution["assignee"]`` wins; otherwise the resolved runner is used.
    """
    skills = [execution["skill"]] if execution.get("skill") else None
    return kb.create_task(
        conn,
        title=execution["title"],
        body=execution["body"],
        assignee=_resolve_assignee(execution, resolved_runner),
        created_by=author,
        parents=[root_id],
        skills=skills,
    )


def _create_verifier_card(kb, conn, exec_id, verifier, author,
                          resolved_runner):
    """Verifier card parented on the execution card.

    Parenting on the execution card (not the root) does two things:
      1. the verifier becomes `ready` only once the execution card completes
         (the execution -> verifier -> driver chain);
      2. build_worker_context injects the execution card's run.metadata into the
         verifier, so the verifier sees the phase output it must evaluate.

    The driver in turn dependency-parks on the verifier, so the verifier's
    completion promotes the driver (the verifier is the terminal parent).

    T5: the card's assignee is :func:`_resolve_assignee` — an explicit
    ``verifier["assignee"]`` wins; otherwise the resolved runner is used.
    """
    skills = [verifier["skill"]] if verifier.get("skill") else None
    return kb.create_task(
        conn,
        title=verifier["title"],
        body=verifier["body"],
        assignee=_resolve_assignee(verifier, resolved_runner),
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


# ── T4: layered exits + HITL escalation ───────────────────────────────────────


def _state_hash(verdict):
    """Stable hash of the verifier verdict — the phase-state signal for
    no-progress detection.

    Identical verdicts across consecutive iterations mean the replan did not
    change the phase state (the loop is circling). Returns a stable string so
    it serializes cleanly into loop_state. The hash is NOT security-sensitive
    — sha1 is used only as a canonical digest."""
    if verdict is None:
        return "none"
    try:
        canonical = json.dumps(verdict, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return "unhashable"
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _human_owes(exit_reason, phase_index, iteration_counter, cap=None,
                budget=None, threshold=None, verdict=None):
    """Human-readable description of exactly what the human owes for each exit.

    Carried in the named event payload so a human unblocks precisely (SPEC user
    story 21: "name exactly what input or decision I owe")."""
    if exit_reason == "hard_cap":
        return (f"Phase {phase_index} exhausted its hard cap of {cap} "
                f"iterations (iteration {iteration_counter}) without meeting "
                f"the DoD. Review the phase DoD, revise the approach, or raise "
                f"the cap, then unblock.")
    if exit_reason == "budget_exhausted":
        return (f"Phase {phase_index} exhausted its budget of {budget} cost "
                f"units at iteration {iteration_counter}. Review spend, raise "
                f"the budget, or descope, then unblock.")
    if exit_reason == "no_progress":
        return (f"Phase {phase_index} produced identical verifier verdicts "
                f"across {threshold} consecutive iterations at iteration "
                f"{iteration_counter} (no convergence). Revise the approach "
                f"or the DoD, then unblock.")
    if exit_reason == "verifier_escalate":
        gaps = (verdict or {}).get("gaps")
        return (f"Phase {phase_index} verifier recommended escalation at "
                f"iteration {iteration_counter}. Address the gaps ({gaps}), "
                f"then unblock.")
    return (f"Phase {phase_index} loop escalated ({exit_reason}) at iteration "
            f"{iteration_counter}. Review and unblock.")


def _escalate(kb, conn, root_id, loop_state, author, run_id, my_card_id,
              exit_reason, phase_index, iteration_counter, cap=None,
              budget=None, threshold=None, verdict=None):
    """Route a layered-exit trip to the HITL escalation.

    Two board actions, both required:
      1. ``block_task(kind="needs_input")`` — sticky. ``_has_sticky_block``
         prevents ``recompute_ready`` from auto-promoting it, so the block
         spans multi-hour waits natively. ``unblock_task`` is the ONLY resume.
      2. ``_append_event(kind="loop_escalated", payload={...})`` — a named
         event describing exactly what the human owes (which exit, which phase,
         which iteration, the gaps/budget/cap as relevant).

    Records the fired exit in ``loop_state.exit_counters`` and persists the
    state. Returns the JSON escalation response. Termination is deterministic:
    this is plugin code, not model-enforced (SPEC §Termination is
    safety-critical, therefore deterministic).
    """
    exit_counters = loop_state.get("exit_counters") or {}
    exit_counters[exit_reason] = exit_counters.get(exit_reason, 0) + 1
    loop_state["exit_counters"] = exit_counters
    loop_state["status"] = "escalated"
    loop_state["exit_reason"] = exit_reason
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    owes = _human_owes(exit_reason, phase_index, iteration_counter,
                       cap=cap, budget=budget, threshold=threshold,
                       verdict=verdict)

    # 1. Sticky block: kind=needs_input routes to `blocked` and is sticky —
    #    recompute_ready will NOT auto-promote (the human must unblock_task).
    reason = f"loop_escalation:{exit_reason}:phase_{phase_index}"
    kb.block_task(conn, my_card_id, reason=reason, kind="needs_input",
                  expected_run_id=run_id)

    # 2. Named event: exactly what the human owes (which exit, which phase...).
    payload = {
        "exit": exit_reason,
        "phase_index": phase_index,
        "iteration": iteration_counter,
        "root_id": root_id,
        "human_owes": owes,
    }
    if cap is not None:
        payload["cap"] = cap
    if budget is not None:
        payload["budget"] = budget
    if threshold is not None:
        payload["no_progress_threshold"] = threshold
    if verdict is not None:
        payload["verdict"] = verdict
    kb._append_event(conn, my_card_id, "loop_escalated", payload,
                     run_id=run_id)

    body = {
        "status": "escalated",
        "decision": exit_reason,
        "root_id": root_id,
        "phase_index": phase_index,
        "iteration": iteration_counter,
        "exit_counters": exit_counters,
        "human_owes": owes,
        "sticky_block": True,
        "resume_via": "unblock_task",
        "message": (
            f"Layered exit '{exit_reason}' fired at phase {phase_index}, "
            f"iteration {iteration_counter}. Driver sticky-blocked "
            f"(kind=needs_input); a human must unblock_task to resume."
        ),
    }
    if cap is not None:
        body["cap"] = cap
    if budget is not None:
        body["budget"] = budget
    if threshold is not None:
        body["no_progress_threshold"] = threshold
    if verdict is not None:
        body["verdict"] = verdict
    return json.dumps(body, indent=2)


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
    phases = args.get("phases")
    execution = args.get("execution")
    verifier = args.get("verifier")
    max_iterations = args.get("max_iterations")
    budget = args.get("budget")
    no_progress_threshold = args.get("no_progress_threshold")
    runner = args.get("runner")
    runner = runner.strip() if isinstance(runner, str) else None
    author = _author(**kwargs)

    # T5: resolve the workflow runner once (configured -> worker -> default).
    # Stored in loop_state so replans / phase advances reuse the same runner.
    resolved_runner = _resolve_runner(runner, known_profiles=_known_profiles())

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
                my_card_id, run_id, verifier, max_iterations, phases,
                budget, no_progress_threshold, resolved_runner,
            )

        return _reinvoke(
            kb, conn, root_id, loop_state, author, run_id,
            my_card_id, execution, verifier, phases,
        )


def _first_invocation(kb, conn, root_id, goal, execution, author,
                      my_card_id, run_id, verifier, max_iterations, phases,
                      budget=None, no_progress_threshold=None,
                      resolved_runner=None):
    """Build root + execution (+ optional verifier), write loop_state, park.

    When ``phases`` is supplied (T3 multi-phase), the first phase's specs are
    resolved from ``phases[0]`` and the full phase plan is stored in
    loop_state. Otherwise the top-level execution/verifier/max_iterations
    drive a single phase (backward compat with T1/T2).

    T4: the verifier-gated branch seeds ``exit_counters`` (budget_remaining +
    no-progress tracking) so the layered-exit guards are active from the first
    iteration. The T1 spine is unchanged (no verifier, no converge loop).

    T5: ``resolved_runner`` is the workflow's default card assignee
    (configured -> worker -> default). It is stored in loop_state (durable
    across replans / phase advances) and applied to every card via
    :func:`_resolve_assignee` unless the card names its own assignee.
    """
    # Complete the root FIRST so the execution card is `ready` immediately
    # (mirrors kanban_chains: complete root, then create children).
    kb.complete_task(
        conn, root_id,
        summary="Loop topology planned; root is the shared blackboard.",
        metadata={"goal": goal},
    )

    # Resolve the first phase's specs.
    if phases is not None:
        phase_0 = phases[0]
        exec_spec = phase_0["execution"]
        verifier_spec = phase_0.get("verifier")
        phase_cap = phase_0.get("max_iterations")
    else:
        exec_spec = execution
        verifier_spec = verifier
        phase_cap = max_iterations

    exec_id = _create_execution_card(kb, conn, root_id, exec_spec, author,
                                     resolved_runner)

    if verifier_spec is None:
        # T1 spine: one execution card, park on it.
        loop_state = {
            "phase_index": 0,
            "iteration_counter": 0,
            "terminal_ids": [exec_id],
            "execution_card": exec_id,
            "resolved_runner": resolved_runner,
        }
        if phases is not None:
            loop_state["phases"] = phases
        _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

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
            "runner": resolved_runner,
            "message": (
                "Loop spine built: root + one execution card. Driver "
                "dependency-parked on the execution card; auto-promotes when it "
                "completes. Do NOT call kanban_complete until re-dispatched."
            ),
        }, indent=2)

    # T2 verifier-gated converge loop.
    verifier_id = _create_verifier_card(kb, conn, exec_id, verifier_spec,
                                        author, resolved_runner)
    cap = phase_cap or DEFAULT_MAX_ITERATIONS

    resolved_budget = (int(budget) if budget is not None else None)
    resolved_threshold = (int(no_progress_threshold)
                          if no_progress_threshold is not None
                          else DEFAULT_NO_PROGRESS_THRESHOLD)

    loop_state = {
        "phase_index": 0,
        "iteration_counter": 1,
        "terminal_ids": [verifier_id],
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "max_iterations": cap,
        "budget": resolved_budget,
        "iteration_cost": DEFAULT_ITERATION_COST,
        "no_progress_threshold": resolved_threshold,
        "resolved_runner": resolved_runner,
        "exit_counters": {
            "hard_cap": 0,
            "budget_remaining": resolved_budget,
            "no_progress_streak": 0,
        },
        "last_state_hash": None,
    }
    if phases is not None:
        loop_state["phases"] = phases
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

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
              my_card_id, execution, verifier, phases):
    """Read the terminal result and decide.

    T1 path (no verifier_card in loop_state): stub-decide at the T1 hard cap.
    T2 path (verifier_card present): verdict-gated advance / replan / hard cap.
    Multi-phase (phases in loop_state with len > 1): DoD-met on a non-last
    phase advances to the next phase; DoD-met on the last phase completes the
    workflow.
    """
    if "verifier_card" not in loop_state:
        return _reinvoke_t1(kb, conn, root_id, loop_state, author, run_id,
                            my_card_id)
    return _reinvoke_verifier(kb, conn, root_id, loop_state, author, run_id,
                              my_card_id, execution, verifier)


def _reinvoke_t1(kb, conn, root_id, loop_state, author, run_id,
                 my_card_id=None):
    """T1: read the execution result and stub-decide at the hard cap of 1.

    In a multi-phase workflow (phases in loop_state with len > 1), advancing
    past the T1 hard cap on a non-last phase transitions to the next phase
    instead of terminating.
    """
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

    # Multi-phase T1: advance to the next phase if there is one.
    stored_phases = loop_state.get("phases")
    phase_index = int(loop_state.get("phase_index", 0))
    if (stored_phases and len(stored_phases) > 1
            and phase_index < len(stored_phases) - 1
            and my_card_id):
        return _advance_phase(kb, conn, root_id, loop_state, author, run_id,
                              my_card_id, stored_phases, phase_index + 1)

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

    T3 multi-phase: when loop_state carries a phases plan with len > 1, DoD-met
    on a non-last phase advances to the next phase (creates its sub-graph,
    advances phase_index, re-parks). DoD-met on the LAST phase completes the
    workflow.
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
        stored_phases = loop_state.get("phases")
        phase_index = int(loop_state.get("phase_index", 0))
        if stored_phases and len(stored_phases) > 1:
            if phase_index < len(stored_phases) - 1:
                # Advance to the next phase: create its sub-graph, re-park.
                return _advance_phase(
                    kb, conn, root_id, loop_state, author, run_id,
                    my_card_id, stored_phases, phase_index + 1,
                    iteration_counter, verdict,
                )
            # Last phase DoD-met -> workflow complete.
            return json.dumps({
                "status": "complete",
                "decision": "workflow_complete",
                "root_id": root_id,
                "phase_index": phase_index,
                "execution_card": exec_id,
                "verifier_card": verifier_id,
                "iteration": iteration_counter,
                "verdict": verdict,
                "message": (
                    f"Last phase {phase_index} DoD met on iteration "
                    f"{iteration_counter}; workflow complete."
                ),
            }, indent=2)
        # Single-phase (backward compat T2): phase complete.
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

    # ── T4: layered-exit counter tracking ────────────────────────────────────
    # Update no-progress streak + budget_remaining from this iteration's verdict
    # BEFORE deciding. These are deterministic, plugin-code guards — termination
    # must not depend on the model (SPEC §Termination is safety-critical).
    phase_index = int(loop_state.get("phase_index", 0))
    budget = loop_state.get("budget")  # None = no budget guard
    iteration_cost = int(loop_state.get("iteration_cost")
                         or DEFAULT_ITERATION_COST)
    threshold = int(loop_state.get("no_progress_threshold")
                    or DEFAULT_NO_PROGRESS_THRESHOLD)
    exit_counters = loop_state.get("exit_counters") or {}
    budget_remaining = exit_counters.get("budget_remaining")  # None or int
    last_state_hash = loop_state.get("last_state_hash")

    cur_hash = _state_hash(verdict)
    if cur_hash == last_state_hash:
        no_progress_streak = int(
            exit_counters.get("no_progress_streak", 0)) + 1
    else:
        # Current verdict is the first of a potential new run. A streak of N
        # means N consecutive iterations (including this one) produced the same
        # verdict — threshold=2 fires on the 2nd identical verdict in a row.
        no_progress_streak = 1
    exit_counters["no_progress_streak"] = no_progress_streak

    # Account for the iteration that just completed.
    if budget_remaining is not None:
        budget_remaining = budget_remaining - iteration_cost
        exit_counters["budget_remaining"] = budget_remaining

    loop_state["exit_counters"] = exit_counters
    loop_state["last_state_hash"] = cur_hash
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    # ── T4: layered exits (all route to the sticky HITL escalation) ──────────
    # Order: explicit verifier-escalate → budget → no-progress → hard cap.
    # A DoD-met advance already returned above (the success path is unchanged).

    # Escalate: the verifier explicitly asked for a human.
    if recommendation == "escalate":
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "verifier_escalate", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)

    # Budget exhausted: cannot afford another iteration.
    if budget_remaining is not None and budget_remaining <= 0:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "budget_exhausted", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)

    # No-progress: identical verdicts across the threshold streak.
    if no_progress_streak >= threshold:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "no_progress", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)

    # Hard cap: the deterministic backstop (replaces the old
    # status=complete/decision=hard_cap_reached with a sticky HITL block).
    if iteration_counter >= cap:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "hard_cap", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)

    # Replan while the iteration count is under the hard cap; the deterministic
    # caps above bound the loop even in stop-condition-optional / non-stop mode.
    replan_exec, replan_verifier = _resolve_phase_specs(
        loop_state, execution, verifier)
    return _replan(kb, conn, root_id, loop_state, author, run_id,
                   my_card_id, replan_exec, replan_verifier,
                   iteration_counter, cap, verdict)


def _resolve_phase_specs(loop_state, execution, verifier):
    """Return (execution_spec, verifier_spec) for the current phase.

    Multi-phase: read from loop_state['phases'][phase_index]. Single-phase:
    use the top-level execution/verifier passed to the handler.
    """
    stored_phases = loop_state.get("phases")
    if stored_phases is not None:
        phase_index = int(loop_state.get("phase_index", 0))
        current = stored_phases[phase_index]
        return current["execution"], current.get("verifier")
    return execution, verifier


def _advance_phase(kb, conn, root_id, loop_state, author, run_id,
                   my_card_id, phases, next_phase_index,
                   prev_iteration=None, prev_verdict=None):
    """Create the next phase's execution (+ optional verifier) sub-graph,
    advance phase_index, dependency-park the driver, return.

    Called from _reinvoke_verifier (T2 DoD-met) and _reinvoke_t1 (T1 hard cap)
    when the current phase is not the last in a multi-phase workflow.
    """
    next_phase = phases[next_phase_index]
    exec_spec = next_phase["execution"]
    verifier_spec = next_phase.get("verifier")
    phase_cap = next_phase.get("max_iterations")
    # T5: reuse the workflow's resolved runner (durable across phase advances).
    resolved_runner = loop_state.get("resolved_runner")

    exec_id = _create_execution_card(kb, conn, root_id, exec_spec, author,
                                     resolved_runner)

    if verifier_spec is None:
        # T1 phase within multi-phase: park on the execution card.
        loop_state["phase_index"] = next_phase_index
        loop_state["iteration_counter"] = 0
        loop_state["execution_card"] = exec_id
        loop_state["terminal_ids"] = [exec_id]
        loop_state.pop("verifier_card", None)
        _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

        state = _park_driver(kb, conn, my_card_id, exec_id, run_id)
        if state == "failed":
            logger.error("Dependency block failed for %s during phase advance "
                         "(run_id=%s)", my_card_id, run_id)
            return _park_failure(root_id, exec_id, None, exec_id, run_id)
        return json.dumps({
            "status": "blocked",
            "decision": "phase_advance",
            "phase_index": next_phase_index,
            "root_id": root_id,
            "execution_card": exec_id,
            "terminal_ids": [exec_id],
            "message": (
                f"Phase {next_phase_index - 1} complete; advanced to phase "
                f"{next_phase_index}/{len(phases) - 1}."
            ),
        }, indent=2)

    # T2 phase within multi-phase: create verifier card, park on it.
    verifier_id = _create_verifier_card(kb, conn, exec_id, verifier_spec,
                                        author, resolved_runner)
    cap = phase_cap or DEFAULT_MAX_ITERATIONS

    loop_state["phase_index"] = next_phase_index
    loop_state["iteration_counter"] = 1
    loop_state["execution_card"] = exec_id
    loop_state["verifier_card"] = verifier_id
    loop_state["terminal_ids"] = [verifier_id]
    loop_state["max_iterations"] = cap
    # T4: reset per-phase no-progress tracking for the new phase (budget is
    # workflow-wide and carries over via exit_counters.budget_remaining).
    ec = loop_state.get("exit_counters") or {}
    ec["no_progress_streak"] = 0
    loop_state["exit_counters"] = ec
    loop_state["last_state_hash"] = None
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, verifier_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s during phase advance "
                     "(run_id=%s)", my_card_id, run_id)
        return _park_failure(root_id, exec_id, verifier_id, verifier_id, run_id)
    return json.dumps({
        "status": "blocked",
        "decision": "phase_advance",
        "phase_index": next_phase_index,
        "root_id": root_id,
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "terminal_ids": [verifier_id],
        "iteration": 1,
        "max_iterations": cap,
        "message": (
            f"Phase {next_phase_index - 1} complete; advanced to phase "
            f"{next_phase_index}/{len(phases) - 1}."
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

    # T5: reuse the workflow's resolved runner (durable across replans).
    resolved_runner = loop_state.get("resolved_runner")
    exec_id = _create_execution_card(kb, conn, root_id, execution, author,
                                     resolved_runner)
    verifier_id = _create_verifier_card(kb, conn, exec_id, verifier, author,
                                        resolved_runner)

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
