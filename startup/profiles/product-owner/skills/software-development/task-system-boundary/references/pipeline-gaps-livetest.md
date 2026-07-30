# Pipeline Gaps Discovered via Livetest (2026-07-29/30)

Ten gaps found during end-to-end livetesting of the production pipeline. All fixed. Gaps 3, 8, 10 were ultimately replaced by the automated QA trigger (workflow engine phase 5).

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
**Fix (original):** Verifier SOUL.md: after merge, create QA card.
**Fix (final):** Replaced with workflow engine phase 5 (qa-trigger) — automatically detects new commits on master and creates QA card. No agent involvement needed.

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
**Fix:** Engine code (`dispatch_bug_to_debugger`) added. PO also manually recognizes bug content and routes to debugger when issue_type is wrong.

## Gap 7: Debugger fix never merges
**Symptom:** Debugger wrote fix on `debug/<bug-id>-<slug>` branch, said "handed back for QA re-verify + merge review," completed card. Fix sat on branch forever.
**Root cause:** Debugger SOUL.md said "NEVER merge the bug branch to main — handed off for review/merge" but nobody picked up the handoff. No card created for the merge step.
**Fix:** Debugger SOUL.md EXIT A: create verifier card for review+merge. Verifier owns merge gate.

## Gap 8: No QA re-test after bug fix
**Symptom:** Bug fix merged, but QA never re-tested the running artifact.
**Root cause:** Nobody created a QA card after the verifier merged the debugger's fix.
**Fix (final):** Same as Gap 3 — workflow engine phase 5 auto-creates QA card when it detects the merge commit.

## Gap 9: --skills flag crashes dispatch_bug_to_debugger
**Symptom:** Workflow engine detected `issue_type=bug`, called `dispatch_bug_to_debugger()`, but the kanban card creation failed silently. Bug bead sat in `bd ready` forever.
**Root cause:** `dispatch_bug_to_debugger()` passed `--skills loops-engineering` to `hermes kanban create`. The CLI doesn't accept `--skills`.
**Fix:** Removed `--skills` from the `run_kanban` call.

## Gap 10: Debugger "already-fixed" case skips QA entirely
**Symptom:** Debugger found bug was already fixed on master. Diagnosed correctly, wrote RCA, closed bead — but never created a QA card.
**Root cause:** EXIT A didn't cover the already-fixed edge case. Debugger skipped both verifier AND QA.
**Fix (final):** Workflow engine phase 5 handles this — it detects ANY commit change on master, regardless of whether a debugger was involved. The "already-fixed" case produces no new commit (the fix was already merged), so the engine's baseline state already matches master. The lesson: don't rely on the debugger to create QA cards; the engine handles it structurally.

## Gap 11: QA trigger fires on initial commit (no code yet)
**Symptom:** Workflow engine phase 5 created a QA card for the initial repo commit (just a spec file, no code). QA tested an empty repo, found "no source code" bugs, filed bug beads.
**Root cause:** First run for a board had no baseline SHA in state file. `state.get(board)` returned None. The code treated None as "different from current SHA" and created a card.
**Fix:** First run seeds the baseline SHA silently and returns empty actions — no card created. Only subsequent SHA changes trigger QA cards.

## Gap 12: QA trigger fires on spec/doc commits (git-based)
**Symptom:** Workflow engine phase 5 detected master HEAD changed and created a QA card. But the change was a PO committing `.driver/` spec files and ADR docs — no code. QA tested an empty repo, found "no source code" bugs, filed bogus bug beads.
**Root cause:** Git-based trigger fired on ANY commit, not just code merges. Added `git rev-list --merges --count` filter, but that introduced gap 11 (first-run seeding bug).
**Fix:** Replaced the entire git-based approach with card-based detection — see Gap 13.

## Gap 13: QA trigger rewritten as card-based scan
**Symptom:** The git-based approach had three failure modes (spec commits, first-run seeding, merge-count fragility). Too many edge cases.
**Root cause:** Git parsing is indirect — it infers "code landed" from commit metadata. The kanban DB already knows exactly when a verifier or debugger card completed (which IS the merge event).
**Fix:** Rewrote phase 5 to scan the kanban DB for recently-completed verifier/debugger cards (1-hour window), filter out probe/sub-review cards, and create QA cards. Dedup via `qa-after-<source-card-id>`. No git parsing, no state file, no false positives. The completed card's summary provides QA context (what was built, what to test).

## Gap 14: QA trigger fires on debugger's internal loop_engine verifier cards
**Symptom:** When the debugger's loop_engine completed internal verifier cards (falsification, RCA verification), the card-based QA trigger fired and created spurious QA cards. These QA cards tested code that hadn't changed — the loop_engine verifier was checking a fix on a branch, not merging to master.
**Root cause:** The card-based trigger queries `assignee IN ('verifier', 'debugger')` and filters `[probe]` and `verify t_` titles. But the debugger's loop_engine creates verifier cards with titles like `5rz phase1 verify: fix GREEN + falsify` — none of the existing filters caught these.
**Fix:** Three filters added: (1) skip debugger cards that don't start with `[auto]` (internal phases), (2) skip verifier cards whose parent (via `task_links`) is a debugger card (loop_engine children), (3) keep existing `[probe]` and `verify t_` filters. Also fixed `conn.close()` placement — it was called before the parent-check query inside the loop.

## Gap 15: Parent-child filter misses loop_engine's complex parent chains
**Symptom:** The parent-child debugger filter (gap 14) still produced spurious QA cards. The loop_engine creates verifier cards with parents that are OTHER verifier cards or developer cards — not the debugger card directly. A card with parent chain verifier→developer→loop still slipped through.
**Root cause:** Parent-child relationships in the kanban DB are not reliable indicators of whether a card is an internal loop phase. The loop_engine uses `kanban_chains` which creates its own dependency model, not the direct parent links the filter checked.
**Fix:** Replaced ALL relationship-based filters (parent-child, [auto] prefix, assignee chains) with regex merge detection on the completion summary. The trigger now fires ONLY when the summary (lowercased) matches: `merged to master`, `merged to main`, `. merged `, or `^merged `. Internal phases say "GREEN", "RED", "RCA", "verified" — never "merged to". Validated against 18 historical cards: 6 correct triggers (all real merges), 0 false positives.

## Gap 16: Regex QA trigger fails — verifiers write "PASS" not "merged"
**Symptom:** Feature merged to master (fast-forward, code files present), verifier card completed, but QA card never created. Board cleared with zero QA cards for a project that has real users.
**Root cause:** The regex merge detection (gap 15) required specific phrases in the completion summary: "merged to master", "merged to main", ". merged", "^merged". But verifiers write "PASS — all 26 ACs verified..." — they describe the verdict, not the merge action. The word "merged" never appears. Additionally, the verifier fast-forwarded (no `--no-ff` merge commit), so `git rev-list --merges` returns 0 even though code landed.
**Fix:** Replaced natural-language regex with **hybrid git-diff + verifier card detection**:
1. Master HEAD advanced (`git rev-parse HEAD` vs state file baseline)
2. Changed files include code extensions (`.py`, `.js`, `.ts`, etc.) via `git diff --name-only`
3. A verifier/debugger card completed in the last hour (confirms it was a code merge, not manual)
This is language-independent — it doesn't depend on what the agent wrote in its summary. State tracked via `qa-trigger-state.json` per board, with first-run seeding (no card on initial commit).

**Root cause of ALL QA trigger failures (gaps 11-16):** relying on agent-written natural language or indirect git metadata to signal a merge. Agents write "PASS", "zero findings", "clean" — rarely the word "merged". Fast-forward merges have no merge commit for `--merges` count. The structural signal (git diff showing code files + a verifier card completing) is reliable where both language and commit metadata are not.

## Key Lesson

The biggest lesson across all 16 gaps: **agent-creates-card patterns are fragile for process-compliance steps.** When a step must happen every time (QA re-test, bug linkage, merge trigger), move it to infrastructure (workflow engine hook) rather than relying on the agent reading its SOUL.md correctly. The agent's natural instinct is to complete its own work and close — not to spawn follow-up cards for other profiles.

The QA trigger evolution through 6 iterations (gaps 3→8→11→12→13→14→15→16) is the clearest example: each attempt fixed the previous failure mode but introduced a new edge case. The final hybrid approach (gap 16) is the first that is truly language-independent and merge-strategy-independent — it detects code files in the git diff + a verifier card completing, not what the agent wrote or whether a merge commit exists.

## Pipeline after all fixes (verified end-to-end, 8+ full livetests)

```
PO → architect-gate → to-tickets → dispatch → tech-lead → dev↔verifier → merge
  → [engine auto-creates QA card] → QA → files bug bead (linked to epic)
  → [engine auto-routes bug to debugger] → debugger → discover → RED → fix
  → falsify → converge → RCA → verifier reviews+merges
  → [engine auto-creates QA re-test card] → QA re-test → PASS → done
```

Items in [brackets] are automated by the workflow engine — no agent intervention needed.

## Final clean runs (2026-07-30, runs 8+9)

After all 15 gaps were fixed, two consecutive full e2e livetests completed with zero structural failures:

**Run 8:**
- 3 slices, 3 sequential tech-lead cards (~1h apart)
- 3 QA cards auto-triggered (one per merge, regex merge detection)
- 0 spurious QA cards (zero false positives)
- 0 bugs found by QA
- 0 structural pipeline failures
- 0 debugger cycles needed

**Run 9:**
- 2 slices (core CLI + type inference, edge cases + --strict)
- 4 QA cards (2 feature merges + 2 bug fix QA re-tests — all legitimate)
- 1 bug found by QA (OSError subclasses leak raw traceback)
- Bug auto-routed to debugger via labels fallback (issue_type was "feature", caught by label check)
- Debugger fix + verifier merge + QA re-test PASS
- 0 structural pipeline failures

The pipeline is production-ready. Dispatch is sequential (one bead per tech-lead
card), so each merge creates a stable state of master that QA tests independently.
The debounce technique in `qa-trigger-parallel-pipelines.md` is NOT needed with
the current sequential dispatch model.
