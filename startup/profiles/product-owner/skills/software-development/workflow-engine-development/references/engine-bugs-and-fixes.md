# Engine Bugs and Fixes — Session-Discovered Issues

## Bug: Archived cards stuck in DISPATCHED forever

**Symptom:** Child workflow instances with externally-archived cards (manual cleanup, mid-test deletion) never reach terminal state. The node stays DISPATCHED, blocking the parent's `spawn_prototypes` node, which blocks the parent workflow from completing.

**Root cause:** PHASE 1 completion checks only looked for `card.status == "done"`. Archived cards have `status = "archived"` — not "done" — so the engine kept waiting.

**Fix:** Treat `"archived"` as terminal alongside `"done"` in two places:

1. **Foreach card check** (PHASE 1, `_check_instance`):
```python
# Before (BUG):
if fcard.status == "done":

# After (FIX):
if fcard.status == "done" or fcard.status == "archived":
```

2. **Single-card check** (PHASE 1, `_check_instance`):
```python
# Before (BUG):
if card.status == "done":

# After (FIX):
if card.status == "done" or card.status == "archived":
```

**Test update:** `test_adv_card_archived_mid_workflow` in `test_engine.py` was updated to assert the new behavior — archived = terminal, workflow advances.

**Gotcha:** When you archive a grill card mid-pipeline to remove an idea, the engine will ADVANCE that child (treating it as done) and dispatch the next node (build). If you truly want to cancel a child:
```python
conn.execute("UPDATE workflow_instances SET status = 'completed' WHERE instance_id = ?", (child_id,))
```

---

## Bug: Trigger context double-prefix

**Symptom:** `${trigger.board}` in template command nodes resolves to empty string when workflow is started via `main.py start --board X`.

**Root cause:** `cmd_start` injected trigger context with keys like `"trigger.board"`, but the `context()` method in `WorkflowInstance` already prepends `"trigger."` to each key. Result: `"trigger.board"` became `"trigger.trigger.board"`.

**Fix:** In `cmd_start` (main.py), inject BARE keys:
```python
# Before (BUG):
context["trigger.board"] = board
context["trigger.source"] = "manual"

# After (FIX):
context["board"] = board
context["source"] = "manual"
```

The `context()` method adds the `trigger.` prefix automatically. Templates then resolve `${trigger.board}` correctly.

**Diagnostic:** Check resolved context keys by querying the instance in the state DB:
```python
conn.execute("SELECT context FROM workflow_instances WHERE instance_id = ?", (iid,))
# If you see "trigger.trigger.board", you have the double-prefix bug
```

---

## Bug: Foreach barrier blocks independent pipelines

**Symptom:** 10 grill cards created, 2 complete, but build cards never dispatch until ALL 10 grills finish.

**Root cause:** Foreach on task nodes is a batch barrier. All N cards must complete before the next node advances.

**Fix:** Use `foreach + subworkflow` instead of `foreach + task`. Each item spawns its own independent child workflow instance. See `references/foreach-subworkflow.md` for the full pattern.

**Key insight:** This is NOT a bug in the engine — it's a design choice. Foreach-task = batch processing (all-at-once). Foreach-subworkflow = pipeline processing (per-item independence). Choose the right one for your use case.

---

## Diagnostic patterns

### Check all active instances
```bash
python3 main.py list
```

### Check if a node is stuck
```python
import sqlite3, json
conn = sqlite3.connect("workflow-state.db")
row = conn.execute("SELECT status, output FROM node_states WHERE instance_id=? AND node_id=?", (iid, node_id)).fetchone()
print(f"Status: {row[0]}, Output: {json.loads(row[1]) if row[1] else None}")
```

### Clean orphaned instances
```python
# Mark orphaned children completed
conn.execute("UPDATE workflow_instances SET status = 'completed' WHERE instance_id = ?", (child_id,))
# Or delete entirely
conn.execute("DELETE FROM node_states WHERE instance_id = ?", (iid,))
conn.execute("DELETE FROM workflow_instances WHERE instance_id = ?", (iid,))
```
