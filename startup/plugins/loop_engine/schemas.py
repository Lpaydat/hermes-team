"""Tool schemas — what the LLM sees."""

# v2 verifier fields (hermes-teams-drj — the 1h5 sibling, one nesting level
# down). The engine (tools.py) reads + validates these off the verifier object;
# declaring them in the schema lets a tool-calling driver pass them (otherwise
# it sees only {assignee, title, body, skill} and drops them on real runs).
# Shared by the top-level `verifier` and each phase's `verifier`.
_VERIFIER_V2_PROPS = {
    "metric_type": {
        "type": "string",
        "enum": ["ground_truth", "proxy"],
        "description": (
            "T4 — declare the metric kind gating this phase. "
            "'ground_truth' = a mechanical, infallible check (test pass/fail, "
            "grep, count); needs no battery. 'proxy' = a gameable judgment "
            "(LLM-rubric, human rating); REQUIRES 'battery'. Absent = treated "
            "as ground_truth unless strict_fact_basis is on."
        ),
    },
    "battery": {
        "type": "object",
        "description": (
            "T5/B6 — held-out battery spec, required when metric_type='proxy'. "
            "The engine dispatches a SEPARATE independent battery card "
            "(assigned to battery.runner, never the phase exec) as a terminal "
            "gate; both the verifier AND the battery must pass for the phase "
            "to advance."
        ),
        "properties": {
            "path": {
                "type": "string",
                "description": "Path/locator of the disjoint held-out battery artifact.",
            },
            "runner": {
                "type": "string",
                "description": "Profile to assign the battery card (independence is load-bearing).",
            },
        },
        "required": ["path", "runner"],
    },
    "dod_signals": {
        "type": "array",
        "description": (
            "T8 — machine-checkable DoD signals "
            "[{artifact_type, locator, expectation?}]. Required under "
            "strict_dod; absent = compat warn."
        ),
        "items": {
            "type": "object",
            "properties": {
                "artifact_type": {"type": "string"},
                "locator": {"type": "string"},
                "expectation": {"type": "string"},
            },
            "required": ["artifact_type", "locator"],
        },
    },
    "strict_fact_basis": {
        "type": "boolean",
        "description": "Per-verifier override of the workflow-wide strict_fact_basis flag (true wins).",
    },
    "strict_dod": {
        "type": "boolean",
        "description": "Per-verifier override of the workflow-wide strict_dod flag (true wins).",
    },
    "artifact_required": {
        "type": "boolean",
        "default": False,
        "description": (
            "Opt-in DoD-artifact gate (the design-council converge use case). "
            "When true, the engine asserts the verdict carries complete "
            "behaviors[] + defect_traces[] with no unfixed latent defect."
        ),
    },
}

LOOP_ENGINE = {
    "name": "loop_engine",
    "description": (
        "Loop-engineering control tool — drives an iterative converge-loop on the "
        "kanban board with durable state. Invoked once per promotion of the "
        "loop-driver card; each invocation runs ONE iteration of the outer "
        "phase-loop.\n\n"
        "Two modes, selected by whether `verifier` is supplied:\n"
        "  * T1 spine (no verifier) — one phase, one iteration, execute-and-read.\n"
        "  * T2 verifier-gated converge loop (verifier supplied) — after the "
        "execution card completes, an independent verifier card evaluates the "
        "phase output against the DoD and completes with a dod_verdict in "
        "run.metadata ({dod_met, score, gaps, recommendation, and optionally "
        "behaviors[] + defect_traces[] for artifact-gated phases}). On promotion "
        "the driver reads the verdict (latest_run direct read), mechanically "
        "validates the artifact when the phase opts in (verifier.artifact_required) "
        "— a latent_defect trace hard-blocks advance — and decides: dod_met AND "
        "artifact-complete -> phase complete; otherwise replan (under the hard "
        "cap) -> replan (fresh execution + verifier, dependency-park again); hard "
        "cap hit without DoD -> escalate (sticky needs_input).\n\n"
        "FIRST invocation (no loop_state on the root blackboard yet): creates a "
        "root card (shared blackboard), creates the execution card parented on the "
        "root (and, in T2, a verifier card parented on the execution card), "
        "completes the root, then dependency-parks your card on the terminal "
        "(execution card in T1; verifier card in T2). Returns.\n"
        "RE-INVOCATION (you auto-promoted once the terminal completed): re-reads "
        "loop_state, reads the terminal's result/verdict, and decides.\n\n"
        "Do NOT call kanban_complete until you are re-dispatched after promotion. "
        "The engine is tool-driven (not hook-driven): it reads board state on its "
        "own promotion; the observer hook it registers is telemetry-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "What the workflow accomplishes. Posted to the root card "
                    "blackboard and used to derive the root idempotency key."
                ),
            },
            "runner": {
                "type": "string",
                "description": (
                    "T5 runner profile — the profile that should drive the loop "
                    "and that execution/verifier cards default to when they do "
                    "not name their own assignee. Resolution order: configured "
                    "runner -> worker -> default. Omit to use 'worker'. A card "
                    "that sets its own assignee overrides the runner default."
                ),
            },
            "execution": {
                "type": "object",
                "description": (
                    "The ONE execution card to run this iteration (T1 = single "
                    "phase, single execution unit). Parented on the root."
                ),
                "properties": {
                    "assignee": {
                        "type": "string",
                        "description": (
                            "Profile name to assign the execution card to. "
                            "OPTIONAL (T5): when omitted the card inherits the "
                            "workflow's resolved runner (configured runner -> "
                            "worker -> default). An explicit assignee overrides "
                            "the runner default."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Short title for the execution card.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Full execution body: acceptance criteria, instructions, "
                            "constraints. The worker's completion summary/metadata "
                            "flows back to the driver on re-invocation."
                        ),
                    },
                    "skill": {
                        "type": "string",
                        "description": "Skill to force-load into the execution worker.",
                    },
                },
                "required": ["title", "body"],
            },
            "verifier": {
                "type": "object",
                "description": (
                    "Evaluate step (T2). When supplied, the engine runs the "
                    "verifier-gated converge loop: a verifier card is dispatched "
                    "parented on the execution card (so it becomes ready once "
                    "execution completes and receives the execution output via "
                    "build_worker_context), and the driver dependency-parks on the "
                    "verifier. The verifier evaluates the phase output against the "
                    "DoD and completes with a dod_verdict in run.metadata "
                    "({dod_met, score, gaps, recommendation}). Omit to use the T1 "
                    "one-shot execute-and-read path."
                ),
                "properties": {
                    "assignee": {
                        "type": "string",
                        "description": (
                            "Profile name to assign the verifier card to (e.g. "
                            "'verifier'). OPTIONAL (T5): when omitted the card "
                            "inherits the workflow's resolved runner."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Short title for the verifier card.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Full verifier body: the phase definition-of-done (DoD) "
                            "plus instructions to evaluate the parent execution's "
                            "output and complete with a dod_verdict "
                            "({dod_met: bool, score: number, gaps: [{dimension, "
                            "issue}], recommendation: \"advance\"|\"replan\"|"
                            "\"escalate\"}) written to run.metadata via "
                            "kanban_complete(metadata={'dod_verdict': ...})."
                        ),
                    },
                    "skill": {
                        "type": "string",
                        "description": "Skill to force-load into the verifier worker.",
                    },
                    **_VERIFIER_V2_PROPS,
                },
                "required": ["title", "body"],
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Hard iteration cap for the verifier-gated converge loop (T2). "
                    "The loop replans while dod_met is false and the iteration count "
                    "is under this cap; on reaching the cap without the DoD met it "
                    "terminates with decision=hard_cap_reached. Defaults to "
                    "DEFAULT_MAX_ITERATIONS when omitted. Ignored in T1 mode and "
                    "when `phases` is supplied (each phase carries its own cap)."
                ),
            },
            "budget": {
                "type": "integer",
                "description": (
                    "T4 layered exit: workflow-wide cost-unit budget. Each "
                    "completed iteration consumes one cost unit "
                    "(DEFAULT_ITERATION_COST). When the budget is exhausted "
                    "before the DoD is met, the loop escalates to a human "
                    "(sticky block_task kind=needs_input + a loop_escalated "
                    "event) rather than terminating. Omit / null for no budget "
                    "guard (the hard cap still bounds the loop)."
                ),
            },
            "no_progress_threshold": {
                "type": "integer",
                "description": (
                    "T4 layered exit: escalate when the verifier verdict is "
                    "byte-identical across this many consecutive iterations "
                    "(the replan is not making progress). Defaults to "
                    "DEFAULT_NO_PROGRESS_THRESHOLD. Set higher to tolerate more "
                    "repetition; set to a large value to effectively disable the "
                    "guard."
                ),
            },
            "strict_fact_basis": {
                "type": "boolean",
                "default": False,
                "description": (
                    "T9 (bd hermes-teams-3g2): strict-fact-basis opt-in. When "
                    "true, the loop hard-requires evidence-cited claims + a "
                    "metric_type on every verifier — an un-cited material claim "
                    "or absent metric_type hard-fails the evidence gate. "
                    "Persisted to loop_state so the decide-time evidence gate "
                    "can read it on every re-promotion (the driver is stateless "
                    "between iterations). Default false = today's additive "
                    "behavior (zero-regression). Workflow-wide: a per-verifier "
                    "strict_fact_basis overrides upward (true wins)."
                ),
            },
            "strict_dod": {
                "type": "boolean",
                "default": False,
                "description": (
                    "B9: strict-definition-of-done opt-in. When true, the "
                    "verifier's DoD must include structured dod_signals (not "
                    "pure prose) — a pure-prose DoD is hard-rejected at "
                    "validation. Default false = today's prose-DoD compat. "
                    "Workflow-wide: a per-verifier strict_dod overrides upward "
                    "(true wins)."
                ),
            },
            "loop_id": {
                "type": "string",
                "description": (
                    "B7 (T6): durable loop handle — aliased to root_id. On "
                    "RE-INVOCATION, echo the root_id captured from the first "
                    "invocation here (drift-immune root pin: opens that exact "
                    "card and reads loop_state directly, with no goal_hash "
                    "derivation). Omit on the FIRST call to use the goal_hash "
                    "bootstrap fallback (byte-for-byte, zero regression). See "
                    "_resolve_root / SPEC §identity."
                ),
            },
            "discover": {
                "type": "object",
                "description": (
                    "B3/SPEC §2: optional discover phase-0 config. When present, "
                    "the engine runs a grounding discover phase before "
                    "phases[0] (or the single execution). The discover worker "
                    "grounds the goal (cites evidence) and its output feeds the "
                    "first phase. Omit to use the engine-default discover (or "
                    "skip discover entirely when goal is already a cited-claim "
                    "array)."
                ),
                "properties": {
                    "assignee": {
                        "type": "string",
                        "description": (
                            "Profile name to assign the discover card to. "
                            "OPTIONAL: when omitted the card inherits the "
                            "workflow's resolved runner (configured runner -> "
                            "worker -> default)."
                        ),
                    },
                    "dod": {
                        "type": "string",
                        "description": (
                            "The grounding definition-of-done — the discover "
                            "worker's instructions (becomes the card body). "
                            "REQUIRED, non-empty."
                        ),
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": (
                            "Caps the discover converge loop. OPTIONAL: defaults "
                            "to DEFAULT_MAX_ITERATIONS when omitted."
                        ),
                    },
                },
                "required": ["dod"],
            },
            "phases": {
                "type": "array",
                "description": (
                    "T3 multi-phase decomposition. When supplied, the goal is "
                    "decomposed into an ordered list of phases (subgoals). Each "
                    "phase runs its own converge-loop (execution + optional "
                    "verifier) and carries its own DoD (embedded in the verifier "
                    "body). When phase N's DoD is met, the engine advances to "
                    "phase N+1; when the LAST phase's DoD is met, the workflow is "
                    "complete. Omit to use the single-phase path (the top-level "
                    "execution/verifier/max_iterations drive one converge-loop). "
                    "When phases is supplied, the top-level execution/verifier are "
                    "not required."
                ),
                "items": {
                    "type": "object",
                    "description": "One phase of the workflow.",
                    "properties": {
                        "execution": {
                            "type": "object",
                            "description": (
                                "The execution card spec for this phase. Same shape "
                                "as the top-level execution property."
                            ),
                            "properties": {
                                "assignee": {"type": "string"},
                                "title": {"type": "string"},
                                "body": {"type": "string"},
                                "skill": {"type": "string"},
                            },
                            "required": ["title", "body"],
                        },
                        "verifier": {
                            "type": "object",
                            "description": (
                                "The verifier card spec for this phase (carries "
                                "the phase DoD in its body). Same shape as the "
                                "top-level verifier property. Omit for a T1 "
                                "(single-shot, no-DoD) phase."
                            ),
                            "properties": {
                                "assignee": {"type": "string"},
                                "title": {"type": "string"},
                                "body": {"type": "string"},
                                "skill": {"type": "string"},
                                **_VERIFIER_V2_PROPS,
                            },
                            "required": ["title", "body"],
                        },
                        "max_iterations": {
                            "type": "integer",
                            "description": (
                                "Per-phase hard iteration cap for this phase's "
                                "verifier-gated converge loop. Defaults to "
                                "DEFAULT_MAX_ITERATIONS when omitted."
                            ),
                        },
                    },
                    "required": ["execution"],
                },
            },
        },
        "required": ["goal"],
        "anyOf": [
            {"required": ["execution"]},
            {"required": ["phases"]},
        ],
    },
}


# ── v2: citation primitive (T1, bd hermes-teams-4gm) ──────────────────────────
#
# ONE shared representation for facts, used by BOTH discover (input grounding)
# AND the evidence-evaluator (output evidence). The engine enforces STRUCTURE
# only — the independent verifier card re-opens each citation (reads file:line,
# re-runs the probe, checks the sha) per the existing independent-verifier trust
# model. See SPEC.md §Fact-Based Loop Enhancement (v2) §1.

from dataclasses import dataclass, field
from typing import List, Optional


# The SEED artifact_type enum — the cross-domain locators every consumer gets
# for free. ``artifact_type`` is an OPEN enum: the seed covers code / design /
# research; a consumer registers domain extensions via
# :func:`register_artifact_type` (the engine never infers types — it only
# validates membership). The locator's semantics are per-type (type-dispatched
# re-open is the verifier profile's concern, not the engine's).
SEED_ARTIFACT_TYPES = frozenset({
    "file_line",
    "test_output",
    "grep_result",
    "commit_sha",
    "url",
    "adr_doc",
    "probe_result",
    "error_string",
})

# Runtime extension registry — the "open" half of the open enum.
_EXTRA_ARTIFACT_TYPES: set = set()


def register_artifact_type(name: str) -> None:
    """Register a domain extension to the ``artifact_type`` enum (T1).

    ``artifact_type`` is an OPEN enum: the seed set covers the cross-domain
    locators (file_line / test_output / ...), and a consumer registers its own
    domain types (e.g. ``design_token``, ``research_paper``) so its citations
    pass the engine's structure check. The engine never infers types — it only
    validates membership — so extension is the consumer's explicit declaration.

    Idempotent (a set); re-registering the same name is a no-op.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("artifact_type name must be a non-empty string")
    _EXTRA_ARTIFACT_TYPES.add(name.strip())


def known_artifact_types() -> frozenset:
    """Return the full artifact_type enum: the seed set ∪ registered extensions."""
    return SEED_ARTIFACT_TYPES | _EXTRA_ARTIFACT_TYPES


@dataclass
class Citation:
    """A pointer to evidence + the optional exact snippet asserted (T1).

    The machine address (``locator``) is what the verifier re-opens:
      * ``file_line``    -> "calc.py:10"
      * ``commit_sha``   -> "a78e25e"
      * ``url``          -> "https://..."
      * ``test_output``  -> "pytest -q -> 3 failed"
      * ``probe_result`` / ``error_string`` / ... — type-dispatched by verifier.

    ``quote`` (optional) is the exact snippet the claim asserts is at the
    locator — the verifier confirms it matches (the semantic check).

    This is the importable building block; the on-the-wire shape (board /
    run.metadata JSON) is a plain dict validated by
    :func:`loop_engine.tools.validate_citation`.
    """

    artifact_type: str
    locator: str
    quote: Optional[str] = None


@dataclass
class Claim:
    """A material assertion + its evidence (T1).

    ``text`` is the material assertion; ``citations`` is its evidence. A
    MATERIAL claim (``material=True``, the default) MUST carry >=1 citation —
    an un-cited material claim is the hard-fail primitive that makes facts not
    self-claim. A non-material claim (``material=False``, e.g. a framing /
    context statement the verdict does not depend on) MAY carry an empty
    citations list. Materiality is ultimately judged by the verifier (T1
    resolution); ``material`` is the consumer's opt-out flag.

    Representation choice (T1): ONE struct with ``material: bool = True`` over
    two parallel structs — simpler (one validator path), fail-safe (default
    material -> empty citations hard-fails), and materiality is verifier-judged
    so a bool flag is the minimal representation.
    """

    text: str
    citations: List[Citation] = field(default_factory=list)
    material: bool = True
