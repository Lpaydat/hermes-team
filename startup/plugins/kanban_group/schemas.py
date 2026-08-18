"""Tool schema — what the LLM sees for group_cards."""

GROUP_CARDS = {
    "name": "group_cards",
    "description": (
        "Deterministic group wiring: block a set of member cards behind ordered "
        "pre stages (unlock = ALL pre markers done), and fan-in ordered post stages "
        "after ALL member done-markers complete. Pure shape — it creates marker "
        "cards and dependency links ONLY; it never executes, completes, or blocks "
        "real work. Use it for milestone barriers, release trains, sign-offs.\n\n"
        "Semantics:\n"
        "1. UNLOCK (AND): a member card only promotes when EVERY marker of the "
        "LAST pre stage is done. Stage sub-lists run in parallel; the stage array "
        "is sequential (stage i+1 waits on all of stage i).\n"
        "2. FAN-IN: the first post stage waits on ALL members' done-markers; post "
        "stages then chain sequentially, sub-lists in parallel.\n"
        "3. IDEMPOTENT: `key` derives deterministic card keys "
        "(group:<key>:pre:0, group:<key>:post:1:0, …) — re-invoking with the same "
        "key returns the SAME cards with status 'recovered'. RETRY IS ALWAYS SAFE.\n"
        "4. VERIFIED: every link is re-read from the board before success is "
        "reported; any failure returns a structured error with the exact repair.\n\n"
        "Members are {card, done} pairs: `card` is the REAL work card to hold "
        "back; `done` is the marker whose completion means the work truly "
        "finished (e.g. its [done-NN] gate). A bare string means the card is its "
        "own marker.\n\n"
        "Never raises. Returns {status: wired|recovered|error, group_key, pre[], "
        "members[], post[], links[{parent,child,verified}], graph, error?{code,"
        "message,repair}}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Stable group key (no whitespace), e.g. 'm2'. Anchors idempotency — same key re-invoke recovers the same cards, zero duplicates.",
            },
            "board": {
                "type": "string",
                "description": "Board slug. Default 'auto': HERMES_KANBAN_BOARD env.",
            },
            "members": {
                "type": "array",
                "description": "The group's real work cards (≥1). Each entry: {card: <id to hold back>, done: <marker id meaning truly finished>} or a bare card id (card is its own marker).",
                "items": {
                    "type": "object",
                    "properties": {
                        "card": {"type": "string", "description": "Work card id the barrier holds back."},
                        "done": {"type": "string", "description": "Marker card id whose completion = real completion (e.g. the ticket's [done-NN] gate). Defaults to card."},
                    },
                    "required": ["card"],
                },
            },
            "pre": {
                "type": "array",
                "description": "Ordered stages before ANY member unlocks. Each element: a step object, or a sub-list of steps that run in parallel. Step = {gate: <existing card id to wait on>} or a create spec {assignee, title, body, skills}.",
                "items": {},
            },
            "post": {
                "type": "array",
                "description": "Ordered stages after ALL member done-markers complete (fan-in). Same shape as pre.",
                "items": {},
            },
            "await_caller": {
                "type": "boolean",
                "description": "Park YOUR card (dependency block) until the group terminus — the last post stage, or every member done-marker when there are no post stages — completes. Default false.",
                "default": False,
            },
        },
        "required": ["key", "members"],
    },
}
