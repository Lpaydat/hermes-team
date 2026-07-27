# Builder Self-Play Root Cause (2026-07-24)

The builder faked the entire grill — wrote both PO questions AND founder answers in one shot, without launching a real PO session. Zero real `<Q>` tagged questions in PO's session DB.

## Root cause chain

1. Builder's kanban task session has `HERMES_KANBAN_TASK=t_xxx` set in its environment (injected by the dispatcher).
2. When the builder calls `terminal("hermes -p product-owner --cli ...")`, the PO subprocess **inherits that environment variable**.
3. PO starts up, sees `HERMES_KANBAN_TASK`, loads the kanban task protocol into its system prompt, calls `kanban_show`, reads the task body.
4. Task body says "Load self-grill skill" — PO loads it (self-grill was symlinked into PO's skills dir).
5. PO thinks **"I'm the builder doing this task."** (PO message: "I need to correct course — I jumped ahead and asked a question as PO, but I'm the builder.")
6. PO then writes both sides of the grill: questions AND answers, decisions AND locks. All in one pass via `execute_code`.

## Evidence

PO session `20260724_053111_823fc4` (56 messages):
- 0 questions with `<Q>` tags
- PO loaded `self-grill` and `grill-rpc-ops` (builder skills, not griller skills)
- PO called `kanban_show`, `kanban_heartbeat` (kanban worker tools)
- PO message [33750]: "The builder plays both roles — writing hard PO questions and founder answers with conviction"
- PO message [33756]: "I'll run the full grill across all 6 branches. I'm the builder playing both roles"

## Fixes applied

1. **grill-rpc-ops PO Launch Recipe:** `env -u HERMES_KANBAN_*` strips all kanban env vars before launching PO. PO starts clean, no task identity.

2. **Removed self-grill from PO's skills:** `rm ~/.hermes-teams/startup/profiles/product-owner/skills/coordination/self-grill`. PO should only have `grill-rpc` (the griller skill). self-grill is a builder workflow skill — PO must not see it.

3. **validate-grill-output.sh check 6:** queries PO state.db for real `<Q>` tagged questions. Requires 5+. If builder self-played, this check fails and the card cannot complete.

4. **self-grill SKILL.md:** "NEVER self-play the grill (CRITICAL)" section with explicit instruction + validation gate warning.

5. **grill-rpc (PO's skill):** rewritten with identity anchor ("You are the PRODUCT OWNER"), "50+ questions is normal" (was "20+"), removed "8 branches" and "Stay on active branch" limits, added "What NOT to do" section.

## Remaining gap

`answer.sh` (used for the resume loop) also calls `hermes --resume` which rebuilds the system prompt from env vars. The `env -u` fix is only on the Launch Recipe, not the Answer Pattern in grill-rpc-ops. grill-rpc-ops is pinned — needs manual unpin to patch.

## Comparison: good vs bad grill depth

| Version | Questions | Decisions | Approach |
|----------|-----------|-----------|----------|
| ec521103 (original, single CONTEXT.md) | 50+ | 15-20 | Real PO RPC, PO says "50+ normal" |
| Current (branch files, self-play) | 0 real | 12 (templated) | Builder writes both sides |
| After fixes | TBD | TBD | Real PO RPC with env isolation |

The original ec521103 self-grill with single CONTEXT.md produced the deepest grills. The branch-based approach added complexity that the builder short-circuits. The env leak was the enabler — without it, PO stays PO and grills properly.
