# Platform Constraints & Swarm Mechanics

Learned from end-to-end testing of the QA swarm protocol. Load when debugging swarm failures or designing new swarm-based workflows.

## kanban_chains — the unified topology tool (LIVE)

Global plugin at `startup/plugins/kanban_chains/`. Replaces both `kanban_delegate` (tech-lead) and `qa_swarm` (QA). One tool, every topology:

- **`chains`**: parallel chains of sequential steps. Each step: `{assignee, title, body, skill, workspace_path}`.
- **`after`**: optional sequential fan-in after all chains complete. Each step same shape.
- **`blackboard`**: optional shared context (image_tag, ports, env_facts, spec_path).
- Caller is linked to terminal card and blocked with `kind=dependency`. Handles all `kanban_link` + `kanban_block` internally.

| Profile | chains | after | Blocks on |
|---|---|---|---|
| tech-lead | `[[{dev}, {verifier}]]` | none | all verifiers |
| QA | `[[{worker}], ...]` | `[{verifier}, {synthesizer}]` | synthesizer |

`kanban_delegate` and `qa_swarm` are deprecated. Skills reference `kanban_chains` exclusively.

### kanban_link + kanban_block — the dependency invariant

`kanban_block(kind=dependency)` sets status to `todo` but does NOT register the dependency. Without `kanban_link(target, my_card_id)`, the dispatcher's `recompute_ready()` never promotes the card — stuck forever. `kanban_chains` handles both internally. If you ever block manually: link first, then block with `kind=dependency`.

A generic block (`kind=null`) creates status `blocked` — requires manual unblocking, never auto-promotes. Always use `kind=dependency` when waiting on another card.

## max_in_progress_per_profile — dispatcher cap

Global setting in ROOT `~/.hermes/config.yaml`. Default 1 → all same-profile workers execute serially. Raise to 5+ for parallel workers. Dispatcher reads at gateway boot — restart after changing. Check lock holder: `fuser .dispatcher.lock`.

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

## End-to-end test results (cross-browser-ai MVP)

| Metric | Option A (CLI) | Option B (Plugin) |
|---|---|---|
| Worker crashes (test 1) | 8 (bracket bug) | 0 |
| Card body | Generic boilerplate | Tailored checklist |
| Test time per worker | ~20 min | ~10-17 min |
| Total findings | 18 | 19 |

Both produced equivalent finding depth. Plugin is faster and more reliable.
