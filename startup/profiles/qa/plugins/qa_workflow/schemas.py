"""Tool schemas — what the LLM sees."""

QA_SWARM = {
    "name": "qa_swarm",
    "description": (
        "Create a QA test swarm: parallel test workers → verifier → synthesizer. "
        "Blocks you until the synthesizer completes. This is the ONLY way to create QA test cards — "
        "do NOT use kanban_create or hermes kanban swarm for QA testing.\n\n"
        "What it does (atomically):\n"
        "1. Creates a root card (shared blackboard) with your goal + image info\n"
        "2. Creates each worker card with its specific checklist + skill + auto-allocated port\n"
        "3. Creates a verifier card (parented on all workers)\n"
        "4. Creates a synthesizer card (parented on verifier)\n"
        "5. Links your card as dependent on the synthesizer\n"
        "6. Blocks your card (kind=dependency → status=todo)\n"
        "7. Returns immediately — you will be auto-promoted when the synthesizer finishes\n\n"
        "Pass workers explicitly based on what the artifact needs. The artifact_type sets "
        "default checklists, but you override or extend them in each worker's body.\n\n"
        "After auto-promotion: read synthesizer summary via kanban_show, then kanban_complete "
        "or kanban_block if critical findings were filed.\n"
        "Do NOT call kanban_complete until you are re-dispatched after promotion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "What's being tested (e.g. 'QA: test cross-browser-ai MVP — all 10 MUST-scope items')",
            },
            "artifact_type": {
                "type": "string",
                "enum": ["cli", "library", "api_server", "daemon", "webapp", "mobile", "blockchain", "tui", "mixed"],
                "description": "The artifact type — determines which default checklists apply",
            },
            "image_tag": {
                "type": "string",
                "description": "Pre-built container image tag (e.g. 'qa-test:t_5ccbc475'). Workers start their own containers from this.",
            },
            "container_port": {
                "type": "integer",
                "description": "The port the app listens on inside the container (e.g. 3000, 8080)",
                "default": 3000,
            },
            "base_port": {
                "type": "integer",
                "description": "First host port for worker containers (e.g. 18081). Each worker gets base_port + N.",
                "default": 18081,
            },
            "env_facts": {
                "type": "string",
                "description": "Critical environment notes for workers (e.g. 'DEMO_MODE=true — Supabase mocked, Playwright real'). Posted to the blackboard.",
            },
            "spec_path": {
                "type": "string",
                "description": "Path to the contract/spec file for claims extraction. Posted to the blackboard.",
            },
            "workers": {
                "type": "array",
                "description": "The test workers to create. Each gets its own card with tailored body + skill. Pass 2-6 workers based on what the artifact needs.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short title (e.g. 'Functional — items 1-4')",
                        },
                        "skill": {
                            "type": "string",
                            "description": "Skill to load for this worker (qa-functional, qa-journeys, qa-security, qa-exploratory)",
                        },
                        "body": {
                            "type": "string",
                            "description": "What to test — claims, journeys, checks, or charters. Be specific: list the exact items, endpoints, or flows to test. This goes directly into the worker's card body.",
                        },
                    },
                    "required": ["title", "skill", "body"],
                },
            },
        },
        "required": ["goal", "artifact_type", "image_tag", "workers"],
    },
}

QA_FILE_FINDING = {
    "name": "qa_file_finding",
    "description": (
        "File a Critical QA finding (P0/P1/P2 bug) as a developer card WITH a verifier "
        "child card. This is the ONLY correct way to file QA-originated developer cards — "
        "it atomically creates the dev→verifier pair so the fix is independently verified. "
        "Do NOT use kanban_create or kanban_delegate for QA findings.\n\n"
        "What it does (atomically):\n"
        "1. Creates a developer card (assignee=developer) with your bug description as the body\n"
        "2. Creates a verifier card (assignee=verifier) parented on the developer card\n"
        "   — the verifier is auto-blocked (todo) until the developer completes the fix\n"
        "3. Returns the card IDs so you can reference them in your completion metadata\n\n"
        "Unlike kanban_delegate, this does NOT block your card — you can continue filing "
        "more findings or complete the synthesizer. The dev→verifier pair runs independently "
        "of the QA swarm lifecycle.\n\n"
        "Pass multiple findings in one call via the findings array."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "One entry per Critical finding to file as a dev+verifier pair.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short bug title including severity, e.g. '[P1] Auth completely broken — missing .auth methods'.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Full bug description: what's broken, evidence (test output, stack trace), expected behavior, acceptance criteria for the fix. This becomes the developer card body.",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["P0", "P1", "P2"],
                            "description": "Severity: P0 (blocker), P1 (critical), P2 (major).",
                        },
                        "workspace_path": {
                            "type": "string",
                            "description": "Absolute path to the project repo the developer will work in. Becomes the developer card's workspace.",
                        },
                    },
                    "required": ["title", "body", "severity", "workspace_path"],
                },
            },
        },
        "required": ["findings"],
    },
}
