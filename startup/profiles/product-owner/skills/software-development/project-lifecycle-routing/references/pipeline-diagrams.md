# Pipeline Diagrams

## Full production pipeline

```
USER
 │
 ▼
PRODUCT OWNER (SOUL.md = charter: role + stance + handoffs + skill index)
 │
 │  Skill index routes the trigger:
 │  ┌──────────────────┬────────────────────────────────┐
 │  │ project-kickoff  │ new project / migration        │
 │  │ project-promotion│ prototype → production         │
 │  │ dev-planning     │ feature work (existing project)│
 │  │ dev-dispatch     │ cron dispatch card appears     │
 │  │ project-discovery│ discovery cron / audit         │
 │  └──────────────────┴────────────────────────────────┘
 │
 ▼

PLANNING PHASE:
  grill (adversarial interview, N decisions locked)
    → spec (to-spec synthesis)
    → architect (design-council: research + peer fan-out, ADRs)
    → to-tickets (tracer-bullet slices citing ADRs)
    → USER APPROVAL GATE
    → beads DB

DISPATCH PHASE:
  stateless graph engine (cron 60s tick: SYNC → RESET → ACTIVATE+DISPATCH → TRIGGERS)
    → dev-dispatch trigger fires on [spec]/[ticket-] card completion
    → routes by type: bug→debugger, research→scout, ops→ops, tickets→PO, default→architect chain

CONSTRUCTION PHASE (per ticket):
  tech-lead-execute trigger fires on [ticket-NN] card completion
    plan (loop_engine: dev phases + verifier phases, max 5 iters)
    → verify (adversarial behavior tests + lint gate)
    → fix↔re-verify (max 10 iterations)
    → close (merge ticket branch to master)
    → merge-verify (verifier mechanically confirms: git log, fsck, tests)

QA PHASE:
  Replaced by the verifier's adversarial behavior testing in tech-lead-execute.
  The old cron QA trigger (5-phase cron) is SUPERSEDED.

DEBUGGER LOOP:
  debug-fix subworkflow: test_failure → debugger → verifier
    EXIT A: fix + regression test + RCA
    EXIT B: design flaw → ADR stub → architect gate

REFACTOR PHASE:
  refactor-cycle trigger fires on [milestone-NN] card completion
  (milestone auto-promotes when all parent tickets complete via kanban dep-gate)
  → refactor scan → may create [refactor-request] card → back to dev-dispatch
```

## The three orchestrators

- **Architect** — design fan-out (researcher + peer perspectives → ADR)
- **Tech-lead** — construction (loop_engine: developer builds, verifier checks per phase)
- **Debugger** — diagnosis (debug-fix subworkflow: test_failure → fix → re-verify)

## Role separation (load-bearing)

- Developer = the Generator. Never reviews, scores, or approves its own work.
- Verifier = the Checker. Never writes code. Reviews output, not reasoning.
- This separation makes adversarial verification meaningful.

## Merge responsibility

The tech-lead owns the merge (close node in tech-lead-execute):
1. Merge ticket branch into master (`git merge --no-ff`)
2. Run ALL tests on merged result
3. Verify no work was lost (`git log master..<branch>` = empty)
4. merge-verify node (verifier) independently confirms: branch merged, no dangling commits, tests pass
