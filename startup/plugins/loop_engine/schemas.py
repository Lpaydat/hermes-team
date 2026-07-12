"""Tool schemas — what the LLM sees."""

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
        "run.metadata ({dod_met, score, gaps, recommendation}). On promotion the "
        "driver reads the verdict (latest_run direct read) and decides: DoD met / "
        "recommendation=advance -> phase complete; dod_met=false / replan (under "
        "the hard cap) -> replan (fresh execution + verifier, dependency-park "
        "again); hard cap hit without DoD -> terminate.\n\n"
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
            "execution": {
                "type": "object",
                "description": (
                    "The ONE execution card to run this iteration (T1 = single "
                    "phase, single execution unit). Parented on the root."
                ),
                "properties": {
                    "assignee": {
                        "type": "string",
                        "description": "Profile name to assign the execution card to.",
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
                "required": ["assignee", "title", "body"],
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
                            "'verifier')."
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
                },
                "required": ["assignee", "title", "body"],
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Hard iteration cap for the verifier-gated converge loop (T2). "
                    "The loop replans while dod_met is false and the iteration count "
                    "is under this cap; on reaching the cap without the DoD met it "
                    "terminates with decision=hard_cap_reached. Defaults to "
                    "DEFAULT_MAX_ITERATIONS when omitted. Ignored in T1 mode."
                ),
            },
        },
        "required": ["goal", "execution"],
    },
}
