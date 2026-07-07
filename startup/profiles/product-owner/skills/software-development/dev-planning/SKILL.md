---
name: dev-planning
description: "Plan dev work with the other party: discuss requirements, write a PRD, decompose into beads. Use when the user or another agent brings a feature idea, bug, or project request, says 'plan this' or 'build this'. Reaches to-prd and to-issues."
---

# Dev Planning

You own the WHAT. Tech-lead owns the HOW — never write code, create dev/verifier cards, or touch the harness.

The leading word is _tracer-bullet_: each bead is a thin end-to-end slice (code + tests) that proves a path through the system, not a horizontal layer.

## Steps

### 1. Discuss with the other party

The other party may be a human user or another agent profile. Either way:

- Ask one question at a time with a recommended answer attached
- Goal: extract enough context to write a PRD — problem, audience, constraints, success criteria
- If the other party is an agent, discuss via kanban comments or chat — same flow

**Completion criterion:** you can state the problem, the user, and what "done" looks like in 2-3 sentences.

### 2. Write the PRD

Load the `to-prd` skill. Synthesize what you learned — do NOT re-interview.

Write the PRD to `<project-dir>/PRD.md`. Publish it as a bead with `ready-for-agent`.

Review the PRD with the other party before proceeding.

**Completion criterion:** PRD bead exists in bd, PRD.md committed to the repo, other party has reviewed.

### 3. Decompose into tracer-bullet beads

Load the `to-issues` skill. Break the PRD into _tracer-bullet_ slices — each delivers end-to-end value, not horizontal layers.

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

## Reference

- [references/workflow-architecture.md](references/workflow-architecture.md) — the full pipeline: PO plans → cron detects ready beads → PO dispatch card → PO creates tech-lead cards → kanban_delegate → dev → verifier → merge
