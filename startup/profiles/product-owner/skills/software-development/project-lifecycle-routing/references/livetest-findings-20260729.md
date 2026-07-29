# Pipeline Livetest Findings (2026-07-29)

6 bugs found through end-to-end livetests of the production pipeline. Each was found, root-caused, and fixed in the skill or config that governs that step.

## Bug 1: PO skips architect entirely

**Symptom:** PO loaded dev-planning, went straight to to-tickets, created beads without architect design.
**Root cause:** `dev-planning` skill had no architect step — it went discuss → to-spec → to-tickets.
**Fix:** Added architect-gate step to dev-planning (step 3). Created `architect-gate` shared skill as single source of truth.
**File:** `dev-planning/SKILL.md`, `shared-skills/architect-gate/SKILL.md`

## Bug 2: Deadlock — PO links architect card as child

**Symptom:** Architect card stuck in `todo`, PO card stuck in `blocked` (dependency). Neither advances.
**Root cause:** PO called `kanban_link` making the architect design card a child of the PO task. Dispatcher keeps children in `todo` while parent is `running`. But parent is `blocked` waiting for the child. Classic circular dependency.
**Fix:** Explicit warning in `architect-gate` and `project-lifecycle-routing` — use `kanban_block(kind="dependency")`, NOT `kanban_link`.
**File:** `architect-gate/SKILL.md`, `project-lifecycle-routing/SKILL.md`

## Bug 3: No QA trigger after merge

**Symptom:** Feature merged, bead closed, nothing happened. No QA card created.
**Root cause:** Verifier SOUL.md said merge + close bead. No instruction to create QA card. Workflow engine didn't dispatch QA. Nobody owned the post-merge trigger.
**Fix:** Verifier SOUL.md — after merge, create QA card (`assignee: qa`) on the same board.
**File:** `verifier/SOUL.md`

## Bug 4: QA findings die in report

**Symptom:** QA found P2 bug, noted it in PASS report, did nothing with it. Finding lost.
**Root cause:** QA SOUL.md said "if it breaks: file beads" — P2 finding on PASS wasn't "breaking" so QA followed instructions literally.
**Fix:** QA SOUL.md — file findings as beads regardless of pass/fail. Route by type: bug→debugger, non-bug→tech-lead, spec→product-owner.
**File:** `qa/SOUL.md`

## Bug 5: Bug beads orphaned from epic

**Symptom:** Bug bead not linked to epic. `bd list` shows it floating independently. No rollup visibility.
**Root cause:** QA SOUL.md said "file beads" but not "link to parent epic."
**Fix:** QA SOUL.md — link every bug bead to parent epic with `bd link`.
**File:** `qa/SOUL.md`

## Bug 6: Bug routing goes to tech-lead, not debugger

**Symptom:** Bug bead dispatched through generic PO dispatch → tech-lead path. Tech-lead crashed twice.
**Root cause:** Workflow engine `phase_dispatch` treated all non-wayfinder beads the same. No routing by `issue_type=bug`.
**Fix:** Added `dispatch_bug_to_debugger()` to workflow-engine.py. Bug beads route directly to debugger, bypassing PO dispatch → tech-lead.
**File:** `workflow-engine.py`
**Note:** Not fully verified in livetest — idempotency key from earlier failed dispatch prevented re-dispatch. Code is syntactically valid and committed.

## Lesson

Livetests are the only reliable way to find pipeline gaps. Each test surfaces bugs that skill inspection and code review miss. Run end-to-end and monitor every step — don't stop at "the proven part works."
