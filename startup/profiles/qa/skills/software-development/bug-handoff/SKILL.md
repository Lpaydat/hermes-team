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

For each finding, create a kanban card on the current board:

```
hermes kanban create \
  --title "[bug] <short description>" \
  --assignee debugger \
  --body "## Finding\n\n**Source:** QA card <card_id>\n**Severity:** Critical\n**Claim:** <claim>\n\n## Detail\n<detail>\n\n## Reproduction\n<reproduction>" \
  --parent <current_qa_card_id>
```

For Critical findings, link the card as a parent of the QA verdict card so the verdict can't complete until the bug is fixed. Use `kanban_link` or `--parent`.

## After filing

Set `findings_filed` in your output metadata to the count of cards created. The template schema validates this field. If `findings_filed > 0`, each one must have a real kanban card ID.

## When NOT to file

- No findings → `findings_filed: 0`, verdict stays PASS
- All findings are Note severity and the artifact is a test fixture → use judgement; filing is still correct practice
