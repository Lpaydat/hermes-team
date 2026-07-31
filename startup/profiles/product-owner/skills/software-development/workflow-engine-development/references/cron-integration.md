# Cron Integration — Wrapper Pattern and Gotchas

> Hard-won lessons from wiring the engine into Hermes cron (2026-08-01).

## The cron wrapper pattern

The Hermes cron daemon resolves script paths **relative to the profile's
`scripts/` directory**. For a shared engine at `startup/scripts/`, the cron
job can't point there directly.

**Solution:** create a wrapper script in the PO scripts dir:

```python
#!/usr/bin/env python3
"""Wrapper — runs the workflow engine tick from the shared location."""
import sys
from pathlib import Path

engine_main = Path.home() / ".hermes-teams/startup/scripts/workflow_engine/main.py"
sys.argv = [str(engine_main)] + sys.argv[1:]
if len(sys.argv) == 1:
    sys.argv.append("tick")  # default to tick if no subcommand

exec(open(engine_main).read())
```

**Critical gotcha:** without `sys.argv.append("tick")`, argparse prints help
and exits 0. The cron reports "completed" but the engine never ticks. This
is a SILENT failure — no error, no output, just help text.

## Cron job setup

The cron job should be `no_agent=True` (zero tokens, script-only):

```python
cronjob(
    action="create",
    name="New Workflow Engine — tick",
    no_agent=True,
    schedule="* * * * *",
    script="wf-engine-tick.py",  # relative to profile scripts/ dir
)
```

Script paths must be just the filename — no subdirectories, no absolute paths.
The cron rejects paths with `/` in them ("Script path escapes the scripts
directory via traversal").

## Hermes cron vs engine: division of labor

| Concern | Owner | Why |
|---------|-------|-----|
| Scheduling (when to run) | Hermes cron | Already has cron expression parser, per-profile jobs, delivery |
| Orchestration (what to do, in what order) | Engine | Templates, edges, conditions, foreach |
| Card creation | Engine | Task/command/foreach nodes |
| Card lifecycle (claim, promote, reclaim) | Dispatcher | Built into Hermes kanban |

**Pattern:** Hermes cron calls `main.py start <template>` on a schedule.
The engine starts a workflow instance, dispatches nodes, advances on
completions. The engine tick (every minute) handles trigger detection
and card completion checking.

## Scheduled templates

Templates that need scheduling use `"trigger": {"source": "manual"}`.
The schedule lives in the Hermes cron job, not the template:

```
Hermes cron (every 6h) → main.py start builder-queue-builds
  → engine creates workflow instance
  → nodes dispatch cards
```
