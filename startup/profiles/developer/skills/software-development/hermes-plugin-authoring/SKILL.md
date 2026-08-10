---
name: hermes-plugin-authoring
description: "Build a Hermes agent plugin. Use when authoring a plugin."
version: 1.0.0
metadata:
  hermes:
    tags: [plugin, hermes, tools, extension, development]
    category: software-development
---

# hermes-plugin-authoring — extend the agent with a new tool

A Hermes plugin adds a model-facing tool without touching the core. Plugins
live in their own directory and work within the register/hook ABCs the
platform provides. This skill covers the verified 4-file authoring pattern.

## 0. Study sibling plugins FIRST

Before writing anything, read 2-3 existing plugins in the same `startup/plugins/`
directory. They are the authoritative pattern for THIS platform version — the
handoff doc or task may name them; if not, `ls startup/plugins/` and pick the
smallest. Sibling plugins show you the exact file layout, the `register()`
signature, the schema dict shape, and config wiring that the current Hermes
build expects. Do NOT reconstruct the pattern from memory or general knowledge.

The cleanest minimal example to start from is a single-tool plugin like
`kanban_chains` (4 files, ~270 lines total). Avoid starting from `loop_engine`
unless you need hooks — it is 150KB+ of tools.py.

## 1. The 4-file structure

Every plugin is a directory under `startup/plugins/<name>/` with four files:

```
startup/plugins/<name>/
├── plugin.yaml      # manifest: name, version, description, provides_tools
├── __init__.py      # register(ctx) — wires schema dict to handler function
├── schemas.py       # JSON-schema dict(s) — what the LLM sees
└── tools.py         # handler function(s) — def tool_name(args, **kwargs) -> str
```

Optional: `conftest.py`, `test_<name>.py` for tests.

### plugin.yaml (manifest)

```yaml
name: my_plugin
version: 1.0.0
description: >-
  One-line trigger here — what it does. The first 57 chars of the
  description show in the skill index, so front-load the trigger.
provides_tools:
  - my_plugin      # MUST match the name passed to ctx.register_tool()
# provides_hooks:                # only if you register lifecycle hooks
#   - kanban_task_completed
```

`provides_tools` is a list of tool names. Each name must match what you pass
to `ctx.register_tool(name=...)`. If you provide a hook, also add
`provides_hooks:`.

### __init__.py (registration)

```python
"""my_plugin plugin — registration."""
import logging
from . import schemas, tools

logger = logging.getLogger(__name__)

def register(ctx):
    """Wire the schema to its handler."""
    ctx.register_tool(
        name="my_plugin",          # matches plugin.yaml provides_tools
        toolset="my_plugin",       # groups the tool in a named toolset
        schema=schemas.MY_PLUGIN,  # the JSON-schema dict from schemas.py
        handler=tools.my_plugin,   # the handler function from tools.py
    )
```

The platform calls `register(ctx)` on load. `ctx.register_tool` is the only
interface you need for a tool plugin.

### schemas.py (the LLM-facing schema)

A plain Python dict in JSON-schema shape. This is what the model sees as the
tool's parameter spec:

```python
MY_PLUGIN = {
    "name": "my_plugin",
    "description": "What the tool does and WHEN to call it. Be specific — "
                   "the model reads this to decide whether to call.",
    "parameters": {
        "type": "object",
        "properties": {
            "required_arg": {
                "type": "string",
                "description": "What this argument means.",
            },
            "optional_arg": {
                "type": "boolean",
                "default": False,
            },
        },
        "required": ["required_arg"],
    },
}
```

The `description` at both the top level and per-property is the LLM's only
guidance on when/how to call — invest in it. State the WHY and the WHAT clearly.

### tools.py (the handler)

The handler receives `args: dict` (the validated parameters) and `**kwargs`
(platform context). It MUST return a JSON string:

```python
import json, logging, os
logger = logging.getLogger(__name__)

def my_plugin(args: dict, **kwargs) -> str:
    task_id = (args.get("required_arg") or "").strip()
    if not task_id:
        return json.dumps({"error": "required_arg is required"})
    # ... do the work ...
    return json.dumps({"result": "ok", "value": task_id}, indent=2)
```

**Returning a JSON string is the convention** — parse errors early, return
`{"error": "..."}` on failure, `{"status": "ok", ...}` on success.

### Reading board state from a plugin

Plugins run as tool handlers, not as board-native code. To read kanban state,
shell out to the CLI the same way `kanban_chains` does:

```python
def _run_kanban_json(args_list, board):
    cmd = ["hermes", "kanban", "--board", board] + args_list + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                            env=os.environ.copy())
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
```

Board slug resolves from `os.environ.get("HERMES_KANBAN_BOARD")`.

## 2. Where worker PIDs live (for process-management plugins)

If your plugin needs a task's worker PID, read it from
`hermes kanban show <id> --json` and resolve in this order:

1. **`payload["events"]`** — the `spawned` event carries `{"pid": N}`. This
   is the PRIMARY source per the handoff spec; it is written by
   `_set_worker_pid` (kanban_db.py) the instant a worker is spawned.
2. **`payload["runs"][-1]["worker_pid"]`** — the latest run's PID. Fallback
   when no `spawned` event is present.

NOTE: `worker_pid` is NOT in the `task` dict (the `_task_to_dict` serializer
omits it) — it's only in the `spawned` event and `runs[].worker_pid`. If a
plugin needs to react to a worker's lifecycle, see §2a below BEFORE assuming
a hook will fire when you expect it to.

## 2a. Lifecycle hooks — what exists, and the archive/delete trap

Hermes kanban fires plugin hooks via `_fire_kanban_lifecycle_hook` (in
`hermes_cli/kanban_db.py`), dispatched through `hermes_cli.lifecycle.invoke_hook`
→ `hermes_cli.plugins.invoke_hook`. Hooks are best-effort and fire AFTER the
write txn commits, so plugin code never runs while a SQLite lock is held.

Register a hook with `ctx.register_hook(name, callback)` and declare it in
`plugin.yaml` under `provides_hooks:` (see `loop_engine` for the only example).

**Only these three hooks exist today** (verified kanban_db.py, 2026-08):

| Hook                    | Fires when                          | Carries |
|-------------------------|-------------------------------------|---------|
| `kanban_task_claimed`   | dispatcher claims a task            | task_id, board, assignee, run_id |
| `kanban_task_completed` | worker completes a task             | task_id, board, assignee, run_id, summary |
| `kanban_task_blocked`   | worker blocks (needs_input/depend.) | task_id, board, assignee, run_id, reason |

THE ARCHIVE/DELETE TRAP — read this before trying to "do X automatically on
archive or delete":

- `archive_task` and `delete_task` fire **NO lifecycle hook**. There is no
  `kanban_task_archived` event. A plugin cannot react to those transitions
  today.
- It gets worse: both transitions destroy the PID data a plugin needs BEFORE
  any hook could fire. `archive_task` sets `worker_pid = NULL` inside its
  write txn (line ~6295); `delete_task` removes the task row entirely. By the
  time a post-txn hook would run, the worker PID is gone from the board.
- The deeper bug this exposes: `archive_task`/`delete_task` do NOT kill the
  worker process at all — they just mutate the DB. The running worker and all
  its spawned subprocesses keep going indefinitely, orphaned. This is a
  **core bug**, not something a plugin can fix reactively.

If you need "kill the worker tree when a card is archived/deleted," that
requires a **core fix** to `archive_task`/`delete_task` (read `worker_pid`
before nulling it, walk + kill the tree, then proceed). A plugin hook alone
cannot deliver it because of the ordering trap above. The sibling flaw —
`reclaim`/`reassign` also use plain `os.kill(pid)` rather than a tree walk —
has the same root cause and should be fixed together (fix the class, not the
site). Keep the kill_task *plugin* for the manual/stuck-worker case and let
core handle the lifecycle automation.

## 3. Enable the plugin in config.yaml

After creating the plugin files, enable it in the target profile's config:

```yaml
plugins:
  enabled:
    - my_plugin
  disabled: []
```

Config lives at `startup/profiles/<profile>/config.yaml`. The plugin directory
is shared across profiles (`startup/plugins/`), but each profile opts in via
its own `config.yaml`.

## 4. Test the plugin

Co-locate a `test_<name>.py` in the plugin directory. Test the pure functions
(processing logic, parsing) AND the real side effects (if the tool touches
the filesystem or process tree, exercise that with real processes/files).

Verify the plugin loads:

```python
import sys; sys.path.insert(0, '..')
import my_plugin
class Ctx:
    def __init__(self): self.t = {}
    def register_tool(self, name, toolset, schema, handler):
        self.t[name] = (toolset, schema, handler)
ctx = Ctx()
my_plugin.register(ctx)
assert "my_plugin" in ctx.t
```

Run: `cd startup/plugins/<name> && python -m pytest test_<name>.py -v`

## Pitfalls

- **Reconstructing the pattern from memory.** Always read 2-3 sibling plugins
  in the same `startup/plugins/` dir first — the register signature, schema
  shape, and config wiring are version-specific.
- **Schema name mismatch.** The `name` in `ctx.register_tool()` MUST match
  `provides_tools` in `plugin.yaml`, or the tool won't load.
- **Handler not returning a string.** The handler must return a JSON string,
  not a dict — wrap with `json.dumps(...)`.
- **Forgetting to enable in config.** The plugin directory is shared, but each
  profile must list it under `plugins.enabled` in its own `config.yaml`.
- **Cross-profile write guard.** If you're running under profile `developer`
  but writing to `startup/plugins/` (shared/default territory), writes will be
  blocked by the soft guard. Pass `cross_profile=True` after confirming the
  location is correct — `startup/plugins/` is the shared home for all plugins.
- **`read_file` mis-detects Python files as binary.** Files containing
  multibyte characters (em-dashes `—`, ellipses `…`, box-drawing chars in
  comments or strings) get flagged "Binary file - cannot display as text",
  and `patch` then can't find the old_string because it was never read. When
  this happens, don't trust the binary verdict: confirm with `file <path>`
  (it'll say "Python script, UTF-8 text"), then re-read the exact content
  via `cat -n <path>` in terminal and proceed with the edit. This is a
  recurring false positive on unicode-rich source, not a real binary file.
- **`worker_pid` not in task dict.** It's only in `runs[].worker_pid` and the
  `spawned` event — not the top-level task serialization.
- **Return-contract drift.** When a handoff/spec specifies the exact return
  shape (e.g. `Return {killed_pids: [...], worker_pid: N}`), match it
  field-for-field — same key names, no extras that weren't asked for. A spec
  reviewer diffs your return keys against the spec line-by-line; renaming
  `killed_pids` → `killed` or adding unrequested keys (`dry_run`, `force`,
  `timeout_seconds`) shows up as a finding. Extra keys aren't always wrong
  (defensive params can be justified), but the spec-named keys MUST be present
  under the spec-named names.
- **See `references/proc-tree-walk.md`** for process-tree killing (the zombie
  gotcha) when building process-management plugins.
- **Assuming a hook exists for the transition you care about.** Only
  `claimed`/`completed`/`blocked` hooks fire today. There is NO archive or
  delete hook, and those transitions destroy `worker_pid` before any hook
  could run — see §2a. Wanting "auto X on archive/delete" is a core-fix
  signal, not a plugin-hook signal.
- **Installing a governance/ops plugin onto worker profiles.** Tools that
  terminate another agent's process tree (kill_task) or otherwise manage the
  board belong on the orchestrator/ops profiles (`product-owner`, `ops`,
  optionally `tech-lead`), NOT on worker profiles (`developer`, `builder`,
  `debugger`, `qa`, `verifier`). A stuck worker with the power to kill a
  sibling's process tree is a footgun. Control-loop tools like `loop_engine`
  are different — a worker driving its OWN loop is fine on worker profiles.

## Support files

- `references/proc-tree-walk.md` — killing a process AND all its descendants
  safely on Linux (the zombie /proc/stat gotcha, PPID-walk, deepest-first kill).
