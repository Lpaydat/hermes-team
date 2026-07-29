---
name: project-kickoff-spec
description: "Part 2 of project kickoff — synthesize spec from grill decisions, route through architect gate, decompose into tickets, set up project infrastructure. Use when grill decisions exist (project-kickoff-grill completed). GATE: grill decisions file must exist before proceeding."
---

# Project Kickoff — Spec Pipeline

You own the flow from "grill decisions exist" to "work is routed to specialists." This is Part 2 of the project kickoff pipeline. Part 1 (`project-kickoff-grill`) must have completed.

The leading word is _tracer-bullet_: each ticket is a thin end-to-end slice that proves a path through the system.

## Gate: grill decisions must exist

Before doing anything, check for existing grill decisions. The builder's grill
covers product and business decisions; the production spec fills implementation
gaps. Accept grill decisions from either source.

Check these locations (in order):
1. `~/projects/<slug>/.driver/grill/decisions.md`
2. `~/projects/<slug>/.context/grill/decisions.md`
3. `~/projects/<slug>/context/*.md` (builder's per-branch grill output)

If grill decisions exist (from any source): proceed. The product decisions are
settled — synthesize the spec from them. Do NOT re-grill product decisions that
are already locked.

If grill decisions do NOT exist: STOP. Tell the user the grill hasn't run yet.
Load `project-kickoff-grill`. Do not proceed to spec without grill decisions.

**Conditional re-grill:** If the user raises new concerns during promotion that
challenge existing grill decisions (e.g., "actually, I want to add offline
support" or "I'm not sure about the pricing model"), load `project-kickoff-grill`
and grill ONLY the new concerns. Do not re-litigate settled decisions.

## Step 1: Write the spec

Load `to-spec`. Synthesize from the grill decisions — do NOT re-interview the user.

Write to `<project-dir>/PRD.md`. Publish as a beads epic with `ready-for-agent`.

**Priority pitfall:** `bd create --priority` rejects words like "high"/"medium"/"low". Use `P0`-`P4`.

**Completion criterion:** spec published as beads epic, PRD.md committed to repo.

## Step 2: Architect gate

Load the `architect-gate` skill. It owns the design card creation, waiting for completion, and reading the design output. The skill is the single source of truth — it includes sequencing warnings and gate-card handling.

**Completion criterion:** architect design card completed, gate cards surfaced to the human, design doc + ADRs published.

## Step 3: Decompose into tracer-bullet tickets

Load `to-tickets`. Break the spec into _tracer-bullet_ slices — each delivers end-to-end value.

Create each ticket as a bead with acceptance criteria and `ready-for-agent`. Link dependencies with `bd link`.

**Completion criterion:** every slice is a bead with acceptance criteria and `ready-for-agent`. Dependencies linked.

## Step 4: Project infrastructure

Run in parallel with Steps 2-3:

```bash
hermes kanban boards create <slug>
mkdir -p ~/projects/<slug> && cd ~/projects/<slug> && git init && bd init
hermes kanban boards switch <slug>
```

Register in `active-projects.json` AFTER the architect gate is complete (see `architect-gate` skill for sequencing).

**Monorepo pitfall:** If the project has frontend + backend, include the directory path in EVERY bead description: "React scaffold **in `frontend/`**". Without it, code lands in repo root.

## Step 5: Close the PRD bead

```bash
bd close <prd-bead-id>
```

If it stays `open`, `bd ready` shows it as dispatchable — tech-lead tries to implement the PRD itself.

**Completion criterion:** PRD bead is closed. Only slice beads remain open.

## Failure modes

- **Proceeding without grill decisions.** The gate exists because specs written from unchallenged discussion have holes. If grill decisions don't exist, go back to Part 1. Don't guess what was decided.
- **Auto-resolving gate cards as a dispatched worker.** Background PO sessions resolve architect gate cards in minutes without consulting the human. Gate cards are HUMAN decisions — surface them, don't resolve them.
- **Registering in active-projects.json too early.** The workflow engine dispatches the moment it sees `ready-for-agent` beads. Register AFTER the architect gate is complete.
- **Using `kanban_chains` for dispatch.** When working the dispatch card (via `dev-dispatch` skill), use `kanban create --assignee tech-lead`. Do NOT use `kanban_chains` — it spawns developer cards directly, bypassing tech-lead.
- **Dispatching architect before grill+spec complete.** The architect runs on the spec. If you dispatch the architect card before the spec is finalized (after grill), the architect produces a full design based on the weaker pre-grill version. Grill → spec → architect, in that order.

## References

- `references/monorepo-setup.md` — directory structure, .gitignore, old-repo-as-reference
- `references/premature-dispatch-recovery.md` — cleanup when workflow engine auto-dispatches before design is complete
- `references/skill-enforcement-layers.md` — enforcement design for making PO follow the skill pipeline
