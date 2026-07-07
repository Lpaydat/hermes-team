# Kanban Workflow Battle Tests — Jul 2026

**Board:** `startup` · **Model:** GLM 5.2 (Z.AI) · **Profiles:** product-owner, tech-lead, developer, verifier (was reviewer)

## Tests Executed

| # | Test | Status | Duration | What it proved |
|---|------|--------|----------|---------------|
| 1 | Spec→Build→Review (linear chain) | ✅ PASS | ~21 min | Full pipeline works. Reviewer independently verified. Code quality high — no rejection triggered. |
| 2 | Dynamic decomposition (orchestrator creates children mid-run) | ✅ PASS | ~26 min | Agent created 3 child tasks via `kanban_create`, blocked itself, dispatcher serialized children, 137/137 tests. |
| 3 | Multi-phase sequential build (Phase 1 → 2 → 3, phases created mid-run) | ✅ PASS | ~18 min | 3 sequential phases: lib (64 tests) → reporter (44 tests) → CLI (32 tests). Full suite 129/129 green. Workspace continuity gap found and recovered from. |
| 4 | The Block (error recovery) | ✅ PASS | ~8 min | Block→unblock→resume cycle worked end-to-end. Agent analyzed options (JSON vs INI vs TOML vs YAML), blocked, resumed with JSON, completed 61 tests. |

## Test 2: Dynamic Decomposition — Full Case Study

### The task
An ETL pipeline (Extract → Transform → Load) was given to tech-lead as a single orchestration task with instructions to decompose via `kanban_create`.

### How the agent handled it
1. Read the spec, identified 3 independent modules
2. Noted the task body suggested `parents=[t_b764c041]` (an unrelated completed task) — correctly discarded as "semantically wrong"
3. Recognized the deadlock in `parents=[itself]`
4. Created **3 child tasks** with `parents=[]` and `workspace_kind="dir"` pointing to the orchestrator's own workspace
5. **Blocked itself** with `kanban_block(reason="delegated: waiting for 3 child modules")`
6. Dispatcher serialized children (max_in_progress=1):
   - Child 1 (Extractor): 39 tests ✅
   - Child 2 (Transformer): 47 tests ✅
   - Child 3 (Loader): 28 tests ✅
7. After unblock, orchestrator re-dispatched → wrote integration → **137/137 tests passing**

### Key lesson: agents self-correct deadlocks
Correct pattern for dynamic decomposition:
- Children: `parents=[]` (no dependency)
- Children share a `dir` workspace
- Orchestrator: `kanban_block(reason="delegated: waiting for N child modules")`
- After all children done → unblock → re-dispatched → writes integration

## Test 3: Multi-Phase Workspace Continuity

### The finding
Phase 1 (`scratch` workspace) completed and was archived. Phase 2 (`dir` pointing to same path) found an **empty** workspace — scratch files cleaned up. Agent resiliently rebuilt from spec.

### Root cause
`scratch` workspaces are ephemeral — cleaned up after completion/archive. Multi-phase builds sharing files must use `workspace_kind="dir"` for ALL phases.

### Outcome
Despite the gap, all 3 phases completed: **129/129 tests green.**

### Fix
Use `workspace_kind="dir"` with explicit stable path for multi-phase builds.

## Test 4: The Block (Error Recovery)

### The task
Build `kv_store.py` — a key-value store. The spec intentionally omitted the file format.

### How it went
1. Agent identified the missing decision, wrote a detailed analysis (JSON vs INI vs TOML vs YAML)
2. **Blocked** with `kanban_block(reason="need-decision: ...", kind="needs_input")`
3. User unblocked with JSON confirmation
4. Agent remembered the decision on re-dispatch
5. Completed: 61 tests, atomic writes, reentrant RLock, crash safety

### The correct block→unblock pattern
```python
# Worker:
kanban_comment(body="analysis of options...")
kanban_block(reason="need-decision: <question>", kind="needs_input")

# Operator:
kanban_comment(task_id="...", body="Answer: use JSON")
kanban_unblock(task_id="...")
```

## ⚠️ CRITICAL CAVEAT — Architecture was wrong

**These tests had the role separation backwards.** All build tasks were assigned to `tech-lead`
directly. Tech-lead wrote code using its own Hermes tools (write_file, terminal, patch) — it never
delegated to `developer`, and **no harness (`pi`/`zz`) was ever invoked**. What these tests actually
proved:

- ✅ The **kanban dispatch mechanism** works (task creation, dependency promotion, blocking, dynamic
  child creation, serial dispatch)
- ❌ The **loops-engineering architecture** was NOT tested — tech-lead was both Planner and Generator
  (the sycophancy trap the architecture exists to prevent)
- ❌ No trace ledger, no structured completion reports, no harness session IDs
- ❌ No model independence (GLM 5.2 generated code, GLM 5.2 reviewed it)
- ❌ The failure-fix loop never triggered (GLM 5.2 code quality too high for the test specs)

**To run REAL loops-engineering tests**, build cards must be assigned to `developer` (not
`tech-lead`). The developer profile wraps a harness (`pi`/`zz`) as a subprocess. The harness uses
a different/weaker model (Gemma 4, GLM 4.5-air) so the reviewer (GLM 5.2) has genuine independence.
See `references/loops-engineering-architecture.md` for the full role separation model.

## What remains untested (for real this time)

- ~~**The closing loop** (review rejection → fix → re-review)~~ — ✅ TESTED in Test 5
- ~~**Harness crash recovery**~~ — ⚠️ Not directly tested (tech-lead used delegate_task for smaller crash-test tasks)
- ~~**Developer/tech-lead crash recovery**~~ — ✅ TESTED in Test 6 (below)
- ~~**Automation loop**~~ — ✅ TESTED in Test 7 (below)
- **Reviewer crash recovery** — kill reviewer mid-review, verify reclaim
- **Multi-iteration fix loop** — spec hard enough to require 2+ fix cycles
- **Goal-mode tasks** — tasks that run until a judge verifies completion

## Test 5: REAL Harness-Direct Loop — ✅ FULL FAILURE-FIX LOOP COMPLETED

**Date:** 2026-07-05 · **Board:** `startup` · **Harness model:** GLM 4.5-air (routed to GLM 4.7)

This was the **first test that actually exercised the loops-engineering architecture.** All prior
tests had the role separation wrong (tech-lead wrote code directly). This test used the correct
3-role flow: tech-lead (Planner) → developer (Generator) → pi harness → verifier (Evaluator).

### The full chain

| Task | Profile | Role | Duration | Key action |
|------|---------|------|----------|------------|
| t_43a9a017 | tech-lead | Planner | 1 min | Created contract + decomposed to dev/reviewer. **Did NOT write code.** |
| t_b204384a | developer | Generator | 7m 44s | Invoked `pi --model glm-4.5-air`. Harness wrote code in 190s. Developer ran gates (35/35), captured trace, filed structured report with 5 suspected weaknesses. |
| t_246249fd | verifier | Evaluator iter 1+2 | 8m 53s | Ran 43 independent probes. Found **2 Important + 1 Minor + 2 Notes**. Blocked. Created fix card + re-verify card. |
| t_767f82fd | developer | Generator (fix) | 8m 30s | **Warm-resumed** pi session (`--session 019f2ecf...`). Harness fixed all 3 bugs + added 5 CLI tests. 40/40 pass. Captured attempt-2.jsonl. |
| t_5d4bc355 | reviewer | Evaluator iter 3 | 13m 10s | Re-verified all fixes with fresh execution. **APPROVED.** |

### What was proven for the first time

1. ✅ **3-role separation works** — tech-lead planned, developer wrapped harness, reviewer evaluated
2. ✅ **Harness delegation works** — `pi --provider zai --model glm-4.5-air` invoked as subprocess, JSON output captured
3. ✅ **Trace ledger works** — `~/vault/traces/hermes-hq/t_b204384a/attempt-{1,2}.jsonl` persisted
4. ✅ **Failure-fix loop works** — reviewer found real bugs → blocked → created fix card → developer warm-resumed → harness fixed → re-review passed
5. ✅ **Warm-resume works** — `pi --session <id>` resumed the prior session
6. ✅ **Adversarial review is real** — the 35 dev-written tests missed the bugs; the reviewer's 43 probes found them
7. ✅ **Honest reporting** — developer flagged 5 suspected weaknesses before the reviewer even looked

### Findings from Test 5

| Severity | Finding |
|----------|---------|
| ⚠️ MINOR | `developer-loop` skill references `--auto-test` and `--max-turns` for pi — these DON'T EXIST. Developer correctly fell back to wall-clock timeout. |
| ⚠️ MINOR | Z.AI routed `glm-4.5-air` → `glm-4.7` silently (upstream aliasing). Developer caught it. |
| ⚠️ MINOR | Warm-resume session dir initially failed (`~/.pi/sessions` vs `~/.pi/agent/sessions/<cwd-encoded>/`). Developer found correct path. |
| ⚠️ MINOR | Reviewer iteration 2 ran against unchanged code (I unblocked without creating fix card first). The reviewer correctly detected this and re-verified all findings. On proper iteration it created the fix card automatically. |
| ✅ | Reviewer created fix cards automatically (I didn't need to intervene) — proper loop behavior |

### Timing

| Phase | Duration |
|-------|----------|
| Planning (tech-lead) | 1 min |
| Build (developer + harness) | 7m 44s (harness itself: 190s / 13 turns) |
| Review iter 1+2 (reviewer) | 8m 53s (43 probes) |
| Fix (developer + warm-resume) | 8m 30s |
| Re-review iter 3 (reviewer) | 13m 10s |
| **Total wall clock** | **~40 min** |

## Test 6: Crash Recovery — ✅ PASS (2026-07-05)

Two crash injection tests verified the dispatcher's auto-reclaim mechanism.

### Test 6a: Kill tech-lead mid-run
- **Run 29** (PID 169608): claimed at 07:15, code already written by 07:16
- **Kill**: process died (post-completion)
- **Auto-reclaim at 07:17**: run 30 (PID 170029) spawned automatically
- **New agent**: detected "crashed run left artifacts", independently verified 32 tests + ran 9 adversarial probes
- **Result**: ✅ completed in 1 min after reclaim

### Test 6b: Kill tech-lead mid-validation
- **Run 31** (PID 170404): claimed at 07:21, code written + 39 tests pass by 07:22
- **Kill at ~07:23**: process became zombie (state Zs)
- **Auto-reclaim at 07:24**: run 32 (PID 170959) spawned
- **New agent**: verified 39 tests, ran 15 adversarial probes, found 2 new defects (configparser % interpolation crash + mailto/ftp scheme misreporting)
- **Result**: ✅ completed at 07:26

### Key crash recovery findings
1. **Auto-reclaim timing**: 1-3 minutes (zombie detection slower than fully-dead detection)
2. **Independent verification on retry**: new agent does NOT trust crashed run's work — re-runs everything from scratch
3. **State preservation**: kanban card body + comment thread + workspace files ARE the complete state. In-memory reasoning is lost but not needed.
4. **Use `hermes kanban reclaim <task_id>`** to force immediate reclaim instead of waiting for the stale timeout.

## Test 7: Automation Loop — ✅ PASS (2026-07-05)

Full cron-driven pipeline: `bd ready` → PO creates card → tech-lead executes → bead closed → next slice unblocked.

### Setup
2-slice dedup project with bead dependency (slice1 → slice2). Cron job ran every 2 min, 20 repeats.

### Execution
1. Cron tick 1: `bd ready` found slice 1 → checked tech-lead not running → created card `t_e3feff91`
2. Tech-lead claimed, executed (pi harness, GLM 4.5-air), closed bead
3. Cron tick 2: **created duplicate card** `t_03108b81` (race condition — card not yet claimed when cron checked)
4. PO archived duplicate, created slice 2 card manually (cron exhausted repeats)
5. Tech-lead executed slice 2, closed bead

### Issues found
- **Duplicate card race** (MAJOR): cron checks `--status running`, but a `ready` card is invisible to this check. Two ticks fire before dispatcher claims the first card. Fix: `--idempotency-key "beads-<bead-id>"` or check `ready` cards too.
- **Cron repeat exhaustion** (MINOR): 20 repeats at 2 min = 40 min total. Slice 1 took ~7 min, but the cron burned 3-4 ticks during execution. Use `repeat: forever` for production.

## Timing Reference

| Task | Tests | Time |
|------|-------|------|
| Time-tracker CLI | 48 | 7m 34s |
| URL shortener API | 36 | 5m 46s |
| JSON config validator | 81 | 4m 24s |
| ETL Extractor | 39 | ~4m |
| ETL Transformer | 47 | ~3m |
| ETL Loader | 28 | ~2m |
| ETL integration | 23 | ~1m |
| Text stats library | 64 | ~3m |
| Report generator | 44 | ~6m |
| CLI wrapper | 32 | ~6m |
| Key-value store | 61 | ~8 min |
| strutils (crash test 6a) | 32 | ~3 min |
| config_spec (crash test 6b) | 39 | ~5 min |
| dedup core (auto test 7) | — | ~5 min |
| dedup CLI (auto test 7) | — | ~5 min |

**Total:** ~500 passing tests, ~2,500 lines, all stdlib-only.
