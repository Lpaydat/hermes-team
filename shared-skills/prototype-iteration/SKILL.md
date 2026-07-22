---
name: prototype-iteration
description: "Process user feedback on built prototypes — decide build vs re-grill vs shelve, and execute the iteration."
---

# Prototype Iteration

When a prototype reaches "Awaiting Review" and the user gives feedback, this skill processes it. The key decision: what kind of feedback is it?

## Triage: what kind of feedback?

| Feedback type | Examples | Action |
|--------------|----------|--------|
| **Execution** | "Fix the dashboard layout", "Add CSV export", "This button is broken", "Make it faster" | **Just build.** No grill, no dossier. The user made the design decision — execute it. |
| **Design** | "This targets the wrong audience", "The monetization model is wrong", "I'm not sure this feature set is right" | **Re-grill the change.** Launch PO on the specific pivot, defend or concede as founder, then build. |
| **New idea** | Feedback that introduces an entirely different product | **Full pipeline.** Enter through Door D, new dossier, verify, grill, build. |
| **Promote** | "This is good, ship it" | **Hand off.** Write spec from brief + grill decisions, dispatch to tech-lead via kanban for production. |
| **Shelve** | "Not right for now" / silence | **Move to shelved list.** Stop building. Can be revived later. |

## Iteration flow

```
User feedback
  → Triage (which type?)
  → Execute:
     Execution  → rebuild directly, same session or next cycle
     Design     → re-grill the specific change → rebuild
     New idea   → Door D intake → full pipeline
     Promote    → spec → tech-lead via kanban
     Shelve     → mark shelved in portfolio.md + idea-bank.md
  → Return prototype to "Awaiting Review" (for execution/design)
  → Track iteration count in portfolio.md
```

## Rules

- **Builder owns iterations.** The builder built the prototype — the builder iterates it. No kanban task to tech-lead for prototype changes. Tech-lead only gets involved on promotion to production.
- **No dossier/verify for iterations.** The prototype already has a verified dossier. Only update the dossier if a design pivot introduces entirely new market claims (different competitor, different audience, different pricing model) — and in that case, re-verify ONLY the new claims.
- **Re-grill is scoped.** When feedback is design-level, grill the SPECIFIC change — not the whole idea from scratch. "The monetization model is wrong" grills monetization, not the entire product.
- **Iteration count matters.** If a prototype goes through 5+ iterations without promotion, flag it — either it's converging (good) or thrashing (needs a design conversation with the user).
- **Never spin silently.** If feedback is ambiguous, ask the user. Don't guess.

## Automated pipeline integration

The pipeline cron (Phase 8) processes feedback from two sources:
1. **Direct chat** — user tells builder directly ("change X")
2. **Kanban comments** — user comments on the build task. The pipeline's urgent-condition check catches new comments and triggers this skill.

When processing kanban feedback automatically, the builder:
1. Reads the comment
2. Triages it (execution / design / new / promote / shelve)
3. Executes
4. Comments back on the kanban task with what was done
