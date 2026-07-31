# Workflow Engine — Pitfalls (learned the hard way)

## Trigger context double-prefix bug

`context()` in `WorkflowInstance` adds the `trigger.` prefix to all keys in `trigger_context`. When injecting manual start context in `main.py`, use bare keys (`board`, `source`), NOT `trigger.board` — or you get `trigger.trigger.board` which resolves to empty.

```python
# WRONG — produces trigger.trigger.board
context.setdefault("trigger.board", args.board)

# CORRECT — context() adds the prefix
context.setdefault("board", args.board)
```

## Cron script path resolution

The cron daemon resolves script paths relative to the profile's `scripts/` dir. If the engine lives in a shared location (`startup/scripts/`), you need a wrapper script in the profile's `scripts/` dir that execs the shared `main.py`.

The wrapper must also inject `tick` into `sys.argv` if no subcommand is given — otherwise argparse prints help and exits 0. The cron reports "completed" but the engine never ticks.

```python
# wf-engine-tick.py (in PO scripts dir)
sys.argv = [str(engine_main)] + sys.argv[1:]
if len(sys.argv) == 1:
    sys.argv.append("tick")
exec(open(engine_main).read())
```

## Cross-workflow double-fire prevention

Engine-created cards (idempotency_key `wf:...`) from workflows with explicit edges are blocked from triggering OTHER workflows. This prevents e.g. dev-review-loop's verifier card from also triggering qa-loop.

Workflows WITHOUT explicit edges still allow cross-workflow triggering (backward compat for trigger-based composition).

## Shell injection in command nodes

Command nodes use `shell=True`. Variable values from card metadata get injected directly. FIX: all variable values are shlex-quoted before substitution into the command string.

```python
# In _run_command_node and _run_foreach_command:
safe_ctx = {}
for k, v in ctx.items():
    safe_ctx[k] = shlex.quote(str(v))
cmd = resolve_template(node.command or "", safe_ctx)
```

## Stale test state

Integration tests share the real state DB. Leftover instances from livetests pollute `load_active_instances()`. Clean the state DB before running integration tests after a livetest.

## FakeWorld body field

The FakeWorld's `_fake_create_card` must include `body` in the INSERT statement. Without it, card bodies are always empty in tests, masking variable resolution bugs.

## Foreach waits for ALL items

A foreach node creates N cards and waits for ALL of them to complete before the next node dispatches. With 10 grill cards (max 3 concurrent), the build node waits for all 10 to finish. This is slightly slower than independent parent-child pairs but acceptable since the profile processes sequentially anyway.

## Dedup is critical for re-runnable workflows

Without dedup, running the same workflow twice creates duplicate cards. The parse command must check the board for existing cards before outputting ideas.

## Schedule/scheduled trigger removed (do not re-add)

We built a `scheduled` trigger source and `schedule` node type, then removed them because Hermes cron already owns scheduling. The engine should NOT have cron expression parsing — that's Hermes cron's job. If a workflow needs to run on a schedule, Hermes cron calls `main.py start <workflow-id>`.

The `wait` node type IS kept — it polls a condition string each tick. That's workflow logic, not scheduling.

## _ensure_schema must check engine_events table

When the state DB exists from an older engine version (before engine_events), `_ensure_schema` must check for the table and run `_init_schema()` if missing. The check `SELECT 1 FROM engine_events LIMIT 1` handles this — an OperationalError triggers full re-init.

## AND/OR edge semantics (the big one)

The original OR-semantics for explicit edges was WRONG. A node with multiple unconditional incoming edges dispatched when only ONE source was done. The fix:

- **Unconditional edges (no condition field): AND** — ALL sources must be DONE
- **Conditional edges (has condition field): OR** — ANY source DONE + condition passes
- **Activation: all unconditional done AND (conditional ok OR no conditional edges)**

This was found by an adversarial test: `test_multiple_waits_one_blocks` — w1 resolved, w2 blocked, but `go` still dispatched because w1's unconditional edge triggered OR semantics.
