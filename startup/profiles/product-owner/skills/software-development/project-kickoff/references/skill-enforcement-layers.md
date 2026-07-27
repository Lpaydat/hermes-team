# Skill Enforcement Layers

How to make the PO follow the workflow pipeline (to-spec → to-tickets → dev-dispatch) instead of improvising.

## The problem

Skills are opt-in via `skill_view`. Nothing forces the PO to load them. Four failure modes observed:

1. **CLI conversation mode:** PO writes spec by hand, creates beads with `bd create`, never loads `to-spec` or `to-tickets`.
2. **Dispatched worker mode:** PO receives dispatch card that says "Run dev-dispatch" as prose, but uses `kanban_chains` instead — prose is a suggestion, not enforcement.
3. **Skill loaded but ignored:** PO could load `to-tickets`, read it, then create beads manually anyway.
4. **False enforcement claim in SOUL.md (verified 2026-07-27):** SOUL.md stated "The `to-spec` skill enforces this at the tool level: it must refuse to write a spec if no grilling has occurred." Grepping the actual `to-spec` SKILL.md confirmed this is false — zero grill/enforce/refuse/gate keywords exist in the skill. The skill is a read-only symlink (chmod 444) to the Matt Pocock shared-skills pack; it cannot be patched to add enforcement. A false claim of enforcement is worse than no claim: the PO believes a safety net exists and relaxes self-discipline. **The only enforcement that exists today is the PO's own pipeline discipline (loading skills at the right steps).** The layers below are DESIGN goals, none implemented yet.

## Layer 0: Config-level tool removal (PROVEN — already in production)

The ONLY enforcement mechanism proven to work reliably. Everything else below is design-only.

The PO config.yaml already uses `disabled_toolsets` to physically remove tools the PO should never use:

```yaml
disabled_toolsets:
  - browser       # no web browsing
  - delegation    # no delegate_task
  - web           # no web_search/web_extract
  - kanban_chains # no matrix topology (prevents the dev→verifier bypass)
```

The PO config has a comment that states the principle directly:
> "PO is grill + coordinate ONLY. Prompting ('no research' in the skill) proved unreliable; PO reasoned around it. Tool removal is the only reliable enforcement."

This proves the pattern: **prompting is a suggestion, tool removal is enforcement.** The same mechanism can enforce other role boundaries by adding the relevant toolset to `disabled_toolsets`.

**How to configure:** `disabled_toolsets` under the top-level or `agent:` key in config.yaml. Per-platform override via `platform_toolsets`. See Hermes docs: `website/docs/user-guide/security.md` and `configuration.md`.

**Limitation:** `disabled_toolsets` works at the tool level (can this agent call `write_file`?), not at the workflow level (did this agent load `to-spec` before calling `bd create`?). For workflow-order enforcement, you need Layers 1-2 (stamps + engine gate). But for role-boundary enforcement ("should this agent have this tool at all?"), config-level removal is the gold standard — the user explicitly confirmed this approach over word-bans.

## Layer 1+: Proof and gate layers (design — not yet implemented)

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

0. **Already done:** Config-level tool removal (Layer 0) — proven, in production. Extend to cover more role boundaries (e.g., PO file-write restriction if needed).
1. **Highest impact:** Workflow engine gate (Layer 2) — blocks dispatch without proof. Pure Python, no LLM.
2. **High impact:** Dispatch card `--skills` flag (Layer 2) — forces dev-dispatch load. One-line patch.
3. **Medium impact:** Skill stamps (Layer 1) — enables the gate. Requires patching each skill (to-spec, to-tickets, dev-dispatch).
4. **Low impact:** Plugin observer (Layer 3) — nice for audit, but the workflow gate is the real enforcement.
5. **Low impact:** Monthly audit (Layer 4) — catches drift after the fact.

## Skills ecosystem + graph engineering research (searched 2026-07-27)

Searched the open agent skills ecosystem (`npx skills find`) for existing tools/libraries that implement "skills as composable workflows." No match exists. Top results were domain-specific patterns (deployment, git, saga orchestration from `wshobson/agents`, `ruvnet/ruflo`) — not a framework for structuring skills-as-workflows. The `codewithjv/agent-skills@create-locked-down-skill` (20 installs) restricts skill execution but doesn't compose workflows.

Also researched "graph engineering" (July 2026 X trend, Peter Steinberger). Read 8 articles. **Not applicable here.** Graph engineering is multi-agent runtime orchestration (nodes = agents, edges = data deps, fan-out/fan-in, shared state). Our problem is single-agent skill composition within one session. The one stealable principle is the **dependency test**: "Does step B actually read step A's output? If no data crosses the boundary, there's no edge." Good for workflow design, doesn't need DAG formalism.

**We are building this ourselves.** The `create-workflow` authoring skill (agreed 2026-07-27) will teach profiles how to write skill-chaining workflows with real gates.
