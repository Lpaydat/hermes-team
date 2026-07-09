"""Tool schema — what the LLM sees for kanban_matrix."""

KANBAN_MATRIX = {
    "name": "kanban_matrix",
    "description": (
        "Create a matrix topology: N parallel chains of sequential steps, an optional "
        "sequential `after` fan-in tail, and a shared root blackboard. Replaces both "
        "kanban_delegate (tech-lead dev→verifier pairs) and qa_swarm (workers→verifier→synth).\n\n"
        "What it does (atomically):\n"
        "1. Creates a root card (shared blackboard) with your goal + optional container/port info, then completes it\n"
        "2. For each chain: creates its steps sequentially — step[0] is parented on root, step[n] on step[n-1]\n"
        "3. If `after` is present: creates the after steps sequentially — after[0] is parented on the LAST step of EVERY chain (fan-in), after[n] on after[n-1]\n"
        "4. Links your card as child of the terminal card(s): last `after` step if present, else the last step of each chain\n"
        "5. Blocks your card (kind=dependency → status=todo) and verifies the block took effect\n"
        "6. Returns immediately — you auto-promote when the terminal card(s) complete\n\n"
        "If `blackboard.image_tag` is set, the first step of each chain gets an auto-allocated port "
        "(base_port + chain_index) baked into its body. Pass a `blackboard` to share image/env/spec context.\n\n"
        "Do NOT call kanban_complete until you are re-dispatched after promotion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "What this matrix accomplishes. Posted to the root card blackboard.",
            },
            "chains": {
                "type": "array",
                "description": "Parallel chains. Chains run concurrently; each inner array is a sequence of steps that run in order.",
                "items": {
                    "type": "array",
                    "description": "One chain — its steps run sequentially (step[n] depends on step[n-1]).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "assignee": {
                                "type": "string",
                                "description": "Profile name assigned to this step.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Card title for this step.",
                            },
                            "body": {
                                "type": "string",
                                "description": "What this step does — becomes the card body.",
                            },
                            "skill": {
                                "type": "string",
                                "description": "Skill to force-load into this step's worker.",
                            },
                            "workspace_path": {
                                "type": "string",
                                "description": "Absolute path to the repo for this step's workspace (passed as dir:<path>).",
                            },
                            "priority": {
                                "type": "integer",
                                "description": "Priority tiebreaker for this card.",
                            },
                        },
                        "required": ["assignee", "title", "body"],
                    },
                },
            },
            "after": {
                "type": "array",
                "description": "Optional sequential tail that runs after ALL chains complete. after[0] fans in from the last step of every chain.",
                "items": {
                    "type": "object",
                    "properties": {
                        "assignee": {
                            "type": "string",
                            "description": "Profile name assigned to this step.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Card title for this step.",
                        },
                        "body": {
                            "type": "string",
                            "description": "What this step does — becomes the card body. Optional for after steps.",
                        },
                        "skill": {
                            "type": "string",
                            "description": "Skill to force-load into this step's worker.",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Priority tiebreaker for this card.",
                        },
                    },
                    "required": ["assignee", "title"],
                },
            },
            "blackboard": {
                "type": "object",
                "description": "Optional shared context posted to the root card as a [swarm:blackboard] comment. When image_tag is set, each chain's first step gets a container + auto-allocated port baked into its body.",
                "properties": {
                    "image_tag": {
                        "type": "string",
                        "description": "Pre-built container image tag (e.g. 'qa-test:t_5ccbc475').",
                    },
                    "container_port": {
                        "type": "integer",
                        "description": "Port the app listens on inside the container.",
                        "default": 3000,
                    },
                    "base_port": {
                        "type": "integer",
                        "description": "First host port for chain containers. Each chain's first step gets base_port + chain_index.",
                        "default": 18081,
                    },
                    "env_facts": {
                        "type": "string",
                        "description": "Critical environment notes posted to the blackboard.",
                    },
                    "spec_path": {
                        "type": "string",
                        "description": "Path to the contract/spec file, posted to the blackboard.",
                    },
                    "extra": {
                        "type": "object",
                        "description": "Arbitrary extra key-value pairs merged into the blackboard payload.",
                    },
                },
            },
            "idempotency_key": {
                "type": "string",
                "description": "Optional dedup key applied to the root card (re-running with the same key returns the existing root instead of duplicating).",
            },
        },
        "required": ["goal", "chains"],
    },
}
