---
name: architect-gate
description: "Hand off a spec to the architect for production design. Use when a project needs production-grade architecture (tech stack, data model, module boundaries) before code is written. Shared across all PO workflows."
disable-model-invocation: true
---

# Architect Gate

Every production project needs architecture design before tickets are cut. The prototype's tech stack was for a demo — production needs a real design.

## Step 1 — Create the design card

Create a kanban card (`assignee: architect`) on the project board with:

- **Spec link** — path to the PRD/spec
- **Context summary** — key decisions and constraints from grilling (the architect doesn't have your conversation)
- **Settled decisions** — what was already decided so the architect doesn't re-litigate
- **Open technical questions** — anything you couldn't answer
- **Stakes** — `low` (prototype/internal), `standard` (normal feature), `high` (revenue/safety/hard-to-reverse)

## Step 2 — Wait

The architect runs `design-council` (research + peer fan-out, convergence loop, ADR recording). It may need PO input on product-ambiguous decisions — it will launch an RPC call to you. Answer immediately with product context.

If the architect assigns a **gate card** to you, surface it to the human — do NOT auto-resolve it. Gate cards are owner decisions, not PO decisions.

## Step 3 — Read the design output

When the architect card completes, read the completion metadata:
- Design doc path
- ADR series (list of ADR files)
- Tech stack decisions
- Data model decisions
- Open questions for PO

## Completion criterion

Architect design card completed, gate cards surfaced to the human, design doc + ADRs published.

## CRITICAL sequencing

Do NOT add `ready-for-agent` to beads until this gate is complete. The moment you register in `active-projects.json`, the workflow engine begins checking beads every tick. If beads are ready before design is finalized, the engine dispatches un-designed work.
