---
name: report-to-base
description: Use when you discover a bug, missing skill, permission gap, or improvement opportunity in the BASE profile or the cloning/transform process itself — anything the base profile maintainer could fix by editing base's skills, SOUL template, config defaults, or cloning scripts. Sends structured feedback as a kanban task on the shared board.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [meta, feedback, base-profile, cloning, kanban, improvement]
    related_skills: [transform]
---

# report-to-base — send feedback about the base profile or cloning process

You are a **cloned** profile (a specialist spawned from `base` via `/transform`). You inherited base's kit, its SOUL template, its cloning pipeline, and its skill catalog. When you hit friction that traces back to **base itself** — not your own work — report it so the next clone doesn't hit the same wall.

## When to use

- A skill you **inherited from base** is broken, outdated, missing steps, or has wrong commands.
- The **`/transform` skill** itself had a gap — a step that should exist doesn't, a permission you needed wasn't configurable, the interview missed something.
- You needed a **capability base doesn't ship** (a skill, a tool, a permission preset) and had to build it yourself — that's a candidate for promoting into base.
- The **cloning process** produced a bad result: bundled-skill pollution came back, a marker file went missing, the skill triage in transform was ambiguous.
- You discovered a **permission/approval** configuration that every clone of your role type will need, and it should be a transform preset instead of a manual fix.
- A **base convention** (naming, directory layout, config key) was unclear or undocumented and cost you time.

## When NOT to use

- Bugs in **your own** specialist skills — those are your problem, not base's.
- Feature requests for **your** role — those go to your operator, not base.
- General Hermes Agent bugs (core tools, CLI, gateway) — those are upstream (`hermes` repo issues), not the base profile. Use this skill only for things the base profile *maintainer* can fix.

## How to report

Create **one kanban task** per discrete issue on the shared board. The base profile's maintainer (the operator who runs `base`) picks these up.

### Step 1 — Confirm base is the right target

Ask: *could the base profile maintainer fix this by editing base's skills, SOUL template, config defaults, or cloning scripts?* If yes, continue. If the fix lives in the Hermes core repo or in your own specialist files, do not use this skill.

### Step 2 — Classify the feedback

Pick **one** category. It drives how the maintainer triages:

| Category | Slug | Example |
|---|---|---|
| Broken/buggy inherited skill | `skill-bug` | `transform` step references a command that doesn't exist |
| Missing capability in base | `missing-capability` | No skill for X; every clone of my role will need it |
| Transform/cloning gap | `transform-gap` | `/transform` didn't let me configure permissions |
| Permission/approval gap | `permission-gap` | My role needs `approvals.mode: smart` but transform didn't offer it |
| Stale/outdated content | `stale` | Inherited skill references a deprecated config key |
| Documentation/convention gap | `docs-gap` | Convention for X is undocumented; cost me 20 min |

### Step 3 — Create the kanban task

Use the `kanban_create` tool (NOT `hermes kanban create` — the tool API works across all terminal backends). Target the **`hermes-hq`** board (the shared board where base lives). Assign to **`base`**.

```
kanban_create(
  title="[<category-slug>] <one-line summary>",
  assignee="base",
  board="hermes-hq",
  body=<the structured report — see template below>,
)
```

**Title format:** `[{category}] {short summary}` — e.g. `[transform-gap] /transform has no permission configuration step`.

### Step 4 — Body template (fill every field)

Use this exact structure in the `body`. The maintainer reads these in bulk, so consistency matters.

```markdown
## Feedback from clone: <your-profile-name>

**Category:** <category-slug>
**Severity:** blocker | high | medium | low
**Discovered during:** <what you were doing when you hit this — e.g. "/transform Step 3", "first real task", "skill triage">

### What happened
<2-4 sentences. Concrete: what you tried, what you expected, what you got.>

### What's wrong in base
<1-2 sentences naming the exact base artifact at fault — a skill name + section, a SOUL line, a transform step, a config default, a missing file. Be specific: "transform SKILL.md Step 3(d)" not "the transform skill".>

### Suggested fix
<Concrete, actionable. "Add a Step 4.5 to transform that..." / "Ship a <name> skill under <category> in base" / "Change the default X to Y". If you already built a workaround in your own profile, say so and attach the approach — the maintainer can promote it.>

### Repro / evidence
<Commands, file paths, error messages, or the exact text that was wrong. If a skill had a wrong command, paste it here.>
```

### Step 5 — Completion criterion

The task is created when `kanban_create` returns a task id. Report that id back to your operator (or log it in your session) so there's a trace. **Do not** wait for the maintainer to resolve it — that happens on their timeline, on the `hermes-hq` board. Your job is to file an actionable report, not to track it to closure.

## Pitfalls

1. **Filing core Hermes bugs as base feedback.** If the bug is in a core tool (`terminal`, `file_tools`, `delegate_task`), the CLI, or the gateway, it belongs in the Hermes repo's issue tracker — not on the base board. This skill is for things the base *profile maintainer* can fix by editing profile files.

2. **Vague reports.** "Transform is confusing" is useless. "Transform Step 3(d) says to verify against `$HERMES_HOME/skills/` but never says what to do if a skill appears in both a category dir AND at top-level" is actionable. Name files, sections, line content.

3. **Batching unrelated issues.** One issue per task. If you hit three unrelated gaps during transform, file three tasks. The maintainer triages by category and severity; mixing them buries the important one.

4. **Filing from the wrong board.** Always target `hermes-hq` with `board="hermes-hq"`. A task created on your project's own board will never be seen by the base maintainer.

5. **Forgetting to include your profile name.** The maintainer may need to inspect your profile to reproduce. The `## Feedback from clone:` header must name you. (For "it's your own specialist bug, not base's" — see *When NOT to use* above; don't file it here.)

## Verification

- [ ] Category is one of the six slugs above (no free-form categories).
- [ ] Title starts with `[<category-slug>]`.
- [ ] `assignee="base"`, `board="hermes-hq"`.
- [ ] Every body field is filled (no "TBD" or empty sections).
- [ ] "What's wrong in base" names a **specific base artifact** (file/step/line), not a vibe.
- [ ] "Suggested fix" is concrete enough that the maintainer could implement it without asking you a follow-up question.
- [ ] Task id returned by `kanban_create` is noted for your operator.
