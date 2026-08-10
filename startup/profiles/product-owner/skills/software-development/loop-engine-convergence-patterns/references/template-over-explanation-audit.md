# Pattern: Template Over-Explanation Audit

Created 2026-08-10 after user correction on route-bug body template.

## The Problem

Body templates accumulated redundant explanations of tool mechanics — how kanban_chains, loop_engine, and the kanban dependency gate work internally. These tools are self-documenting: their return values tell the agent what to do next.

## User Correction

"kanban_chains will do that automatically. do we need to re-explain to the agent that use it how automation work so that it can use the tool that work automatic?"

"what about original `handoff_bug` skill?" — pointing out that the bug-handoff skill already exists on the QA profile and already knows the routing rules. The template body was duplicating the skill's knowledge.

## What Was Removed

Three nodes had over-explanation stripped:

1. **route-bug (milestone-gate)** — removed "kanban_chains handles parent-child linking, dependency blocking, and auto-promotion automatically." Added `skill: "bug-handoff"` to the node so QA loads the routing skill. Body now just says: "Your `bug-handoff` skill tells you which profile each severity routes to. Call `kanban_chains` with one chain per finding."

2. **plan (tech-lead-execute)** — "handles ALL card creation internally" → "handles card creation"

3. **route-milestone (dev-dispatch)** — removed entire "How milestones work" section explaining what a milestone is and how the kanban dependency gate auto-promotes. Replaced with one-line: "The milestone card stays in `todo` until all parent tickets complete, then auto-promotes."

## The Principle

Tools (kanban_chains, loop_engine, dependency gate) are self-documenting. Their return messages instruct the agent what to do next. Re-explaining their mechanics in body templates:
- Obscures the actual task instructions
- Duplicates knowledge already in skills (bug-handoff, loops-engineering)
- Creates maintenance burden — if the tool changes, every body template needs updating

## Audit Method

Scan all active templates for these phrases (they indicate over-explanation):

```python
over_phrases = [
    "parent-child linking", "dependency blocking", "auto-promotion",
    "dependency gate", "kanban_block", "park this card",
    "handles all card creation", "handles parent", "handles dependency",
    "handles all iteration", "will block", "will park", "will auto-promote",
]
```

If any phrase appears in a body_template, the node is over-explaining. Strip the mechanics, keep only the task-specific instruction.

## Commit

35e9816 — "fix: remove over-explanation of tool mechanics from template bodies"

Re-scanned all 15 active templates after cleanup: zero over-explanation patterns remain.
