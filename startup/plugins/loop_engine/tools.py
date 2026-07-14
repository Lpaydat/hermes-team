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
from typing import Optional

logger = logging.getLogger(__name__)

# v2 (T1): the citation primitive lives in the sibling schemas module (pure
# dataclasses + the open artifact_type enum). No cycle — schemas never imports
# tools — so this is safe at module load.
from . import schemas as _schemas

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

# T6: durability — bound on consecutive stale/missing-verdict re-evaluations. A
# persistent optimistic-lock drop (verifier runs keep completing without writing
# a dod_verdict) would otherwise loop unbounded on re-evaluations, since each
# reeval does NOT advance iteration_counter (so the hard cap does not bound it).
# Reaching the cap escalates to HITL (deterministic termination, SPEC
# §Termination is safety-critical, therefore deterministic).
MAX_REEVAL_ATTEMPTS = 3

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


def _resolve_root(kb, conn, loop_id):
    """Return ``loop_id`` if it resolves to an existing card, else None (T6/B7).

    The durable identity of a loop is ``root_id`` (the root card's task id), NOT
    the goal hash. When a caller supplies ``loop_id`` (aliased to ``root_id``),
    the engine trusts it as the root pin and opens that card directly — no
    ``goal_hash`` derivation, no goal-byte sensitivity (the defect-#5 class,
    hermes-teams-5w9). A handle that does not resolve (stale/garbage) is NEVER
    trusted; the caller falls back to the goal_hash bootstrap path and a
    ``loop_id_mismatch`` event is logged. loop_state itself is unaffected — it
    lives as blackboard comments ON root_id, so pinning the root pins the state.
    """
    if not loop_id:
        return None
    try:
        task = kb.get_task(conn, loop_id)
    except Exception:  # kernel without the card / lookup error -> unresolved
        return None
    if task is None:
        return None
    if not getattr(task, "id", None):
        return None
    return loop_id


def _card_idempotency_key(my_card_id, phase_index, iteration, role):
    """Intent-stable dedup key for a phase card (execution or verifier).

    T6. Stable across re-drives of the SAME (driver, phase, iteration, role), so
    a crash-replay that re-enters card creation dedups against cards already
    created that iteration (SPEC §Constraints respected — idempotency is a
    pre-check with NO unique index; we design for dedup-by-intent, not locking).
    The key is distinct on every axis:

      * driver  — two workflows on one board never collide
      * phase   — a phase-0 exec card is never confused with a phase-1 one
      * iter    — a replan (iter N+1) mints fresh cards, distinct from iter N
      * role    — exec vs verify vs a reeval attempt are distinct

    This extends the root's goal_hash stability (T4) to the phase cards, so the
    whole topology is recoverable across a reclaimed/crashed driver. Different
    iterations yield different keys (so replan still mints fresh cards); only a
    RE-drive of the SAME intent dedups.
    """
    return f"loop:{my_card_id}:phase{phase_index}:iter{iteration}:{role}"


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


def _validate_phases(phases, strict_dod=False, strict_fact_basis=False):
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
            # T4: metric_type/battery live on the verifier spec; a proxy
            # verifier without a well-formed battery is a validation error.
            # T9 strict_fact_basis (workflow-wide OR per-verifier; mirrors
            # strict_dod below): an absent metric_type hard-fails when opted in.
            pver_sfb = (bool(strict_fact_basis)
                        or bool(pver.get("strict_fact_basis")))
            err = _validate_metric_type(pver, f"phases[{i}].verifier",
                                        strict_fact_basis=pver_sfb)
            if err:
                return err
            # T8: DoD-checkability linter (input-side, symmetric to
            # _validate_dod_artifact). strict_dod is workflow-wide OR
            # per-verifier; a WARN is non-blocking (compat tier — the loop
            # proceeds), so it never masks a later phase's hard error.
            pver_strict = bool(strict_dod) or bool(pver.get("strict_dod"))
            sig = _validate_dod_signals(
                pver, f"phases[{i}].verifier",
                strict_dod=pver_strict, phase_index=i)
            if sig is not None and sig.get("severity") != "warn":
                return sig
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


def _validate_discover(discover):
    """B3/SPEC §2: validate the optional discover phase-0 config.

    Shape: ``{assignee?, dod, max_iterations?}``. The consumer configures the
    grounding phase; the engine runs it as phase 0 before ``phases[0]``.

      * ``dod`` (REQUIRED, non-empty string) — the grounding definition-of-done;
        becomes the discover worker's instructions (card body).
      * ``assignee`` (OPTIONAL) — the grounding-worker profile; defaults to the
        resolved runner (configured -> worker -> default).
      * ``max_iterations`` (OPTIONAL, positive int) — caps the discover loop;
        defaults to DEFAULT_MAX_ITERATIONS.

    Ambiguity 2 (Round-0 absorption): discover has its OWN ``{assignee, dod,
    max_iterations}``; the discover WORKER (the configured assignee) performs
    whatever grounding the dod specifies. The engine does NOT hardcode debugger
    Round-0 ops (doctrine-read/worktree/ledger) — "absorbs Round-0" is realized
    when B10 (debug-loop skill) configures discover's assignee/dod to subsume
    the old Round-0. Returns an error string or None (house-style seam).
    """
    if not isinstance(discover, dict):
        return "discover must be an object {assignee?, dod, max_iterations?}"
    dod = discover.get("dod")
    if not isinstance(dod, str) or not dod.strip():
        return ("discover.dod is required and must be a non-empty string "
                "(the grounding definition-of-done the discover worker runs)")
    err = _validate_optional_assignee(discover.get("assignee"),
                                      "discover.assignee")
    if err:
        return err
    dmax = discover.get("max_iterations")
    if dmax is not None:
        if isinstance(dmax, bool) or not isinstance(dmax, int) or dmax < 1:
            return "discover.max_iterations must be a positive integer"
    return None


def _validate_metric_type(verifier, label, strict_fact_basis=False):
    """T4: validate a verifier spec's ``metric_type`` + ``battery``.

    ``metric_type`` is a VERIFIER-SPEC field (parallel to assignee/title/body),
    NOT a ``dod_verdict`` field — the verdict is the RESULT, metric_type is the
    SPEC. The consumer declares which kind of metric gates this phase:

      * ``ground_truth`` — the DoD is a mechanical check (test pass/fail, grep
        match, count==N, exit code). Infallible keep/discard; NO battery needed.
      * ``proxy`` — the DoD is a judgment (LLM-rubric, human-rating, "is X
        good"). Gameable, so a held-out ``battery`` spec is MANDATORY.
        Proxy-without-battery is the exact overfitting failure autoresearch
        warns about (the loop would report success while gameable); the engine
        REFUSES to run such a verifier.

    ``battery`` shape (validated here, RUN by B6): ``{path: <str>, runner:
    <profile>}`` alongside ``metric_type: proxy``.

    Default-compat (zero-regression; see SPEC §7 / T9 + bd hermes-teams-s54):
    an ABSENT ``metric_type`` is accepted unchanged — the proxy->battery rule
    fires ONLY when ``proxy`` is EXPLICITLY declared.

    T9 ``strict_fact_basis`` opt-in (bd hermes-teams-3g2; mirrors ``strict_dod``
    in :func:`_validate_dod_signals`): when a consumer opts a phase in
    (workflow-wide OR per-verifier — see :func:`_validate` /
    :func:`_validate_phases`), an ABSENT ``metric_type`` becomes a VALIDATION
    ERROR — the loop REFUSES to run (the phase must declare its metric kind).
    Default ``False`` = today's additive behavior (absent = accepted, treated
    ``ground_truth``); the hard cutover is per-consumer at its coupled release.
    Returns an error string or ``None`` (house-style error-or-None seam).
    """
    mt = verifier.get("metric_type")
    if mt is None:
        if strict_fact_basis:
            return (f"{label}.metric_type is required under strict_fact_basis: "
                    f"declare 'ground_truth' or 'proxy' (got none) — a phase "
                    f"opted into the fact-basis must state its metric kind")
        return None  # default-compat: undeclared -> accepted (ground_truth).
    if mt not in ("ground_truth", "proxy"):
        return (f"{label}.metric_type must be 'ground_truth' or 'proxy' "
                f"(got {mt!r})")
    if mt == "ground_truth":
        return None  # mechanical checks need no held-out battery.
    # proxy -> held-out battery MANDATORY.
    battery = verifier.get("battery")
    if not isinstance(battery, dict):
        return (f"{label}.battery is required for metric_type='proxy' "
                f"(proxy metrics are gameable; a held-out battery is "
                f"mandatory — proxy-without-battery is the overfitting "
                f"failure the loop refuses to run)")
    path = battery.get("path")
    runner = battery.get("runner")
    if (not isinstance(path, str) or not path.strip()
            or not isinstance(runner, str) or not runner.strip()):
        return (f"{label}.battery must be a non-empty object with 'path' "
                f"(str) and 'runner' (profile); got path={path!r}, "
                f"runner={runner!r}")
    return None


# ── T8 (bd hermes-teams-cqv): INPUT-side DoD-checkability linter ──────────────
#
# Symmetric to the OUTPUT-side _validate_dod_artifact gate (which lints a
# verdict's artifact at decide-time). This lints the DoD DECLARATION at call
# time, before any card is created — a DoD that can't be measured ("the design
# is good") is flagged before the loop wastes cycles. THE CHECKABILITY RULE: a
# checkable DoD declares >=1 measurable DoDSignal{artifact_type, locator,
# expectation?} (artifact_type reuses the T1 open enum + 'count'). Pure-prose
# DoDs are WARNED in compat (default; loop proceeds — zero-regression) and
# HARD-FAILED when strict_dod is opted in. Present-but-malformed signals always
# hard-fail (the consumer opted into structure by providing the key).


# T8: 'count' — a numeric threshold/occurrence measurable (e.g. "0 matches",
# "p95 < 200ms") — is a cross-domain DoD signal type every consumer uses.
# Register it via the OPEN-enum extension path B2 designed
# (register_artifact_type) rather than mutating the seed contract: B2's tests
# pin SEED_ARTIFACT_TYPES to the 8 cross-domain locators, so the extension
# registry is the zero-regression way to make 'count' known. Idempotent (a set).
_schemas.register_artifact_type("count")


# The verifier-relative shape a checkable DoD's signals must take — referenced
# by every structured error this linter emits.
_DOD_SIGNAL_EXPECTED = (
    "a non-empty array of DoDSignal{artifact_type, locator, expectation?} "
    "(artifact_type in the T1 enum or 'count'; locator a non-empty string; "
    "expectation an optional non-empty string)")


def _got(value):
    """Short machine-readable description of a received value for the
    structured-error ``got`` field (a type name for non-literals)."""
    return type(value).__name__


def _validation_error(summary, field, expected, got, hint,
                      phase_index=None, severity="error"):
    """T8: build a structured validation-error object.

    ADDITIVE to the flat ``{"error": str}`` contract: the returned dict carries
    BOTH a flat ``error`` string (``summary`` — one line, back-compat so nothing
    that parses the flat shape today breaks) AND a structured ``validation``
    block ``{phase_index, field, expected, got, hint}`` so the driver
    self-corrects on retry. ``severity`` is ``"error"`` (reject) or ``"warn"``
    (advisory; the loop proceeds — the compat tier for pure-prose DoDs).

    The wiring (``_validate`` / ``_validate_phases``) REJECTS on ``"error"`` and
    PROCEEDS on ``"warn"`` (non-blocking); the handler gate emits the dict as-is
    for a rejection (so the response keeps the flat ``error`` AND gains the
    ``validation`` block).
    """
    return {
        "severity": severity,
        "error": summary,
        "validation": {
            "phase_index": phase_index,
            "field": field,
            "expected": expected,
            "got": got,
            "hint": hint,
        },
    }


def _validate_dod_signals(verifier, label, strict_dod=False, phase_index=None):
    """T8: lint a verifier spec's DoD for checkability (the input-side gate).

    Returns ``None`` when the DoD is checkable (well-formed ``dod_signals``);
    otherwise a structured dict (``_validation_error``) with ``severity`` either
    ``"warn"`` (compat — pure-prose DoD with no signals; loop proceeds) or
    ``"error"`` (strict pure-prose, OR present-but-malformed signals; rejected).

    Check order per cqv: (1) ``dod_signals`` absent -> compat warn / strict
    hard-fail (zero-regression default); (2) present but not a non-empty array
    -> hard-fail (opted into structure); (3) each signal: ``artifact_type`` in
    the T1 open enum (+ 'count'), ``locator`` non-empty, ``expectation`` (if
    present) a non-empty string; (4) well-formed -> pass. DoD prose stays in
    ``verifier.body`` (required, unchanged); signals live in the new
    ``verifier.dod_signals`` field.

    ``label`` is the full JSON path to the verifier (``"verifier"`` single-phase
    or ``"phases[i].verifier"`` multi-phase) used in the flat ``error`` summary;
    ``phase_index`` (None single-phase, int multi-phase) is carried in the
    structured ``validation`` block.
    """
    signals = verifier.get("dod_signals")
    if signals is None:
        # absent: compat (warn, proceed) / strict (hard-fail). Zero-regression
        # default — existing v1 prose-DoD consumers warn but still run.
        if strict_dod:
            return _validation_error(
                summary=(f"{label}.dod_signals is required under strict_dod: "
                         f"a checkable DoD must declare >=1 measurable signal "
                         f"(got none)"),
                field="verifier.dod_signals",
                expected=_DOD_SIGNAL_EXPECTED, got="absent",
                hint='Declare >=1 DoDSignal, e.g. {"artifact_type":"test_output",'
                     '"locator":"pytest -q"}. Bare prose is not checkable.',
                phase_index=phase_index, severity="error")
        return _validation_error(
            summary=(f"{label}.dod_signals absent: DoD is not machine-checkable "
                     f"(compat: accepted; strict_dod would reject)"),
            field="verifier.dod_signals",
            expected=_DOD_SIGNAL_EXPECTED, got="absent",
            hint="Declare >=1 DoDSignal so the DoD is verifier-re-openable; "
                 "bare prose is accepted in compat but not measurable.",
            phase_index=phase_index, severity="warn")
    # present -> must be well-formed (hard-fail always; the consumer opted into
    # structure by providing the key).
    if not isinstance(signals, list):
        return _validation_error(
            summary=(f"{label}.dod_signals must be a non-empty array "
                     f"(got {_got(signals)})"),
            field="verifier.dod_signals",
            expected=_DOD_SIGNAL_EXPECTED, got=_got(signals),
            hint="Provide a non-empty array of DoDSignal objects.",
            phase_index=phase_index, severity="error")
    if len(signals) == 0:
        return _validation_error(
            summary=(f"{label}.dod_signals is empty: a checkable DoD must "
                     f"declare >=1 measurable signal (got 0)"),
            field="verifier.dod_signals",
            expected=_DOD_SIGNAL_EXPECTED, got="[]",
            hint='Add a signal, e.g. {"artifact_type":"test_output",'
                 '"locator":"pytest -q"}. Bare judgment is not checkable.',
            phase_index=phase_index, severity="error")
    known = _schemas.known_artifact_types()
    for j, sig in enumerate(signals):
        sfield = f"verifier.dod_signals[{j}]"
        slabel = f"{label}.dod_signals[{j}]"
        if not isinstance(sig, dict):
            return _validation_error(
                summary=f"{slabel} must be an object (got {_got(sig)})",
                field=sfield, expected="a DoDSignal object", got=_got(sig),
                hint="Each signal is {artifact_type, locator, expectation?}.",
                phase_index=phase_index, severity="error")
        atype = sig.get("artifact_type")
        if not isinstance(atype, str) or not atype.strip():
            return _validation_error(
                summary=(f"{slabel}.artifact_type is required (a T1 enum "
                         f"member or 'count')"),
                field=f"{sfield}.artifact_type",
                expected="one of: " + ", ".join(sorted(known)),
                got=atype,
                hint='e.g. "test_output", "file_line", "grep_result", "count".',
                phase_index=phase_index, severity="error")
        if atype not in known:
            return _validation_error(
                summary=(f"{slabel}.artifact_type {atype!r} is not a known "
                         f"type"),
                field=f"{sfield}.artifact_type",
                expected="one of: " + ", ".join(sorted(known)),
                got=atype,
                hint="Use a seed type, or register a domain type via "
                     "schemas.register_artifact_type().",
                phase_index=phase_index, severity="error")
        locator = sig.get("locator")
        if not isinstance(locator, str) or not locator.strip():
            return _validation_error(
                summary=(f"{slabel}.locator is required (where the signal is "
                         f"measured)"),
                field=f"{sfield}.locator",
                expected="a non-empty string (the machine address)",
                got=locator,
                hint='e.g. "pytest -q", "src/calc.py:10", "grep -c TODO src/".',
                phase_index=phase_index, severity="error")
        expectation = sig.get("expectation")
        if (expectation is not None and (not isinstance(expectation, str)
                or not expectation.strip())):
            return _validation_error(
                summary=(f"{slabel}.expectation, when present, must be a "
                         f"non-empty string"),
                field=f"{sfield}.expectation",
                expected="a non-empty string (the pass criterion), or omitted",
                got=expectation,
                hint='e.g. "passes", "0 matches", "p95 < 200ms".',
                phase_index=phase_index, severity="error")
    return None


def _validate(args):
    # B3/SPEC §2: goal is polymorphic — a non-empty string (v1, bare goal) OR a
    # non-empty array of Claim dicts (the structural fast-pass form: a goal that
    # arrives already-cited skips the discover worker). A [Claim] goal carrying
    # an un-cited material claim is rejected here (it must be grounded to fast-
    # pass). String goals (the 192-test baseline) are accepted byte-for-byte.
    goal = args.get("goal")
    if isinstance(goal, str):
        if not goal.strip():
            return ("goal is required and must be a non-empty string or a "
                    "non-empty array of Claim dicts")
    elif isinstance(goal, list):
        if len(goal) < 1:
            return "goal array must be a non-empty array of Claim dicts"
        for i, claim in enumerate(goal):
            err = validate_claim(claim)
            if err:
                return f"goal[{i}]: {err}"
    else:
        return ("goal is required (a non-empty string, or a non-empty array "
                "of Claim dicts for the structural fast-pass)")
    # T5: optional workflow runner profile (defaults to worker -> default).
    runner = args.get("runner")
    if runner is not None:
        if not isinstance(runner, str) or not runner.strip():
            return ("runner must be a non-empty string (the profile that "
                    "drives the loop)")
    # B3/SPEC §2: optional discover phase-0 config {assignee?, dod,
    # max_iterations?}. When present, the engine runs discover before phases[0].
    discover = args.get("discover")
    if discover is not None:
        err = _validate_discover(discover)
        if err:
            return err
    phases = args.get("phases")
    if phases is not None:
        return _validate_phases(phases, strict_dod=args.get("strict_dod"),
                                strict_fact_basis=args.get("strict_fact_basis"))
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
        # T4: metric_type/battery live on the verifier spec; a proxy verifier
        # without a well-formed battery is a validation error.
        # T9 strict_fact_basis (workflow-wide OR per-verifier; mirrors the
        # strict_dod thread just below): absent metric_type hard-fails when in.
        v_sfb = (bool(args.get("strict_fact_basis"))
                 or bool(verifier.get("strict_fact_basis")))
        err = _validate_metric_type(verifier, "verifier",
                                    strict_fact_basis=v_sfb)
        if err:
            return err
        # T8: DoD-checkability linter (input-side, symmetric to
        # _validate_dod_artifact). strict_dod is workflow-wide OR per-verifier;
        # a WARN is non-blocking (compat tier — the loop proceeds).
        v_strict = bool(args.get("strict_dod")) or bool(verifier.get("strict_dod"))
        sig = _validate_dod_signals(verifier, "verifier",
                                    strict_dod=v_strict, phase_index=None)
        if sig is not None and sig.get("severity") != "warn":
            return sig
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


# ── v2: citation structure-validators (T1, bd hermes-teams-4gm) ───────────────
#
# PUBLIC building blocks that later beads CALL: B3 (discover), B4 (evidence-
# evaluator), B9 (DoD-linter). The engine enforces STRUCTURE only — the
# independent verifier card re-opens each citation (reads file:line, re-runs the
# probe, checks the sha) per the existing independent-verifier trust model.
#
# These validators accept plain dicts — the on-the-wire shape the board and
# run.metadata JSON yield (matching _validate / _validate_dod_artifact). They
# return an error string (None == valid) so a caller can route the structured
# failure into replan / a structured-error response. Wiring the hard-fail into
# the discover flow (B3) / the dod_verdict evidence gate (B4) is THOSE beads'
# job; this primitive only raises the structured error.


def validate_citation(data) -> Optional[str]:
    """Validate the STRUCTURE of a Citation dict (T1).

    The engine's structure contract — it does NOT re-open the citation (that is
    the independent verifier card's job). Checks:

      * ``data`` is a dict;
      * ``artifact_type`` is a non-empty string in the OPEN enum
        (seed set ∪ registered extensions — see
        :func:`loop_engine.schemas.register_artifact_type`);
      * ``locator`` is a non-empty string (the machine address);
      * ``quote``, when present, is a non-empty string.

    Returns an error string naming the first violation, or None when valid.
    """
    if not isinstance(data, dict):
        return "citation must be an object"
    atype = data.get("artifact_type")
    if not isinstance(atype, str) or not atype.strip():
        return ("citation.artifact_type is required and must be a "
                "non-empty string")
    if atype not in _schemas.known_artifact_types():
        return (f"citation.artifact_type {atype!r} is not a known type; "
                f"register it via schemas.register_artifact_type() to extend "
                f"the open enum")
    locator = data.get("locator")
    if not isinstance(locator, str) or not locator.strip():
        return ("citation.locator is required and must be a non-empty string "
                "(the machine address)")
    quote = data.get("quote")
    if quote is not None and (not isinstance(quote, str) or not quote.strip()):
        return ("citation.quote, when present, must be a non-empty string "
                "(the exact snippet asserted)")
    return None


def validate_claim(data) -> Optional[str]:
    """Validate the STRUCTURE of a Claim dict (T1) — the hard-fail primitive.

    Checks:

      * ``data`` is a dict;
      * ``text`` is a non-empty string (the material assertion);
      * ``citations`` is a list of valid Citation dicts;
      * ``material`` (default True) is a boolean;
      * a MATERIAL claim MUST carry >=1 citation — an un-cited material claim is
        the HARD-FAIL case (this is what makes it a fact rather than a
        self-claim). A non-material claim may carry an empty citations list.

    Returns an error string naming the first violation, or None when valid.
    Wiring this error into replan is B3/B4's job; this primitive only raises it.
    """
    if not isinstance(data, dict):
        return "claim must be an object"
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return "claim.text is required and must be a non-empty string"
    citations = data.get("citations")
    if not isinstance(citations, list):
        return "claim.citations is required and must be a list"
    for i, cite in enumerate(citations):
        err = validate_citation(cite)
        if err:
            return f"claim.citations[{i}]: {err}"
    # material defaults True (fail-safe: a claim is material unless marked).
    material = data.get("material", True)
    if not isinstance(material, bool):
        return "claim.material, when present, must be a boolean"
    if material and len(citations) == 0:
        return ("claim is material but carries zero citations — a material "
                "assertion requires at least one citation (the hard-fail "
                "primitive: an un-cited material claim replans; mark the "
                "claim material=false if it is a non-load-bearing statement)")
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


def _validate_dod_artifact(verdict, artifact_required=False):
    """Mechanically validate the DoD artifact shape before trusting ``dod_met``.

    The verifier's ``dod_met`` is a self-report. When a phase opts in
    (``artifact_required=True`` on its verifier spec — e.g. design-council's
    converge phase), the engine independently asserts the defect-coverage
    artifact is complete and carries no unfixed latent defect, so a lenient or
    buggy verifier cannot advance a design with an open failure-implication.

    ``artifact_required`` is **opt-in** so the generic engine stays usable by
    consumers that return a simple ``{dod_met, gaps}`` verdict (debugging,
    research). When False (default), the gate validates the artifact ONLY if the
    verifier produced one; a verdict with no ``behaviors``/``defect_traces`` is
    artifact-neutral (defers to ``dod_met``).

    When ``artifact_required`` is True (or an artifact is present), returns True
    only when:

      - ``behaviors[]`` and ``defect_traces[]`` are both non-empty lists;
      - there is at least one trace per behavior (``len(traces) >= len(behaviors)``);
      - every trace has a non-empty ``citation``;
      - no trace is flagged ``fabricated`` (fabrication guard failed);
      - no trace is left at ``status == "latent_defect"``.
    """
    if not isinstance(verdict, dict):
        return False
    behaviors = verdict.get("behaviors")
    traces = verdict.get("defect_traces")
    # No artifact produced:
    #   - artifact_required=True -> FAIL (the converge verifier was lazy; it
    #     must produce behaviors+defect_traces, not advance on dod_met alone).
    #   - artifact_required=False -> neutral (generic/ADR-convention; defer to
    #     dod_met). This keeps the engine generic.
    if not behaviors and not traces:
        return not artifact_required
    if not isinstance(behaviors, list) or not isinstance(traces, list):
        return False
    if not behaviors or not traces:
        return False
    if len(traces) < len(behaviors):
        return False
    for tr in traces:
        if not isinstance(tr, dict):
            return False
        if not (tr.get("citation") or "").strip():
            return False
        if tr.get("fabricated"):
            return False
        if tr.get("status") == "latent_defect":
            return False
    return True


def _evidence_gate(verdict, strict_fact_basis=False):
    """T3: evaluate the evidence gate on a dod_verdict.

    The engine enforces STRUCTURE only (per T1's re-open contract): it CALLS
    :func:`validate_claim` (the B2 primitive) on each evidence Claim. The engine
    does NOT re-open files/run probes — that is the independent verifier card's
    job. Returns ``(ok, reason)`` where ``ok`` is True when the gate passes and
    ``reason`` is an optional human-readable string explaining a trip.

    ADDITIVE (backward-compat, s54 reconciliation): a verdict with NO
    ``evidence`` key passes the gate — a bare v1 verdict still constructs and
    evaluates without error. The gate fires only when a verdict actually
    CARRIES evidence claims. This makes the gate REAL on the verifier-returned
    path while keeping the v1 baseline green: "required" = the gate trips on
    un-cited material, NOT "the dict key must always be present".

    T9 ``strict_fact_basis`` opt-in (bd hermes-teams-3g2; mirrors
    ``strict_dod`` in :func:`_validate_dod_signals`): when a consumer opts a
    phase in, a verdict with NO ``evidence`` key TRIPS the gate — nothing
    advances on assertion; every material claim must be cited. Default
    ``False`` = today's additive behavior (a bare v1 verdict passes). Un-cited
    material trips ALWAYS (opt-in only tightens the missing-key case).

    Trips (returns ``ok=False``) when:
      * ``strict_fact_basis`` and ``evidence`` is absent (opt-in: nothing
        advances without cited evidence); OR
      * ``evidence`` is present and not a list (malformed); OR
      * any evidence Claim fails :func:`validate_claim` (e.g. a MATERIAL claim
        with zero citations — the hard-fail primitive that makes facts not
        self-claim).
    """
    if not isinstance(verdict, dict):
        return True, None
    evidence = verdict.get("evidence")
    if evidence is None:
        if strict_fact_basis:
            return (False, "evidence is required under strict_fact_basis: the "
                    "verdict must cite >=1 Claim (got none) — nothing advances "
                    "on assertion")
        return True, None  # additive: bare v1 verdict passes
    if not isinstance(evidence, list):
        return False, "evidence must be a list of Claim objects"
    for i, claim in enumerate(evidence):
        err = validate_claim(claim)
        if err:
            return False, f"evidence[{i}]: {err}"
    return True, None


def _apply_evidence_gate(verdict, strict_fact_basis=False):
    """T3: evidence GATES ``dod_met`` (the integration — the core of B4).

    Returns the verdict with ``dod_met`` (and ``recommendation``) corrected when
    the evidence gate trips; returns the verdict unchanged when the
    gate passes (and for a missing/None verdict). The original verdict dict is
    NOT mutated — a corrected copy is returned so the verifier's self-report
    record is preserved while the engine routes on the gated view.

    A "done" verdict with an un-cited material claim does NOT advance: the gate
    forces ``dod_met=False`` and ``recommendation="replan"``. This is what makes
    ``dod_met`` mean "DoD met AND every material claim cited", not a self-claim.
    ONE advance/replan signal — evidence is baked INTO dod_met, not a parallel
    dimension (score stays DoD-quality / informational, not routed on).

    T9 ``strict_fact_basis`` (bd hermes-teams-3g2): when a consumer opts a phase
    in, a verdict WITHOUT an ``evidence`` key also trips — ``dod_met`` is forced
    ``False`` (hard-fail -> replan). Default ``False`` = today's additive path
    (a bare v1 verdict passes unchanged). Threaded from ``loop_state`` at the
    decide-time call sites (the flag persists from the first invocation).
    """
    ok, reason = _evidence_gate(verdict, strict_fact_basis=strict_fact_basis)
    if ok or verdict is None:
        return verdict
    corrected = dict(verdict)
    corrected["dod_met"] = False
    corrected["recommendation"] = "replan"
    # Surface the gate reason so replan workers can target the un-cited claim
    # (informational; does not affect routing — dod_met=false already replans).
    corrected["evidence_gate"] = reason
    return corrected


def _persist_council_state(kb, conn, root_id, author, verdict):
    """Persist the latest council iteration to the root blackboard.

    The verifier is a grandchild (root -> exec -> verifier) and cannot reach the
    root blackboard, so the DRIVER (which holds ``root_id``) writes the verdict
    downstream where converge-execution + replan workers can read it:

      ``council:last_iteration`` = {dod_verdict, design_version_ref, gaps, score}
      ``council:best_so_far``    = the highest-scoring iteration's snapshot

    This is what makes keep/discard (replan from best-so-far on regression) and
    replan-learning (read the last gaps) reachable by the next execution worker.
    No-op when ``verdict`` is not a dict (missing/stale verdict path).
    """
    if not isinstance(verdict, dict):
        return
    snapshot = {
        "dod_verdict": verdict,
        "dod_met": verdict.get("dod_met"),
        "recommendation": verdict.get("recommendation"),
        "design_version_ref": verdict.get("design_version_ref"),
        "gaps": verdict.get("gaps"),
        "score": verdict.get("score"),
    }
    _write_blackboard(kb, conn, root_id, author,
                      "council:last_iteration", snapshot)
    score = verdict.get("score")
    if isinstance(score, (int, float)):
        prev = _read_blackboard(kb, conn, root_id, "council:best_so_far")
        prev_score = prev.get("score") if isinstance(prev, dict) else None
        if not isinstance(prev_score, (int, float)) or score > prev_score:
            _write_blackboard(kb, conn, root_id, author,
                              "council:best_so_far", snapshot)


def _loop_protocol_footer(root_id):
    """Body footer injected into execution + verifier cards so any worker can
    read the shared root blackboard (the verifier is a grandchild and otherwise
    has no root pointer)."""
    return (
        f"\n\n## Loop protocol\n"
        f"- Shared blackboard / root card: `{root_id}`\n"
        f"- Read `council:last_iteration` + `council:best_so_far` + "
        f"`council:po_interview` (when present) via kanban_show on the root "
        f"card (last-write-wins blackboard comments).\n"
    )


def _create_execution_card(kb, conn, root_id, execution, author,
                           resolved_runner, my_card_id=None,
                           phase_index=0, iteration=0):
    """Execution card parented on the root (ready immediately; the root is
    completed first). Shared by the first invocation and every replan.

    T5: the card's assignee is :func:`_resolve_assignee` — an explicit
    ``execution["assignee"]`` wins; otherwise the resolved runner is used.

    T6: the card carries an intent-stable idempotency key
    (:func:`_card_idempotency_key`) so a crash-replay that re-enters card
    creation for the SAME (driver, phase, iteration) dedups against the card
    already created that iteration (no duplicate phase cards on re-drive).
    """
    skills = [execution["skill"]] if execution.get("skill") else None
    idem = None
    if my_card_id is not None:
        idem = _card_idempotency_key(my_card_id, phase_index, iteration, "exec")
    return kb.create_task(
        conn,
        title=execution["title"],
        body=execution["body"] + _loop_protocol_footer(root_id),
        assignee=_resolve_assignee(execution, resolved_runner),
        created_by=author,
        parents=[root_id],
        skills=skills,
        idempotency_key=idem,
    )


def _create_verifier_card(kb, conn, exec_id, verifier, author,
                          resolved_runner, my_card_id=None, phase_index=0,
                          iteration=0, role="verify", root_id=None):
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

    T6: the card carries an intent-stable idempotency key (role defaults to
    ``"verify"``; re-evaluations pass ``"reeval{N}"`` so each reeval attempt is
    distinct while a re-drive of the SAME attempt dedups).
    """
    skills = [verifier["skill"]] if verifier.get("skill") else None
    idem = None
    if my_card_id is not None:
        idem = _card_idempotency_key(my_card_id, phase_index, iteration, role)
    body = verifier["body"]
    if root_id:
        body = body + _loop_protocol_footer(root_id)
    return kb.create_task(
        conn,
        title=verifier["title"],
        body=body,
        assignee=_resolve_assignee(verifier, resolved_runner),
        created_by=author,
        parents=[exec_id],
        skills=skills,
        idempotency_key=idem,
    )


# ── T5/B6: held-out battery card (terminal independent gate) ───────────────────


def _has_battery(verifier_spec):
    """T5/B6: does this per-phase verifier spec carry a held-out battery?

    A battery materializes ONLY when the verifier declares
    ``metric_type='proxy'`` AND a well-formed ``battery:{path, runner}`` dict
    (B5's :func:`_validate_metric_type` validates this shape on the way in).
    Ground-truth verifiers and v1 verifiers (no ``metric_type``) return False ->
    no battery card -> no behavior change (the 204 baseline is structural).
    """
    if not isinstance(verifier_spec, dict):
        return False
    return (verifier_spec.get("metric_type") == "proxy"
            and isinstance(verifier_spec.get("battery"), dict))


def _create_battery_card(kb, conn, exec_id, verifier_spec, author,
                         my_card_id=None, phase_index=0, iteration=0,
                         root_id=None):
    """T5/B6: the held-out battery card — a SEPARATE independent verifier card
    dispatched to the battery spec's ``runner`` profile.

    Like :func:`_create_verifier_card` but:

      * ``assignee`` = ``battery.runner`` (INDEPENDENCE is load-bearing — the
        battery never runs as the phase exec agent or the improving agent; this is
        what makes the held-out check hard to game: autoresearch "independent
        evaluator, not the agent that produced the artifact", design-council
        "independently re-graded");
      * parented on the execution card (so ``build_worker_context`` injects the
        phase output the battery must re-grade — same reasoning as the verifier);
      * intent-stable idempotency key with role=``"battery"`` (distinct from
        exec/verify, so a re-drive of the SAME (phase, iteration) dedups while a
        later iteration mints a fresh battery card).

    The battery card is itself a verifier: it reads the disjoint battery artifact
    at ``battery.path``, runs the held-out checks, and completes with its own
    evidence-cited ``dod_verdict`` (B4/T3) in ``run.metadata``.
    """
    battery = verifier_spec["battery"]
    runner = battery["runner"]
    battery_path = battery.get("path")
    idem = None
    if my_card_id is not None:
        idem = _card_idempotency_key(
            my_card_id, phase_index, iteration, "battery")
    body = (
        "## Held-out battery evaluation (terminal independent gate)\n\n"
        f"Read the disjoint battery artifact and run its held-out checks: "
        f"`{battery_path}`\n\n"
        "Re-grade the phase output (injected from the execution card) "
        "INDEPENDENTLY against the held-out battery. Do NOT consult the prior "
        "verifier's verdict — grade the artifact fresh. Complete with a "
        "`dod_verdict` in run.metadata (`{dod_met, gaps, recommendation, "
        "evidence}`); every material claim must carry its citation."
    )
    if root_id:
        body = body + _loop_protocol_footer(root_id)
    return kb.create_task(
        conn,
        title=f"battery: held-out check — {battery_path}",
        body=body,
        assignee=runner,
        created_by=author,
        parents=[exec_id],
        idempotency_key=idem,
    )


def _dispatch_battery(kb, conn, root_id, loop_state, author, run_id,
                      my_card_id, verifier_spec, exec_id, verifier_id,
                      iteration_counter):
    """T5/B6: the per-phase verifier passed (proxy DoD met) on a proxy phase —
    dispatch the independent held-out battery card and dependency-park the driver
    on it.

    The battery is an ADDITIONAL TERMINAL gate; the actual advance (or
    replan-on-battery-fail) happens in :func:`_reinvoke_battery` once the battery
    returns its own evidence-cited ``dod_verdict``. Records
    ``battery_state='pending'`` + the battery card id in loop_state so the
    re-invoke routes to :func:`_reinvoke_battery` (the battery is the new terminal
    the driver parked on).
    """
    phase_index = int(loop_state.get("phase_index", 0))
    battery_id = _create_battery_card(
        kb, conn, exec_id, verifier_spec, author,
        my_card_id=my_card_id, phase_index=phase_index,
        iteration=iteration_counter, root_id=root_id)

    loop_state["battery_card"] = battery_id
    loop_state["battery_state"] = "pending"
    loop_state["battery"] = verifier_spec.get("battery")
    loop_state["terminal_ids"] = [battery_id]
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, battery_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s during battery dispatch "
                     "(run_id=%s)", my_card_id, run_id)
        return _park_failure(root_id, exec_id, verifier_id, battery_id, run_id)
    return json.dumps({
        "status": "blocked",
        "decision": "battery_dispatch",
        "root_id": root_id,
        "phase_index": phase_index,
        "battery_state": "pending",
        "battery_card": battery_id,
        "execution_card": exec_id,
        "verifier_card": verifier_id,
        "terminal_ids": [battery_id],
        "iteration": iteration_counter,
        "message": (
            "Per-phase verifier passed (proxy DoD met); dispatching the "
            "independent held-out battery card as a terminal gate. The phase "
            "advances only if BOTH the verifier AND the battery pass."
        ),
    }, indent=2)


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


# ── T6: durability — re-park + re-evaluate (crash-resume reconciliation) ──────


def _repark_existing(kb, conn, root_id, loop_state, author, run_id,
                     my_card_id, terminal_id, terminal_ids, phase_index,
                     execution_card=None, verifier_card=None):
    """Re-park the driver on an EXISTING in-flight terminal.

    T6 partial-topology reconciliation. Reached when a re-drive finds the
    terminal NOT yet ``done`` — the driver was reclaimed/crashed BETWEEN
    creating the iteration's cards and parking (or re-promoted prematurely). The
    in-flight iteration's topology already exists; the right move is to
    RE-ESTABLISH the dependency barrier on the existing terminal, not read a
    phantom verdict or create duplicate cards.

    Records a ``loop_repark`` event so observers can see the recovery, then
    dependency-parks the driver on the existing terminal and returns
    status=blocked, decision=repark.
    """
    kb._append_event(
        conn, my_card_id, "loop_repark",
        {
            "phase_index": phase_index,
            "terminal_id": terminal_id,
            "root_id": root_id,
            "reason": "in_flight_terminal_not_done",
        },
        run_id=run_id,
    )
    state = _park_driver(kb, conn, my_card_id, terminal_id, run_id)
    if state == "failed":
        logger.error("Re-park block failed for %s (run_id=%s)",
                     my_card_id, run_id)
        return _park_failure(root_id, execution_card, verifier_card,
                             terminal_id, run_id)
    body = {
        "status": "blocked",
        "decision": "repark",
        "root_id": root_id,
        "terminal_ids": terminal_ids,
        "phase_index": phase_index,
        "message": (
            "Re-drive found the in-flight terminal not yet complete (crash "
            "between create-cards and park, or premature re-promotion). "
            "Re-established the dependency barrier on the existing terminal; "
            "no duplicate cards created. The driver auto-promotes when the "
            "terminal completes."
        ),
    }
    if execution_card is not None:
        body["execution_card"] = execution_card
    if verifier_card is not None:
        body["verifier_card"] = verifier_card
    return json.dumps(body, indent=2)


def _reevaluate(kb, conn, root_id, loop_state, author, run_id, my_card_id,
                exec_id, old_verifier_id, verifier_spec, phase_index,
                iteration_counter):
    """Dispatch a FRESH verifier for the same iteration and re-park.

    T6 stale/missing-verdict detection. Reached when the terminal verifier IS
    ``done`` but produced NO structured ``dod_verdict`` — the completion was
    dropped/stale (optimistic-lock drop, run reclaimed mid-verdict). Acting on
    that as a verdict would phantom-advance or replan on empty evidence; instead
    the engine RE-EVALUATES: a fresh verifier card (parented on the done exec
    card) re-checks the phase output.

    Bounded by :data:`MAX_REEVAL_ATTEMPTS` — a persistent dropper escalates to
    HITL (``stale_verdict``) rather than looping forever (deterministic
    termination). The fresh verifier carries an intent-stable ``reeval{N}`` key
    so a re-drive of the SAME reeval attempt dedups while a new attempt is
    distinct.
    """
    reeval_counter = int(loop_state.get("reeval_counter") or 0)
    if reeval_counter >= MAX_REEVAL_ATTEMPTS:
        return _escalate(
            kb, conn, root_id, loop_state, author, run_id, my_card_id,
            "stale_verdict", phase_index, iteration_counter,
            verdict=None,
        )

    resolved_runner = loop_state.get("resolved_runner")
    reeval_counter += 1
    new_verifier_id = _create_verifier_card(
        kb, conn, exec_id, verifier_spec, author, resolved_runner,
        my_card_id=my_card_id, phase_index=phase_index,
        iteration=iteration_counter, role=f"reeval{reeval_counter}",
        root_id=root_id,
    )

    loop_state["verifier_card"] = new_verifier_id
    loop_state["terminal_ids"] = [new_verifier_id]
    loop_state["reeval_counter"] = reeval_counter
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    kb._append_event(
        conn, my_card_id, "loop_reevaluate",
        {
            "phase_index": phase_index,
            "iteration": iteration_counter,
            "stale_verifier": old_verifier_id,
            "fresh_verifier": new_verifier_id,
            "reeval_counter": reeval_counter,
            "root_id": root_id,
            "reason": "terminal_done_no_verdict",
        },
        run_id=run_id,
    )

    state = _park_driver(kb, conn, my_card_id, new_verifier_id, run_id)
    if state == "failed":
        logger.error("Re-eval block failed for %s (run_id=%s)",
                     my_card_id, run_id)
        return _park_failure(root_id, exec_id, new_verifier_id,
                             new_verifier_id, run_id)
    return json.dumps({
        "status": "blocked",
        "decision": "reevaluate",
        "root_id": root_id,
        "execution_card": exec_id,
        "verifier_card": new_verifier_id,
        "stale_verifier": old_verifier_id,
        "terminal_ids": [new_verifier_id],
        "reeval_counter": reeval_counter,
        "phase_index": phase_index,
        "iteration": iteration_counter,
        "message": (
            f"Terminal verifier {old_verifier_id} was done but produced no "
            f"dod_verdict (dropped/stale completion). Re-evaluating with a "
            f"fresh verifier ({new_verifier_id}); driver re-parked on it."
        ),
    }, indent=2)


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
    if err is not None:
        # T8: a structured validation error (dict) preserves the flat `error`
        # string AND adds the `validation` block (additive — nothing that parses
        # the flat {"error": str} today breaks); a plain string is the existing
        # flat contract, unchanged.
        if isinstance(err, dict):
            return json.dumps(err)
        return json.dumps({"error": err})

    my_card_id = _my_card_id(**kwargs)
    if not my_card_id:
        return json.dumps({
            "error": "Cannot determine current task ID. "
                     "Set HERMES_KANBAN_TASK or pass task_id.",
        })

    # B3/SPEC §2: goal is polymorphic (string | [Claim]). A [Claim] goal is the
    # structural fast-pass form (already grounded -> discover worker skipped).
    # goal_claims carries the [Claim] form; goal is always a display string (root
    # title + idempotency salt derive from it — stable per the claim set).
    goal_raw = args.get("goal")
    if isinstance(goal_raw, list):
        goal_claims = goal_raw
        first = goal_claims[0] if goal_claims else {}
        goal = (first.get("text") if isinstance(first, dict) else "")[:200]
        if not goal.strip():
            goal = "grounded goal"
    else:
        goal = goal_raw.strip()
        goal_claims = None
    discover_spec = args.get("discover")
    phases = args.get("phases")
    execution = args.get("execution")
    verifier = args.get("verifier")
    max_iterations = args.get("max_iterations")
    budget = args.get("budget")
    no_progress_threshold = args.get("no_progress_threshold")
    runner = args.get("runner")
    runner = runner.strip() if isinstance(runner, str) else None
    # T9 (bd hermes-teams-3g2): strict_fact_basis opt-in — persisted to
    # loop_state so the decide-time evidence gate can read it on every
    # re-promotion (the driver is stateless between iterations). Default
    # False = today's additive behavior (zero-regression).
    strict_fact_basis = bool(args.get("strict_fact_basis"))
    author = _author(**kwargs)

    # T6/B7: loop_id (aliased to root_id) is the durable loop handle. Supplied
    # => PRIMARY, drift-immune root pin (open that card, read loop_state; no
    # goal_hash derivation). Absent => today's goal_hash bootstrap fallback
    # (byte-for-byte, zero regression). See _resolve_root / SPEC §identity.
    loop_id = args.get("loop_id") or args.get("root_id")
    if isinstance(loop_id, str):
        loop_id = loop_id.strip() or None
    else:
        loop_id = None

    # T5: resolve the workflow runner once (configured -> worker -> default).
    # Stored in loop_state so replans / phase advances reuse the same runner.
    resolved_runner = _resolve_runner(runner, known_profiles=_known_profiles())

    kb = _kb()
    run_id = _run_id()

    with kb.connect_closing(board=_board()) as conn:

        # 1. Root card (shared blackboard) — resolution order (T6/B7):
        #    a) loop_id SUPPLIED (PRIMARY, drift-immune): trust it as root_id,
        #       open that card directly. No goal_hash derivation, no goal-byte
        #       sensitivity. This is the within-workflow promotion path.
        #    b) loop_id ABSENT or UNRESOLVED (FALLBACK = today's behavior
        #       verbatim): derive loop:{my_card_id}:{sha1(goal)[:10]} and
        #       create_task with it (recovers the root iff goal stable; mints
        #       fresh iff new goal — preserves cross-workflow separation).
        #    A supplied loop_id that does not resolve (stale/garbage) is never
        #    trusted: fire a loop_id_mismatch event and fall back to goal_hash.
        loop_id_mismatch = False
        root_id = _resolve_root(kb, conn, loop_id) if loop_id else None
        if root_id is None:
            if loop_id:
                loop_id_mismatch = True
                kb._append_event(
                    conn, my_card_id, "loop_id_mismatch",
                    {"supplied": loop_id, "fallback": "goal_hash"})
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
            result = _first_invocation(
                kb, conn, root_id, goal, execution, author,
                my_card_id, run_id, verifier, max_iterations, phases,
                budget, no_progress_threshold, resolved_runner,
                goal_claims=goal_claims, discover_spec=discover_spec,
                strict_fact_basis=strict_fact_basis,
            )
        else:
            result = _reinvoke(
                kb, conn, root_id, loop_state, author, run_id,
                my_card_id, execution, verifier, phases,
            )

        # Surface a supplied-but-unresolved loop_id on the response so the
        # driver can observe the fallback (observability complement to the event).
        if loop_id_mismatch:
            try:
                data = json.loads(result)
                data["loop_id_mismatch"] = True
                result = json.dumps(data, indent=2)
            except (ValueError, TypeError):
                pass
        return result


def _first_invocation(kb, conn, root_id, goal, execution, author,
                      my_card_id, run_id, verifier, max_iterations, phases,
                      budget=None, no_progress_threshold=None,
                      resolved_runner=None, goal_claims=None,
                      discover_spec=None, strict_fact_basis=False):
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
    # (mirrors kanban_chains: complete root, then create children). This is
    # idempotent under crash-replay: complete_task is a no-op (returns False,
    # no duplicate event) on an already-done root, and create_task deduped the
    # root row itself via its goal-hash idempotency key (T4).
    kb.complete_task(
        conn, root_id,
        summary="Loop topology planned; root is the shared blackboard.",
        metadata={"goal": goal},
    )

    # ── B3/SPEC §2: discover — ALWAYS-ON phase-0 input grounding ──────────────
    # discover is structurally phase 0 for EVERY loop (SPEC §2: "always-on,
    # engine-governed phase 0... v1 callers get it automatically, +1 phase"): a
    # PHYSICAL discover card is minted on the board so phase 0 is VISIBLE. The
    # card's lifecycle is adaptive so the always-on force is cheap when there is
    # nothing to ground:
    #   * discover:{...} configured + bare goal -> DISPATCH: the discover worker
    #     grounds the goal; the driver parks on the card; the user's phases run
    #     after a scope-clear verdict (single-call w/ redirect — _reinvoke_discover).
    #   * goal as [Claim] (pre-grounded)      -> FAST-PASS: the goal claims BECOME
    #     the context brief; the discover card is minted but RESOLVED as a skeleton
    #     (discover_state="skipped"); no worker dispatched; fall through to phases[0].
    #   * neither (v1 no-block bare goal)     -> FAST-PASS: the discover card is
    #     minted but RESOLVED as a skeleton (discover_state="unconfigured"); no
    #     worker dispatched; fall through to phases[0]. Honors SPEC §2 structurally
    #     (+1 visible phase-0 card for EVERY loop) without forcing every caller to
    #     configure a grounding worker.
    # Ambiguity 2 (Round-0): discover has its OWN {assignee, dod, max_iterations};
    # the engine does NOT hardcode doctrine-read/worktree/ledger — the consumer
    # configures the grounding work.
    if goal_claims is not None:
        _write_blackboard(kb, conn, root_id, author, "context_brief",
                          goal_claims)
        discover_extras = _fast_pass_discover_card(
            kb, conn, root_id, goal, author, resolved_runner, my_card_id,
            "skipped")
    elif isinstance(discover_spec, dict):
        return _dispatch_discover(
            kb, conn, root_id, goal, discover_spec, author, my_card_id,
            run_id, phases, execution, verifier, max_iterations,
            budget=budget, no_progress_threshold=no_progress_threshold,
            resolved_runner=resolved_runner,
            strict_fact_basis=strict_fact_basis)
    else:
        discover_extras = _fast_pass_discover_card(
            kb, conn, root_id, goal, author, resolved_runner, my_card_id,
            "unconfigured")

    # Build the user's first phase (shared with the discover scope-clear path).
    return _begin_first_user_phase(
        kb, conn, root_id, phases, execution, verifier, max_iterations,
        author, my_card_id, run_id, resolved_runner,
        budget=budget, no_progress_threshold=no_progress_threshold,
        loop_state_extras=discover_extras,
        strict_fact_basis=strict_fact_basis)


def _begin_first_user_phase(kb, conn, root_id, phases, execution, verifier,
                            max_iterations, author, my_card_id, run_id,
                            resolved_runner, budget=None,
                            no_progress_threshold=None,
                            loop_state_extras=None, strict_fact_basis=False):
    """Build the first USER phase's execution (+ optional verifier) sub-graph,
    write loop_state, dependency-park the driver. Shared by:

      * :func:`_first_invocation` — the no-discover / fast-pass / v1-no-op paths
        (loop_state_extras carries the discover marker when discover ran).
      * :func:`_reinvoke_discover` — the discover scope-clear transition (the
        user's phases run after discover grounds the goal).

    When ``phases`` is supplied the first phase's specs resolve from
    ``phases[0]``; otherwise the top-level execution/verifier/max_iterations
    drive a single phase (T1/T2 backward compat). ``loop_state_extras`` is merged
    into loop_state before writing (None = no extras = byte-for-byte v1 path).
    """
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

    # T6: the iteration value for the intent-stable idempotency key tracks
    # loop_state.iteration_counter: T1 seeds 0, T2 seeds 1. Computing it here
    # means the exec card is created exactly ONCE with the right recovery key.
    first_iter = 1 if verifier_spec is not None else 0
    exec_id = _create_execution_card(kb, conn, root_id, exec_spec, author,
                                     resolved_runner, my_card_id=my_card_id,
                                     phase_index=0, iteration=first_iter)

    if verifier_spec is None:
        # T1 spine: one execution card, park on it.
        loop_state = {
            "phase_index": 0,
            "iteration_counter": 0,
            "terminal_ids": [exec_id],
            "execution_card": exec_id,
            "resolved_runner": resolved_runner,
            "strict_fact_basis": strict_fact_basis,
        }
        if phases is not None:
            loop_state["phases"] = phases
        if loop_state_extras:
            loop_state.update(loop_state_extras)
        _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

        state = _park_driver(kb, conn, my_card_id, exec_id, run_id)
        if state == "failed":
            logger.error("Dependency block failed for %s (run_id=%s)",
                         my_card_id, run_id)
            return _park_failure(root_id, exec_id, None, exec_id, run_id)

        resp = {
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
        }
        # SPEC §2 always-on: surface the discover phase-0 card + state when
        # discover fast-passed (cited goal -> "skipped", v1 no-block ->
        # "unconfigured") or completed ("done" on the scope-clear redirect). The
        # card physically exists on the board; this makes it visible on response.
        if loop_state_extras and "discover_state" in loop_state_extras:
            resp["discover_state"] = loop_state_extras["discover_state"]
            if "discover_card" in loop_state_extras:
                resp["discover_card"] = loop_state_extras["discover_card"]
        return json.dumps(resp, indent=2)

    # T2 verifier-gated converge loop. T6: the verifier carries an intent-stable
    # key at iter1 (loop_state seeds iteration_counter=1); the exec card was
    # already created above with the same iteration.
    verifier_id = _create_verifier_card(
        kb, conn, exec_id, verifier_spec, author, resolved_runner,
        my_card_id=my_card_id, phase_index=0, iteration=1, root_id=root_id)
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
        "strict_fact_basis": strict_fact_basis,
        "exit_counters": {
            "hard_cap": 0,
            "budget_remaining": resolved_budget,
            "no_progress_streak": 0,
        },
        "last_state_hash": None,
    }
    if phases is not None:
        loop_state["phases"] = phases
    if loop_state_extras:
        loop_state.update(loop_state_extras)
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, verifier_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s (run_id=%s)",
                     my_card_id, run_id)
        return _park_failure(root_id, exec_id, verifier_id, verifier_id, run_id)

    resp = {
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
    }
    # SPEC §2 always-on: surface the discover phase-0 card + state (see the T1
    # branch above for the rationale).
    if loop_state_extras and "discover_state" in loop_state_extras:
        resp["discover_state"] = loop_state_extras["discover_state"]
        if "discover_card" in loop_state_extras:
            resp["discover_card"] = loop_state_extras["discover_card"]
    return json.dumps(resp, indent=2)


def _create_discover_card(kb, conn, root_id, discover_exec, author,
                          resolved_runner, my_card_id=None, iteration=1):
    """discover worker card parented on the root (B3/SPEC §2).

    Like :func:`_create_execution_card` but the intent-stable idempotency key
    carries role=``"discover"`` so a discover card at (phase 0, iter N) NEVER
    collides with a later user-phase exec card at the same (phase, iteration).
    The card body is the discover DoD (the grounding instructions); assignee is
    :func:`_resolve_assignee` (explicit ``discover.assignee`` wins, else runner).
    """
    skills = [discover_exec["skill"]] if discover_exec.get("skill") else None
    idem = None
    if my_card_id is not None:
        idem = _card_idempotency_key(my_card_id, 0, iteration, "discover")
    return kb.create_task(
        conn,
        title=discover_exec["title"],
        body=discover_exec["body"] + _loop_protocol_footer(root_id),
        assignee=_resolve_assignee(discover_exec, resolved_runner),
        created_by=author,
        parents=[root_id],
        skills=skills,
        idempotency_key=idem,
    )


def _fast_pass_discover_card(kb, conn, root_id, goal, author, resolved_runner,
                             my_card_id, discover_state):
    """SPEC §2 always-on: mint the discover phase-0 card as a RESOLVED SKELETON
    (fast-pass). The card physically EXISTS on the board — a visible phase 0 and
    the skeleton an agent can expand — but NO grounding worker is dispatched.

    Used when the goal is already grounded (cited ``[Claim]``; ``discover_state
    ="skipped"``) or no ``discover:`` block is configured (v1 bare-goal caller;
    ``discover_state="unconfigured"``). The card is created via the SAME seam as
    a dispatched discover card (:func:`_create_discover_card` — role="discover"
    idempotency key, parented on the root) and immediately resolved
    (``complete_task``) with ``discover_state`` recorded ON it, so the state
    machine advances straight to the user's phases[0].

    Returns the ``loop_state`` extras (``discover_state`` + ``discover_card``)
    for :func:`_begin_first_user_phase` to persist + surface.
    """
    if discover_state == "skipped":
        reason = "The goal arrived already grounded (cited [Claim])."
    else:
        reason = "No discover block was configured for this loop."
    discover_exec = {
        "title": f"discover: ground the goal — {goal[:60]}",
        "body": (f"[fast-pass:{discover_state}] discover phase-0 — no "
                 f"grounding worker ran. {reason} Skeleton phase-0 card; "
                 "re-open to run grounding."),
        "assignee": resolved_runner,
    }
    discover_id = _create_discover_card(
        kb, conn, root_id, discover_exec, author, resolved_runner,
        my_card_id=my_card_id, iteration=1)
    kb.complete_task(
        conn, discover_id,
        summary=f"discover phase-0 fast-passed ({discover_state})",
        metadata={"discover_state": discover_state, "fast_pass": True})
    return {"discover_state": discover_state, "discover_card": discover_id}


def _dispatch_discover(kb, conn, root_id, goal, discover_spec, author,
                       my_card_id, run_id, phases, execution, verifier,
                       max_iterations, budget=None,
                       no_progress_threshold=None, resolved_runner=None,
                       strict_fact_basis=False):
    """B3/SPEC §2: run discover as phase 0 — dispatch the discover worker, write
    loop_state (discover_state='pending'), dependency-park the driver on it.

    The user's phases[0] is NOT built yet; it runs after discover returns a
    scope-clear verdict (single-call w/ redirect — see :func:`_reinvoke_discover`).
    The phases plan is NORMALIZED here (single-phase ``execution`` shorthand is
    folded into a 1-element phases list) so the scope-clear transition always has
    a phases plan to hand to :func:`_begin_first_user_phase`.
    """
    cap = int(discover_spec.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    discover_exec = {
        "title": f"discover: ground the goal — {goal[:60]}",
        "body": discover_spec["dod"],
        "assignee": discover_spec.get("assignee"),
    }
    discover_id = _create_discover_card(
        kb, conn, root_id, discover_exec, author, resolved_runner,
        my_card_id=my_card_id, iteration=1)

    # Normalize the phases plan (fold single-phase execution shorthand into a
    # 1-element list) so the scope-clear path always resolves phases[0].
    normalized_phases = phases
    if normalized_phases is None:
        phase_0 = {"execution": execution}
        if verifier is not None:
            phase_0["verifier"] = verifier
        if max_iterations is not None:
            phase_0["max_iterations"] = max_iterations
        normalized_phases = [phase_0]

    resolved_threshold = (int(no_progress_threshold)
                          if no_progress_threshold is not None
                          else DEFAULT_NO_PROGRESS_THRESHOLD)
    resolved_budget = int(budget) if budget is not None else None

    loop_state = {
        "phase_index": 0,
        "iteration_counter": 1,
        "terminal_ids": [discover_id],
        "discover_card": discover_id,
        "discover": discover_spec,
        "discover_state": "pending",
        "discover_max_iterations": cap,
        "goal_text": goal,  # so _replan_discover can rebuild the card title.
        "resolved_runner": resolved_runner,
        "strict_fact_basis": strict_fact_basis,
        "phases": normalized_phases,
        # Seed the layered-exit counters so the discover loop is bounded by the
        # same deterministic guards as a normal phase (SPEC §Termination).
        "budget": resolved_budget,
        "iteration_cost": DEFAULT_ITERATION_COST,
        "no_progress_threshold": resolved_threshold,
        "exit_counters": {
            "hard_cap": 0,
            "budget_remaining": resolved_budget,
            "no_progress_streak": 0,
        },
        "last_state_hash": None,
    }
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, discover_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s during discover dispatch "
                     "(run_id=%s)", my_card_id, run_id)
        return _park_failure(root_id, discover_id, None, discover_id, run_id)
    return json.dumps({
        "status": "blocked",
        "root_id": root_id,
        "phase": "discover",
        "phase_index": 0,
        "discover_state": "pending",
        "discover_card": discover_id,
        "terminal_ids": [discover_id],
        "iteration": 1,
        "max_iterations": cap,
        "message": (
            "discover phase 0 dispatched: the discover worker grounds the goal "
            "in evidence. Driver dependency-parked on the discover card; "
            "auto-promotes when it completes. The user phases run after discover "
            "returns a scope-clear verdict."
        ),
    }, indent=2)


def _reinvoke_discover(kb, conn, root_id, loop_state, author, run_id,
                       my_card_id):
    """B3/SPEC §2: read the discover worker's verdict and route.

      * scope clear (``dod_met=true`` / ``advance``) -> store the context brief
        on the blackboard, then proceed to the user's phases[0] via
        :func:`_begin_first_user_phase` (the single-call redirect).
      * replan (under the deterministic caps) -> re-dispatch a fresh discover
        worker (next iteration); the context brief from the failed attempt is on
        the blackboard for the re-plan to read.
      * layered exits (escalate / budget / no-progress / hard cap) -> sticky HITL
        escalation (mirrors :func:`_reinvoke_verifier`'s deterministic guards).

    The discover verdict IS a ``dod_verdict`` (SPEC §2); its ``evidence`` field
    is the context brief as ``[Claim]``. The B4 evidence gate is applied
    additively (a bare verdict passes unchanged).

    TODO(B3-followup): discover invalidation hook. SPEC §2 OMITS invalidation;
    the ldr design comment describes a downstream "grounding stale -> re-run
    discover" signal but it depends on a ``grounding:{valid,...}`` field that B4
    REMOVED from ``dod_verdict``. The invalidation signal mechanism is currently
    UNDEFINED — it needs a design decision (wayfinder) before implementing. The
    hook would live here (a downstream worker flags stale grounding -> engine
    re-runs discover). Left as a seam; NO behavior.
    """
    discover_id = loop_state.get("discover_card")
    cap = int(loop_state.get("discover_max_iterations")
              or DEFAULT_MAX_ITERATIONS)
    iteration_counter = int(loop_state.get("iteration_counter", 1))

    # Reconcile against board state BEFORE reading any verdict (mirrors
    # _reinvoke_verifier). If the discover terminal is NOT done, the in-flight
    # discover hasn't finished -> re-park on the EXISTING card (no phantom
    # verdict, no duplicate cards).
    if discover_id and hasattr(kb, "get_task"):
        term = kb.get_task(conn, discover_id)
        term_status = getattr(term, "status", None) if term is not None else None
        if term_status != "done":
            return _repark_existing(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                discover_id, [discover_id], 0, execution_card=discover_id)

    run = kb.latest_run(conn, discover_id) if discover_id else None
    verdict = _extract_verdict(run)

    # The context brief = the discover verdict's evidence ([Claim], per SPEC §2).
    # Store it on the root blackboard whenever the discover worker produced one,
    # so BOTH the replan and the scope-clear path surface the latest brief.
    evidence = (verdict or {}).get("evidence")
    if isinstance(evidence, list):
        _write_blackboard(kb, conn, root_id, author, "context_brief", evidence)

    # B4 evidence gate — additive (a bare verdict with no evidence key passes).
    verdict = _apply_evidence_gate(
        verdict, strict_fact_basis=loop_state.get("strict_fact_basis"))

    dod_met = bool(verdict and verdict.get("dod_met"))

    # Scope clear -> mark discover done, proceed to the user's first phase
    # (the single-call redirect: phases[0] runs after discover grounds the goal).
    if dod_met:
        phases = loop_state.get("phases")
        return _begin_first_user_phase(
            kb, conn, root_id, phases, None, None, None, author,
            my_card_id, run_id, loop_state.get("resolved_runner"),
            loop_state_extras={"discover_state": "done",
                               "discover": loop_state.get("discover")})

    # ── layered exits (mirror _reinvoke_verifier's deterministic guards) ───────
    threshold = int(loop_state.get("no_progress_threshold")
                    or DEFAULT_NO_PROGRESS_THRESHOLD)
    exit_counters = loop_state.get("exit_counters") or {}
    budget_remaining = exit_counters.get("budget_remaining")
    last_state_hash = loop_state.get("last_state_hash")
    iteration_cost = int(loop_state.get("iteration_cost")
                         or DEFAULT_ITERATION_COST)

    cur_hash = _state_hash(verdict)
    if cur_hash == last_state_hash:
        no_progress_streak = int(
            exit_counters.get("no_progress_streak", 0)) + 1
    else:
        no_progress_streak = 1
    exit_counters["no_progress_streak"] = no_progress_streak
    if budget_remaining is not None:
        budget_remaining = budget_remaining - iteration_cost
        exit_counters["budget_remaining"] = budget_remaining
    loop_state["exit_counters"] = exit_counters
    loop_state["last_state_hash"] = cur_hash
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    recommendation = verdict.get("recommendation") if verdict else None
    if recommendation == "escalate":
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "verifier_escalate", 0,
                         iteration_counter, cap=cap, budget=budget_remaining,
                         threshold=threshold, verdict=verdict)
    if budget_remaining is not None and budget_remaining <= 0:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "budget_exhausted", 0,
                         iteration_counter, cap=cap, budget=budget_remaining,
                         threshold=threshold, verdict=verdict)
    if no_progress_streak >= threshold:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "no_progress", 0,
                         iteration_counter, cap=cap, budget=budget_remaining,
                         threshold=threshold, verdict=verdict)
    if iteration_counter >= cap:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "hard_cap", 0,
                         iteration_counter, cap=cap, budget=budget_remaining,
                         threshold=threshold, verdict=verdict)

    # Replan: dispatch a fresh discover worker (next iteration), re-park.
    return _replan_discover(kb, conn, root_id, loop_state, author, run_id,
                            my_card_id, verdict, iteration_counter, cap)


def _replan_discover(kb, conn, root_id, loop_state, author, run_id,
                     my_card_id, verdict, iteration_counter, cap):
    """Re-dispatch a fresh discover worker (next iteration) and re-park the
    driver. Mirrors :func:`_replan` but for the discover phase-0 worker. The
    context brief from the failed attempt is already on the root blackboard
    (written in :func:`_reinvoke_discover`); the re-plan reads it from there."""
    next_iter = iteration_counter + 1
    resolved_runner = loop_state.get("resolved_runner")
    discover_spec = loop_state.get("discover") or {}
    goal = loop_state.get("goal_text") or "the goal"
    discover_exec = {
        "title": f"discover: ground the goal — {goal[:60]}",
        "body": discover_spec.get("dod", "Ground the goal in evidence."),
        "assignee": discover_spec.get("assignee"),
    }
    discover_id = _create_discover_card(
        kb, conn, root_id, discover_exec, author, resolved_runner,
        my_card_id=my_card_id, iteration=next_iter)

    loop_state["iteration_counter"] = next_iter
    loop_state["discover_card"] = discover_id
    loop_state["terminal_ids"] = [discover_id]
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    state = _park_driver(kb, conn, my_card_id, discover_id, run_id)
    if state == "failed":
        logger.error("Dependency block failed for %s during discover replan "
                     "(run_id=%s)", my_card_id, run_id)
        return _park_failure(root_id, discover_id, None, discover_id, run_id)
    return json.dumps({
        "status": "blocked",
        "decision": "replan",
        "phase": "discover",
        "root_id": root_id,
        "discover_card": discover_id,
        "terminal_ids": [discover_id],
        "iteration": next_iter,
        "max_iterations": cap,
        "verdict": verdict,
        "message": (
            f"discover under-grounded (recommendation="
            f"{verdict.get('recommendation') if verdict else None}); re-planning "
            f"discover iteration {next_iter}/{cap} from the context brief on the "
            f"blackboard. Driver re-parked on the new discover card."
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
    # B3: discover is the active phase-0 -> read the discover verdict and route
    # (scope clear -> proceed to the user's phases[0]; replan -> re-dispatch a
    # fresh discover worker from the context brief). See _reinvoke_discover.
    if loop_state.get("discover_state") == "pending":
        return _reinvoke_discover(kb, conn, root_id, loop_state, author,
                                  run_id, my_card_id)
    # B6: a proxy phase's held-out battery is the active terminal gate (the
    # per-phase verifier already passed; the battery's completion re-promoted the
    # driver). Read the battery verdict and route (advance iff BOTH pass).
    if loop_state.get("battery_state") == "pending":
        return _reinvoke_battery(kb, conn, root_id, loop_state, author,
                                 run_id, my_card_id, execution, verifier)
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

    # T6: reconcile against board state. If the exec terminal is NOT done, the
    # in-flight iteration hasn't finished (crash between create-cards and park,
    # or a premature re-promotion). Re-park on the EXISTING terminal — do NOT
    # stub-decide on a phantom result or create duplicate cards.
    if exec_id and hasattr(kb, "get_task"):
        term = kb.get_task(conn, exec_id)
        if term is not None and getattr(term, "status", None) != "done":
            return _repark_existing(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                exec_id, [exec_id], int(loop_state.get("phase_index", 0)),
                execution_card=exec_id)

    iteration_counter = int(loop_state.get("iteration_counter", 0)) + 1

    # Read the execution card's closing run for its structured handoff.
    run = kb.latest_run(conn, exec_id) if exec_id else None
    result = {
        "summary": getattr(run, "summary", None),
        "metadata": getattr(run, "metadata", None),
        "outcome": getattr(run, "outcome", None),
    }

    # Persist a PO-interview reply (T1 interview phase) to the root blackboard
    # so the downstream ADR phase can cite it. The interview worker writes
    # {po_interview: ...} to its run.metadata via kanban_complete; only present
    # for the interview phase, so this is a no-op for other T1 phases.
    _meta = result.get("metadata")
    if isinstance(_meta, dict) and _meta.get("po_interview") is not None:
        _write_blackboard(kb, conn, root_id, author,
                          "council:po_interview", _meta.get("po_interview"))

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
    # The terminal signal is workflow_complete (matching T2 semantics) so the
    # driver's "on workflow_complete: confirm ADR on disk" step fires for BOTH
    # tiers. (Do NOT use hard_cap_reached here — that label means ESCALATE in
    # T2 and would conflate normal T1 completion with a HITL escalation.)
    return json.dumps({
        "status": "complete",
        "root_id": root_id,
        "execution_card": exec_id,
        "iteration": iteration_counter,
        "decision": "workflow_complete",
        "result": result,
        "message": (
            f"T1 phase complete at hard cap {MAX_PHASE_STEPS}: reporting the "
            f"execution result (no verifier/DoD in T1). Workflow complete."
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

    # T6: reconcile against board state BEFORE reading any verdict. If the
    # terminal verifier is NOT done, the in-flight iteration hasn't finished
    # (crash between create-cards and park, or premature re-promotion). Re-park
    # on the EXISTING terminal — no phantom verdict, no duplicate cards.
    if verifier_id and hasattr(kb, "get_task"):
        term = kb.get_task(conn, verifier_id)
        term_status = getattr(term, "status", None) if term is not None else None
        if term_status != "done":
            return _repark_existing(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                verifier_id, [verifier_id],
                int(loop_state.get("phase_index", 0)),
                execution_card=exec_id, verifier_card=verifier_id)

    run = kb.latest_run(conn, verifier_id) if verifier_id else None
    verdict = _extract_verdict(run)

    # T6: stale/missing-verdict detection. The verifier IS done but produced NO
    # structured dod_verdict — the completion was dropped/stale (optimistic-lock
    # drop, run reclaimed mid-verdict). Acting on that as a verdict would
    # phantom-advance or replan on empty evidence; instead RE-EVALUATE (a fresh
    # verifier re-checks the phase output). Bounded by MAX_REEVAL_ATTEMPTS.
    if verdict is None:
        _re_exec, _re_verifier = _resolve_phase_specs(loop_state, execution,
                                                      verifier)
        if _re_verifier is not None:
            return _reevaluate(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                exec_id, verifier_id, _re_verifier,
                int(loop_state.get("phase_index", 0)), iteration_counter)

    # T3: evidence GATES dod_met (hard-fail on an un-cited material claim, per
    # T1). Applied additively — a bare v1 verdict (no evidence key) passes
    # unchanged so legacy fixtures/consumers keep working; the gate fires only
    # when a verdict actually carries evidence claims with an un-cited material
    # assertion. A "done" verdict with an un-cited material claim does NOT
    # advance (dod_met forced false -> replan).
    verdict = _apply_evidence_gate(
        verdict, strict_fact_basis=loop_state.get("strict_fact_basis"))

    # Persist the council iteration to the root blackboard so converge/replan
    # workers (grandchildren that cannot reach root themselves) can read the
    # last verdict + best-so-far for keep/discard and gap-targeted replan.
    _persist_council_state(kb, conn, root_id, author, verdict)

    dod_met = bool(verdict and verdict.get("dod_met"))
    recommendation = verdict.get("recommendation") if verdict else None
    _cur_exec, _cur_verifier = _resolve_phase_specs(loop_state, execution,
                                                    verifier)
    _artifact_required = bool((_cur_verifier or {}).get("artifact_required",
                                                        False))
    artifact_complete = _validate_dod_artifact(verdict, _artifact_required)

    # Advance: DoD met AND the artifact is complete. The engine no longer
    # trusts recommendation='advance' to override a failed/partial DoD — a
    # latent_defect trace (or a missing/incomplete defect_traces table) hard-
    # blocks advance even if the verifier mistakenly wrote dod_met=true.
    # (recommendation=='escalate' is still honored below.)
    if dod_met and artifact_complete:
        # B6: proxy metric -> held-out battery is a TERMINAL gate (the autoresearch
        # anti-overfitting defense). The per-phase verifier passed (proxy DoD met);
        # if this phase's verifier is metric_type=proxy with a battery spec,
        # dispatch the independent battery card and park on it — the phase does NOT
        # advance yet. The actual advance (or replan-on-battery-fail) happens in
        # _reinvoke_battery after the battery returns its own evidence-cited
        # dod_verdict. Ground-truth / no-battery phases advance unchanged (zero
        # regression: battery cards materialize ONLY for proxy+battery phases).
        _adv_exec, _adv_verifier = _resolve_phase_specs(loop_state, execution,
                                                        verifier)
        if _has_battery(_adv_verifier):
            return _dispatch_battery(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                _adv_verifier, exec_id, verifier_id, iteration_counter)
        return _advance_or_complete(
            kb, conn, root_id, loop_state, author, run_id, my_card_id,
            exec_id, verifier_id, iteration_counter, verdict)

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


def _advance_or_complete(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, exec_id, verifier_id, iteration_counter,
                         verdict):
    """Resolve the advance decision once a phase has passed ALL its gates.

    Called after the per-phase verifier passes (ground-truth / no-battery), AND
    after the held-out battery passes (proxy phase — :func:`_reinvoke_battery`).
    This is the shared advance topology so the battery composes as a terminal
    gate WITHOUT duplicating the multi-phase / single-phase decision:

      * multi-phase + non-last -> :func:`_advance_phase` (next phase sub-graph);
      * multi-phase + last phase -> workflow complete;
      * single-phase -> advance/complete.
    """
    _dod_met = bool(verdict and verdict.get("dod_met"))
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
            f"(verifier dod_met={_dod_met}); verifier-gated phase complete."
        ),
    }, indent=2)


def _reinvoke_battery(kb, conn, root_id, loop_state, author, run_id,
                      my_card_id, execution, verifier):
    """T5/B6: read the held-out battery card's dod_verdict and decide.

    Reached when ``loop_state.battery_state == 'pending'`` (the per-phase verifier
    passed on a proxy phase and the engine dispatched the independent battery card
    as a terminal gate; the battery's completion promoted the driver).

    The battery is itself a verifier: its verdict is an evidence-cited
    ``dod_verdict`` (B4/T3), run through the evidence gate. Composition is a
    TERMINAL gate — BOTH the per-phase verifier AND the battery must pass:

      * battery dod_met=true  -> :func:`_advance_or_complete` (phase advances);
      * battery dod_met=false (overfit detected) -> :func:`_replan` the phase with
        the battery's gaps fed back (the proxy leaked; re-converge). Bounded by
        the same deterministic layered exits as a verifier replan (mirrors
        :func:`_reinvoke_discover`) so a proxy that always games the verifier but
        always fails the battery cannot loop forever.
    """
    battery_id = loop_state.get("battery_card")
    verifier_id = loop_state.get("verifier_card")
    exec_id = loop_state.get("execution_card")
    cap = int(loop_state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    iteration_counter = int(loop_state.get("iteration_counter", 1))
    phase_index = int(loop_state.get("phase_index", 0))

    # Reconcile against board state BEFORE reading any verdict (mirrors
    # _reinvoke_verifier). If the battery terminal is NOT done, the held-out check
    # is still in-flight -> re-park on the EXISTING battery card (no phantom
    # verdict, no duplicate card — the role='battery' idempotency key dedups too).
    if battery_id and hasattr(kb, "get_task"):
        term = kb.get_task(conn, battery_id)
        term_status = getattr(term, "status", None) if term is not None else None
        if term_status != "done":
            return _repark_existing(
                kb, conn, root_id, loop_state, author, run_id, my_card_id,
                battery_id, [battery_id], phase_index,
                execution_card=exec_id, verifier_card=verifier_id)

    run = kb.latest_run(conn, battery_id) if battery_id else None
    verdict = _extract_verdict(run)

    # T3: evidence GATES dod_met on the battery verdict too (the battery is itself
    # a verifier). Additive — a bare battery verdict passes unchanged.
    verdict = _apply_evidence_gate(
        verdict, strict_fact_basis=loop_state.get("strict_fact_basis"))

    # Persist the battery iteration so replan workers read the battery's gaps
    # (where the proxy leaked) from council:last_iteration on the root blackboard.
    _persist_council_state(kb, conn, root_id, author, verdict)

    dod_met = bool(verdict and verdict.get("dod_met"))

    # Battery PASS -> the phase cleared BOTH terminal gates -> advance. Clear the
    # battery bookkeeping first so it cannot haunt the next phase/iteration.
    if dod_met:
        loop_state.pop("battery_state", None)
        loop_state.pop("battery_card", None)
        loop_state.pop("battery", None)
        _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)
        return _advance_or_complete(
            kb, conn, root_id, loop_state, author, run_id, my_card_id,
            exec_id, verifier_id, iteration_counter, verdict)

    # ── battery FAIL: the proxy was overfit. Bounded replan (mirror the verifier
    # layered exits) so the held-out gate cannot force an unbounded loop. ─────────
    budget = loop_state.get("budget")  # None = no budget guard
    iteration_cost = int(loop_state.get("iteration_cost")
                         or DEFAULT_ITERATION_COST)
    threshold = int(loop_state.get("no_progress_threshold")
                    or DEFAULT_NO_PROGRESS_THRESHOLD)
    exit_counters = loop_state.get("exit_counters") or {}
    budget_remaining = exit_counters.get("budget_remaining")
    last_state_hash = loop_state.get("last_state_hash")

    cur_hash = _state_hash(verdict)
    if cur_hash == last_state_hash:
        no_progress_streak = int(
            exit_counters.get("no_progress_streak", 0)) + 1
    else:
        no_progress_streak = 1
    exit_counters["no_progress_streak"] = no_progress_streak
    if budget_remaining is not None:
        budget_remaining = budget_remaining - iteration_cost
        exit_counters["budget_remaining"] = budget_remaining
    loop_state["exit_counters"] = exit_counters
    loop_state["last_state_hash"] = cur_hash
    # Clear the battery bookkeeping before delegating (replan mints a fresh
    # verifier which, if it passes, dispatches a FRESH battery next iteration).
    loop_state.pop("battery_state", None)
    loop_state.pop("battery_card", None)
    loop_state.pop("battery", None)
    _write_blackboard(kb, conn, root_id, author, "loop_state", loop_state)

    recommendation = verdict.get("recommendation") if verdict else None
    if recommendation == "escalate":
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "verifier_escalate", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)
    if budget_remaining is not None and budget_remaining <= 0:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "budget_exhausted", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)
    if no_progress_streak >= threshold:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "no_progress", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)
    if iteration_counter >= cap:
        return _escalate(kb, conn, root_id, loop_state, author, run_id,
                         my_card_id, "hard_cap", phase_index,
                         iteration_counter, cap=cap, budget=budget,
                         threshold=threshold, verdict=verdict)

    # Replan the phase with the battery's gaps fed back. _replan reads the current
    # phase's exec/verifier specs (the verifier still carries the battery, so the
    # next iteration is re-checked by a fresh held-out battery).
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
    # T6: a fresh phase starts a fresh evaluation — clear any stale reeval
    # counter from the prior phase so it cannot cause a premature
    # stale_verdict escalation here.
    loop_state.pop("reeval_counter", None)
    # T6: intent-stable keys — T1 phase seeds iter0, T2 phase seeds iter1.
    next_iter = 1 if verifier_spec is not None else 0

    exec_id = _create_execution_card(
        kb, conn, root_id, exec_spec, author, resolved_runner,
        my_card_id=my_card_id, phase_index=next_phase_index,
        iteration=next_iter)

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

    # T2 phase within multi-phase: create verifier card (intent-stable key at
    # iter1), park on it.
    verifier_id = _create_verifier_card(
        kb, conn, exec_id, verifier_spec, author, resolved_runner,
        my_card_id=my_card_id, phase_index=next_phase_index, iteration=1,
        root_id=root_id)
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
    # T6: intent-stable keys at (phase, next_iter) so a re-drive of THIS replan
    # dedups while a later replan (next_iter+1) mints distinct cards.
    phase_index = int(loop_state.get("phase_index", 0))
    # A replan starts a fresh evaluation: clear any stale reeval counter.
    loop_state.pop("reeval_counter", None)
    exec_id = _create_execution_card(
        kb, conn, root_id, execution, author, resolved_runner,
        my_card_id=my_card_id, phase_index=phase_index, iteration=next_iter)
    verifier_id = _create_verifier_card(
        kb, conn, exec_id, verifier, author, resolved_runner,
        my_card_id=my_card_id, phase_index=phase_index, iteration=next_iter,
        root_id=root_id)

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
