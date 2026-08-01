# Engine Bugs Discovered During Livetests

Four bugs found and fixed during the builder pipeline livetest (10 ideas, foreach subworkflow, real builder agent).

## Bug 1: Archived cards not treated as terminal

**Symptom:** 3 child workflow instances stuck as "active" forever after their grill cards were externally archived.

**Root cause:** PHASE 1 completion checks only recognized `status="done"`. Archived cards have `status="archived"` — a different terminal state. The engine kept waiting for them to reach "done".

**Fix:** Treat `"archived"` as terminal alongside `"done"` in both foreach card checks and single-card checks:

```python
# Foreach cards (PHASE 1)
if fcard.status == "done" or fcard.status == "archived":

# Single-card checks (PHASE 1)
if card.status == "done" or card.status == "archived":
```

**Test:** `test_adv_card_archived_mid_workflow` updated to assert archived = terminal (workflow advances).

**Pitfall:** If you archive cards to remove ideas from a running pipeline, the engine will still advance their child workflows (archived = terminal = "done enough to proceed"). To truly cancel a child workflow, mark the instance as `completed` directly in the state DB.

## Bug 2: Trigger context double-prefix

**Symptom:** `${trigger.board}` resolved to empty string in command nodes during manual workflow starts.

**Root cause:** `cmd_start` in main.py injected trigger context keys WITH the `trigger.` prefix already applied (`trigger.board`). But the `context()` method that merges trigger context into runtime context ALSO adds the `trigger.` prefix — creating `trigger.trigger.board`.

**Fix:** Use bare keys in cmd_start:
```python
# WRONG
context["trigger.board"] = args.board    # → trigger.trigger.board

# RIGHT
context["board"] = args.board            # → trigger.board (context() adds prefix)
```

## Bug 3: title_template only on foreach nodes

**Symptom:** Child workflow cards got default titles (`[grill] task`) instead of custom titles (`Grill: LeadPilot`).

**Root cause:** `title_template` was wired into `_dispatch_foreach_node` but NOT `_dispatch_node` (the regular task dispatch path). Child workflow nodes are regular task nodes, not foreach nodes.

**Fix:** Added title_template check to `_dispatch_node`:
```python
if node.title_template:
    card_title = resolve_template(node.title_template, ctx)
else:
    card_title = f"[{node.id}] {node.skill or 'task'}"
```

## Bug 4: Per-profile config.yaml ignored by dispatcher

**Symptom:** Set builder concurrency to 5 in `profiles/builder/config.yaml` but dispatcher still limited to 3.

**Root cause:** The kanban dispatcher reads from the **global** `startup/config.yaml`, not per-profile configs. The per-profile config has no effect on `max_in_progress` / `max_in_progress_per_profile`.

**Fix:** Edit global config.yaml:
```yaml
kanban:
  max_in_progress: 10              # global cap
  max_in_progress_per_profile: 5   # per-profile cap (tighter)
```

Gateway must be restarted after config change (kill + relaunch with `terminal(background=true)`).
