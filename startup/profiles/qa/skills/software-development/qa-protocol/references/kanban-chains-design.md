# kanban_chains — Unified Topology Plugin (Design Reference)

## Why unified

`kanban_delegate` (tech-lead) and `qa_swarm` (qa) are the same primitive — parallel chains with optional fan-in — expressed as two separate profile-scoped plugins with duplicated helper code and incompatible schemas. `kanban_chains` unifies them.

## Schema

```
kanban_chains(
    goal: str (required),
    chains: [[step]] (required) — parallel, each inner array sequential,
    after: [step] (optional) — sequential fan-in after all chains complete,
    blackboard: {image_tag, container_port, base_port, env_facts, spec_path, extra} (optional)
)
```

Each step: `{assignee, title, body, skill, workspace_path, priority}`

## Topology

1. Root card (completed immediately, acts as blackboard)
2. Chains: step[0] parented on root, step[n] parented on step[n-1]. All chains parallel.
3. After: step[0] parented on last step of EVERY chain. Step[n] parented on step[n-1].
4. Caller linked as child of terminal card (last `after` step OR last step of each chain).
5. Caller blocked with `kind=dependency`.

## Profile usage

| Profile | chains | after | Blocks on |
|---|---|---|---|
| tech-lead | `[[{dev}, {verifier}]]` | none | all verifiers |
| QA | `[[{worker}], ...]` | `[{verifier}, {synthesizer}]` | synthesizer |
| research | `[[{scout}], ...]` | `[{report}]` | report |

## End-to-end test results (Option A vs Option B)

Both tested against cross-browser-ai MVP:

| Metric | Option A (CLI swarm) | Option B (qa_swarm plugin) |
|---|---|---|
| Worker crashes | 8 (bracket bug) → 0 (fixed) | 0 |
| Card body | Generic boilerplate | Tailored checklist per worker |
| Worker self-sufficiency | Had to parse blackboard | Knew assignment from card body |
| Port allocation | Manual (blackboard) | Auto-allocated, baked in |
| Finding depth | 18 findings | 19 findings (comparable) |
| Test time per worker | ~20 min | ~10-17 min |

## Key findings from e2e testing

1. **Beads for planning, kanban for execution.** Don't create kanban cards when asked for beads. Use `bd create` + `bd dep`.
2. **Findings route to tech-lead, not developer.** Tech-lead triages and uses kanban_delegate for dev+verifier pairs. No bypassed verifier.
3. **Synthesizer dedupes before filing.** 3 workers independently found SSRF → 1 finding, not 3. Group by root cause.
4. **kanban_link must pair with kanban_block.** Block alone = stuck forever.
5. **Container build takes 10+ min.** Heartbeat every minute during builds.
6. **Podman default.** Rootless, daemonless, lighter than Docker.
7. **Auto-decomposer tasks are NOT team self-healing.** They're the platform responding to dashboard submissions. Read session DB before claiming system behavior.

## Spec and beads

- Full spec: `/home/lpaydat/kanban-chains-spec.md`
- Beads project: `/home/lpaydat/.hermes-teams/.beads` (5 beads with dependency graph)
