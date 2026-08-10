# Subworkflow Cross-Workflow Connections

How to connect two workflow templates via `type: "subworkflow"` nodes.

## The mechanism

The engine natively supports cross-workflow connections via `type: "subworkflow"` nodes (runtime.py:2790). A node starts a CHILD workflow instance, blocks until it completes, and receives results via `output_mapping`.

```json
{
  "id": "debug-fix",
  "type": "subworkflow",
  "workflow_ref": "debug-fix",
  "input_mapping": {
    "repo": "${trigger.card_body}",
    "failing_tests": "${nodes.close.output.failing_tests}"
  },
  "output_mapping": {
    "verdict": "${nodes.verify-fix.output.verdict}"
  }
}
```

## CRITICAL: Variable naming in child templates

`_build_ctx()` in runtime.py stores all trigger_context items with a `trigger.` prefix:
```python
for k, v in inst.trigger_context.items():
    ctx[f"trigger.{k}"] = v
```

So `input_mapping: {"repo": "..."}` becomes `trigger.repo` in the child's context. Child template body MUST use `${trigger.repo}` — NOT bare `${repo}`.

**If you see empty values in child card bodies**, check:
1. Is the child body using `${trigger.X}` (correct) or `${X}` (wrong)?
2. Does the parent have the variable in its context? (e.g., `${trigger.card_body}` requires `card_body` in trigger_context, which requires `CardInfo.body` field)
3. Does the input_mapping reference a parent variable that actually exists?

## CRITICAL: CardInfo.body and trigger.card_body

Before commit `636233d`, `CardInfo` had no `body` field and `find_recent_completions` SQL didn't SELECT `t.body`. This meant `${trigger.card_body}` resolved to empty everywhere.

Fix: `CardInfo` now has `body: str = ""`, the SQL includes `t.body`, and `_start_from_trigger` uses `getattr(trigger_card, "body", "")`.

## How it works

1. `_dispatch_subworkflow_node` starts the child workflow on the same board
2. Parent node stays DISPATCHED, blocking the parent workflow
3. `_check_subworkflow_completion` polls each tick until child reaches `completed`
4. Child's node outputs are mapped back to the parent via `output_mapping`
5. Parent advances once the child is done

## Conditional edge to subworkflow

The parent uses a conditional edge to route to the subworkflow only when needed:

```json
{"from": "close", "to": "debug-fix", "condition": "${nodes.close.output.verdict} == 'test_failure'"}
{"from": "close", "to": "merge-verify", "condition": "${nodes.close.output.verdict} == 'merged'"}
```

## depends_on requirement

Subworkflow nodes need `depends_on: ["parent-node"]` set. An edge alone is insufficient — the engine's activation logic checks `depends_on`, not edges.

## Proven FULL CHAIN (EXT-dbg3, commits `636233d` + `85b6465`)

After fixing both the CardInfo.body + SQL issue and the trigger.* variable naming:

1. Close node: detected `verdict=test_failure` (test_mul failed: mul(3,4)=7)
2. Conditional edge: `close → debug-fix` (verdict == 'test_failure')
3. Engine spawned debug-fix child workflow
4. input_mapping resolved correctly: repo=/tmp/ext-dbg-repo, failing_tests=test_calc.py::test_mul
5. Debugger card body showed correct values (NOT empty)
6. Debugger dispatched developer card → fixed calc.py:5 (a+b → a*b)
7. Verifier mutation-tested 3/3 caught, PASS
8. Debugger converged with PASS, commit ceaed0a on master, 2/2 tests green

Before the fixes: all input_mapping values were empty. Debugger defaulted to hermes-teams repo and fixed unrelated bugs (FakeWorld teardown leak). The debugger's `todo` status was loop_engine dependency-parking (NORMAL), not "blocking for review."

## Research before building

ALWAYS search existing templates before proposing new workflow nodes:

```bash
grep -l "debugger\|bug\|fix" startup/scripts/workflow_engine/templates/*.json
python3 -c "import json; d=json.load(open('templates/<name>.json')); print(d['trigger']); print([n['id'] for n in d['nodes']])"
ls profiles/<name>/skills/software-development/
```

The debugger-exit.json workflow ALREADY has a complete reproduce→fix→verify→converge loop triggered by `[bug]` prefix cards. Don't reinvent it — use a subworkflow node to call it.

## State DB location

`startup/kanban/workflow-state.db` — NOT `scripts/workflow_engine/workflow_state.db`. The scripts dir file is stale/empty. Always check `STATE_DB` in `runtime.py` (line 39).
