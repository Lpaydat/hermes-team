# Real Integration Testing — Beyond FakeWorld

The FakeWorld suite proves the engine's LOGIC (tick ordering, trigger detection, variable
resolution, state management) in milliseconds. But it can't prove the PLUMBING — that the
engine's `hermes kanban` CLI calls produce valid cards, that the real dispatcher claims
them, that real agent profiles execute them, and that real completion metadata flows back.

The real integration test is the bridge between "tests pass" and "it works."

## The echo-test pattern

A minimal 2-node workflow that exercises the full pipeline:

```json
{
  "id": "echo-test",
  "name": "Echo Test — 2 node pipeline",
  "nodes": [
    {
      "id": "write",
      "profile": "developer",
      "skill": "developer-loop",
      "body_template": "Write 'hello from workflow engine' to /tmp/wf-test.txt. Complete with metadata: {file_written: true}"
    },
    {
      "id": "read",
      "profile": "verifier",
      "skill": "adversarial-review",
      "body_template": "Read /tmp/wf-test.txt and verify content. Complete with metadata: {verified: true}",
      "depends_on": ["write"]
    }
  ]
}
```

## Setup

```bash
# Create project dir
mkdir -p ~/projects/wf-engine-test && cd ~/projects/wf-engine-test
git init && echo "# test" > README.md && git add . && git commit -m "init"

# Create board
hermes kanban boards create wf-engine-test
```

## Run

```bash
# 1. Start the workflow
python3 workflow_engine/main.py start echo-test \
  --board wf-engine-test \
  --project-dir ~/projects/wf-engine-test \
  --context '{"test_run": "integration-1"}'

# 2. Tick to dispatch first node
python3 workflow_engine/main.py tick
# → DISPATCHED node write on wf-engine-test → card t_xxx

# 3. Wait for real agent to complete (~60s)
# The developer gateway claims the card, writes the file, completes with metadata

# 4. Tick to detect completion + dispatch next node
python3 workflow_engine/main.py tick
# → DONE node write (card t_xxx)
# → DISPATCHED node read on wf-engine-test → card t_yyy

# 5. Wait for verifier to complete

# 6. Final tick
python3 workflow_engine/main.py tick
# → DONE node read (card t_yyy)
# → WORKFLOW COMPLETE: echo-test
```

## What this proves that FakeWorld can't

| Mechanic | FakeWorld | Real integration |
|----------|-----------|------------------|
| Card creation via `hermes kanban create` | Mocked | Real CLI call, real card on real board |
| Dispatcher claims card | Simulated (status change) | Real gateway picks up, spawns real process |
| Agent executes work | N/A (we set status) | Real developer/verifier profile runs |
| Completion metadata | Hardcoded JSON | Real `kanban_complete(metadata={...})` |
| SQLite schema | Simplified tables | Real kanban DB schema (all columns) |
| Idempotency key dedup | Checked in mock | Real `hermes kanban create --idempotency-key` |

## Key findings from first real integration test

1. **`active-projects.json` format mismatch** — the engine expected `{board: path}` but
   the real Hermes config uses `{"active_projects": [{"name", "path", "board"}]}`. The
   `_board_to_project_dir` method must handle both formats.

2. **Real agents complete in ~60-90 seconds** — much faster than livetest slices. The
   echo-test is a 2-minute cycle, not a 2-hour cycle.

3. **The engine and the old cron can coexist** — both read the same kanban DBs. The
   engine creates cards with `wf:` idempotency key prefixes, so the old cron ignores them.
