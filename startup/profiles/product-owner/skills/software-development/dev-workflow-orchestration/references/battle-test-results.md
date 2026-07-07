# Battle Test Results — 2026-07-05

## Two test phases

### Phase 1: Infrastructure tests (Tests 1-4, CHEATING)
These proved the kanban dispatch mechanism but NOT the loops architecture — PO interfered (wrote contracts, manually unblocked tasks). Documents what NOT to do.

| # | Test | Status | What it actually proved |
|---|------|--------|-------------------------|
| 1 | Closing Loop (URL shortener) | ✅ PASS | Pipeline works, but WRONG architecture (tech-lead wrote code directly) |
| 2 | Emerging Task (ETL pipeline) | ✅ PASS | Dynamic task creation works (but still wrong — no harness used) |
| 3 | Deep Chain (3-phase text analyzer) | ✅ PASS | Multi-phase workspace continuity works (with a cleanup gap) |
| 4 | The Block (kv_store) | ✅ PASS | Block→unblock→resume works |

### Phase 2: Correct architecture tests (Test 5 + 5R, HONEST)
These proved the real loops-engineering architecture with correct role separation.

#### Test 5: Single-slice harness-direct loop
**Status**: ✅ PASS — the first test that actually exercised the 3-role architecture.

Chain: tech-lead (plan) → developer (pi harness, GLM 4.5-air) → reviewer (adversarial, GLM 5.2) → fix card → developer (warm-resume) → re-review → APPROVED.

- 43 reviewer probes found 2 Important bugs the developer's 35 tests missed
- Developer warm-resumed pi session (`pi --session <id>`) — harness kept memory
- 6 tasks, ~40 min total

#### Test 5R: Multi-slice automation loop (THE KEY TEST)
**Status**: ✅ PASS — proved the full FAANG-style workflow end-to-end.

PO created PRD (15 user stories) → beads (3 slices with dependencies) → created ONE card per bead with ONLY bead ID + workspace path → tech-lead ran autonomously for all 3 slices.

| Slice | Bead | Harness | Tests | Defects | Duration |
|-------|------|---------|-------|---------|----------|
| 1: Library | goc | delegate_task (GLM 5.2) | 49 | 6 found (2 CRITICAL) | ~15 min |
| 2: CLI | k59 | **pi (GLM 4.5-air)** | 68 | 2 found + fixed | ~16 min |
| 3: Edge cases | guq | **pi (GLM 4.5-air)** | 92 | 0 (proactive hardening) | ~13 min |

**Total: 92 tests, 8 defects found, all resolved or documented. ~44 min total.**

### Issues found during Test 5R and fixes applied

1. **`developer-loop` skill had wrong pi flags** — `--auto-test` and `--max-turns` don't exist in pi. Patched: added verified pi invocation recipe.
2. **Tech-lead used delegate_task instead of pi on slice 1** — investigated claude (not logged in) and codex (incompatible with Z.AI), then fell back to delegate_task. Patched loops-engineering skill to explicitly prefer pi harness. Slices 2+3 used pi correctly.
3. **Tech-lead didn't close bead on slice 1** — skill said "mark done on board" but didn't say `bd close`. Patched loops-engineering to include explicit `bd close <bead-id>` step. Slices 2+3 closed beads correctly.
4. **Z.AI routed glm-4.5-air → glm-4.7** — upstream model aliasing. Developer caught and reported honestly.
5. **Pi session path** — skill said `~/.pi/sessions`, actual path is `~/.pi/agent/sessions/<cwd-encoded>/`. Patched in developer-loop.
6. **Scratch workspace cleanup** — `scratch` workspaces cleaned on archival. Fix: use `workspace_kind="dir"` for multi-phase builds.

### Verified `pi` invocation (the correct form)

```bash
# Cold start
timeout --signal=TERM --kill-after=30 900 \
  pi --provider zai --model glm-4.5-air \
    -p "<prompt>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json

# Warm resume (harness keeps prior memory)
timeout --signal=TERM --kill-after=30 900 \
  pi --provider zai --model glm-4.5-air \
    --session <session_id> \
    -p "<findings>" \
    --mode json
```

`--auto-test` and `--max-turns` DO NOT EXIST in pi. The `timeout` wrapper IS the only cap.
Sessions at `~/.pi/agent/sessions/<cwd-encoded>/`. Resume is cwd-scoped.

### Test 8: New Verifier Skill Test (2026-07-05)
**Status**: ⚠️ INCONCLUSIVE — verifier skill NOT exercised.

Tech-lead was given a card with 12 structured ACs and instructed to use `pi --provider zai --model GLM-4.6`. Instead:
- Tech-lead used `delegate_task` (GLM 5.2) for both building AND verification
- No kanban cards assigned to developer or verifier profiles
- The adversarial-review v4.0.0 skill (two-phase protocol, AC checklist gate, /review + ponytail-review) was never loaded
- GLM-4.6 harness instruction was ignored — tech-lead treated it as a suggestion
- An old LLM-based cron (869fb179233e) created a duplicate card, but the new script cron stayed silent correctly

**Positive**: Tech-lead DID independently verify all 12 ACs with fresh fixtures and AST inspection — just did it in the wrong role.

**Root cause**: Tech-lead shortcuts to delegate_task for small tasks. Card body language ("Use GLM-4.6") was not forceful enough. Need explicit "MUST create developer + verifier kanban cards" language.

**Fix**: See [references/tech-lead-enforcement.md](tech-lead-enforcement.md) for enforcement strategies.

### Test 9: Toolset-Restricted Tech-Lead (2026-07-05)
**Status**: ✅ PASS — toolset restriction forced correct loops behavior for the first time.

After disabling `delegation`, `file`, `code_execution` (and 7 others) on tech-lead:
1. Tech-lead tried codex (failed — local gateway disconnect), claude (failed — SSL), opencode (failed)
2. **Fell back to `pi --provider zai --model glm-4.5-air`** ← the harness we wanted
3. pi wrote code (inimerge.py + 23 tests)
4. Tech-lead ran adversarial probes — found AC5 failure (comment preservation — configparser drops comments)
5. Caught rubber-stamp test — generator's test wrote a comment but only asserted keys survived, never the comment itself
6. Re-delegated to pi with fix instructions — pi implemented custom `_extract_comments()`
7. Second probe confirmed all 11 AC sub-checks pass

**This was the first test where toolset restriction forced pi harness usage.** After 8 prior tests where SOUL rules, skill patches, and card body language all failed to prevent tech-lead from shortcutting to delegate_task, removing the tool worked immediately. See [references/tech-lead-enforcement.md](tech-lead-enforcement.md).

### Test 10: First True 3-Role Test (2026-07-05)
**Status**: ⚠️ PARTIAL — harness delegation worked, but no kanban-native dev/verifier cards.

After full toolset restriction (no file, no delegation, no code_execution) + gateway restart:
1. Cron auto-dispatched the bead
2. **Tech-lead used Claude Code harness** (`claude -p --allowedTools 'Read,Edit,Write,Bash' --max-turns 15 --output-format json`) — first time Claude Code was used as generator
3. Claude Code built heap.py (28 tests pass)
4. Tech-lead ran independent adversarial probes (22 sub-checks, fresh fixtures)
5. All ACs verified, bead closed, trace saved
6. **Did NOT use write_file** (toolset restriction confirmed working after restart)
7. **Did NOT use delegate_task** (toolset restriction confirmed)

**Critical finding**: Tech-lead treats harness-direct as "invoke the harness via terminal subprocess." It does NOT create kanban cards for developer/verifier profiles. The loops-engineering skill presents harness-direct and kanban-native as alternatives — tech-lead picks harness-direct because it's faster.

**The developer and verifier profiles have NEVER been invoked** across all 10 tests. Every test has been tech-lead doing everything itself (either via delegate_task before restriction, or via terminal subprocess after restriction).

See [references/tech-lead-enforcement.md](tech-lead-enforcement.md) § "The remaining gap" for the three options to force kanban-native flow.

### Deepseek fallback — silent model switching (2026-07-05)
All profiles had `fallback_model: [deepseek-v4-flash]` configured. When Z.AI had transient connection errors, tasks silently switched to deepseek — different quality characteristics, breaking role separation. **Fix**: set `fallback_model: []` on ALL profiles. When you need deterministic model selection for role separation (GLM 5.2 governs, GLM 4.5-air generates), zero fallback is correct — let the task crash and auto-reclaim rather than silently degrade.

### Cron race condition + cleanup (2026-07-05)

Two competing dispatch crons were discovered:
- `b236003fa59f` (PO, Beads Dispatch): scans `dev-workflow-battle-tests/`, creates cards on `startup` board — the CORRECT one
- `0aad63ed7096` (tech-lead, Beads Watchdog): old architecture, scans `~/workspace/`, creates cards on per-project boards — DEAD WEIGHT

They didn't directly conflict (different scan dirs, different target boards) but the old tech-lead watchdog was from the deleted per-project board architecture. **Fix**: paused + removed the old watchdog. Only one dispatch cron should be active.

**Also**: old LLM-based cron (`869fb179233e`, 20-repeat test cron) was still in "completed" state and had created a duplicate card in Test 8. Removed it entirely.

**Lesson**: When evolving the dispatch architecture, clean up old cron jobs. A paused/completed cron can still have side effects if its state gets confused. Use `hermes cron list --all` across ALL profiles to find stale jobs.

### Untested → TESTED (Tests 10b-21, Jul 2026)

The "untested" list below was written before Tests 10b-21. Here's what got tested:

- ✅ **Verifier profile**: invoked in Tests 10b, 12, 13, 14, 17, 18, 21 — ran adversarial-review v4.0.0 every time
- ✅ **Developer profile**: invoked in Tests 10b, 12, 13, 14, 15, 17, 18, 21 — used pi harness with GLM-4.5-air
- ✅ **Two-phase verification**: delta + fresh-eyes ran in Test 14 iteration 2 (verifier confirmed fix + found no new bugs)
- ✅ **AC checklist gate**: verifier independently probed every AC in Tests 10b-21 (prover-verifier pattern)
- ✅ **Failure-fix loop**: Test 14 — verifier FAIL (syslog process bug) → fix card → developer warm-resume → verifier PASS
- ✅ **Crash recovery at developer level**: Test 15 — 2 crash recoveries (runs 68→69→70), pipeline completed
- ✅ **Network resilience**: Test 17 — Z.AI 429 rate limits handled gracefully

### Still untested (as of Jul 2026)
- Goal-mode tasks (task runs until a judge verifies completion)
- Iteration cap escalation (≥3 failures → tech-lead) — GLM 4.5-air passed on iteration 2
- Merge slot serialization (bd merge-slot)
- 5-slice dependency chain (Test 20 skipped due to time)
- pi harness crash mid-execution (developer recovered from profile crashes, but pi itself wasn't killed)

### Test 6: Crash Recovery (2026-07-05)
**Status**: ✅ PASS — Auto-reclaim works at all levels.

Two crash injection tests:
- **6a**: Tech-lead process (PID 169608) killed mid-run → dispatcher auto-detected within ~60s → re-dispatched run 30 → new agent detected "crashed run left artifacts" → independently verified 32 tests + ran 9 adversarial probes → completed.
- **6b**: Tech-lead process (PID 170404) killed mid-validation → became zombie (state Zs) → dispatcher auto-reclaimed within ~3 min → run 32 verified 39 tests, ran 15 adversarial probes, found 2 new defects (configparser interpolation crash) the crashed run would have missed.

**Key finding**: Crash recovery preserves workspace artifacts. New agent does NOT trust prior work — re-verifies from scratch. Kanban card + files on disk ARE the state.

### Test 7: Automation Loop (2026-07-05)
**Status**: ✅ PASS — Cron-driven bd ready → PO → tech-lead works end-to-end.

2-slice dedup project. Cron job ran every 2 min:
1. Checked `bd ready` → found ready bead
2. Checked tech-lead not running → created kanban card
3. Tech-lead picked up, executed, closed bead
4. Next cron tick → next ready bead → repeat

**Issues found**:
- **Duplicate card race**: cron fired twice before dispatcher claimed the first card, creating a duplicate. Fix: use `--idempotency-key` or check `ready` cards too (not just `running`).
- **Cron repeat exhaustion**: set to 20 repeats, exhausted before slice 2 was ready. Production cron should run forever.
