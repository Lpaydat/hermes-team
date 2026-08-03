# kanban_chains — the static topology primitive

`kanban_chains` is a plugin (tool) that atomically builds a **parallel-chains +
optional fan-in tail** topology on the kanban board, then parks the caller as a
dependency block until terminal cards complete. It replaces both
`kanban_delegate` (tech-lead dev→verifier pairs) and `qa_swarm`
(workers→verifier→synth).

**Source:** `plugins/kanban_chains/` — `tools.py` (handler), `schemas.py` (LLM
tool schema), `plugin.yaml` (registration), `__init__.py` (wiring).

## Three-layer orchestration model

The Hermes orchestration stack has three distinct layers. Understanding the
boundary prevents misusing them:

```
kanban_chains         = STATIC topology primitive (this doc)
                        Caller pre-plans the whole DAG at call-time,
                        builds it atomically, parks, re-dispatched ONCE.
                        No iteration, no DoD contract.

loop_engine           = DYNAMIC converge-loop engine (composes with kanban_chains)
                        Breaks a goal into ordered phases; each phase is
                        discover→execute→verify. EXECUTE delegates to the
                        kanban_chains kernel seams directly. Adds the
                        iterative layer (verifier verdicts, replan, hard-cap)
                        AROUND the static execute step.

declarative workflow   = STATELESS routing-graph compiler (JSON templates)
engine                 `startup/scripts/workflow_engine/templates/`.
                        Creates one kanban card per node. Profiles assigned
                        to nodes MAY invoke kanban_chains/loop_engine at
                        runtime to fan out children — the engine does NOT
                        track these children. `kanban_complete` on the
                        parent node card is the sole completion signal.
```

**Key relationship:** `loop_engine` does NOT call `kanban_chains` as a
subprocess. It calls the same kernel seams (`create_task` /
`complete_task` / `link_tasks` / `block_task`) directly, mirroring the
kanban_chains patterns (blackboard last-write-wins, idempotency-key recovery,
dependency-parking). Per `loop_engine/SPEC.md`: *"Composition, not
modification: the engine calls kanban_chains for execute, dispatches a verifier
card for evaluate, and uses the board for state. kanban_chains stays the clean
static-topology primitive."*

## Tool API

One tool: `kanban_chains`, handler `tools.kanban_chains(args: dict, **kwargs) -> str` (returns JSON).

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `goal` | string | yes | What the matrix accomplishes; goes on root card. |
| `chains` | array of arrays | yes | N parallel chains; each inner array is a sequence of steps. |
| `after` | array | no | Sequential fan-in tail; `after[0]` parents on the last step of EVERY chain. |
| `blackboard` | object | no | Shared context posted as `[swarm:blackboard]` comment on root. |
| `idempotency_key` | string | no | Dedups the root card. |

**Step fields (chains):** `assignee` (req), `title` (req), `body` (req),
`skill`, `workspace_path`, `priority`.

**Step fields (after):** `assignee` (req), `title` (req), `body` (opt),
`skill`, `priority`.

**Blackboard fields:** `image_tag`, `container_port` (default 3000),
`base_port` (default 18081), `env_facts`, `spec_path`, `extra`.

When `blackboard.image_tag` is set, the first step of each chain gets an
auto-allocated host port (`base_port + chain_index`) and a podman run/teardown
block baked into its body.

## How chains are created (8-step sequence)

The handler shells out to `hermes kanban --board <board> <subcommand>` via
`_run_kanban` / `_run_kanban_json`. Reading `HERMES_KANBAN_BOARD` (default
`startup`) and caller id from `HERMES_KANBAN_TASK` or `kwargs["task_id"]`.

1. **Validate** args (goal, chains non-empty, each step has assignee/title/body).
2. **Create root card** with `goal` + blackboard info in body; assignee = first
   chain's first step's assignee.
3. **Complete the root immediately** — it is only a blackboard anchor, so
   children can promote (`_run_kanban(["complete", root_id, ...])`).
4. **Post `[swarm:blackboard]` JSON comment** on the root with
   goal/image/ports/env/spec/extra.
5. **Create chains** — for each chain, steps created sequentially: step[0]
   parented on `root_id`, step[n] parented on step[n-1]'s id. Optional
   `--skill`, `--workspace dir:<path>`, `--priority`.
6. **Create after steps** (optional) — sequentially; `after[k]` → `after[k-1]`.
7. **Link caller** as child of terminal card(s).
8. **Block caller** with `block_task(my_card_id, kind="dependency")` → caller
   routed to `todo`. Then **verify** status is `todo` (block took effect).
   Return structured JSON: `{root_id, chains, after, terminal_ids,
   block_verified, message}`.

## Fan-out / fan-in mechanism

- **Fan-out:** multiple chains each independently parented on the shared root
  (which is completed at step 3) → all run concurrently.
- **Fan-in via `after[0]`:** created with no parent, then
  `hermes kanban link <terminal_id> <after[0]_id>` called once per chain
  terminal — so `after[0]` has EVERY chain's last step as a parent and won't
  promote until all complete.
- **Fan-in without `after`:** the caller itself is linked as a child of EACH
  chain's last step (multi-parent fan-in directly onto the caller).

Parenting is set at create-time via `hermes kanban create --parent <id>`. The
`--parent` flag establishes a parent→child edge: child stays `todo` until parent
is `done`, then `recompute_ready` promotes it.

## Critical invariant

The caller ALWAYS lands in `todo` with `block_kind='dependency'` — NEVER the
human `blocked` bucket. `recompute_ready` auto-promotes it when all terminals
hit `done`. No cron, no human, no escalation needed. This is verified at step 8
and asserted in `test_kanban_chains_e2e.py`.

The return message explicitly says: *"Do NOT kanban_complete until re-dispatched
after promotion."* — the caller's worker session ends after `kanban_chains`
returns; the dispatcher re-spawns it when promoted.

## Profile enablement

Enabled in `plugins:` list of **13 profiles** (each with
`allow_tool_override: false`):

advisor, architect, base, builder, debugger, developer, ops, product-owner, qa,
researcher, scout, tech-lead, verifier.

## loop_engine composition detail

`loop_engine` (plugin at `plugins/loop_engine/`) mirrors these kanban_chains
patterns explicitly (per its own code comments and SPEC.md):

- **Blackboard:** last-write-wins per key on the root card comment (same
  `[swarm:blackboard]` prefix, same JSON `{key, value}` shape).
- **Recovery:** idempotency_key on root `create_task`; re-read blackboard + task
  edges to distinguish first-invocation from re-invocation.
- **Dependency-park:** `_park_driver()` in loop_engine mirrors
  kanban_chains' caller-blocking — `link_tasks` + `block_task(kind="dependency")`
  → `todo`, auto-promote via `recompute_ready`.

The difference: loop_engine adds the iterative converge-loop layer (phase DoD,
verifier verdicts, replan/hard-cap decisions) around the static execute step.
