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
  workflow engine (cron 60s: bead-sync + dispatch + scanner)
    → dev-dispatch (PO creates tech-lead cards)

CONSTRUCTION PHASE:
  tech-lead (kanban_delegate: creates dev + verifier atomically)
    → developer (harness wrapper, generates code)
    ↔ verifier (adversarial review, 3-stage: execute → fan out → synthesize)
    │   FAIL → fix card → re-iterate (inner loop, no tech-lead)
    │   iter ≥3 → ESCALATE → tech-lead
    │   PASS → verifier merges (serialized, post-rebase test)

QA PHASE:
  QA (tests the assembled running artifact, no code reading)
    PASS → ACTUAL DONE
    FAIL → triage by type:
      bug (code wrong) → DEBUGGER
      non-bug (behavior wrong) → TECH-LEAD
      spec (spec wrong) → PRODUCT-OWNER

DEBUGGER LOOP:
  reproduce → hypothesize+fix (→ developer) → falsify (→ verifier) → converge
    EXIT A: localized bug → fix + regression test + RCA → back to QA
    EXIT B: design flaw → RCA + ADR stub → architect gate (re-enters top)

ESCALATION CHAIN:
  developer/verifier blocked → tech-lead
  tech-lead blocked → product-owner
  product-owner blocked → human (HUMAN_REQUIRED)
  tech-lead hard bug → debugger
  verifier iter ≥3 → tech-lead
  QA bug → debugger
  debugger design flaw → architect
```

## The three orchestrators

- **Architect** — design fan-out (researcher + peer perspectives → ADR)
- **Tech-lead** — construction fan-out (developer + verifier → merged feature)
- **Debugger** — diagnosis fan-out (developer fix + verifier falsify → proven fix)

## Role separation (load-bearing)

- Developer = the Generator. Never reviews, scores, or approves its own work.
- Verifier = the Checker. Never writes code. Reviews output, not reasoning.
- This separation makes adversarial verification meaningful.

## Verifier merge gate

The verifier owns the merge:
1. Acquire merge slot (`bd merge-slot`)
2. Rebase onto main
3. Re-run full test suite on rebased candidate
4. Merge
5. Release slot

Serialized — one slot holder at a time.
