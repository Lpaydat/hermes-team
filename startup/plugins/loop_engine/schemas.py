"""Tool schemas — what the LLM sees."""

LOOP_ENGINE = {
    "name": "loop_engine",
    "description": (
        "Loop-engineering control tool — drives an iterative converge-loop on the "
        "kanban board with durable state. Invoked once per promotion of the "
        "loop-driver card; each invocation runs ONE iteration of the outer "
        "phase-loop.\n\n"
        "What it does (T1 spine — one phase, one iteration):\n"
        "1. FIRST invocation (no loop_state on the root blackboard yet): creates a "
        "root card (shared blackboard), creates ONE execution card parented on the "
        "root, completes the root, then dependency-parks your card on the execution "
        "card (link_tasks + block_task kind=dependency -> status=todo). Returns.\n"
        "2. RE-INVOCATION (you auto-promoted once the execution card completed): "
        "re-reads loop_state, reads the execution card's result, and stub-decides. "
        "T1 hard cap = 1 iteration -> reports the result and terminates.\n\n"
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
        },
        "required": ["goal", "execution"],
    },
}
