---
name: project-promotion
description: "Promote a prototype to production — create project structure, write spec, hand off to tech-lead."
disable-model-invocation: true
---

# Project Promotion

When the gate approves a prototype ("ship it" / "promote this"), this skill handles the handoff from builder to tech-lead. It creates the project structure, copies context, writes the production spec, and dispatches the first tech-lead task.

## Project structure

Every promoted project lives at `~/projects/<slug>/`:

```
~/projects/<slug>/
├── .context/
│   ├── dossier.md          ← copied from ~/vault/ventures/ideas/<slug>.md
│   ├── spec.md             ← production spec (written on promotion)
│   ├── grill-summary.md    ← exported grill decisions
│   └── verification.md     ← fact-check report
├── prototype/              ← builder's working demo (may be gitignored)
├── src/                    ← production code (PO controls, tech-lead/developer writes)
├── tests/
├── STATUS.md               ← project dashboard (milestones, epics, health)
├── README.md               ← what this is, current state
└── (language-specific files: package.json, pyproject.toml, go.mod, etc.)
```

Structure adapts to the stack. Only `.context/`, `STATUS.md`, and `README.md` are fixed. Tech-lead creates `src/`, `tests/`, etc. based on the language.

## Promotion steps

1. **Create project directory**
```bash
mkdir -p ~/projects/<slug>/.context
mkdir -p ~/projects/<slug>/prototype
cd ~/projects/<slug>
git init
```

2. **Copy context from pipeline**
```bash
cp ~/vault/ventures/ideas/<slug>.md .context/dossier.md
cp ~/vault/ventures/ideas/<slug>-verification.md .context/verification.md 2>/dev/null
# If a grill summary exists:
cp /tmp/grill-<slug>/SUMMARY.md .context/grill-summary.md 2>/dev/null
```

3. **Copy prototype**
```bash
# Move or copy the prototype code into prototype/
cp -r <prototype-location>/* prototype/
```

4. **Write production spec** — `.context/spec.md` from the dossier's three pillars + grill decisions. This is the blueprint tech-lead receives. Include:
   - Core features (from dossier, refined by grill)
   - User stories (from dossier)
   - Technical architecture sketch (from dossier, refined by grill)
   - Acceptance criteria per feature
   - What the prototype proved vs what production needs to solve

5. **Initialize STATUS.md** from template at `~/.hermes-teams/shared-skills/project-promotion/templates/STATUS.md`. Set stage to "production", first milestone to "MVP Core".

6. **Create project kanban board**
```bash
hermes kanban create --board <slug>
```

7. **Dispatch to product-owner (PO)** — create a kanban task:
   - Title: "Production build: <project name>"
   - Assignee: product-owner
   - Board: <slug>
   - Body: "Build production version of <project>. Spec at ~/projects/<slug>/.context/spec.md. Prototype for reference at ~/projects/<slug>/prototype/. STATUS.md is the project dashboard. You own this project: create epics, milestones, beads tickets, dependencies. Control tech-lead for implementation, verifier for review."
   - PO takes it from here — creates design goals, epics, milestones, beads issues, and dispatches to tech-lead/verifier as needed.

8. **Update portfolio** — move from "Awaiting Review" to "In Production" in `~/vault/ventures/portfolio.md`.

## After promotion

- Builder is done. PO owns the project from here.
- PO creates spec, epics, milestones, beads tickets with dependencies.
- PO controls tech-lead (implementation), verifier (review), debugger (fixes).
- PO owns STATUS.md.
- The user reviews production milestones via STATUS.md and the project kanban board.
