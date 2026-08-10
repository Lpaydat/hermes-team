---
name: bug-handoff
description: "Route QA findings to the right profile. Use when QA finds bugs during testing and needs to file them as kanban cards. Reads severity from findings[] and routes Critical→debugger, Important/Minor/Note→tech-lead."
---

# Bug Handoff

When QA testing produces findings, route each one to the right profile. The template's output schema already enforces `findings[]` — each finding has `severity`, `claim`, `detail`, and `reproduction`. This skill tells you where to send them.

## Routing rules

| Severity | Route to | Card prefix | Block? |
|----------|----------|-------------|--------|
| Critical | debugger | `[bug]` | Yes — block the finding card on the fix |
| Important | tech-lead | `[fix]` | No — ship with follow-up |
| Minor | tech-lead | `[fix]` | No — ship with follow-up |
| Note | tech-lead | `[fix]` | No — ship with follow-up |

Critical bugs block shipping. Everything else ships and gets fixed later.

## How to file

For each finding, create a kanban card on the current board. The finding card is a CHILD of the current QA card — the QA card is the parent.

```
kanban_create(
  title: "[bug] <short description>",
  assignee: "debugger",
  parents: ["<current_qa_card_id>"],
  body: "## Finding\n\n**Source:** QA card <card_id>\n**Severity:** Critical\n**Claim:** <claim>\n\n## Detail\n<detail>\n\n## Reproduction\n<reproduction>"
)
```

CRITICAL: `parents: ["<qa_card_id>"]` means the QA card is the PARENT and the finding card is the CHILD. The finding card blocks in `todo` until dispatched, and the QA card can't complete until all its children (findings) are done. Never link the finding card as a parent of the QA card — that blocks QA from dispatching.

DO NOT pass `skills` on finding cards. The target profile (debugger/tech-lead) has its own skills. Passing QA-specific skills (like live-testing) to other profiles causes crashes — "Unknown skill(s)".

For Critical findings, the dependency gate ensures the QA card stays in `todo` until the finding card (its child) completes.

## After filing

Set `findings_filed` in your output metadata to the count of cards created. The template schema validates this field. If `findings_filed > 0`, each one must have a real kanban card ID.

## When NOT to file

- No findings → `findings_filed: 0`, verdict stays PASS
- All findings are Note severity and the artifact is a test fixture → use judgement; filing is still correct practice
