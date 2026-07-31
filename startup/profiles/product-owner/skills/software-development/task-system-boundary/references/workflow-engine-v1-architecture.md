# Workflow Engine v1 — Built Architecture

> Branch: `feat/workflow-engine` (off main `58403248`)
> Location: `~/.hermes-teams/startup/profiles/product-owner/scripts/workflow_engine/`
> Status: built, 51/51 checks passed, first template (`qa-loop.json`) proven via manual start + card creation

## Module breakdown

```
workflow_engine/
├── __init__.py
├── model.py           # Workflow/Node/Trigger dataclasses + template resolution
├── store.py           # TemplateStore — loads JSON templates from templates/
├── kanban_adapter.py  # Thin wrapper over hermes kanban CLI + direct SQLite reads
├── runtime.py         # Engine tick loop + StateDB (SQLite cache)
├── main.py            # CLI entry point (tick, loop, list, render, start, templates)
└── templates/
    └── qa-loop.json   # First template: QA re-test on verifier PASS+merge
```

## Data model (model.py)

- `Workflow` — parsed from JSON: `id`, `name`, `trigger`, `nodes[]`
- `Node` — one step: `id`, `profile`, `skill`, `body_template`, `input`, `output`, `card_mode`, `depends_on[]`, `condition`, `foreach`
- `Trigger` — entry point: `source` (card_completed/bead_ready/manual), `condition` dict
- `resolve_template(template, context)` — replaces `${variable}` references with resolved values
- `evaluate_condition(condition, context)` — supports `${var} exists`, `is empty`, `== 'val'`, `!= 'val'`

## Kanban adapter (kanban_adapter.py)

All board access goes through this layer:
- `create_card(board, title, assignee, body, idempotency_key, ...)` → calls `hermes kanban create`
- `get_card(board, card_id)` → reads from SQLite
- `get_card_metadata(board, card_id)` → reads latest `task_runs.metadata`
- `find_recent_completions(board, since_ts)` → completed cards since timestamp
- `find_cards_by_idempotency_key(board, key)` → dedup check
- `validate_output(board, card_id, schema)` → JSON Schema validation of card metadata

## Tick loop (runtime.py)

```
tick():
  1. Load active instances from StateDB
  2. For each instance:
     a. Check pending nodes: deps met + condition passes → dispatch (create kanban card)
     b. Check dispatched nodes: card done → read output metadata, mark node done
     c. All nodes done → complete instance
  3. Check triggers: scan recent completions across all boards for trigger matches
     → matched? Start new workflow instance
```

## StateDB schema

SQLite at `~/.hermes-teams/startup/kanban/workflow-state.db`:
- `workflow_instances` — instance_id, workflow_id, board, project_dir, trigger_context, parent_instance_id, created_at, status
- `node_states` — instance_id, node_id, status (pending/dispatched/done/failed), card_id, output (JSON)
- `trigger_watermark` — board+workflow_id → last_ts checked

**The state DB is a CACHE, not source of truth.** Kanban DB (card status) is ground truth. If state DB is lost, engine rebuilds from kanban on restart.

## Card→instance link

`idempotency_key = wf:<instance_id>:<node_id>` on each created card. This is how the engine finds its own cards and prevents duplicate creation.

## Variable binding flow

```
trigger_context = {card_id, board, merged_commit_sha, ...}  # from triggering card
  ↓
node output = {verdict: "PASS", findings_count: 0, ...}  # from card metadata
  ↓
context = {
  "trigger.merged_commit_sha": "abc1234",
  "nodes.plan.output.spec_path": "/path/to/spec.md",
  ...
}
  ↓
resolve_template("Merge commit: ${trigger.merged_commit_sha}", context)
  → "Merge commit: abc1234"
```

## Template format (JSON)

```json
{
  "id": "qa-loop",
  "name": "QA Re-test Loop",
  "trigger": {
    "source": "card_completed",
    "condition": {
      "assignee": "verifier",
      "status": "done",
      "metadata.verdict": "PASS"
    }
  },
  "nodes": [
    {
      "id": "qa_retest",
      "profile": "qa",
      "skill": "live-testing",
      "body_template": "## QA re-test — merge ${trigger.merged_commit_sha}...",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]}
          }
        }
      }
    }
  ]
}
```

## CLI commands

```
python3 workflow_engine/main.py tick        # Run one engine tick
python3 workflow_engine/main.py loop        # Continuous (for debugging)
python3 workflow_engine/main.py list        # Active instances + node status
python3 workflow_engine/main.py render <id> # Mermaid graph
python3 workflow_engine/main.py start <id> --board X [--context '{}']
python3 workflow_engine/main.py templates   # List available templates
```

## Migration plan (incremental)

The old 645-line cron (`workflow-engine.py`) and the new engine coexist. Each cron phase gets replaced one at a time:

| Cron phase | Replacement template | Status |
|---|---|---|
| qa-trigger (phase 5) | `qa-loop.json` | Template exists, not yet wired to cron |
| dispatch (phase 2) | `dev-dispatch.json` (TODO) | Not started |
| bead-sync (phase 1) | Engine reads kanban directly (no beads sync needed) | Design only |
| human-escal (phase 3) | `escalation.json` (TODO) | Not started |
| scanner (phase 4) | `scanner.json` (TODO) | Not started |

Each migration step: write template → test manually → livetest → disable old cron phase → commit.

## Gotchas

- Package dir MUST be `workflow_engine/` (underscore), not `workflow-engine/` (hyphen) — Python can't import hyphenated names.
- `sys.path` must include the `scripts/` directory (parent of `workflow_engine/`), not the package dir itself.
- `TEMPLATES_DIR` must point to `scripts/workflow_engine/templates/`, not `scripts/workflow-engine/templates/`.
- `run_kanban()` uses `subprocess.run(["hermes", "kanban", ...])` — the `hermes` CLI must be on PATH.
- The `_matches_trigger()` method supports `title_not_prefix` but the JSON template uses `title_not_prefix2` for a second prefix exclusion — this is a naming quirk to be cleaned up.
