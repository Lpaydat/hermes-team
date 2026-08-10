# System Architecture: Two Systems, Not Four

## Correct model

There are exactly TWO systems:

1. **Workflow engine** — orchestration layer. JSON templates define graphs of nodes/edges/conditions. Decides WHAT card to create next. Runs as a cron job (`main.py tick`, every 1 min). State at `startup/kanban/workflow-state.db`.

2. **Hermes kanban** — execution layer. Dispatcher claims ready cards, spawns worker processes, manages lifecycle (retry, crash recovery, stale timeout). Runs as async loop in gateway (`kanban_watchers.py:1423`, `dispatch_interval_seconds` default 60).

loop_engine and kanban_chains are **plugins/tools**. They run inside agent card sessions and create structured sub-cards. They are NOT separate orchestration systems. The kanban dispatcher is part of kanban, not a third system.

## Polling latency analysis (code evidence)

### Workflow engine tick

```
# main.py line 4, 42-64
"""Runs as a cron job (every 1 minute). Each tick:
1. Loads all active workflow instances from state DB
2. Checks for completed node cards → reads outputs → resolves variables
3. Dispatches nodes whose dependencies are met
4. Checks triggers for new workflow starts
"""
def cmd_tick(args):
    actions = engine.tick()

# tick() at runtime.py:942
def tick(self) -> list[str]:
    # 3-pass stateless tick: SYNC → RESET → ACTIVATE+DISPATCH
    for inst in self.state.load_active_instances():
        actions += self._tick_instance(inst)
    actions += self._check_triggers()
```

### Kanban dispatcher tick

```
# kanban_watchers.py:953-1029
async def _kanban_dispatcher_watcher(self) -> None:
    """Embedded kanban dispatcher — one tick every dispatch_interval_seconds."""
    interval = float(kanban_cfg.get("dispatch_interval_seconds", 60) or 60)
    interval = max(interval, 1.0)  # sanity floor
    
    while self._running:
        results = await asyncio.to_thread(_tick_once)
        # ... process results ...
        await asyncio.sleep(interval)  # implicit via loop structure
```

### Node transition latency

Both poll independently at 60s. Neither knows about the other's timing:

```
agent completes card (T=0)
  → workflow engine tick fires at T=0 to T=60 (avg 30s wait)
  → workflow engine creates next card
  → kanban dispatcher tick fires at T=30 to T=90 (avg 30s wait)
  → dispatcher claims card, spawns agent
```

Average: ~60s per node transition. Worst case: ~120s. Structural floor.

### Why Temporal/n8n feel different

- **Temporal**: deterministic event loop. When activity completes, next step executes in-process, milliseconds. Push-based.
- **n8n**: webhook triggers. Push-based.
- **Hermes**: polling. Necessary because workers are separate processes (can't call synchronously). The card→dispatcher→worker model requires async decoupling.

### Config tuning

```yaml
# config.yaml
kanban:
  dispatch_interval_seconds: 5  # tighten dispatcher (default 60)
```

Workflow engine could run as gateway-embedded loop (like the dispatcher) instead of cron to eliminate its 60s floor. Not yet implemented.

## What each system actually does

### Workflow engine responsibilities (verified from code)

- **Trigger detection** (`runtime.py:2956 _check_triggers`): scans all boards for completed cards matching trigger conditions. Creates workflow instances.
- **Node dispatch** (`runtime.py:2203 _dispatch_node`): creates kanban cards for workflow nodes. Supports template, delegate, chain, foreach, subworkflow modes.
- **Conditional routing** (`runtime.py:1966-2009`): evaluates edge conditions (`${nodes.X.output.Y} == 'value'`) to route between nodes.
- **State persistence** (`runtime.py:331 StateDB`): tracks node status, outputs, iteration counters in workflow-state.db.
- **Subworkflow management** (`runtime.py:2790`): starts child workflows, blocks parent, maps outputs back.

### Kanban responsibilities (verified from code)

- **Worker spawning** (`kanban_db.py:8964 _default_spawn`): fire-and-forget `hermes -p <profile> chat -q "work kanban task <id>"` subprocess.
- **Claim/retry** (`kanban_db.py:8204 dispatch_once`): atomic claim under board-scoped lock, TTL-based reclaim, crash detection via PID.
- **Workspace management**: scratch dirs, git worktrees, project-linked repos.
- **Status lifecycle**: todo → ready → running → done/blocked/archived.

### What loop_engine/kanban_chains do

- **loop_engine** (`plugins/loop_engine/tools.py`): agent calls it inside a card session. Creates exec+verify sub-cards on the board, dependency-parks the driver, handles replan/advance/escalate. The agent (driver) re-calls loop_engine on each promotion.
- **kanban_chains** (`kanban_swarm.py`): agent calls it inside a card session. Creates parallel chains of cards with parent-child dependencies. Used for matrix topologies.

Both create cards that the kanban dispatcher picks up. They are tools, not systems.
