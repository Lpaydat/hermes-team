---
name: prototype-review-handoff
description: "Write the review handoff when a prototype is ready for founder feedback — portfolio entry, kanban comment, and the 'look here' pointer."
---

# Prototype Review Handoff

The prototype is built. The README exists. Now write the handoff — the three things that surface the prototype for founder review.

The **handoff** is the founder's entry point. It tells them: what to open, what to click, and what to decide. Without it, a built prototype sits invisible.

## What to write

### 1. Portfolio entry (portfolio.md)

Append to the "Awaiting Review" table in `~/vault/ventures/portfolio.md`. One row, packed:

```markdown
| **<Product Name>** | <score>/25 | <grill-date> | <2-3 sentence description: what it is, who it's for, the core mechanism> | `open ~/projects/<slug>/prototype/<main-file>` → <one-sentence "how to start" with the aha moment> |
```

Completion criterion: every field filled. The "how to start" must name the specific file and the first interaction.

### 2. Kanban comment

Post a comment on the completed build card:

```
Prototype ready for review.

**Open:** ~/projects/<slug>/prototype/<main-file>
**README:** ~/projects/<slug>/README.md
**Grill decisions:** ~/projects/<slug>/context/

**Aha moment:** <one sentence — the specific interaction that makes the product click>

**Decisions to challenge:** <list 2-3 grill decisions the founder might disagree with>
```

Completion criterion: comment posted. "Aha moment" is specific (names a button, a view, an interaction). "Decisions to challenge" surfaces the riskiest calls, not safe ones.

### 3. Verify the README is review-ready

The README at `~/projects/<slug>/README.md` is the detailed review surface. Before completing the card, verify:

- [ ] "How to Review" section has click-by-click steps (not "try the demo")
- [ ] "Grill Decisions" table lists every locked decision with lock values
- [ ] "Riskiest Assumption" names the one thing that could kill the product
- [ ] "What Happens Next" lists the three options (fix / promote / shelve)

If any section is vague or missing, fix it before completing.

## Pitfalls

- **Vague aha moment.** "See the dashboard" is useless. "Click Start Pentest Run, watch finding #3 get dropped as false positive — that's the validation layer working" is useful.
- **Challenging safe decisions.** Listing "we chose $499/mo" is boring. Listing "we killed AI-app specialist positioning because Traceforce already launched it — the founder might disagree" surfaces real tension.
- **Forgetting the portfolio.** The founder checks portfolio.md first. If the prototype isn't there, it doesn't exist.

## NEVER

- **NEVER mark the prototype "Awaiting Review" without all three artifacts** (portfolio entry + kanban comment + verified README). A partial handoff is worse than none — the founder opens it, finds gaps, loses trust.
- **NEVER write the portfolio entry before the README is done.** The portfolio points TO the README — if the README is incomplete, the handoff is broken.
