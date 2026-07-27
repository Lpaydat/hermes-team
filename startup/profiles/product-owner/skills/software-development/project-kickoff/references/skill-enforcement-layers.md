# Skill Enforcement Layers

How to make the PO follow the workflow pipeline (to-spec → to-tickets → dev-dispatch) instead of improvising.

## The problem

Skills are opt-in via `skill_view`. Nothing forces the PO to load them. Four failure modes observed:

1. **CLI conversation mode:** PO writes spec by hand, creates beads with `bd create`, never loads `to-spec` or `to-tickets`.
2. **Dispatched worker mode:** PO receives dispatch card that says "Run dev-dispatch" as prose, but uses `kanban_chains` instead — prose is a suggestion, not enforcement.
3. **Skill loaded but ignored:** PO could load `to-tickets`, read it, then create beads manually anyway.
4. **False enforcement claim in SOUL.md (verified 2026-07-27):** SOUL.md stated "The `to-spec` skill enforces this at the tool level: it must refuse to write a spec if no grilling has occurred." Grepping the actual `to-spec` SKILL.md confirmed this is false — zero grill/enforce/refuse/gate keywords exist in the skill. The skill is a read-only symlink (chmod 444) to the Matt Pocock shared-skills pack; it cannot be patched to add enforcement. A false claim of enforcement is worse than no claim: the PO believes a safety net exists and relaxes self-discipline. **The only enforcement that exists today is the PO's own pipeline discipline (loading skills at the right steps).** The layers below are DESIGN goals, none implemented yet.

## The three-layer defense

### Layer 1: Skills leave proof (stamps)

Each workflow skill writes a tiny marker file when it completes successfully:

- `to-spec` → `.driver/.spec-stamp` (timestamp, spec hash, skill version)
- `to-tickets` → `.driver/.tickets-stamp` (bead count, blocking-edge count, skill version)
- `dev-dispatch` → `.driver/.dispatch-stamp` (beads dispatched, assignee must be tech-lead)

No stamp = skill didn't run. Stamps are machine-verifiable, not prose.

**Limitation:** a stamp proves the skill RAN, not that it was FOLLOWED. The stamp is necessary but not sufficient.

### Layer 2: Workflow engine gate (enforcement)

The workflow engine (`workflow-engine.py`) runs before dispatching. Add a validation step:

```python
# PHASE 2: DISPATCH — gated
for each project:
    1. bd ready → find beads with ready-for-agent
    2. Check: .driver/.spec-stamp exists? NO → log, skip dispatch
    3. Check: .driver/.tickets-stamp exists? NO → log, skip dispatch
    4. Check: ready beads have blocking edges in bd? NO → log, skip
    5. All pass → create PO dispatch card with --skills dev-dispatch
```

This is Python — no LLM judgment. It makes dispatch structurally impossible without proof the skills ran.

Also patch the dispatch card creation to force-load the skill:

```python
# Current (broken — prose only):
"--body", f"... Run `dev-dispatch` to create tech-lead cards."

# Fixed (skill forced):
"--skills", "dev-dispatch",  # force-loads the skill into the PO's context
```

### Layer 3: Plugin observer (audit trail)

A Hermes plugin with `post_tool_call` hook can log skill loads to a central audit file. This gives visibility — "was the skill actually loaded?" — but CANNOT block actions because:

- `pre_tool_call` can block tool calls, but only based on tool name + args, not workflow context
- The plugin doesn't know whether `to-spec` should run before `bd create` — that's project-specific workflow knowledge
- Plugins see WHAT tools were called, not WHY or whether the order is correct

Plugin value: cross-referencing stamps (Layer 1) against actual skill loads (Layer 3) in the monthly audit. If a stamp exists but the plugin log shows no `skill_view to-spec` call, the stamp was forged.

### Layer 4: Monthly hygiene audit (drift catch)

A script run by the hygiene watchdog cron that checks every active project:

- Spec stamp exists and hash matches actual spec?
- Tickets stamp exists and bead count matches actual beads?
- Any beads with `ready-for-agent` but no blocking edges (sign of ad-hoc creation)?
- Any dispatched cards assigned to `developer` instead of `tech-lead`?
- `.driver/spec.md` content matches epic bead body? (drift check)

Report violations as a kanban comment on the project's board.

## Why the plugin alone isn't enough

The plugin runs inside the agent's tool stream. It sees tool calls. But it can't know if the workflow order is correct — that requires project context (which beads should have blocking edges, which assignee is correct, whether the spec was grilled). The workflow engine has that context. The plugin doesn't.

**Enforcement belongs in the layer that KNOWS the workflow (engine). Visibility belongs in the layer that SEES the tools (plugin). You need both, for different reasons.**

## Implementation priority

1. **Highest impact:** Workflow engine gate (Layer 2) — blocks dispatch without proof. Pure Python, no LLM.
2. **High impact:** Dispatch card `--skills` flag (Layer 2) — forces dev-dispatch load. One-line patch.
3. **Medium impact:** Skill stamps (Layer 1) — enables the gate. Requires patching each skill (to-spec, to-tickets, dev-dispatch).
4. **Low impact:** Plugin observer (Layer 3) — nice for audit, but the workflow gate is the real enforcement.
5. **Low impact:** Monthly audit (Layer 4) — catches drift after the fact.
