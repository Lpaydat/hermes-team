# Pipeline Livetest Findings (2026-07-29 → 2026-07-30)

15 bugs found through 9 rounds of end-to-end livetests of the production pipeline. Each was found, root-caused, and fixed in the skill or config that governs that step.

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
**Note:** Verified in livetest 3+4 — `dispatch_bug_to_debugger()` fires correctly when `issue_type=bug`. Also added labels fallback (`issue_type == 'task'` + `'bug' in labels`) because bd versions may store the type differently.

## Bug 7: Debugger fix never merges

**Symptom:** Debugger fixes bug, writes RCA, closes bug bead — but fix sits on `debug/<bug-id>` branch forever. Never merged to master.
**Root cause:** Debugger SOUL.md said "handed back to qa/originator to re-verify" but nobody picked up the handoff. No card created for the merge step.
**Fix:** Debugger SOUL.md EXIT A now says: create a verifier card (`assignee: verifier`) for review+merge. Verifier merges fix branch, then creates QA card for re-test.
**File:** `debugger/SOUL.md`

## Bug 8: No QA re-test after bug fix

**Symptom:** Bug fixed and merged, but nobody tested the running artifact. Same gap as bug 3 but for the bug-fix path.
**Root cause:** The verifier created for the bug merge didn't know to also create a QA card.
**Fix:** Same pattern as feature post-merge — verifier creates QA card after any merge, including bug fixes.
**File:** `verifier/SOUL.md`

## Bug 9: dispatch_bug_to_debugger passes invalid --skills flag

**Symptom:** Workflow engine detected `issue_type=bug`, called `dispatch_bug_to_debugger()`, but card creation failed silently. Board stayed empty.
**Root cause:** `dispatch_bug_to_debugger()` passed `--skills loops-engineering` to `hermes kanban create`, but the CLI doesn't accept `--skills`. The error was `unrecognized arguments`.
**Fix:** Removed `--skills` from the kanban create call. Debugger loads its own skills via SOUL.md.
**File:** `workflow-engine.py`

## Bug 10: Debugger "already-fixed" case skips QA entirely

**Symptom:** Debugger found the bug was already fixed on master (duplicate of a prior fix). Closed the bead without creating any QA card or verifier card. The running artifact was never re-tested.
**Root cause:** Debugger SOUL.md EXIT A said create verifier+QA cards for the normal fix case, but the "already-fixed" edge case had no QA instruction. Debugger closed the bead and exited.
**Fix:** Initially patched debugger SOUL.md to create QA card directly for already-fixed case. Later replaced with workflow engine phase 5 (qa-trigger) which auto-creates QA cards for ALL completed verifier/debugger cards with "merged" in summary.
**File:** `debugger/SOUL.md`, `workflow-engine.py`

## Bug 11: QA trigger fires on internal loop phases (spurious cards)

**Symptom:** 12 QA cards created when only 5 were legitimate. Debugger's loop_engine internal verifier cards (falsification, RCA verification, discover phase) triggered the QA card-based trigger.
**Root cause:** QA trigger checked `assignee IN ('verifier', 'debugger')` and `status = 'done'`, but didn't filter out internal loop phases. Parent-child checks failed because loop_engine uses complex hierarchies that don't follow simple parent-assignee patterns.
**Fix (after 4 iterations):** Regex pattern matching on completion summaries. Only triggers when summary contains "merged to master", "merged to main", ". merged ", or "^merged ". Validated: 6 correct triggers, 0 false positives across 18 historical cards.
**Lesson:** Detect outcomes in natural language summaries, not structural relationships. The verifier writing "merged to master" is ground truth — parent-child links and assignee checks are indirect and unreliable.
**File:** `workflow-engine.py`

## Bug 12: QA trigger first-run creates card for initial commit (no code)

**Symptom:** QA trigger fired on the initial project commit (just spec/driver files, no code). QA tested an empty repo and filed "no source code" bugs.
**Root cause:** First-run state seeding was missing. The engine saw `last_sha = None` (no baseline) and treated the initial commit as "master advanced."
**Fix:** Added first-run check: if `last_sha is None`, seed state with current HEAD and return empty actions. Only trigger on subsequent advances.
**File:** `workflow-engine.py` (later replaced entirely by card-based approach)

## Bug 13: QA trigger fires on PO spec/doc commits (git-based approach)

**Symptom:** QA trigger fired when PO committed `.driver/` spec files and ADR docs — no code merged, but the git HEAD changed.
**Root cause:** The git-based trigger detected ANY commit on master, not just merge commits. Added `git rev-list --merges --count` filter, but this introduced the first-run seeding bug (bug 12).
**Fix:** Replaced the entire git-based approach with card-based detection. See bug 14.
**File:** `workflow-engine.py`

## Bug 14: Card-based QA trigger fires on debugger internal loop phases

**Symptom:** Card-based trigger created spurious QA cards when the debugger's loop_engine completed internal verifier cards (falsification, RCA verification). 12 QA cards when only 5 were legitimate.
**Root cause:** Parent-child and assignee filters couldn't distinguish loop_engine's internal verifier cards from real merge-gate verifier cards. The loop_engine creates complex parent chains (verifier→developer→loop) that don't match simple parent-assignee patterns.
**Fix (after 4 iterations of increasing sophistication):** Regex pattern matching on completion summaries. Only triggers when the summary matches: `merged to master`, `merged to main`, `. merged `, `^merged `. Internal phases say "GREEN", "RED", "RCA" — never "merged to". Zero false positives validated against 18 historical cards.
**Lesson:** Detect outcomes in natural language summaries, not structural relationships.
**File:** `workflow-engine.py`

## Bug 15: Bug routing — `issue_type == "bug"` insufficient (labels fallback needed)

**Symptom:** Bug beads with `issue_type=task` (bd stores them this way in some versions) bypassed the debugger routing and went to tech-lead.
**Root cause:** `bd create --type=bug` may store `issue_type` as `task`. The engine's check `issue_type == "bug"` missed these.
**Fix:** Added labels fallback: also route to debugger when `issue_type == "task"` AND any label contains the keyword "bug".
**File:** `workflow-engine.py`

## Clean runs (stability confirmed)

After all 15 bugs were fixed, two consecutive clean e2e runs confirmed stability:

- **Run 8 (2026-07-30):** 3 slices, 3 sequential merges (~1h apart), 3 QA cards (all legitimate), 0 bugs, 0 structural failures, 0 debugger cycles needed.
- **Run 9 (2026-07-30):** 2 slices, 4 QA cards (2 feature merges + 2 bug fix QA re-tests), 1 bug found by QA (OSError traceback), auto-routed to debugger via labels fallback, fixed+merged+QA re-tested PASS. Zero structural failures.

## Lesson

Livetests are the only reliable way to find pipeline gaps. Each test surfaces bugs that skill inspection and code review miss. Run end-to-end and monitor every step — don't stop at "the proven part works."

### Monitoring protocol (HARD REQUIREMENT)

When running a livetest, monitor continuously and report every milestone. Use `terminal(background=true, notify_on_complete=true)` for long waits. Never disappear for hours without reporting. Commit everything before moving on to the next task. The user catches silence — it is a first-class failure signal.
