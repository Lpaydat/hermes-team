---
name: dev-planning
description: "Plan dev work: discuss requirements, write a PRD, decompose into beads. Use when the user or another agent brings a feature to build. Reaches to-spec and to-tickets."
---

# Dev Planning

You own the WHAT. Tech-lead owns the HOW — never write code, create dev/verifier cards, or touch the harness.

The leading word is _tracer-bullet_: each bead is a thin end-to-end slice (code + tests) that proves a path through the system, not a horizontal layer.

## Steps

### 1. Discuss with the other party

The other party may be a human or an agent. Force-load `grill-with-docs` (`grilling` + `domain-modeling`) and interview them to extract enough context to write a PRD — problem, audience, constraints, success criteria.

**Completion criterion:** you can state the problem, the user, and what "done" looks like in 2-3 sentences.

### 2. Write the PRD

Load the `to-spec` skill. Synthesize what you learned — do NOT re-interview.

Write the PRD to `<project-dir>/PRD.md`. Publish it as a bead with `ready-for-agent`.

Review the PRD with the other party before proceeding.

**Completion criterion:** PRD bead exists in bd, PRD.md committed to the repo, other party has reviewed.

### 3. Decompose into tracer-bullet beads

Load the `to-tickets` skill. Break the PRD into _tracer-bullet_ slices — each delivers end-to-end value, not horizontal layers.

Run autonomously. Do NOT quiz the other party on granularity — if the decomposition is wrong, verification failures will surface it.

Create each slice:

```bash
bd create "<title>" -d "<description>" --acceptance "<AC1>. <AC2>." -l "ready-for-agent"
```

Link dependencies with `bd link <child-id> <parent-id>` — NOT `--deps` (silently ignored).

Review the bead list + dependency graph with the other party.

**Completion criterion:** every slice is a bead with acceptance criteria and `ready-for-agent`. Dependencies linked via `bd link`. Other party has reviewed.

### 4. Close the PRD bead

```bash
bd close <prd-bead-id>
```

If it stays `open`, `bd ready` shows it as dispatchable — tech-lead tries to "implement" the PRD itself.

**Completion criterion:** PRD bead is `closed`. Only slice beads remain `open`.

## Rules

- Create ALL beads in ONE session. Beads are the persistent memory of the plan.
- Each bead must have acceptance criteria — the verifier checks these independently.
- Use `bd link`, not `--deps`.
- The other party reviews at two points: after PRD (step 2) and after beads (step 3).
- Never create tech-lead/dev/verifier cards — dispatch happens via the workflow engine cron.
- Be _decisive_. When the other party gives a clear instruction, execute it. When the natural design has a single path, state it and move on — creating options where none exist is unnecessary complexity.
- Create the project board before adding it to `active-projects.json`: `hermes kanban boards create <slug> --default-workdir <path>`. Then add `{name, path, board}` to the config.

## Reference

- [references/workflow-architecture.md](references/workflow-architecture.md) — the full pipeline: PO plans → cron detects ready beads → PO dispatch card → PO creates tech-lead cards → kanban_delegate → dev → verifier → merge. Includes per-board model.
