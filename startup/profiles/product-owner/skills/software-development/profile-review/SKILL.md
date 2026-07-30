---
name: profile-review
description: Review and audit a Hermes specialist profile's identity (SOUL.md) and configuration (config.yaml) for correctness — line-test compliance, skill-index liveness, enforcer-pin soundness, and charter↔skill consistency. Use when asked to "review the architect/qa/tech-lead profile", "audit a profile", "check enforcer pins", or "check SOUL.md compliance". Works across all profiles in ~/.hermes-teams/startup/profiles/<name>/.
---

# Profile review

A specialist profile is three coupled layers: a **charter** (SOUL.md specialty block), an **operational skill** (the SKILL.md the specialty indexes), and **config** (config.yaml: which skills are on, which are mandatory, which plugins run). A review that checks any one layer in isolation misses bugs that live in the *coupling* between them. This session found a completely bricked skill by cross-checking config against config — no single-file read would have caught it.

## What to read for any profile

1. `<profile>/SOUL.md` — the specialty block (between `<!-- SPECIALTY:BEGIN -->` and `<!-- SPECIALTY:END -->`).
2. Every skill the specialty indexes — load each via `skill_view`.
3. `<profile>/config.yaml` — three sections: `skills.disabled`, `skill_enforcer.mandatory`, `plugins.enabled`.

## Checks (run all five)

### 1. Charter line-test (writing-great-soul compliance)

Apply the line test from `writing-great-soul` to every line of the specialty block. The most common failures:

- **Inlined procedure** — a charter line names a *tool call* or *step* (`kanban_chains for fan-out`) instead of a stance. These go stale the moment the skill's procedure changes. Keep the stance; drop the tool name.
- **Tool-name staleness** — a stance line that names a specific tool (`Use the board, not subagents. kanban_chains for design fan-out`) where the underlying skill has since refactored to a different mechanism (e.g., `loop_engine`). The stance is correct but the tool reference is a **stale contradiction** with the skill. Check every tool name in the charter against the skill — if the skill says "do not hand-call X, the engine does that," the charter must not tell the agent to use X.
- **Arrow-notation in skill index** — an index entry like `adversarial-review — when you receive a review card (3-stage: execute → fan-out probes → synthesize verdict → merge)` uses ordered arrows (`→`) that a reader can follow as a sequence without loading the skill. This is a procedure, not a pointer. Fix: replace arrows with comma-separated topics (`execute, probe fan-out, verdict synthesis, merge gate`) that say *what* the skill covers, not the *order to do it in*.
- **Over-specified skill index entry** — an index entry that describes *how the skill works* instead of *when to reach for it*. If a reader could follow the entry without loading the skill, it's a procedure, not a pointer.

### 2. Charter ↔ skill consistency

Echo every durable claim in the charter against the indexed skill. The highest-value echoes:

- "Never X" boundaries (never implement, never read code) — must match the skill's stance.
- Tool-routing claims — if the charter says "use tool T" and the skill says "do NOT hand-call tool T" (e.g. after a refactor to an engine), that's a **direct contradiction** and the charter is the stale copy. The skill is authoritative; the charter must be fixed.

### 3. Skill-index liveness (each entry is loadable)

For every skill named in the specialty's "Skill index" section, confirm it is **not** in that profile's `skills.disabled`. A charter that indexes a disabled skill is a broken pointer: `skill_view` refuses disabled skills (`success: false`), so the agent can never load what the charter tells it to reach for. Cross-check each index name against the `disabled` list.

### 4. Enforcer-pin soundness (the dead-pin check) — load-bearing

**A skill listed in BOTH `skills.disabled` AND `skill_enforcer.mandatory` (same config.yaml) is a silent dead pin — it enforces nothing.** This is the single most damaging config bug because it looks correct at a glance (the pin IS there) and produces no error (the load just fails softly).

**This is not theoretical — it was found in production.** The QA profile's `live-testing` skill was in BOTH lists simultaneously after a config template copy. The skill was bricked: the agent couldn't load it, the enforcer couldn't enforce it, and the SOUL.md skill index pointed to a skill the agent was configured to refuse. The only way to detect it is to diff the two lists against each other — no single-file read catches it.

Mechanism (traced in source):
- `skills_tool.py skill_view()` checks `_is_skill_disabled()` and returns `{"success": false, "error": "Skill 'X' is disabled."}` for any disabled skill.
- The `skill_enforcer` plugin (`plugins/skill_enforcer/__init__.py`) only reformats results where `data.get("success")` is truthy — on `success: false` it returns the error unchanged, so the directive framing never fires.
- `agent/prompt_builder.py` excludes disabled skills from the system-prompt catalog, so the agent never auto-suggests them either.

Net effect: the mandatory pin is inert. Fix: remove the skill from `skills.disabled` (or, if disabling is intentional, remove it from `mandatory`).

How this happens: copying a profile config from a template lands the skill in `disabled` (templates disable everything the source profile doesn't use); later, someone adds it to `mandatory` without removing it from `disabled`. Always diff the two lists against each other — run this check for EVERY profile, not just ones you suspect.

### 5. Skill sediment

Check the indexed skill's own body for stale pitfalls or sediment that predates a refactor: unnumbered bullet lists, pitfall numbering that breaks (8, 9, then unnumbered, then 12), or pitfalls that describe a *different* skill's domain (e.g. a "use clarify for design" pitfall inside a live-testing skill). These accumulate when skills are copied or edited in place.

## Output shape

Present findings as a table: profile × (pass/fail) × severity, then a per-finding block with the file, line, the exact contradiction, and the one-line fix. Lead with the verdict. Distinguish "verified by reading the file" from "verified by tracing source" — flag the dead-pin check as source-verified because the consequence (zero enforcement) is not visible from the config alone.

## Pitfalls

1. **Reviewing config in isolation.** Reading only config.yaml, or only SOUL.md, catches neither the disabled∩mandatory contradiction (needs both config sections) nor the charter↔skill contradiction (needs both layers). Read all three layers before judging.

2. **Declaring a pin "live" without checking the disabled list.** A `skill_enforcer.mandatory` entry that is also `disabled` is the bug, not the fix. Always diff the two lists.

3. **Trusting the enforcer to force-load.** The enforcer only *reframes* a `skill_view` result into directive tone — it never force-loads a skill and never overrides `disabled`. Do not assume "mandatory" means "will be loaded regardless of other config."

4. **Skipping the skill's pitfalls/numbering.** Sediment hides at the bottom of long skills. Read the full file, including the pitfalls tail, not just the procedure body.
