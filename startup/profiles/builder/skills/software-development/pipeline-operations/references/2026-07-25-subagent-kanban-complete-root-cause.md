# Subagent kanban_complete Root Cause and Fix (2026-07-25)

## The bug

Leaf subagents spawned via `delegate_task` can call `kanban_complete` on the parent task, marking it done before the work is finished. This caused grill cards to auto-complete after dossier research, before the grill ran.

Impact across 3 E2E batches:
- Batch 2: 2/3 pairs broke (required recovery cards)
- Batch 3: 1/3 pairs auto-completed but builder continued in same session (self-healed)

## Root cause (traced to source)

File: `~/.hermes-teams/startup/hermes-agent/tools/delegate_tool.py`, line 46:

```python
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # no recursive delegation
    "clarify",         # no user interaction
    "memory",          # no writes to shared MEMORY.md
    "send_message",    # no cross-platform side effects
    "execute_code",    # children should reason step-by-step
    "cronjob",         # no scheduling more work
])
```

Kanban lifecycle tools were NOT in this list. All kanban lifecycle tools were available to leaf subagents.

## Fix APPLIED (commit d8ad4be77)

Added 6 kanban lifecycle tools to `DELEGATE_BLOCKED_TOOLS`:

```python
"kanban_complete",   # no completing parent/grandparent tasks
"kanban_block",      # no blocking parent/grandparent tasks
"kanban_create",     # no spawning sibling/child tasks
"kanban_unblock",    # no unblocking tasks
"kanban_link",       # no modifying task dependency graph
"kanban_heartbeat",  # no heartbeating parent tasks
```

Leaf subagents RETAIN read-only and communication tools:
- `kanban_show` — read task details
- `kanban_list` — list tasks
- `kanban_comment` — post findings to task thread
- `kanban_attachments` — attach files

Commit: `d8ad4be77` on branch `local/prompts-exp` in `~/.hermes-teams/startup/hermes-agent/` (NousResearch/hermes-agent fork). Gateway restart required: `hermes gateway restart --profile builder`.

## How the blocklist works

`_blocked_toolsets_for_role(role)` in `delegate_tool.py` applies `DELEGATE_BLOCKED_TOOLS` to both leaf and orchestrator roles. The only exception: orchestrators get `delegate_task` back (line 810). The blocked tools are subtracted from the child's toolset via `model_tools` after composite expansion, surviving later registry/MCP refreshes through the agent's stored `disabled_toolsets`.

## Three fix options considered

1. **Add to DELEGATE_BLOCKED_TOOLS (chosen, applied)** — one frozenset change, same pattern as existing blocks, deterministic enforcement at spawn time. Applies to all child roles.
2. **Plugin using pre_tool_call hook** — block `kanban_complete` when `_delegate_depth > 0`. More flexible but adds a plugin to maintain. Hermes supports this via `resolve_pre_tool_block` in `hermes_cli/plugins.py`.
3. **Text instruction in card body** — tell the builder to pass `enabled_toolsets=["web","file","terminal"]` to delegate_task. Already in place as a fallback. Works when the builder reads it, but not enforced.

## Validation

Batch 3 (2026-07-25): 3 new pairs tested after the fix. Zero premature completions that broke the pipeline. The race condition (build card checking context/ before grill finishes) still exists but is cosmetic.

## Related: blocked to ready auto-promotion

When a build card blocks (`kind=needs_input`) because context/ is empty (race condition), and then the parent grill card completes, the auto-promote to `ready` does NOT fire. Requires manual `kanban_unblock`. This is a separate dispatcher limitation, not related to the subagent bug.
