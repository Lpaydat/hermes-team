# kanban_delegate Plugin Tool — Creation Guide

> **RENAMED Jul 2026**: `delegate_and_wait` → `kanban_delegate`. The old name was too unclear — tech-lead didn't understand it was supposed to USE the tool instead of manual `kanban_create` + polling. The new name clearly says "delegate" (create cards + block). All references below apply to the renamed tool.

## Why a plugin, not a script

Tech-lead **ignored** a bash script (`delegate-wait.sh`) embedded in skill prose.
It created dev/verifier cards and called `kanban_complete` without running the script.
The model does not reliably follow `bash ~/.hermes-teams/.../script.sh` commands
buried in long skill text.

A first-class Hermes plugin tool appears in the tool list alongside `kanban_create`,
`kanban_block`, etc. The model sees the name + description and calls it directly —
no prose interpretation needed.

## Why the rename matters

In C6 R3, the truncate tech-lead did NOT use `delegate_and_wait` — it manually
created cards via `kanban_create` and polled in a sleep-loop. This caused a
duplicate fix card (both the verifier AND the still-running tech-lead created
fix cards for the same merge conflict). If tech-lead had been blocked (via
the tool), it wouldn't have been running to create a duplicate.

The rename to `kanban_delegate` + the 3-step checklist with "STOP HERE" and
"NEVER poll" rules directly addresses this failure mode.

## Plugin structure

```
<profile-dir>/plugins/dev_workflow/
├── plugin.yaml      # manifest
├── __init__.py      # registration (register function)
├── schemas.py       # tool schema (what the LLM sees)
└── tools.py         # handler (the code that runs)
```

### plugin.yaml

```yaml
name: dev_workflow
version: 1.1.0
description: Dev workflow orchestration tools
provides_tools:
  - kanban_delegate
```

### Key schema design

The `description` field is how the LLM decides when to use the tool. Be explicit:

```python
"description": (
    "Create developer + verifier cards and block yourself until the verifier completes. "
    "Use this AFTER you have written a contract and are ready to delegate implementation. ..."
)
```

### Handler pattern

```python
def kanban_delegate(args: dict, **kwargs) -> str:
    # 1. Get contracts from args
    # 2. Get my_card_id from kwargs["task_id"] or HERMES_KANBAN_TASK env
    # 3. For each contract: create dev card + verifier card (parented on dev)
    # 4. Link my_card_id as CHILD of each verifier: hermes kanban link <verifier> <me>
    # 5. Block self: hermes kanban block <me> <reason> --kind dependency
    # 6. Return JSON with created card IDs
```

## Discovery path (CRITICAL)

`get_hermes_home()` returns the **PROFILE** directory, not `~/.hermes/`:
```
~/.hermes-teams/startup/profiles/tech-lead/plugins/dev_workflow/
```

NOT `~/.hermes/plugins/dev_workflow/` — that's the global path, not scanned by profiles.

## Enable per-profile

```bash
hermes plugins enable dev_workflow --profile tech-lead
hermes gateway stop --profile tech-lead && hermes gateway start --profile tech-lead
```

## Reference file consistency (DISCOVERED Jul 2026)

When you change the card-creation mechanism in the SKILL.md, you MUST also update
the reference files (`references/kanban-native-loops.md`). The flow diagram, card
schema section, and commissioning steps ALL referenced the old manual `kanban_create`
flow. Tech-lead reads BOTH the skill and references — conflicting guidance caused
it to skip the tool and fall back to the old manual pattern.

## `kanban block` argparse quirk (Jul 2026)

`hermes kanban --board X block <task_id> <reason> --kind dependency` works.
`hermes kanban --board X block <task_id> --kind dependency <reason>` FAILS —
the top-level hermes parser intercepts positional args after `--kind`.

In the plugin's subprocess call, put reason BEFORE `--kind`:
```python
_run_kanban(["block", my_card_id, reason, "--kind", "dependency"])
```

**Rule**: after any SKILL.md mechanism change:
```bash
grep -rn '<old-pattern>' <skill-dir>/references/
```
Update or annotate every match. A contradiction between SKILL.md and a reference file makes both unreliable.

## Plugin subprocess debugging (DISCOVERED Jul 2026 — 3 iterations to fix)

The `kanban_delegate` tool uses `subprocess.run()` to call `hermes kanban` CLI.
Three bugs were found and fixed across iterations (when the tool was still named
`delegate_and_wait` — same code, different name):

### Bug 1: `env` not inherited — subprocess can't authenticate

**Symptom**: tool returned `{"status": "blocked"}` but the card stayed `running` —
the block command failed silently.

**Root cause**: the subprocess didn't inherit `HERMES_KANBAN_TASK` and
`HERMES_KANBAN_RUN_ID` from the parent process. The CLI's `_worker_run_id_for()`
function checks these env vars to authenticate as the worker that owns the task
claim. Without them, `expected_run_id=None`, and `block_task()` fails because
the task is claimed by a different run.

**Fix**: always pass `env=os.environ.copy()` to `subprocess.run()`:
```python
env = os.environ.copy()
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
```

### Bug 2: Return code 0 ≠ success — kanban CLI exits 0 even on "cannot block"

**Symptom**: `_run_kanban` returned `(True, "")` — success — but the block
didn't happen. The CLI prints "cannot block t_X" to stderr and exits 0.

**Root cause**: `hermes kanban block` returns `rc=0` even when the block fails.
The error message goes to stderr, not stdout.

**Fix**: check the output text, not just the return code. Also log on failure:
```python
ok, block_out = _run_kanban(["block", my_card_id, reason, "--kind", "dependency"])
if not ok or "cannot" in block_out.lower():
    return json.dumps({"error": f"Block failed: {block_out}", "created": created})
```

### Bug 3: Block fires asynchronously — check 30-60s later, not immediately

**Symptom**: tool returned `{"status": "blocked"}`, but checking the kanban DB
5 seconds later showed the card still `running`. Appeared the block failed.

**Root cause**: the tool's subprocess calls create the dev/ver cards first, then
the link, then the block. These are sequential subprocess calls that take 1-2
seconds each. The kanban events (linked, dependency_wait) fire AFTER the tool
returns. Checking the DB too early shows intermediate state.

**Fix**: when debugging, wait 60 seconds after the tool returns before checking
the kanban event log. The `dependency_wait` event is the definitive signal.

### Debugging checklist for plugin subprocess issues

1. Check the session DB for the tool's actual return value:
   ```python
   db = sqlite3.connect(f'{profile_dir}/state.db')
   row = db.execute("SELECT content FROM messages WHERE tool_name='kanban_delegate' ORDER BY timestamp DESC LIMIT 1").fetchone()
   ```
2. Check the kanban event log 60s after the tool call:
   ```sql
   SELECT task_id, kind, datetime(created_at,'unixepoch'), substr(payload,1,100)
   FROM task_events WHERE created_at >= <test_start> AND kind IN ('linked','dependency_wait')
   ```
3. If `dependency_wait` event is missing → the block command failed. Run it
   manually to see the error: `hermes kanban --board startup block <tid> test_reason --kind dependency`
4. If `linked` event is missing → the link command failed. Run manually:
   `hermes kanban --board startup link <verifier_id> <tech_lead_id>`
5. Check `HERMES_KANBAN_TASK` and `HERMES_KANBAN_RUN_ID` are set in the
   dispatcher-spawned environment (line 7711 of `kanban_db.py`).
