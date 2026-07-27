# SOUL.md Refactor Design

Structural analysis and design for refactoring Hermes profile SOUL.md files:
make SOUL.md clean/generic (identity only), move all actions/instructions to skills.

Produced 2026-07-27 during the profile-refactor planning session.

## Current structure — every SOUL.md has 5 blocks

| Block | Lines | Identical across profiles? | What it is |
|-------|-------|---------------------------|------------|
| Base intro | 1 | Yes | "You are an unspecialized base agent..." |
| Constitution | 9 | Yes (FROZEN) | The 4 invariants — never edit |
| Until-specialized | 4 | Yes | Bootstrap instructions |
| SPECIALTY | 50-130 | No (profile-specific) | Identity + instructions mixed together |
| Team coordination | 10 | Yes | Kanban board coordination rules |

16 profiles × ~60 lines average = 921 total lines. ~530 are copy-pasted duplicates.

## The problem: SPECIALTY mixes identity with instructions

Every profile's SPECIALTY block contains two categories jammed together:

**Identity (5-10 lines):** Who you are, your role, your boundaries.
- "You are the product owner — the single front door for all ideas, bugs, requests."
- "You are the tech lead — you design and run coding loops."
- "NEVER write code" (tech-lead, architect — identity-level constraint)

**Instructions (50-100 lines):** Workflows, step-by-step procedures, pipeline stages, what-to-read tables, grill triggers, architect handoff protocols.
- PO: front-door routing model, tagging convention, discovery/analyze/act/steer, steering state, grill gate section (lines 81-118), architect handoff
- Tech-lead: five-phase loop, contract-first, execute-autonomously, validate-strictly, memory architecture, multi-profile team
- Builder: four-door pipeline, promotion flow, prototype philosophy, HITL rules

The instructions are the bloat. They're procedural knowledge that should live in skills (structured, step-by-step, loadable) not in system-prompt prose (ignorable, unstructured).

## Design principle: SOUL.md = identity, skills = instructions

After refactor, SPECIALTY contains ONLY:
1. **Role statement** — 1-3 sentences: who you are, what you own
2. **Hard identity constraints** — things that define the role boundary ("never write code", "never create untagged tasks", "never auto-resolve gate cards"). These aren't workflow steps — they're who the agent IS. Removing them would change the identity.
3. **Skill pointers** — which skills carry the operational doctrine (e.g., "Load `project-kickoff` for new project pipeline. Load `dev-planning` for feature planning.")

Everything else — pipeline stages, step-by-step procedures, what-to-read tables, grill triggers — moves into skills.

## What's identity vs instruction (the line)

| Content | Identity or instruction? | Where it goes |
|---------|-------------------------|---------------|
| "You are the product owner" | Identity | SOUL.md |
| "Never write code" | Identity (role boundary) | SOUL.md |
| "Never create untagged tasks" | Identity (role boundary) | SOUL.md |
| "Never auto-resolve gate cards" | Identity (role boundary) | SOUL.md |
| Front-door routing model (5 steps) | Instruction | Skill (project-kickoff or dev-planning) |
| Tagging convention | Instruction | Skill |
| Grill gate (when to grill, what it looks like) | Instruction | Skill (project-kickoff already has it) |
| Architect handoff protocol | Instruction | Skill (project-kickoff already has it) |
| Discovery/analyze/act/steer | Instruction | Skill (project-discovery) |
| What-to-read table | Instruction | Skill |
| Steering state (.driver/ files) | Instruction | Skill (project-discovery) |

Rule of thumb: if it's a workflow step or a procedure, it's an instruction. If it's a role boundary that removing would change who the agent fundamentally is, it's identity.

## Constraint: transform skill writes the SPECIALTY block

The `transform` skill (meta, one-shot bootstrap) writes the SPECIALTY block during specialization. If the new design is "SPECIALTY = identity only", `transform` must produce that format. Any refactor of existing profiles should also update `transform` so future specializations produce clean SOUL.md.

## Refactor scope (per-profile analysis)

| Profile | SPECIALTY lines | Estimated identity lines | Instruction destination |
|---------|----------------|------------------------|------------------------|
| product-owner | 100 | ~15 | project-kickoff, dev-planning, project-discovery (already exist) |
| tech-lead | 60 | ~10 | loops-engineering (already exists) |
| builder | 90 | ~10 | builder pipeline skill (needs check if exists) |
| architect | 50 | ~10 | design-council / codebase-design (already exist) |
| Others (scout, researcher, qa, etc.) | 50-80 each | ~5-10 | respective operational skills |

## Sequencing: refactor before enforcement

The workflow enforcement problem (PO skipping to-spec/to-tickets) cannot be solved with stamps/gates while the instructions live in SOUL.md prose. The enforcement layers (see `skill-enforcement-layers.md`) need instructions to live in skills — that's where stamps can be written, that's what the workflow engine can gate on. Refactoring profiles first creates the right home for the enforcement.

## User's refined vision (2026-07-27 discussion)

After reviewing the structural analysis, the user refined the design in three directions:

### 1. Identity should be RICH, not minimal

Identity isn't just "you are the PO." It should include **what that role follows as best practice** in the general nature of the elite of that role. Think of it as the professional ethos — what makes a great product owner great (front-door routing, no duplicate issues, evidence before agreement, grill before committing resources). This is NOT instructions (don't write "step 1, step 2"). It's the character and principles of the role. These are durable, identity-level rules that should persist even if the specific workflow skills change.

### 2. Multiple workflows per profile (NOT one-profile-one-workflow)

A profile can have many workflows it loads and follows depending on the trigger:
- PO: project-kickoff (new project), dev-planning (feature), project-discovery (cron scan), dev-dispatch (bead dispatch)
- Builder: discovery pipeline, grill+build, promotion handoff

One-profile-one-workflow would be as rigid as the current monolithic SOUL.md. The workflows are independent skills loaded on-demand.

### 3. Config-level enforcement over word-bans (THE key insight)

The user's principle: "rather than blocking it by words to ban from some actions, if that actions can be ban in config, that's much better." This means:
- `disabled_toolsets` in config.yaml is the PRIMARY enforcement mechanism (see `skill-enforcement-layers.md` Layer 0)
- SOUL.md text like "never write code" is secondary (identity reinforcement, not the actual gate)
- The PO config already proves this works (browser/delegation/web/kanban_chains removed)

### Dedup decision: keep shared blocks in SOUL.md

The constitution, base intro, and team coordination blocks are duplicated across all 16 profiles. Decision: leave them in SOUL.md rather than extracting to a shared include. Rationale: the blocks are small (constitution=9 lines, team coordination=10 lines), they're the persistent context every profile needs, and extracting adds a dependency for no functional gain. A clean SOUL.md with identity + shared context should be ~40-50 lines.

### Scope: builder + PO first

Pilot the refactor on the two proven profiles (builder + PO pair). Validate the architecture before applying to the other 14 profiles.

### Skills ecosystem finding

Searched `npx skills find` for existing "skills as composable workflows" frameworks. None exist. We're building this ourselves. (See `skill-enforcement-layers.md` for the full finding.)

### Graph engineering research (2026-07-27)

Researched "graph engineering" (exploded on X July 18, 2026 via Peter Steinberger). Read 8 articles (explainx.ai, bemiagent.com, eigent.ai, truefoundry.com, flowtivity.ai, youmind.com, aibuilderclub.com, eliteaiadvantage.com). **Conclusion: NOT applicable to our problem.** Graph engineering is about multi-agent runtime orchestration — nodes = agents, edges = data dependencies, typed transitions, parallel fan-out/fan-in, shared state across agents. It's the layer above loop engineering for wiring multiple agent loops together. Frameworks: LangGraph, AutoGen, LlamaIndex workflows.

Our problem is **single-agent skill composition** — how one profile loads skill A → skill B → skill C in sequence within ONE session. We don't need runtime graph execution or inter-agent state. `kanban_chains` already handles multi-agent orchestration (dev→verify→iterate is a graph).

One principle worth stealing from graph engineering — the **dependency test**: "Does step B actually read step A's output? If no data crosses the boundary, there's no edge — they're independent." This is a good gate for workflow design but doesn't need DAG formalism to express.

### Skill vs workflow distinction (crystallized 2026-07-27)

- **Skill** = one self-contained procedure (e.g., `to-spec` takes conversation → produces a spec). Does ONE thing. No gates on other skills.
- **Workflow** = a skill whose body is "load skill X, check result, load skill Y, with gates between them." Doesn't do work itself — orchestrates skills that do.
- **Structurally identical** — both are SKILL.md files. A workflow is a skill whose content happens to chain other skills.
- **Three real differences:** (1) composition — workflows reference other skills by name; (2) gates — workflows enforce preconditions ("STOP if no grill transcript"); (3) registry — workflows listed in SOUL.md identity.

### `create-workflow` authoring skill (agreed 2026-07-27)

New skill that teaches how to author workflow-skills. Name: `create-workflow` (agreed over `build-workflow`, `skill-flow`, `graph-engineering`). Same relationship as `writing-great-skills` (authors regular skills) → `create-workflow` (authors workflow-skills). Not yet written — next session builds it.

Key authoring concerns it must cover:
- How to chain skills by name (explicit references, not prose)
- How to write gates that actually enforce (not just prompt text)
- The dependency test from graph engineering
- When a workflow is warranted vs just a skill
- Registry format for SOUL.md (workflow name + one-line trigger)

## Pitfall: don't lose the grill gate during refactor

The grill gate currently lives in PO SOUL.md lines 81-118. When moving instructions to skills, the grill gate MUST land in `project-kickoff` (which already has it in Step 2). The refactor should DELETE it from SOUL.md only after confirming `project-kickoff` carries the full grill procedure. Same for the architect handoff (Step 4 in project-kickoff).
