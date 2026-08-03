# Measured Evidence: Dead-Branch Leak on verify→close Shortcut

Session-specific measured proof for lesson #17 (dead-branch skip fails on fix↔re-verify cycles when verify=PASS). A full 5-board unbiased livetest of `tech-lead-execute`, reconstructed from `workflow-state.db` `engine_events`.

## The correlation (the headline)

Every instance that exercised the fix loop completed cleanly. Every instance that took the verify→close shortcut (verify=PASS, fix/re-verify bypassed) **leaked** — reached `DONE node close` but never emitted `workflow_completed`, stuck `status='active'`.

| Board | Instance suffix | Path taken | Fix iters | workflow_completed? | Final status |
|-------|-----------------|-----------|-----------|---------------------|--------------|
| 1 | `71943120` | plan→verify→close | 0 | ❌ NO | **leaked (active)** |
| 1 | `843e10cb` | plan→verify→close | 0 | ❌ NO | **leaked (active)** |
| 2 | `94a0ef72` | plan→verify→fix→re-verify→fix→re-verify→close | 2 | ✅ yes | completed |
| 3 | `eff137c2` | plan→verify→close | 0 | ❌ NO | **leaked (active)** |
| 4 | `18de592b` | plan→verify→fix→re-verify→close | 1 | ✅ yes | completed |
| 5 | `dbd61207` | plan→verify→fix→re-verify→fix→re-verify→close | 2 | ✅ yes | completed |

**3 of 6 instances leaked — 100% on the shortcut path, 0% on the fix-loop path.** This is not noise; it is a deterministic structural defect.

## Contrast proof: qa-gate dead-branch marking works, tech-lead-execute's doesn't

The same engine ran `qa-gate` instances on the same boards in the same window. qa-gate **correctly emitted `node_skipped`** for its 9 dead branches (qa-receive, qa-build, qa-functional, qa-journeys, qa-security, qa-explore, qa-quick, qa-verdict, route-bug) on the "no code merge" path, and **all 9 qa-gate instances completed**.

Query that proves the absence in tech-lead-execute:
```sql
SELECT COUNT(*) FROM engine_events
WHERE event_type='node_skipped' AND workflow_id='tech-lead-execute';
-- → 0
```

The dead-branch mechanism exists and works (qa-gate uses it). It is simply not being applied to the `fix`/`re-verify` nodes in `tech-lead-execute` when the verify→close PASS edge fires. This narrows the fix from "the dead-branch logic is broken" to "the dead-branch logic is not invoked for this specific cycle topology."

## The smoking-gun query

Find instances that reached `DONE node close` but never emitted `workflow_completed`:
```sql
SELECT w.instance_id, w.board, w.status,
       (SELECT MAX(datetime(e.timestamp,'unixepoch'))
        FROM engine_events e
        WHERE e.instance_id=w.instance_id AND e.message LIKE 'DONE node close%') AS close_done_ts,
       (SELECT MAX(datetime(e.timestamp,'unixepoch'))
        FROM engine_events e
        WHERE e.instance_id=w.instance_id AND e.event_type='workflow_completed') AS wf_completed_ts
FROM workflow_instances w
WHERE w.workflow_id='tech-lead-execute';
```
Leaked rows have a non-null `close_done_ts` and a null `wf_completed_ts`.

## Reconstruction queries (reusable for any template)

```sql
-- Dispatch order per instance (the actual graph path)
SELECT datetime(timestamp,'unixepoch'), instance_id, message
FROM engine_events
WHERE event_type='node_dispatched' AND workflow_id='<WF>'
ORDER BY instance_id, timestamp;

-- Fix-loop iteration count per instance
SELECT instance_id, COUNT(*) AS fix_dispatches
FROM engine_events
WHERE event_type='node_dispatched' AND message LIKE 'DISPATCHED node fix%'
GROUP BY instance_id;

-- Instance status vs completion event (the leak detector)
-- (see smoking-gun query above)
```

## Secondary defects observed in the same run

- **Duplicate instance (trigger-key race):** board-1 spawned two tech-lead instances off `spec-1`. The first (`71943120`) was created at 19:10:27, but its trigger_key (`trig:tech-lead-execute:spec-1`) was registered at 19:11:11 — 44s LATER. The dedup check could not see the first instance when the second trigger arrived. See lesson #20.
- **node_states not updated on re-dispatch:** on board-2, `fix` shows `card_id=t_dcc77d23` (iteration 1) in node_states, but the iteration-2 fix card `t_69482243` appears only in engine_events. `output` is `{}` for ALL tech-lead nodes — verdict data lives only in qa-gate `trigger_context`, not in tech-lead node outputs. node_states is not a faithful snapshot of final node state when a node dispatches more than once.
