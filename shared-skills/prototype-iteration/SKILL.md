---
name: prototype-iteration
description: "Process user feedback on built prototypes — triage feedback type and execute the iteration."
disable-model-invocation: true
---

# Prototype Iteration

Triage user feedback on built prototypes into one of five paths and execute. The triage is the whole skill — the feedback type determines everything downstream.

## Triage

| Feedback type | Signal | Action |
|--------------|--------|--------|
| **Execution** | "Fix X", "add Y", "this is broken", "make it faster" | Rebuild directly. No grill, no dossier. |
| **Design** | "Wrong audience", "monetization is off", "feature set isn't right" | Re-grill the specific change. Then rebuild. |
| **New idea** | Feedback introduces an entirely different product | Door D intake → full pipeline (dossier → verify → grill → build). |
| **Promote** | "Ship it" | Run `project-promotion` skill: create `~/projects/<slug>/`, copy context, write spec, dispatch to PO. |
| **Shelve** | "Not right now" or silence | Mark shelved in portfolio.md + idea-bank.md. |

After execution or design iterations, return the prototype to "Awaiting Review" and increment the iteration count in portfolio.md.

## Rules

- **Builder owns iterations.** The builder built the prototype — the builder iterates it. PO only gets involved on promote.
- **No dossier/verify for iterations.** Only if a design pivot introduces entirely new market claims — then re-verify ONLY the new claims.
- **Re-grill is scoped.** Grill the specific change, not the whole idea.
- **5+ iterations without promotion → flag.** Converging (good) or thrashing (needs a design conversation).

## Interactive feedback (Stage 4)

This skill loads during interactive review — user reviews prototype and gives feedback to builder:
1. **Direct chat** — user tells builder directly
2. **Kanban comments** — on completed build tasks

The feedback loop is NOT part of the pipeline cron (Stage 1). It happens in interactive builder sessions when the user initiates review.
