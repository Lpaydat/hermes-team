# Real Pipeline Pattern — mini-pipeline.json

A reference template + tick-by-tick trace for proving the workflow engine
against a real pipeline with real agents, real kanban, and real dispatch.

## Template: mini-pipeline.json

```json
{
  "id": "mini-pipeline",
  "name": "Mini Dev Pipeline — build → review → test",
  "description": "Real pipeline test: developer writes code, verifier reviews, QA tests.",
  "nodes": [
    {
      "id": "build",
      "profile": "developer",
      "skill": "developer-loop",
      "body_template": "Write a Python function `greet(name)` in greet.py that returns 'Hello, {name}!'. Include a test in test_greet.py. Commit both files."
    },
    {
      "id": "review",
      "profile": "verifier",
      "skill": "adversarial-review",
      "body_template": "Review the code changes. Run the tests. Set verdict to PASS or FAIL in your completion metadata."
    },
    {
      "id": "qa",
      "profile": "qa",
      "skill": "live-testing",
      "body_template": "Test the greet function by running the test suite. Report the result."
    }
  ],
  "edges": [
    {"from": "build", "to": "review"},
    {"from": "review", "to": "qa", "condition": "${nodes.review.output.verdict} == 'PASS'"}
  ]
}
```

## Tick-by-tick trace (real run, 2026-07-31)

### Tick 0: Manual start
```
python3 main.py start mini-pipeline --board livetest-pipeline --project-dir ~/projects/livetest-pipeline
→ Started: wf_1785488177_mini-pipeline_7e38597c
```
Instance created with 3 nodes: build (pending), review (pending), qa (pending).

### Tick 1: Dispatch build
```
DISPATCHED node build on livetest-pipeline → card t_98285a2d
```
Engine creates real kanban card. Developer gateway claims it (status: ready → running).

### Tick 2 (after developer completes): Build done, dispatch review
```
DONE node build (card t_98285a2d) on livetest-pipeline
DISPATCHED node review on livetest-pipeline → card t_b4aa88d1
```
Engine detected build card status=done. Explicit edge build→review advanced to review.
Verifier gateway claims the review card.

### Tick 3 (after verifier completes with verdict=PASS): Review done, conditional edge fires
```
DONE node review (card t_b4aa88d1) on livetest-pipeline
DISPATCHED node qa on livetest-pipeline → card t_ba82f927
STARTED workflow qa-loop (wf_1785488574_qa-loop_af5035d7) — triggered by card t_b4aa88d1
```

**Two things happened simultaneously:**
1. **Explicit edge:** conditional `${nodes.review.output.verdict} == 'PASS'` evaluated TRUE → QA node dispatched
2. **Trigger:** qa-loop workflow trigger (`card_completed` with `assignee=qa, metadata.verdict=PASS`) also fired → started a SECOND workflow instance

This is correct behavior. Triggers watch all boards globally. Edges route within a single instance. They don't conflict.

### Tick 4 (after QA completes): Workflow complete
```
DONE node qa (card t_ba82f927) on livetest-pipeline
WORKFLOW COMPLETE: mini-pipeline (wf_1785488177_mini-pipeline_7e38597c)
```

All 3 nodes reached terminal state (DONE). Instance marked COMPLETE.

## What this proves

1. **Card creation → real dispatch → real completion → metadata reading** — full plumbing works
2. **Explicit conditional edges** — verdict metadata from verifier card flows into edge condition evaluation
3. **Trigger-based composition coexists with edge routing** — both fire without conflict
4. **Real agent metadata** — verifier stamped `verdict=PASS` in completion metadata, engine read it correctly
5. **Workflow completion** — all nodes reached terminal state, instance marked complete autonomously

## What it does NOT prove

- FAILED verdict path (verifier says FAIL → qa node should be SKIPPED via edge condition)
- Foreach with real agents
- Subworkflow with real agents
- Blocked status with dynamic children (tech-lead pattern)
- Beads integration

## Cleanup after livetest

```python
# Clean up active instances left on the shared state DB
import sqlite3, pathlib
db = pathlib.Path.home() / '.hermes-teams/startup/kanban/workflow-state.db'
conn = sqlite3.connect(str(db))
conn.execute('UPDATE workflow_instances SET status = "completed" WHERE status = "active"')
conn.execute('DELETE FROM trigger_keys WHERE created_at < strftime("%s", "now", "-1 hour")')
conn.commit()
conn.close()
```

Leftover active instances on the shared state DB will cause integration tests
to fail with "Expected 1 active instance, got N" — see the integration test
isolation pitfall in SKILL.md.
