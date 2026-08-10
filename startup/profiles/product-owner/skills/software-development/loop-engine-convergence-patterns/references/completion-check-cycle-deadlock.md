# Completion-Check Cycle Deadlock — Forensic Analysis & Diagnostic

> Root cause confirmed 2026-08-09 via code-level investigation against 6 stuck hashtree instances.

## The bug

`tech-lead-execute` workflow instances stay `status='active'` after ALL real work completes. `_check_completion` returns False forever because `fix` and `re-verify` nodes are stuck at `PHASE_PENDING` and are reachable. They can never be skipped because they form a cyclic SCC — each blocks the other's dead-branch skip.

## Affected vs unaffected templates

| Template | Edges | Cyclic SCCs | Completes? |
|----------|-------|-------------|------------|
| tech-lead-execute | 7 | 1 (`{fix, re-verify}`) | ✗ stuck |
| milestone-gate | 16 | 0 | ✓ |
| dev-dispatch | 8 | 0 | ✓ |

**The cycle is the necessary condition.** No other template in the library has a non-trivial SCC.

## Exact call chain (runtime.py)

```
_tick_instance (L998)
  → _activate_dispatch_pass / pass 3 (L1369) — dispatches what it can
  → _check_completion (L1598)
      → find exit_nodes (L1612: nodes with no outgoing edges)
      → exit nodes terminal? (L1642-1645) — close/merge-verify: ✓
      → _reachable_nodes (L1652) — BFS from done/running seeds, ALL edges
      → check all reachable terminal? (L1656-1658)
          fix=PHASE_PENDING → returns False ✗
```

## Why fix/re-verify can never be skipped

`all_incoming_terminal_and_none_fired` (L303) requires ALL incoming sources terminal:

**Node `fix` incoming edges:**
- `verify→fix` (cond: verdict=='FAIL'): source verify=DONE ✓
- `re-verify→fix` (back-edge, cond: verdict=='FAIL'): source re-verify=PENDING ✗
- → returns False: re-verify not terminal

**Node `re-verify` incoming edges:**
- `fix→re-verify` (unconditional, back-edge): source fix=PENDING ✗
- → returns False: fix not terminal

**Circular deadlock:** fix waits on re-verify; re-verify waits on fix. Neither dispatches (verify=PASS so FAIL condition never fires). Neither can be skipped.

## State blob evidence (all 6 hashtree instances)

```json
{
  "fix": {"card_id": null, "card_status": "", "output": {}, "iteration": 0},
  "re-verify": {"card_id": null, "card_status": "", "output": {}, "iteration": 0},
  "verify": {"card_id": "t_xxx", "card_status": "done", "output": {"verdict": "PASS"}},
  "close": {"card_id": "t_xxx", "card_status": "done", "output": {"verdict": "merged"}},
  "merge-verify": {"skipped": true}
}
```

Key: `fix` and `re-verify` have no `skipped` flag, no `failed` flag, no card — pure PENDING.

## Key code locations

| Location | What | Line |
|----------|------|------|
| `node_phase()` | Derives phase from state blob | runtime.py:150 |
| `_TERMINAL_PHASES` | `{done, failed, skipped}` | runtime.py:147 |
| `activation_rule_satisfied()` | AND/OR edge semantics for dispatch | runtime.py:238 |
| `all_incoming_terminal_and_none_fired()` | Dead-branch skip detector | runtime.py:303 |
| `_activate_dispatch_pass()` | Pass 3: walk graph, dispatch/skip | runtime.py:1369 |
| `_check_completion()` | Exit-node + reachability fence | runtime.py:1598 |
| `_reachable_nodes()` | BFS from done/running, ALL edges | runtime.py:1661 |
| `bfs_reachable()` | Forward BFS helper | model.py:81 |
| `annotate_back_edges()` | Marks cycle-closing edges | model.py:171 |
| `tarjan_scc()` | SCC computation | model.py:100 |

## Proposed fix directions (NOT implemented)

### Option A — Condition-aware reachability (preferred)

In `_reachable_nodes` (L1661), don't traverse edges whose condition evaluated False at dispatch time. If `verify→fix` (verdict=='FAIL') is False, `fix` is only reachable via the back-edge from `re-verify`, which itself is unreachable → fix and re-verify become orphans → excluded from the completion check (L1654: `if node.id not in reachable: continue`).

This fixes the root cause: the reachability computation incorrectly treats dead conditional edges as traversal paths.

### Option B — SCC-aware dead-branch skip

In `all_incoming_terminal_and_none_fired` (L303), detect when a node is part of a cyclic SCC where NO member has ever dispatched (no card_id, iteration=0). If the entire SCC's external incoming edges are all terminal-but-not-firing, skip all SCC members simultaneously.

Breaks the circular dependency by treating the SCC as a unit.

## Reusable diagnostic script

Run this against any template to detect cycle-deadlock risk and find stuck instances:

```python
"""Diagnose whether a template's instances will deadlock on the completion check."""
import sqlite3, json, sys
sys.path.insert(0, "/home/lpaydat/.hermes-teams/startup/scripts")
from workflow_engine.model import tarjan_scc

DB = "/home/lpaydat/.hermes-teams/startup/kanban/workflow-state.db"
TPL_DIR = "/home/lpaydat/.hermes-teams/startup/scripts/workflow_engine/templates"

def check_template(workflow_id, board=None):
    # 1. Check for cyclic SCCs in template
    with open(f"{TPL_DIR}/{workflow_id}.json") as f:
        tmpl = json.load(f)
    node_ids = [n["id"] for n in tmpl["nodes"]]
    edges = [(e["from"], e["to"]) for e in tmpl.get("edges", [])]
    sccs = tarjan_scc(node_ids, edges)
    cyclic = [c for c in sccs if len(c) > 1]

    if not cyclic:
        print(f"{workflow_id}: ACYCLIC — no completion deadlock risk")
        return

    print(f"{workflow_id}: {len(cyclic)} cyclic SCC(s) — AT RISK")
    for c in cyclic:
        print(f"  SCC: {c}")

    # 2. Check stuck instances
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    query = "SELECT instance_id, status, state FROM workflow_instances WHERE workflow_id=?"
    params = [workflow_id]
    if board:
        query += " AND board=?"
        params.append(board)
    for r in conn.execute(query, params):
        state = json.loads(r["state"])
        stuck_nodes = []
        for nid in node_ids:
            ns = state.get(nid, {})
            if not ns.get("skipped") and not ns.get("failed") and not ns.get("done"):
                cs = ns.get("card_status", "")
                if cs not in ("done", "archived"):
                    stuck_nodes.append(nid)
        flag = "STUCK" if stuck_nodes else "ok"
        print(f"  {r['instance_id']}: status={r['status']} {flag}")
        if stuck_nodes:
            print(f"    non-terminal nodes: {stuck_nodes}")
    conn.close()

# Usage:
# check_template("tech-lead-execute", "hashtree")
# check_template("milestone-gate")
```

## Manual workaround (emergency)

For each stuck instance, mark fix and re-verify as `skipped` in the state JSON blob. This makes `_check_completion` return True on the next tick. WARNING: band-aid only — the engine bug remains.

```python
import sqlite3, json
conn = sqlite3.connect(DB)
for iid in [...stuck_instance_ids...]:
    row = conn.execute("SELECT state FROM workflow_instances WHERE instance_id=?", (iid,)).fetchone()
    state = json.loads(row[0])
    state["fix"]["skipped"] = True
    state["re-verify"]["skipped"] = True
    conn.execute("UPDATE workflow_instances SET state=? WHERE instance_id=?", (json.dumps(state), iid))
conn.commit()
conn.close()
```
