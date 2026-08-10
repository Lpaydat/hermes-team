# Bug-Handoff Parent-Child Link Direction Bug

Found 2026-08-10 during port-csv2md livetest. QA quick card stuck in `todo`
forever — never dispatched.

## Symptom

QA quick card sits in `todo` status. The QA gateway is running, no other QA
workers are active, but the card never gets dispatched.

## Root Cause

The `bug-handoff` skill (line 33) says: "For Critical findings, link the card
as a parent of the QA verdict card so the verdict can't complete until the bug
is fixed."

This instruction is AMBIGUOUS about direction. The QA agent interpreted "link
the card as a parent of the QA card" as `kanban_link(parent_id=bug_card,
child_id=qa_card)` — making the BUG card the PARENT of the QA card.

In kanban's dependency gate, a child card cannot promote to `ready` while its
parent is not `done`. The bug card was `blocked` (crashed x2 from the
loops-engineering skill issue), so the QA card stayed in `todo` forever.

## Detection

```sql
-- Find cards blocking QA from dispatching
SELECT parent_id, child_id FROM task_links
WHERE child_id IN (
  SELECT id FROM tasks WHERE assignee='qa' AND status='todo'
);

-- If the parent is a bug/fix card (not a milestone or workflow card),
-- the link is backwards
```

## Fix

1. Remove the wrong link: `hermes kanban unlink <bug_id> <qa_id>`
2. Unblock any blocked bug cards: `hermes kanban unblock <bug_id>`

## Skill Fix Needed

The bug-handoff skill (on the `qa` profile) line 33 should change from:

> "link the card as a parent of the QA verdict card"

To:

> "create the bug card with `--parent <qa_card_id>` (the bug is a CHILD of
> the QA card that discovered it)"

The `--parent` flag on `kanban create` sets the NEW card's parent — so
`create bug --parent qa_card` correctly makes QA the parent and bug the child.
This is the correct direction: QA discovers bugs, bugs are children of QA.

## General Rule

Bug/finding cards are always CHILDREN of the QA card that discovered them.
When in doubt, check: the card that CREATED the finding is the PARENT. The
finding card is the CHILD.

This is the same class of bug as Pattern 5 (trigger card freelancing) —
ambiguous instructions about card creation direction lead to wrong parent-child
relationships that block the pipeline silently.
