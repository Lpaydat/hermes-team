# Platform Constraints & Swarm Mechanics

Learned from end-to-end testing of the QA swarm protocol. Load when debugging swarm failures or designing new swarm-based workflows.

## kanban_chains — the unified topology tool (LIVE, uses kanban_db API)

Global plugin at `startup/plugins/kanban_chains/`. Replaces both `kanban_delegate` (tech-lead) and `qa_swarm` (QA). One tool, every topology:

- **`chains`**: parallel chains of sequential steps. Each step: `{assignee, title, body, skill, workspace_path}`.
- **`after`**: optional sequential fan-in after all chains complete. Each step same shape.
- **`blackboard`**: optional shared context (image_tag, ports, env_facts, spec_path).
- Caller is linked to terminal card and blocked with `kind=dependency`. Handles all `kanban_link` + `kanban_block` internally.
- All DB operations run in a single `kanban_db.connect_closing()` context — no subprocess calls, no cross-process state divergence.

| Profile | chains | after | Blocks on |
|---|---|---|---|
| tech-lead | `[[{dev}, {verifier}]]` | none | all verifiers |
| QA | `[[{worker}], ...]` | `[{verifier}, {synthesizer}]` | synthesizer |

`kanban_delegate` and `qa_swarm` are deprecated. Skills reference `kanban_chains` exclusively.

### kanban_link + kanban_block — the dependency invariant

`kanban_block(kind=dependency)` sets status to `todo` but does NOT register the dependency. Without `kanban_link(target, my_card_id)`, the dispatcher's `recompute_ready()` never promotes the card — stuck forever. `kanban_chains` handles both internally. If you ever block manually: link first, then block with `kind=dependency`.

A generic block (`kind=null`) creates status `blocked` — requires manual unblocking, never auto-promotes. Always use `kind=dependency` when waiting on another card.

## max_in_progress_per_profile — dispatcher cap

Global setting in `startup/config.yaml` (team config). Team gateways read this at boot, NOT `~/.hermes/config.yaml`. Default 1 → all same-profile workers execute serially. Raise to 5+ for parallel workers. **Always edit `startup/config.yaml`** — the dispatcher reads it at gateway boot, so restart the dispatcher-holding gateway after changes. Check lock holder: `fuser .dispatcher.lock`.

## Finding routing — QA → tech-lead (NOT developer)

QA findings filed directly to `developer` create lone cards with no verifier child — fixes ship without adversarial review. Correct flow:

```
QA synthesizer → dedup by root cause → 1 triage report to tech-lead
  → tech-lead → kanban_chains → developer + verifier → merge → new QA card for re-test
```

The orchestrator COMPLETES after filing the verdict. It does NOT block waiting for the fix. The re-test is a separate QA card created by tech-lead after fixes merge.

## Auto-decomposer ≠ team self-healing

Tasks with `created_by: "auto-decomposer"` are created by the platform's triage-to-workgraph decomposer. It decomposes triage cards (submitted via dashboard/intercom) into tech-lead + developer + verifier chains. NOT the team self-correcting. Always check `created_by` and read session DBs before claiming system behavior.

## Beads-watchdog requires active-projects entry

`bd create` creates beads in the planning layer, but the beads-watchdog cron only scans projects listed in `~/.hermes-teams/startup/active-projects.json`. A new beads database that isn't in this file is invisible to the watchdog — beads stay "ready" forever with no kanban card created. Each entry needs: name, path (repo root with `.beads/`), and board (kanban board slug). Add the project to the file, then the watchdog bridges beads→kanban automatically on its next 5-min tick.

## delegate_task fragility

Ephemeral — dies with parent session, shares parent's API rate limits. Under load, frequently hits HTTP 429 and fails silently. Recovery: check session DB for stuck sessions (1 message, 0 tool calls), kill sandbox, re-dispatch with simpler instructions. Prefer kanban child cards for long tasks.

## Dispatcher scan interval — per-board latency

The dispatcher (whichever gateway holds `.dispatcher.lock`) reaps zombie workers every ~1 min but only does a full per-board scan at irregular intervals (~15 min observed on the `team` board). A `ready` card can sit idle for 15+ minutes before being claimed. This is NOT a stuck card — it's dispatch latency. Check `grep 'dispatcher.*<board>' <dispatcher_profile>/logs/agent.log` to see the actual scan interval. Only investigate further if the card has been `ready` longer than 2x the observed scan interval.

## Stale claim_lock — the invisible stuck card

A card can sit at `ready` for hours without being dispatched because the `claim_lock` field retains a stale value (e.g., `lambda:926`) from a prior spawn. The dispatcher's `release_stale_claims` should clean expired locks, but doesn't always — especially when the lock was placed by a different gateway than the one holding the dispatcher lock.

**Diagnosis:** `hermes kanban --board <board> dispatch --dry-run` — if it shows `Spawned: 0` despite a ready card, check `claim_lock`:
```sql
SELECT id, status, claim_lock, claim_expires FROM tasks WHERE id = '<id>';
```
If `claim_lock` is non-null and `claim_expires` is in the past, clear it:
```sql
UPDATE tasks SET claim_lock = NULL, claim_expires = NULL WHERE id = '<id>';
```
Then re-run the dry-run dispatch to confirm `Spawned: 1`.

**Root cause:** When the orchestrator is first spawned, the dispatcher sets `claim_lock = "lambda:<pid>"` with a 15-min TTL. The orchestrator runs, calls `kanban_chains`, and blocks (status → `todo`). When the synthesizer completes, the card is promoted to `ready`. But the stale `claim_lock` from the original spawn is never cleared — the dispatcher sees it and skips the card on every tick.

## Config file location — startup/config.yaml vs ~/.hermes/config.yaml

Team gateways (venture-builder, tech-lead, etc.) read `startup/config.yaml` at boot, NOT `~/.hermes/config.yaml`. If you change `max_in_progress_per_profile` in `~/.hermes/config.yaml`, the team gateways won't see it — they use the value from `startup/config.yaml` cached at boot time.

**Always edit `startup/config.yaml` for team-wide settings.** After changing any kanban config (`max_in_progress`, `max_in_progress_per_profile`, `dispatch_interval_seconds`), restart the gateway that holds the dispatcher lock for the change to take effect.

Check which gateway holds the lock: `cat /home/lpaydat/.hermes-teams/startup/kanban/.dispatcher.lock` → PID → `hermes gateway list`.

## kanban_chains block — subprocess protocol_violation (RESOLVED)

**Original failure:** `kanban_chains` called `hermes kanban block` as a subprocess. The block_task SQL correctly transitioned the card, but the dispatcher's `detect_crashed_workers` (running in a different gateway process) didn't see the committed write on its next tick — it still saw `status='running'` and flagged `protocol_violation`, crashing the run and moving the card to `blocked` with `block_kind=NULL`.

**Three-step debugging path:**
1. First symptom: `hermes kanban show` verification returned `status=None` (SQLite WAL lock window after block subprocess commit). Fix: removed the verification step. But protocol_violation persisted.
2. Root cause: subprocess DB writes commit in a separate process from the dispatcher. The zombie reaper queries `WHERE status='running' AND worker_pid IS NOT NULL` — if it reads stale state, it fires protocol_violation.
3. Fix: refactored `kanban_chains` to use `kanban_db` Python API directly (`connect_closing`, `create_task`, `link_tasks`, `block_task`, `complete_task`, `add_comment`). All operations run in a single `with kb.connect_closing() as conn:` context — card creation and the caller block commit atomically in the same transaction. The zombie reaper can never see cards without their corresponding block.

**Lesson:** Plugins that modify kanban state must use the in-process `kanban_db` API, not subprocess CLI calls. The subprocess approach creates a cross-process DB state divergence that the dispatcher's zombie reaper can observe.

## kanban_chains API refactor — session ID leak (UNRESOLVED)

**Symptom:** After refactoring `kanban_chains` to use `kanban_db` Python API directly (eliminating subprocess calls), the plugin creates all 7 swarm cards successfully but fails on the last `link_tasks` call with `ValueError: unknown task(s): <session_id>`.

**What happened:** The runtime passes `session_id` as a kwarg to plugin tool handlers alongside `task_id` (see `agent/tool_executor.py:1407` — `handle_function_call(function_name, function_args, effective_task_id, session_id=agent.session_id)`). The plugin's `**kwargs` receives `{"task_id": "t_xxx", "session_id": "20260710_...", "user_task": "..."}`. Somehow the session ID leaked into a `link_tasks(conn, parent_id, child_id)` call as one of the arguments.

**Impact:** Cards created but not fully linked (3 of 4 fan-in links succeeded, 4th failed). Caller block never ran (card stayed `running`). Dispatcher flagged `protocol_violation` when worker exited without `kanban_complete` or `kanban_block`.

**Debugging path:**
1. Check the tool handler kwargs — `kwargs` contains `task_id`, `session_id`, `user_task`
2. `_my_card_id(**kwargs)` reads `kwargs.get("task_id")` — should be correct
3. But if `task_id` kwarg is None (runtime didn't pass it), and env `HERMES_KANBAN_TASK` is unset, the plugin might fall through to something unexpected
4. The 4th chain's create_task return value might have been the session ID somehow

**Next steps for fix:**
- Add ID validation: every create_task return value must match `^t_[a-f0-9]+$`
- Add a guard: reject any ID passed to link_tasks that doesn't start with `t_`
- Consider whether the `with kb.connect_closing() as conn:` context commits between inner `write_txn` calls — if not, newly created tasks may be invisible to `link_tasks`' `_find_missing_parents` query

**Key lesson:** When using the kanban_db API directly from a plugin, the handler's `**kwargs` receives both `task_id` and `session_id` from the runtime. Never confuse the two — `session_id` is the agent session identifier (format: `YYYYMMDD_HHMMSS_<6hex>`), `task_id` is the kanban task ID (format: `t_<hex>`).

## End-to-end test results (cross-browser-ai MVP)

| Metric | Option A (CLI) | Option B (Plugin) |
|---|---|---|
| Worker crashes (test 1) | 8 (bracket bug) | 0 |
| Card body | Generic boilerplate | Tailored checklist |
| Test time per worker | ~20 min | ~10-17 min |
| Total findings | 18 | 19 |

Both produced equivalent finding depth. Plugin is faster and more reliable.
