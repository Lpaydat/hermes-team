# Answer Pattern Env Isolation Gap

## Finding (2026-07-24)

The grill-rpc-ops PO Launch Recipe has `env -u HERMES_KANBAN_*` isolation to prevent PO from inheriting the builder's kanban task identity. But the Answer Pattern — which calls `answer.sh` → `hermes --resume` internally — does NOT have this isolation.

`hermes --resume` rebuilds the system prompt from current environment variables. So even though the initial PO launch was clean, every subsequent answer turn leaks `HERMES_KANBAN_TASK` back into PO's context.

## Fix needed in grill-rpc-ops (PINNED — ask user to unpin to patch)

Wrap every `answer.sh` call with the same `env -u` prefix as the launch recipe:

```bash
env -u HERMES_KANBAN_TASK \
    -u HERMES_KANBAN_WORKSPACE \
    -u HERMES_KANBAN_RUN_ID \
    -u HERMES_KANBAN_CLAIM_LOCK \
    -u HERMES_KANBAN_BOARD \
    -u HERMES_KANBAN_DB \
    -u HERMES_PROFILE \
    HERMES_GRILL_STATE_DIR="$STATE_DIR" \
    "$STATE_DIR/answer.sh" --file /dev/stdin << 'ANSWER'
Lock D1: Title = Value

Your answer text here.
ANSWER
```

## Detection

If PO starts saying things like "I need to correct course — I jumped ahead and asked a question as PO, but I'm the builder" mid-grill, the env leak is happening on the answer turn. Check PO session DB for identity-confusion messages after the first answer.
