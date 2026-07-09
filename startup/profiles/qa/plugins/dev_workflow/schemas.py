"""Tool schemas — what the LLM sees."""

KANBAN_DELEGATE = {
    "name": "kanban_delegate",
    "description": (
        "Delegate work to developer + verifier and block yourself until verification completes. "
        "This is the ONLY way to create dev/verifier cards — do NOT use kanban_create for dev or verifier cards.\n\n"
        "What it does (atomically):\n"
        "1. Creates a developer card (assignee=developer)\n"
        "2. Creates a verifier card (assignee=verifier, parented on developer)\n"
        "3. Links your card as dependent on the verifier\n"
        "4. Blocks your card (kind=dependency → status=todo)\n"
        "5. Returns immediately — you will be auto-promoted when ALL verifiers finish\n\n"
        "Single chain: pass one contract → one dev→verifier pair.\n"
        "Parallel chains: pass multiple contracts → N pairs, blocks on ALL.\n\n"
        "After auto-promotion: read verifier summaries via kanban_show, then kanban_complete.\n"
        "Do NOT call kanban_complete until you are re-dispatched after promotion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "contracts": {
                "type": "array",
                "description": "One or more work contracts to delegate. Each creates a dev→verifier pair.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short title for the work (e.g. 'statistics.py — mean, median, mode')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Full contract body: acceptance criteria, evals command, constraints, bead reference",
                        },
                        "workspace_path": {
                            "type": "string",
                            "description": "Absolute path to the project directory the developer should work in",
                        },
                    },
                    "required": ["title", "body", "workspace_path"],
                },
            },
        },
        "required": ["contracts"],
    },
}
