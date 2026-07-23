# Prototype Deliverable Requirements

Every prototype produced by the builder pipeline MUST include:

## Required Files

### 1. `index.html`
- Single-file, zero dependencies, works offline by opening directly
- Interactive clickable demo showing the product's core value

### 2. `README.md` (REQUIRED — no exceptions)
Must contain these sections:
- **What This Is** — one paragraph, plain language, no jargon
- **The Problem** — what pain it solves, who has it, what they do today instead
- **Core Features** — 3-7 capabilities, each traceable to a pain point
- **How to View/Test** — exact command (`open index.html`) + step-by-step interactive walkthrough
- **Grill Decisions** — table of locked decisions (D1, D2, ...) with titles and values
- **Dossier** — path to `~/vault/ventures/ideas/<slug>.md`

### 3. `grill-decisions.md` (or `design-decisions.md`)
- Full grill output with all branches, questions, answers, and locked decisions

## Quality Bar

- The README is how the founder reviews the prototype. Without it, the prototype is invisible.
- If only index.html exists without README.md, the prototype is INCOMPLETE.
- Do not mark the kanban card as done until all three files exist.
