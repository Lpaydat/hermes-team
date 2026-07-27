---
name: project-kickoff-spec
description: "Part 2 of project kickoff — synthesize spec from grill decisions, route through architect gate, decompose into tickets, set up project infrastructure. Use when grill decisions exist (project-kickoff-grill completed). GATE: grill decisions file must exist before proceeding."
---

# Project Kickoff — Spec Pipeline

You own the flow from "grill decisions exist" to "work is routed to specialists." This is Part 2 of the project kickoff pipeline. Part 1 (`project-kickoff-grill`) must have completed.

The leading word is _tracer-bullet_: each ticket is a thin end-to-end slice that proves a path through the system.

## Gate: grill decisions must exist

Before doing anything, verify:

```
~/projects/<slug>/.driver/grill/decisions.md exists AND contains locked decisions
```

If it does not exist or is empty: STOP. Tell the user the grill hasn't run yet. Load `project-kickoff-grill`. Do not proceed to spec without grill decisions — a spec written from unchallenged discussion will have holes that surface during implementation when they're 10x more expensive to fix.

For migrations: also verify the old → new field mapping table exists in the grill decisions file.

## Step 1: Write the spec

Load `to-spec`. Synthesize from the grill decisions — do NOT re-interview the user.

Write to `<project-dir>/PRD.md`. Publish as a beads epic with `ready-for-agent`.

**Priority pitfall:** `bd create --priority` rejects words like "high"/"medium"/"low". Use `P0`-`P4`.

**Completion criterion:** spec published as beads epic, PRD.md committed to repo.

## Step 2: Architect gate

If the project involves ANY technical decisions (stack, data model, sync strategy, deployment), create a design card for the architect.

Create a kanban card (`assignee: architect`) with:
- **Spec link** — path to the PRD
- **Grill transcript** — paste key decisions and resolved stress scenarios (the architect doesn't have your conversation)
- **Settled decisions** — explicitly list what was decided in the grill so the architect doesn't re-litigate
- **Open technical questions** — anything the grill couldn't answer
- **Stakes** — `low` / `standard` / `high`

Wait for the architect to complete. Read the design output (design doc + ADR series). Surface any gate cards for the user — do NOT auto-resolve them.

**Gate card rule:** Gate cards are owner decisions, not PO decisions. When the architect assigns a gate card to `product-owner`, the PO's job is to surface it to the human (comment, block) — NOT to resolve it. A dispatched PO worker has no authority to make product decisions on the user's behalf.

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

Register in `active-projects.json`.

**CRITICAL sequencing:** Do NOT add `ready-for-agent` to beads until Step 2 (architect gate) is complete. The moment you register in `active-projects.json`, the workflow engine begins checking beads every tick. If beads have `ready-for-agent`, the engine dispatches immediately — before design is finalized.

Correct order:
1. Create board + beads WITHOUT `ready-for-agent`
2. Run architect design + resolve gate cards
3. Apply owner decisions to ADRs
4. ONLY NOW: add `ready-for-agent` to beads AND register in `active-projects.json`

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
