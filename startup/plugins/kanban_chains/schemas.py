"""Tool schemas — what the LLM sees."""

KANBAN_CHAINS = {
    "name": "kanban_chains",
    "description": (
        "Create complex task topologies — parallel chains with optional sequential synthesis — "
        "in one atomic call. This is the ONLY way to create delegated work topologies; "
        "do NOT use kanban_create for delegation or swarm cards.\n\n"
        "What it does (atomically):\n"
        "1. Creates a root card (shared blackboard) with your goal, completed immediately so "
        "children can promote when ready\n"
        "2. Creates each chain's steps sequentially: step[0] is parented on root, step[n] on "
        "step[n-1]. All chains run in parallel.\n"
        "3. If 'after' is given, creates the after sequence (fan-in): step[0] is parented on the "
        "last step of EVERY chain, then each later step is parented on the previous\n"
        "4. Links your card as dependent on the terminal card(s): the last 'after' step, or the "
        "last step of each chain when there is no 'after'\n"
        "5. Blocks your card (kind=dependency -> status=todo), verified before returning\n"
        "6. Returns immediately — you auto-promote when all terminal work completes\n\n"
        "Examples:\n"
        "- tech-lead: chains=[[dev, verifier], ...], no after -> blocks on all verifiers.\n"
        "- QA: chains=[[worker], ...], after=[verifier, synthesizer] -> blocks on synthesizer.\n"
        "- research: chains=[[scout], ...], after=[compile_report] -> blocks on report.\n\n"
        "Validation runs BEFORE any card is created, so a bad call leaves no partial topology. "
        "Do NOT call kanban_complete until you are re-dispatched after promotion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "What the topology accomplishes. Posted to the root card blackboard.",
            },
            "chains": {
                "type": "array",
                "description": (
                    "Parallel chains of sequential steps. Each inner array is one chain; its steps "
                    "run in order (parent->child). All chains run in parallel."
                ),
                "items": {
                    "type": "array",
                    "description": "One chain: an ordered list of steps (1+).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "assignee": {
                                "type": "string",
                                "description": "Profile name to assign this step to.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Short title for the card.",
                            },
                            "body": {
                                "type": "string",
                                "description": (
                                    "Full step body: acceptance criteria, instructions, constraints."
                                ),
                            },
                            "skill": {
                                "type": "string",
                                "description": "Skill to force-load into the worker for this step.",
                            },
                            "workspace_path": {
                                "type": "string",
                                "description": "Absolute path to the project directory (becomes dir:<path> workspace).",
                            },
                            "priority": {
                                "type": "integer",
                                "description": "Priority tiebreaker.",
                            },
                        },
                        "required": ["assignee", "title", "body"],
                    },
                },
            },
            "after": {
                "type": "array",
                "description": (
                    "Optional sequential fan-in that runs after ALL chains complete. step[0] is "
                    "parented on the last step of every chain; each later step is parented on the "
                    "previous. The caller blocks on the last after step."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "assignee": {
                            "type": "string",
                            "description": "Profile name to assign this step to.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Short title for the card.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Step body (optional; defaults to the title).",
                        },
                        "skill": {
                            "type": "string",
                            "description": "Skill to force-load into the worker for this step.",
                        },
                    },
                    "required": ["assignee", "title"],
                },
            },
            "blackboard": {
                "type": "object",
                "description": (
                    "Optional shared blackboard, posted as a [swarm:blackboard] comment on the root "
                    "card. When image_tag is set, each chain's first step gets an auto-allocated port "
                    "(base_port + chain_index) baked into its body."
                ),
                "properties": {
                    "image_tag": {
                        "type": "string",
                        "description": "Container image tag for worker containers.",
                    },
                    "container_port": {
                        "type": "integer",
                        "description": "Port the app listens on inside the container.",
                        "default": 3000,
                    },
                    "base_port": {
                        "type": "integer",
                        "description": "First host port; each chain's first step gets base_port + chain_index.",
                        "default": 18081,
                    },
                    "env_facts": {
                        "type": "string",
                        "description": "Critical environment notes, posted to the blackboard.",
                    },
                    "spec_path": {
                        "type": "string",
                        "description": "Path to the contract/spec file, posted to the blackboard.",
                    },
                    "extra": {
                        "type": "object",
                        "description": "Arbitrary extra key-value pairs posted to the blackboard.",
                    },
                },
            },
        },
        "required": ["goal", "chains"],
    },
}
