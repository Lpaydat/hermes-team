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

**Completion criterion:** design card created on the project board with `assignee: architect`.

## Step 2 — Respond to architect queries

The architect runs `design-council` (research + peer fan-out, convergence loop, ADR recording) autonomously. It may launch an RPC call to you with product-ambiguous questions — answer immediately with product context.

Surface any architect **gate cards** to the human. Gate cards are owner decisions, not PO decisions.

**Completion criterion:** architect design card reaches `done` status.

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
