# Platform Constraints & Swarm Mechanics

Learned from end-to-end testing of the QA swarm protocol. Load when debugging swarm failures or designing new swarm-based workflows.

## kanban_link + kanban_block — the dependency invariant

`kanban_block(kind=dependency)` sets status to `todo` but does NOT register the dependency. Without a matching `kanban_link(dependency_target, my_card_id)`, the dispatcher's `recompute_ready()` never promotes the card when the target completes. The card stays stuck forever.

**Always pair them:**
```python
kanban_link(synthesizer_id, my_card_id)  # register the dependency
kanban_block(my_card_id, kind=dependency)  # set status to todo
```

The `qa_swarm` plugin does this correctly (tools.py Step 5). The bug appeared when an orchestrator blocked manually without linking.

## hermes kanban swarm CLI — known gotchas

### Skill name bracket bug
`--worker PROFILE:TITLE[:SKILL,SKILL]` — brackets in help text denote optional syntax. Typing literal brackets produces skill name `qa-functional]` → agent crash. Correct: `--worker "qa:Title:qa-functional"`.

### Hardcoded verifier/synthesizer skills
`kanban_swarm.py` creates verifier with `skills=["requesting-code-review"]` and synthesizer with `skills=["humanizer"]`. Neither exists on the QA profile by default. Stub versions installed that redirect to QA roles. Do NOT edit platform source.

### Generic card bodies
The CLI creates correct topology but generic card bodies. Workers must parse a shared blackboard blob. The `qa_swarm` plugin solves this by baking tailored content into each card body.

## qa_swarm plugin (Option B)

Located at `plugins/qa_workflow/`. Creates root (blackboard) + workers + verifier + synthesizer atomically. Each worker gets: specific checklist in body, auto-allocated port, container start command, skill loaded. No hardcoded skills.

## max_in_progress_per_profile — dispatcher cap

Global setting in ROOT `~/.hermes/config.yaml`. Default 1 → all same-profile workers execute serially. Raise to 5+ for parallel workers. Dispatcher reads at gateway boot — restart after changing. Check lock holder: `fuser .dispatcher.lock`.

## Finding routing — QA → tech-lead (NOT developer)

QA findings filed directly to `developer` create lone cards with no verifier child — fixes ship without adversarial review. Correct flow:

```
QA synthesizer → dedup by root cause → 1 triage report to tech-lead
  → tech-lead → kanban_delegate → developer + verifier → merge → QA re-test
```

## Auto-decomposer ≠ team self-healing

Tasks with `created_by: "auto-decomposer"` are created by the platform's triage-to-workgraph decomposer. It decomposes triage cards (submitted via dashboard/intercom) into tech-lead + developer + verifier chains. NOT the team self-correcting. Always check `created_by` and read session DBs before claiming system behavior.

## Beads-watchdog requires active-projects entry

`bd create` creates beads in the planning layer, but the beads-watchdog cron only scans projects listed in `~/.hermes-teams/startup/active-projects.json`. A new beads database that isn't in this file is invisible to the watchdog — beads stay "ready" forever with no kanban card created. Each entry needs: name, path (repo root with `.beads/`), and board (kanban board slug). Add the project to the file, then the watchdog bridges beads→kanban automatically on its next 5-min tick.

## delegate_task fragility

Ephemeral — dies with parent session, shares parent's API rate limits. Under load, frequently hits HTTP 429 and fails silently. Recovery: check session DB for stuck sessions (1 message, 0 tool calls), kill sandbox, re-dispatch with simpler instructions. Prefer kanban child cards for long tasks.

## End-to-end test results (cross-browser-ai MVP)

| Metric | Option A (CLI) | Option B (Plugin) |
|---|---|---|
| Worker crashes (test 1) | 8 (bracket bug) | 0 |
| Card body | Generic boilerplate | Tailored checklist |
| Test time per worker | ~20 min | ~10-17 min |
| Total findings | 18 | 19 |

Both produced equivalent finding depth. Plugin is faster and more reliable.
