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
