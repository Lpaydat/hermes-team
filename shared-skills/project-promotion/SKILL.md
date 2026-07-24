---
name: project-promotion
description: "Promote a prototype to production — create project structure, copy context, dispatch to PO."
disable-model-invocation: true
---

# Project Promotion

When the user says "promote this" / "ship it", this skill handles the handoff from builder to PO. It creates the project structure, copies context, and dispatches to PO. PO owns production from here — not tech-lead directly.

## Project structure

Every promoted project already lives at `~/projects/<slug>/` (the builder created it during prototype build). Promotion adds production structure:

```
~/projects/<slug>/
├── .context/
│   ├── dossier.md          ← copied from ~/vault/ventures/ideas/<slug>.md
│   ├── grill/              ← per-branch grill decisions (already here from build)
│   └── verification.md     ← fact-check report
├── prototype/              ← builder's working demo (already here from build)
├── src/                    ← production code (PO → tech-lead → developer)
├── tests/
├── STATUS.md               ← project dashboard (PO maintains this)
├── README.md               ← what this is, current state
└── (language-specific files: package.json, pyproject.toml, go.mod, etc.)
```

Structure adapts to the stack. Only `.context/`, `STATUS.md`, and `README.md` are fixed.

## Promotion steps

1. **Copy dossier + verification** — `cp ~/vault/ventures/ideas/<slug>.md ~/projects/<slug>/.context/dossier.md` and `cp ~/vault/ventures/ideas/<slug>-verification.md ~/projects/<slug>/.context/verification.md` (if verification exists)
2. **Copy grill context** — `cp ~/projects/<slug>/context/*.md ~/projects/<slug>/.context/grill/` (the per-branch grill decisions are the prototype blueprint)
3. **Initialize STATUS.md** from template at `templates/STATUS.md`
4. **Initialize git** (if not already) — `cd ~/projects/<slug> && git init && git add -A && git commit -m "promote: <slug> prototype to production"`
5. **Create project kanban board** — `hermes kanban create --board <slug>`
6. **Dispatch to PO** (NOT tech-lead) — create kanban task assigned to `product-owner` with board `<slug>`. Body: "Take this prototype to production. Read .context/grill/ for locked decisions, .context/dossier.md for market context, prototype/ for the working demo. You own: design goals, epics, milestones, beads tickets, dependencies. You control tech-lead for implementation and verifier for review."
7. **Update portfolio** — move from "Awaiting Review" to "In Production" in `~/vault/ventures/portfolio.md`.

## After promotion

- Builder is done. PO owns the project from here.
- PO creates spec, epics, milestones, beads tickets — NOT the builder.
- PO dispatches to tech-lead for implementation, verifier for review.
- PO maintains STATUS.md.

## Why PO, not tech-lead

PO is the project owner for production. PO creates goals/epics/milestones/beads, controls tech-lead and verifier. Tech-lead is a worker under PO's direction — not the entry point. Builder dispatches to PO, PO controls tech-lead.

## Pitfall: spec/tickets timing

Specs, epics, milestones, and beads tickets are PRODUCTION artifacts — created by PO during promotion, NOT before the prototype. The dossier + grill decisions are the prototype blueprint. Don't spec a prototype you might shelve. Invest in formal planning only for prototypes that pass user review.
