# Kanban Block Research — Per-Tool Disable Investigation

**Date:** 2026-07-24
**Question:** Can we disable `kanban_block` for only the builder profile?

## Answer: No

Hermes has two layers of tool filtering:

### 1. Toolset level (config.yaml)
`enabled_toolsets` / `disabled_toolsets` work at the toolset group level. The `kanban` toolset includes ALL kanban tools together: `kanban_show`, `kanban_list`, `kanban_complete`, `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`, `kanban_link`, `kanban_unblock`, `kanban_attach`, `kanban_attach_url`, `kanban_attachments`. You cannot remove one tool from a toolset.

### 2. check_fn per tool (registry)
The tool registry (`tools/registry.py`) has a per-tool gating mechanism (`check_fn`), but it's for runtime availability checks (is terminal available? is browser installed?), NOT for config-based enabling/disabling. It's not user-configurable.

### 3. Kanban toolset is force-injected
`model_tools.py` line 369-370: "Dispatcher-spawned workers are scoped by HERMES_KANBAN_TASK and must always receive the lifecycle handoff tools." Even if you remove `kanban` from the profile's toolsets, the worker gets it re-added at spawn time.

## What actually happens when builder blocks

The builder process is NOT killed when the card is blocked. `kanban_block` only changes the card's DB status — the process keeps running. The builder:
1. Blocks the card (changes status to `blocked`)
2. Keeps working internally (still heartbeating, still doing grill)
3. Finishes the work
4. Tries `kanban_complete` → fails (card is blocked)
5. Falls back to CLI: `hermes kanban claim <task_id>` then `hermes kanban complete <task_id>`

The blocking is "soft" — advisory, not enforced. The builder process is the enforcement boundary, not the card status.

## Root cause: system prompt priority

The builder receives two conflicting instructions:
- **System prompt (kanban task protocol):** "Block on genuine ambiguity... call kanban_block(reason=...)"
- **Skill (self-grill):** "NEVER block the kanban card during self-grill"

The system prompt wins because it's injected at a higher structural priority than skills. Skills are loaded on-demand; the task protocol is always present.

## Realistic fixes (in order of preference)

1. **SOUL.md instruction** (profile-level system prompt) — same priority level as the kanban task protocol
2. **Accept + optimize self-heal** — add to self-grill: "if you accidentally blocked, immediately run `hermes kanban unblock <task_id>` via CLI"
3. **Patch kanban_tools.py check_fn** — fragile, upgrade-breaking, not recommended
