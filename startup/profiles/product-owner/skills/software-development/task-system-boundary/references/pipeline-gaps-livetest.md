# Pipeline Gaps Discovered via Livetest (2026-07-29)

Eight gaps found during end-to-end livetest of the production pipeline. All fixed in SOUL.md or workflow-engine.py, documented here for future debugging.

## Gap 1: PO skips architect entirely
**Symptom:** PO went straight from spec to to-tickets, never routing through architect.
**Root cause:** `dev-planning` skill had no architect step. The skill went spec → to-tickets directly.
**Fix:** Added architect-gate step (step 3) to dev-planning. Extracted as shared skill so all PO workflows point to it.

## Gap 2: Deadlock — PO links waited-on card as child
**Symptom:** PO created architect design card, then linked it as child of its own task. Both stuck: PO blocks on dependency waiting for architect, architect card stuck in todo because parent (PO) is still running.
**Root cause:** `kanban_link` creates parent→child dependency. The child can't promote to ready until the parent is done. But the parent is blocked waiting for the child. Circular.
**Fix:** Use `kanban_block(kind="dependency")` to wait, never `kanban_link` for waited-on cards. Added explicit warning to architect-gate and team-delegation skills.

## Gap 3: No QA trigger after merge
**Symptom:** Feature merged to master, bead closed, but QA never ran.
**Root cause:** Nobody in the pipeline created a QA card. The verifier merges and completes — nothing triggers QA.
**Fix:** Verifier SOUL.md: after merge, create QA card (`assignee: qa`) on same board.

## Gap 4: QA findings die in report
**Symptom:** QA found P2 bug, noted it in PASS report, but filed no bead. Finding lost.
**Root cause:** QA SOUL.md said "if it breaks: file beads" — P2 on a PASS isn't "breaking."
**Fix:** QA SOUL.md step 6: file findings as beads regardless of pass/fail. Route by type: bug→debugger, non-bug→tech-lead, spec→product-owner.

## Gap 5: Bug beads orphaned (no epic link)
**Symptom:** Bug bead floating independently in bd list, not linked to epic.
**Root cause:** QA SOUL.md didn't say to link bugs to parent epic.
**Fix:** QA SOUL.md: link every bead to parent epic with `bd dep add <bug-id> <epic-id> --type parent-child`.

## Gap 6: bd --type=bug doesn't set issue_type
**Symptom:** Workflow engine bug routing (`issue_type == "bug"`) never fires. Bug beads dispatch to PO→tech-lead instead of debugger.
**Root cause:** `bd create --type=bug` stores `issue_type` as `task` and puts "bug" in the title. The `--type` flag sets the title, not issue_type.
**Fix:** Engine code (`dispatch_bug_to_debugger`) added. PO also manually recognizes bug content and routes to debugger when issue_type is wrong. Engine check may need to also match on title or labels containing "bug".

## Gap 7: Debugger fix never merges
**Symptom:** Debugger wrote fix on `debug/<bug-id>-<slug>` branch, said "handed back for QA re-verify + merge review," completed card. Fix sat on branch forever.
**Root cause:** Debugger SOUL.md said "NEVER merge the bug branch to main — handed off for review/merge" but nobody picked up the handoff. No card created for the merge step.
**Fix:** Debugger SOUL.md EXIT A: create verifier card for review+merge. Verifier owns merge gate (rebase, re-run tests, merge, release slot).

## Gap 8: No QA re-test after bug fix
**Symptom:** Bug fix merged, but QA never re-tested the running artifact.
**Root cause:** Nobody created a QA card after the verifier merged the debugger's fix.
**Fix:** Verifier creates QA card after merging any fix (same pattern as feature post-merge). Debugger SOUL.md EXIT A explicitly calls out: verifier reviews+merges, then creates QA card for re-test.

## Pipeline after all fixes (verified end-to-end)

```
PO → architect-gate → to-tickets → dispatch → tech-lead → dev↔verifier → merge
  → QA → files bug bead (linked to epic) → debugger → discover → RED → fix → falsify
  → converge → RCA → verifier reviews+merges → QA re-test → PASS → done
```
