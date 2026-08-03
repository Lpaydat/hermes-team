---
name: debugger-exit-template
description: "Route debugger exit verdicts to handlers. Use when building or debugging the debugger-exit workflow template."
disable-model-invocation: true
---

# Debugger Exit Template

Wraps the debugger card and routes its exit verdict. 3 nodes, 3 edges, no cycle.

## Architecture

```
check-verdict (command) extracts verdict from trigger metadata
  ├── fixed → re-verify (verifier independently confirms the fix)
  │             ├── PASS → exit (ship)
  │             └── FAIL → escalate-po (PO decides: manual-fix, accept-risk, wont-fix)
  ├── escalated-design → escalate-po (PO opens architect gate)
  └── blocked-hitl → escalate-po (PO unblocks or redirects)
```

## Why no iteration loop

The initial design had a `re-verify ↔ re-debug` back-edge cycle for iterative fix attempts. This caused a dead-branch deadlock: when the escalated path fired, re-verify couldn't be skipped because re-debug (in the cycle) was still pending. The engine's dead-branch check can't propagate through cycles.

Simplified to: re-verify FAIL → escalate-po. The debugger's internal `loop_engine` already handles iteration (reproduce→fix→converge with its own caps). The template routes the final outcome only.

## Configurable iteration cap

The iteration cap lives in `debugger-exit.config.md` (not `.json` — the engine loads all `.json` files as templates). Current value: 10. To change it, update the config file AND the conditions in the template (if iteration conditions are used).

## Pitfalls encountered

1. **Back-edge cycle deadlock** — dead-branch skip can't propagate through cycles. Avoid cycles when non-cycle paths need dead-branch propagation.
2. **`depends_on` conflicts with explicit edges** — implicit unconditional edges from `depends_on` block conditional dispatch. Remove `depends_on` when explicit edges exist.
3. **Config `.json` loaded as template** — engine tries to load all `.json` files in templates dir. Use `.md` for config files.
4. **Debugger detects synthetic test cards** — when testing with fake bug cards, the debugger intelligently refuses to fix non-existent bugs (blocked-hitl: "no symptom, no expected behavior"). This is correct behavior.
5. **completed_at must be set for triggers** — synthetic completed cards need `completed_at` timestamp set in the tasks table. Cards with `status=done` but `completed_at=NULL` won't trigger workflows. The engine's trigger_watermark uses this timestamp.
6. **ESCALATE deadlock in kanban_chains** — ESCALATE'd verifier cards have status=blocked (not done), which permanently blocks kanban_chains parents. Use loop_engine instead — it handles escalation internally.
