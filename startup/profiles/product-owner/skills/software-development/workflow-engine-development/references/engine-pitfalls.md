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

## Cross-workflow trigger guard — the critical composition blocker

Engine-created cards (idempotency_key `wf:...`) are subject to a self-trigger
prevention guard at `runtime.py:1783-1800`. The guard has two rules:

1. **Same-workflow self-trigger: always block.** If `_{wf.id}_` appears in the
   instance part of the idempotency key, the card cannot trigger its own workflow.
2. **Cross-workflow: block if parent has explicit edges.** If the card's parent
   workflow declares explicit `edges`, the card is blocked from triggering ANY
   other workflow. The rationale: an edge-using workflow "handles routing
   internally."

Workflows WITHOUT explicit edges (implicit `depends_on` only) still allow
cross-workflow triggering — backward compat for trigger-based composition.

### Why this is a composition blocker (empirically verified, 2026-08-02)

Approach C (goal-bounded workflows: multiple agents cooperate inside one
workflow via edges, composed via card_completed triggers between workflows) is
**self-blocking under this guard.** Every goal workflow uses explicit edges
internally → every cross-workflow handoff card carries a `wf:` key → the guard
suppresses the downstream trigger. Probed with the real engine (FakeWorld):

```
CASE 1: construction WITH explicit edges (C shape)
  → qa-loop instances: 0   ← trigger SILENTLY BLOCKED

CASE 2: construction WITHOUT edges (implicit depends_on, B shape)
  → qa-loop instances: 1   ← trigger fires
```

**This means**: the shipped `qa-loop.json` works today ONLY because the verifier
card is agent-created (kanban_chains, no `wf:` key). The moment a verifier card
becomes an engine node in an edge-using workflow, the qa-loop trigger dies.

### The fix: `idempotency_key_template` on terminal nodes

Give the handoff card a non-`wf:` key so the guard is skipped entirely:

```json
{
  "id": "verify",
  "idempotency_key_template": "qa-merge-${trigger.bead_id}",
  ...
}
```

Intermediate nodes keep `wf:` keys (no accidental cross-workflow firing from
mid-pipeline cards); only terminal/export nodes get custom keys. This also
matches the old cron's idempotency conventions (e.g. `qa-merge-<sha>`,
`bead-<bead_id>`) enabling safe coexistence during incremental migration.

**STATUS: This field does NOT exist in the engine yet.** It is referenced as
load-bearing in `MIGRATION-PLAN.md §7` and the Phase 0 checklist, but has 0
grep hits in `model.py`/`runtime.py`. It is the #1 prerequisite for goal-bounded
composition.

### The hyphenated-ID parsing bug

The guard extracts the parent workflow ID from the instance part by splitting on
`_` and looking for "a chunk that isn't wf, isn't empty, isn't all digits, and
is longer than 3 chars." This heuristic BREAKS on:

- Workflow IDs with hyphens (e.g. `tech-lead-build` splits into `tech`, `lead`,
  `build` — each ≤4 chars, may match wrong workflow or fail to match)
- Timestamp chunks that happen to look non-digit-ish

Consequences: cross-workflow triggers that should fire get blocked (parent_wf
misidentified as having edges); self-triggers that should be blocked slip through
(substring match fails on hyphenated IDs).

**Before relying on cross-workflow triggering, fix this parser** to use a
structured lookup (store the workflow_id explicitly in the instance row) rather
than parsing it out of the idempotency key string.

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

## Foreach task barrier — the WRONG pattern for pipelines

A foreach on a task node creates N cards and waits for ALL of them to complete before advancing. With 10 grill cards, the build node can't start until ALL 10 grills finish. This is WRONG when each item should flow independently through a multi-node pipeline (grill→build→handoff).

**User expectation:** "I expect each prototype run in its workflow" — each idea should run grill→build→handoff independently. When grill(A) completes, build(A) starts immediately, even while grill(B) is still running.

**Fix:** Use `foreach + subworkflow`. The parent workflow has a command node (parse idea bank) → foreach subworkflow node that spawns N independent child workflows. Each child has grill→build→handoff as its own sequential pipeline. No barriers.

```
Parent:  parse (command) → spawn (foreach + subworkflow)
Child:   grill (task) → build (task) → handoff (task)
```

**When foreach barrier IS fine:** batch processing where all items genuinely must complete before downstream work. E.g., "collect all test results, then aggregate."

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

## Foreach subworkflow child dispatch needs extra tick

When `_dispatch_foreach_subworkflow` spawns child instances during PHASE 2 of a tick, the children won't dispatch their own nodes until the NEXT tick. This is because `load_active_instances()` runs at the START of the tick — children created mid-tick aren't in the list.

**In tests:** call `world.tick()` twice after expecting child dispatch — once to spawn, once for children to dispatch their cards.

**In production:** the cron tick runs every 60s, so children dispatch on the next tick naturally. Not a production issue.

## Subagent research must prescribe, not describe

When delegating research for a migration, tell subagents to WRITE the replacement templates — not to "analyze what exists." Descriptive analysis produces "these profiles just receive cards" when the real question is "should THIS ENGINE be what sends those cards." Prescribe the target, don't describe the current state.

## Kanban concurrency: global config overrides per-profile

The dispatcher reads `max_in_progress` from the GLOBAL `startup/config.yaml`, not from `profiles/<name>/config.yaml`. Changing the per-profile config has no effect. Edit the global config and restart the gateway.

## Archived cards must be treated as terminal

When a card is archived externally (manual cleanup, GC, or user removing unwanted cards), the engine must treat `"archived"` status the same as `"done"`. Without this, nodes stay DISPATCHED forever waiting for a card that will never reach `"done"`.

Both the single-card check and the foreach card check must handle archived:
```python
if card.status == "done" or card.status == "archived":
```

Found during livetest when 3 grill cards were archived to limit the test scope — the child workflow instances hung forever until the fix was applied.

## Livetest cleanup pattern

After a livetest, clean BOTH the board AND the engine state DB:
1. Archive all test cards on the board
2. Delete workflow_instances + node_states for the test workflow from the state DB
3. Delete trigger_keys to prevent stale dedup
4. Run `main.py tick` to verify zero active instances

Without full cleanup, leftover state pollutes integration tests (they share the real state DB).

## Don't ask permission for obvious fixes

User feedback: "stop asking for what things you should done long ago already." When you identify bugs in code you wrote, fix them immediately. Don't present a menu of "want me to fix #1, #2, #3?" — just fix all of them. Asking for permission on obvious next steps wastes the user's time.

## Discuss before coding when design is unclear

User feedback: "when the task is not clear, you should stop jump to code and discuss or plan first." When a task involves architectural decisions (e.g., "should this be 1 workflow or N workflows?"), present options and tradeoffs BEFORE writing code. Only start coding after the direction is confirmed.

## Engine code was untracked — gitignore whitelist needed

The engine at `startup/scripts/workflow_engine/` was gitignored because `.gitignore` whitelisted `startup/profiles/*/scripts/` but NOT `startup/scripts/`. This meant a git worktree created from main was missing the entire engine, and the engine had never been version-controlled.

Fix (commit `c9e297a1` on main): add to `.gitignore`:
```
!startup/scripts/
!startup/scripts/**
```
Then commit the engine to main BEFORE creating a worktree branch. Also exclude `workflow_state.db` (runtime SQLite state, not source):
```
startup/scripts/workflow_engine/workflow_state.db
```

When starting engine work in a worktree, ALWAYS verify `startup/scripts/workflow_engine/` is present after `git worktree add` — a missing directory means the gitignore whitelist isn't applied yet.

## Boolean condition engine bug — bare == True silently fails

The condition engine's `==`/`!=` operators only matched single-quoted strings (`${x} == 'PASS'`). Bare values like `${x} == True` fell through to `return False` — the regex `^\s*\$\{(.+?)\}\s*==\s*'(.+?)'\s*$` didn't match unquoted forms.

**FIX (committed f498e77):** Added bare-value `==`/`!=` patterns that handle `True`/`False`/`true`/`false`/`null`/`None`.

**Defensive rule for templates:** prefer `exists` for boolean gates (`${nodes.plan.output.plan_complete} exists`) over `== True`. Works for all types, immune to string-coercion edge cases.

If a conditional edge silently fails (node dead-branched when it should fire), test with:
```python
from workflow_engine.model import evaluate_condition
evaluate_condition("${x} == True", {"x": True})  # should be True
```

## Trigger cards need completed_at set

The `card_completed` trigger checks `completed_at`, not just `status=done`. When seeding synthetic spec cards for testing, set `completed_at = int(time.time())` — otherwise the trigger watermark check skips the card.

## Run all 16 test suites, not just one

The engine has 16 test suites. 15 pass consistently; the concurrency suite (`test_concurrency_standalone.py`) has 3 known failures (double-dispatch race, lost-update on concurrent state writes, overlapping ticks). These are pre-existing timing-sensitive failures in the engine's concurrency model, not test bugs. When verifying engine changes:
```bash
cd startup/scripts && for f in workflow_engine/test_*.py; do python3 "$f" >/dev/null 2>&1 && echo "PASS $(basename $f)" || echo "FAIL $(basename $f)"; done
```
Expect 15 pass + 1 fail (concurrency). Any OTHER failure is real. Do NOT treat the concurrency failures as caused by your change unless you touched `_check_instance` or `update_node_state`.
