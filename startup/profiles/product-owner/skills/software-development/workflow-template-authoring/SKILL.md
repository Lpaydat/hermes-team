---
name: workflow-template-authoring
description: "Author workflow templates for the Hermes workflow engine. Use when creating, editing, or debugging JSON workflow templates — triggers, nodes, edges, conditions, loops, subworkflows, foreach."
---

# Workflow Template Authoring

Write declarative JSON templates that the stateless workflow engine compiles into a routing graph. Each template is one `.json` file in `startup/scripts/workflow_engine/templates/`.

**This is one of three building blocks.** Before authoring a template, check whether your workflow needs dynamic fan-out (`kanban_chains`) or dynamic iteration (`loop_engine`) — those run inside profile cards, not as template nodes. See the [`template-ab-testing`](../template-ab-testing) skill's [`references/building-blocks.md`](../template-ab-testing/references/building-blocks.md) for the decision tree and verified APIs.

## Template skeleton

```json
{
  "id": "kebab-case-no-underscores",
  "name": "Human name",
  "description": "One line.",
  "trigger": { "source": "card_completed", "condition": {} },
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

Workflow IDs **must not contain underscores** — the self-trigger guard splits instance IDs on `_`. Use hyphens.

## Triggers

| source | fires when | condition keys |
|--------|-----------|----------------|
| `card_completed` | a kanban card reaches `done` | `assignee`, `status`, `title_prefix`, `title_not_prefix`, `metadata.*` |
| `bead_ready` | `bd ready` returns a matching bead | `issue_type`, `label` |
| `manual` | `start_manual` called (by parent subworkflow or CLI) | — |

Condition keys are AND-matched (all must pass). `metadata.*` matches against the card's latest task_run metadata field (e.g. `"metadata.verdict": "PASS"`).

Trigger context available in node bodies as `${trigger.*}`: `card_id`, `board`, `assignee`, `title`, plus any metadata fields spread flat.

## Nodes

Every node needs `id` and `profile`. Everything else depends on `type` (defaults to `task`).

### task (default) — creates a kanban card, waits for an agent

```json
{
  "id": "build",
  "profile": "tech-lead",
  "skill": "",
  "body_template": "Implement ${trigger.title}. Spec: ${trigger.card_id}",
  "title_template": "[auto] ${trigger.title}",
  "card_mode": "template",
  "output": { "schema": { "type": "object", "required": ["verdict"] } }
}
```

- `body_template`: resolved with `${trigger.*}` and `${nodes.X.output.*}` variables.
- `title_template`: defaults to `[node-id] task`.
- `card_mode`: `template` (one card, default), `delegate` (meta-card, profile spawns children), `chain` (parent + linked children).
- `output.schema`: JSON Schema. Card metadata validated against it on completion. Mismatch → node fails.
- `depends_on`: implicit unconditional edge from the listed nodes (use when you don't need conditions).
- `condition`: self-gating condition for the node (only meaningful on entry nodes in implicit-edge mode).

### command — runs a shell command synchronously, no card

```json
{
  "id": "parse",
  "profile": "product-owner",
  "type": "command",
  "command": "python3 script.py --board ${trigger.board}"
}
```

Output is `json.loads(stdout)` if it parses, else `{}`. Use for routing junctions, data prep, or side effects. Completes in the same tick.

### subworkflow — spawns a child workflow instance, blocks until done

```json
{
  "id": "spawn",
  "profile": "builder",
  "type": "subworkflow",
  "workflow_ref": "child-template-id",
  "input_mapping": { "idea": "${nodes.parse.output.title}" }
}
```

Child runs independently. Parent node completes when the child instance completes. Output is the child's exit-node outputs via `output_mapping`.

### wait — polls a condition each tick until true

```json
{
  "id": "gate",
  "profile": "qa",
  "type": "wait",
  "wait_condition": "${nodes.deploy.output.status} == 'healthy'"
}
```

No card created. Silently re-checks every tick. Completes when condition passes.

### foreach — fan-out over a list (applies to task, command, subworkflow)

Add a `foreach` field to any node:

```json
{
  "id": "spawn-all",
  "profile": "builder",
  "type": "subworkflow",
  "workflow_ref": "builder-single",
  "foreach": "${nodes.parse.output.ideas}"
}
```

Creates N cards / runs N commands / spawns N child instances — one per list item. Each item gets `${item}` and `${item_index}` in context. Node completes when ALL items complete.

## Edges

Explicit edges give you conditional routing. Omit edges to use implicit `depends_on` edges (unconditional).

```json
"edges": [
  { "from": "entry", "to": "route-a", "condition": "${trigger.type} == 'feature'" },
  { "from": "entry", "to": "route-b", "condition": "${trigger.type} == 'bug'" },
  { "from": "review", "to": "fix", "condition": "${nodes.review.output.verdict} == 'FAIL'", "max_iterations": 3 },
  { "from": "fix", "to": "review" }
]
```

- **Unconditional edge** (no `condition`): source must be done → target dispatches. AND semantics: all unconditional sources must be done.
- **Conditional edge** (has `condition`): source done AND condition true → target dispatches. OR semantics: any conditional source satisfying its condition activates the target.
- **Back-edge** (cycle-closing): detected via DFS discovery order at load time. Requires `max_iterations` or an `${...iteration...}` condition on at least one edge in the cycle. The engine resets the target node on each iteration, bumping `iteration` and archiving the old card.
- **Dead-branch skip**: if all incoming edges are terminal (source done/failed/skipped) but none fired, the target is skipped. Propagates downstream.

## Condition grammar

```
condition := clause (OR clause)*
clause    := atom (AND atom)*
atom      := ${var} <op> <value>
```

- AND binds tighter than OR. No parentheses.
- Operators: `==`, `!=`, `exists`, `is empty`, `<`, `<=`, `>`, `>=` (numeric with float coercion).
- Unrecognized forms return False.
- Variables: `${trigger.*}`, `${nodes.X.output.*}`, `${nodes.X.iteration}`, `${item}`, `${item_index}`.

## Patterns

### Routing diamond (one entry → N conditional routes)

Use a `command` entry node as a synchronous junction. Conditional edges fan out. Dead-branch skip ensures only one route fires.

See `templates/dev-dispatch.json` for a working example.

### Dev-verifier loop (back-edge iteration)

```json
"edges": [
  { "from": "build", "to": "review" },
  { "from": "review", "to": "ship", "condition": "${nodes.review.output.verdict} == 'PASS'" },
  { "from": "review", "to": "build", "condition": "${nodes.review.output.verdict} == 'FAIL'", "max_iterations": 3 }
]
```

On FAIL, build resets (iteration bumps, old card archived, fresh card dispatched). After 3 FAILs the cap stops the reset.

### Cross-workflow handoff (card_completed trigger)

One workflow's routed card completes → another workflow triggers:

- dev-dispatch creates a tech-lead card (assignee=tech-lead)
- tech-lead completes → qa-loop triggers (assignee=verifier, metadata.verdict=PASS)
- qa completes → bug-fix triggers (metadata.verdict=FAIL)

No explicit wiring needed — the trigger conditions chain them.

### Profile-driven dynamic work (kanban_chains / loop_engine)

A task node assigned to a profile can internally call `kanban_chains` (parallel fan-out) or `loop_engine` (iterative converge-loop). The template doesn't declare these children — it just dispatches the parent card and waits for `done`.

When to use this pattern:
- **Tech-lead card** fans out developer + verifier pairs via `kanban_chains` — the template can't predict how many features need implementation.
- **Debugger card** iterates via `loop_engine` — reproduce → fix → converge, retrying until DoD met. The template can't predict how many iterations are needed.

The engine observes only the parent card's status. It doesn't track the dynamic children. This is the **static-dynamic coexistence** boundary.

## Pitfalls (proven across 8 A/B rounds)

These are real bugs and behavioral findings discovered through empirical testing. Each was caught and fixed in production templates.

### Output schema enforcement > body text

The most important lesson. A `body_template` tells the agent what to do. An `output.schema` with `required` fields forces the agent to produce it — or the card fails validation and retries. Body text instructions are routinely ignored by the agent.

```
output.schema (required fields) → ENFORCED (card fails, retries)
body_template (structured text) → IGNORED (agent writes what it wants)
skill field on node             → NO-OP (skill_enforcer handles it)
```

If you need structured output (per-claim evidence, security checklists, exploration results), put them as required arrays in the output schema:

```json
"output": {
  "schema": {
    "type": "object",
    "required": ["verdict", "verdicts", "checks"],
    "properties": {
      "verdicts": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["claim_id", "claim", "verdict", "evidence"],
          "properties": { ... }
        }
      }
    }
  }
}
```

### Boolean values and conditions

Python `str(True)` produces `"True"` (capital T). Condition comparisons against `'true'` (lowercase) fail silently. Fix: use `type: "boolean"` in the output schema, and compare in conditions with the Python form.

### Optional fields in output schema

If a field might be `None` (e.g., `image_tag` when there's no container), don't put it in `required` or set a strict `type: "string"` — the engine will reject `None`. Either omit from schema or make it nullable.

### `depends_on` with explicit edges

If you use explicit `edges`, nodes declared in `depends_on` must also have corresponding explicit edges — otherwise they're unreachable and the template won't validate.

### `skill` field is a no-op

Setting `"skill": "live-testing"` on a node does not load the skill on the card. The profile's `skill_enforcer` config handles skill loading. The field is safe to set (documents intent) but has no runtime effect.

## Validation checklist

Before deploying a template:

- [ ] `id` has no underscores (hyphens only)
- [ ] Every node has `id` and `profile`
- [ ] `type` defaults to `task` — only set for command/subworkflow/wait
- [ ] Explicit edges: every node reachable from an entry node
- [ ] Explicit edges: at least one exit node (no outgoing edges) unless `exit_condition` set
- [ ] Back-edges: at least one edge in each cycle has `max_iterations` or `${...iteration...}` condition
- [ ] `body_template` variables resolve (`${trigger.*}`, `${nodes.X.output.*}`)
- [ ] `output.schema` on nodes whose output downstream depends on
- [ ] **Output schema uses `required` arrays for structured fields** (not body text)
- [ ] **Boolean fields use `type: "boolean"`** (not string enum)
- [ ] **Optional fields that can be `None` are not in `required`**
- [ ] Load test: `python3 -c "from workflow_engine.model import Workflow; Workflow.from_dict(json.load(open('template.json')))"` passes
- [ ] E2E test: create spec card on test board → tick → verify correct routing
- [ ] **A/B test against previous version** (see `template-ab-testing` skill)
