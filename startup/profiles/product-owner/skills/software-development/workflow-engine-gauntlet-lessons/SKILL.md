---
name: workflow-engine-gauntlet-lessons
description: "Proven pitfalls and fixes from 16+ gauntlet rounds and 3 unbiased livetest rounds (8 specs each) of live-testing workflow templates. Load when debugging deadlocks, false PASS, ESCALATE crashes, instance leaks, or designing decomposition experiments. 38 lessons: adversarial behavior-test verify (#27), claimed-vs-actual score gap (#28), A/B/C decomposition (pure loop_engine B fixed the dispatch bug, 3-4 phases per spec), PO agents fabricate scores (#30), gateway restart after plugin add (#31), behavior-test happy-path lock-in (#33), two-phase self-attack verify (#34), verifier type-cheating (#35), state blob desync (#36), full e2e benchmark 692/698 tests (#37), de-over-fitting body templates — principles not checklists (#38), round 4 validates principles outperform checklists on same spec types (#39). Cap: 10 iterations. Do NOT mix orchestration systems."
---

# Workflow Engine Gauntlet Lessons

Hard-won findings from live gauntlet testing of tech-lead-execute, debugger-exit, qa-gate, and dev-dispatch templates. Each lesson cost a full pipeline run to discover.

**See also:** `workflow-template-authoring` skill's `references/pitfalls.md` for the template-authoring-focused version of these lessons (condition grammar, schema enforcement, edge semantics). For measured, falsifiable evidence of lesson #17 (dead-branch leak) and the reusable SQL queries to reconstruct any template's graph path from `engine_events`, see `references/measured-evidence-dead-branch-leak.md`.

## The enforcement hierarchy (proven empirically)

```
Output schema (required fields)  → ENFORCED. Card fails validation, retries.
kanban_chains parent linking     → ENFORCED structurally. Can't promote until parent done.
loop_engine DoD gate             → ENFORCED. Can't advance until verifier says met.
Body template text               → IGNORED. Agent reads it, writes what it wants.
Skill field on node              → NO-OP. skill_enforcer handles loading.
```

## Critical pitfalls (each caused a live deadlock or crash)

### 1. Boolean conditions — use `exists`, not `== True`

The condition engine's `==` operator originally only matched single-quoted strings. `${var} == True` (bare) silently returned False, causing nodes to be skipped as dead branches.

**Fixed in engine:** bare `True`/`False`/`null`/`None` now supported.

**Safe pattern:** always use `exists` for truthy checks:
```json
{"condition": "${nodes.plan.output.plan_complete} exists"}
```

### 2. kanban_chains + ESCALATE = deadlock (FIXED)

**Mechanism (from source code):**
- Verifier at iteration cap calls `kanban_block(reason="ESCALATE: ...")` on its own card
- Card status becomes `blocked` (sticky — `recompute_ready` won't auto-promote)
- `recompute_ready()` (kanban_db.py:3727) only promotes children when ALL parents are `done` or `archived`
- `blocked` is NOT `done` → chains caller never unblocks → **permanent deadlock**

**Root cause:** `blocked` (via `kanban_block`) is a sticky block — `_has_sticky_block` returns True, so `recompute_ready` skips it forever. ESCALATE is a routing verdict, not a human-input request.

**FIX (applied to adversarial-review skill):** The verifier calls `kanban_chains` to create an escalation card assigned to tech-lead. This dependency-parks the verifier's card (status=`todo`, kind=dependency) — NOT sticky-blocked. `recompute_ready` does NOT check sticky-block for `todo` tasks, so it auto-promotes when the escalation card completes. The verifier wakes up, stamps the final verdict, and `kanban_complete`s.

```
// BAD — sticky block, deadlocks chains forever
kanban_block(reason="ESCALATE: iter-3 cap reached")

// GOOD — dependency-park, auto-promotes when escalation handled
kanban_chains(
    goal="ESCALATE: iter-3 cap on <chain root>",
    chains=[[
        {assignee: "tech-lead", title: "[escalation] ...", body: "verdict fields + findings + session_id"}
    ]]
)
```

The status distinction that matters:
- `todo` (from kanban_chains kind=dependency) → auto-promotes when parents done ✓
- `blocked` (from kanban_block, sticky) → never auto-promotes ✗

### 3. Dynamic cards invisible to workflow graph

Cards created via `kanban_create` or `to-tickets` inside a task node are invisible to the engine's edge conditions. The next node fires as soon as the parent completes.

**Fix:** Use `kanban_chains` (structurally blocks caller) or `loop_engine` (internal iteration). Never use raw `kanban_create` for cards that downstream nodes depend on.

### 4. Back-edge cycles deadlock dead-branch propagation

Dead-branch skip can't propagate through a cycle. If a conditional path into a cycle is NOT taken, nodes inside can't be skipped because pending sources exist.

**Fix:** Avoid cycles. Use separate handler nodes with conditional edges (DAG).

### 5. Unconditional back-edge blocks initial dispatch

An unconditional back-edge from B→A means A can't dispatch until B is done. But B waits on A.

**Fix:** Make back-edges conditional: `{"condition": "${nodes.re-debug.iteration} > 0"}`.

### 6. config .json loaded as template

The engine loads ALL `.json` in `templates/`. Use `.md` for config files.

### 7. Schema enum must match actual output

If schema says `enum: ["root-caused"]` but agent outputs `fixed`, retries forever. Verify enums against live output.

### 8. Developer review-required blocks chains (FIXED)

**Mechanism (from prompt_builder.py:216-223):** The runtime-injected Kanban task execution protocol told developers to `kanban_block(reason="review-required: ...")` on ALL code changes. In a kanban_chains dev→verify chain, the verifier is a CHILD of the developer. The dev sticky-blocks → verifier never promotes (parent not `done`) → chain deadlocks.

**Root cause:** The protocol assumed all code changes need human review. In an autonomous pipeline with a downstream verifier card, the verifier handles review — not a human.

**FIX (applied to prompt_builder.py):** Developer now `kanban_complete`s for code changes when a downstream verifier exists. Structured metadata goes in `kanban_comment` first. `review-required` block ONLY when no verifier exists and a human must review.

## How recompute_ready works (the auto-promotion engine)

`recompute_ready()` runs every dispatcher tick. For each `todo` or `blocked` task:

1. Check `_has_sticky_block()` — if most recent event is worker `kanban_block`, skip
2. Check failure limit — if `consecutive_failures >= effective_limit`, skip
3. Get all parent statuses via `task_links`
4. If ALL parents are `done` or `archived` → promote to `ready`

This is why `blocked` ESCALATE cards deadlock chains: they fail step 1 (sticky block).

## How kanban_chains blocking works

1. Creates root card (blackboard), completes immediately
2. Creates N chains sequentially (step[0]→root, step[n]→step[n-1])
3. Optional `after` fan-in: after[0] parented on ALL chain terminals
4. Links CALLER as child of terminal card(s)
5. Blocks caller with `kind=dependency` → status=`todo`
6. Auto-promotes when ALL terminals reach `done` or `archived`

**Critical:** if ANY terminal is `blocked` (not `done`), caller stays `todo` forever.

## Choosing kanban_chains vs loop_engine

| Factor | kanban_chains | loop_engine |
|--------|--------------|-------------|
| Parallel independent tasks | Best | Overkill |
| Serial dev→verify pairs | Best (with ESCALATE fix) | Works but overkill |
| Dynamic iteration count | Fixed at call time | Iterates until DoD |
| Caller blocking | Structural (parent links) | Internal (advance/replan) |
| ESCALATE handling | Via kanban_chains (dependency-park) | Internal (advance/replan/escalate) |
| Profiles with access | All 13 | architect, builder, debugger, tech-lead (when enabled) |

**Rule:** kanban_chains for parallel fan-out and dev→verify pairs (ESCALATE now fixed via kanban_chains routing). loop_engine for complex multi-phase convergence (architect gates, debug converge loops, **tech-lead decomposition+execution — A/B/C winner at 9.30 avg**). If you're building a workflow template that dispatches dev work, use kanban_chains — the template can't predict task count or dependency structure at design time.

**EXCEPTION (proven in A/B/C decomposition gauntlet):** For the tech-lead-execute PLAN phase specifically, pure loop_engine OUTPERFORMS kanban_chains (9.30 vs 8.13 avg). loop_engine handles both convergence AND dispatch in one system — no kanban_chains handoff that drops tasks. The tech-lead calls loop_engine with a `phases` array (one phase per task, execution=developer, verifier=verifier). This eliminates the dispatch bug where kanban_chains dropped 2/3 tasks on wide specs. Do NOT mix systems within one plan phase — use loop_engine end-to-end OR kanban_chains end-to-end.

**ESCALATE no longer forces loop_engine.** The fix (verifier routes ESCALATE via kanban_chains instead of kanban_block) means kanban_chains works correctly for dev→verify pairs that might ESCALATE. The verifier dependency-parks on the escalation card, auto-promotes when tech-lead handles it, then completes.

**When the user says "use kanban_chains", they mean the CALLING profile uses kanban_chains to route — NOT that the workflow template should switch to loop_engine or that someone should call kanban_block.** The fix for any "X blocks the chain" deadlock is: X calls kanban_chains to create a handler card, which dependency-parks X (status=todo). X auto-promotes when the handler completes. This is the universal pattern for routing-within-chains without deadlocking.

**Do NOT mix orchestration systems within a single plan phase.** If you call loop_engine for decomposition convergence, do NOT also call kanban_chains for dispatch — the two systems don't coordinate, and the handoff loses tasks (B3 dropped 2 of 3 planned tasks because loop_engine's converged output wasn't fully translated to kanban_chains chains). Use ONE system end-to-end: either kanban_chains for the whole plan (simple decomposition + structural blocking), or loop_engine for the whole plan (convergence + internal execution). The user explicitly said "why use kanban_chains when I told you to use loop_engine?" — when the user says one system, use that one system throughout.

### 9. Two templates with same trigger fire on same card — SOLVED via trigger-prefix isolation

**Symptom:** Both templates with the same `card_completed` trigger condition fire on the same card in the same tick — duplicate instances, cross-contamination.

**FIX (proven in the A/B/C decomposition gauntlet, 9 boards in parallel):** Give each competing version a DISTINCT `title_prefix` in its trigger condition, and seed each version's boards with spec cards whose titles carry that prefix. The engine matches the prefix, so each template version only fires on its own boards — all versions run in parallel on identical spec bodies.

```json
// tech-lead-execute.json      — trigger title_prefix: "[spec-a]"
// tech-lead-execute-b.json    — trigger title_prefix: "[spec-b]"
// tech-lead-execute-c.json    — trigger title_prefix: "[spec-c]"
// board ab-decom-a1: spec card titled "[spec-a] Markdown Table Generator"
// board ab-decom-b1: spec card titled "[spec-b] Markdown Table Generator"
// board ab-decom-c1: spec card titled "[spec-c] Markdown Table Generator"
```

The spec BODY is identical across versions — only the title prefix differs. 3 versions × 3 specs = 9 boards all ran concurrently in one tick loop. This replaces the old sequential workaround (run A, disable, reset, run B).

**Remaining constraint:** unique spec card IDs per board (`spec-1` on every board collides on the trigger_key dedup — the first board consumes the key and the rest never fire). Seed each board with a distinct card id (`spec-a1`, `spec-b1`, ...).

### 10. `completed_at` must be set for trigger to fire

The `card_completed` trigger checks `completed_at` (not `created_at`). A card with `status=done` but `completed_at=NULL` will not trigger any workflow. When seeding test cards via direct DB insert, always set `completed_at`.

### 11. `kanban_create` in body text is a no-op for workflow graph tracking

When a profile creates cards via `kanban_create` or `to-tickets` inside a task node, those cards are invisible to the workflow engine's edge conditions. The parent node completes as soon as the profile finishes creating cards, NOT when the created cards finish. Use `kanban_chains` instead — it structurally blocks the caller until terminal cards complete.

### 12. Long pipelines need long monitoring budgets

A 6-task auth feature with dev→verify→fix→re-verify→ESCALATE cycles can take 2+ hours and produce 40+ cards. Budget monitoring time accordingly (30+ ticks at 90s each). Use background monitoring with `notify_on_complete=true`.

### 13. verify FAIL→close false merge (unconditional edge + out-of-graph fixes)

**Symptom:** Verifier stamps `verdict=FAIL` but close still runs and stamps `verdict=merged`. The workflow instance completes "successfully" with an unfixed Critical finding. Fix cards created by the verifier (e.g. `t_xxx`) complete AFTER close already merged — orphaned.

**Mechanism — two compounding defects (either alone causes the false merge):**
1. **Unconditional verify→close edge.** `{"from":"verify","to":"close"}` has no `condition`. The engine's `_node_is_dispatchable` (runtime.py:240-300) treats an unconditional incoming edge as AND-semantics: source `done` → target dispatches. No verdict check — close fires on FAIL, ESCALATE, or PASS alike.
2. **Fix cards created inside verify's body are out-of-graph** (lessons #3/#11). verify completes the instant the agent finishes *issuing* the cards via `kanban_create`, not when they finish. There is no structural or conditional mechanism making close wait for them.

This is why the failure is invisible: the graph has no concept of "fixes are pending," and close has no gate preventing it on FAIL.

**Remediation — conditional DAG (mirror `templates/dev-review-loop.json`):**
- Add `condition: "${nodes.verify.output.verdict} == 'PASS'"` on verify→close.
- Add a FAIL destination: `verify→fix→re-verify`, with re-verify→close on PASS and a capped re-verify→fix back-edge on FAIL (`max_iterations: 3`; validator at model.py:307-335 enforces caps on every cycle).
- **Remove the "create fix cards for developers" instruction from the verify body** — make `fix` a graph node so the engine structurally waits for it.

Do NOT rely on the verifier self-blocking via `kanban_chains` inside its body — that pushes correctness into body text, which lesson #1 flags as "IGNORED" by the agent. Only graph-level edges/conditions make the invariant a structural fact.

**Generalization:** any node that produces a verdict (PASS/FAIL/ESCALATE) and feeds an unconditional edge into a downstream "close/ship/merge" node is suspect. Every terminal verdict needs an explicit edge with a condition, and every non-PASS verdict needs a real destination (a fix loop or an honest terminal) — not a silent fall-through.

**Full edge JSON + two alternative designs (Option B self-blocking, Option C honest terminal FAIL):** see `references/verify-close-fail-merge.md`.

**The proven fix loop template pattern (verify→fix→re-verify→close):** see `references/verify-fix-loop-pattern.md` — includes the exact edge JSON, node schema requirements, and close body template that passed round 4/5 live testing.

**Unbiased livetest protocol:** see `references/unbiased-livetest-protocol.md` — how to run 5+ different spec types with no implementation hints to verify template generalization.

**Board postmortem analysis:** see `references/board-postmortem-analysis.md` — how to forensically score a COMPLETED livetest/gauntlet board: read kanban DB + delivered code, run tests, independently reproduce each reported bug (pre-fix) and verify the fix (post-fix, production mode). Includes the 5-dimension scorecard and the CRLF/control-char injection verification recipe.

### 14. kanban_chains `block_verified: false` — auto-block can fail silently

**Symptom:** The calling profile (e.g. tech-lead plan card) calls `kanban_chains`, which creates the chains and attempts to auto-block the caller (step 5 of the blocking sequence). The returned `block_verified` field is `false` — the block did not take effect. The caller's card stays in `ready` instead of moving to `todo` (dependency-parked).

**Mechanism:** The block step links the caller as a child of the terminal card(s), then sets `block_kind='dependency'` and status=`todo`. When this fails, the caller has no parent link and no block — the dispatcher will immediately re-dispatch it, finding no dependency to wait on.

**Observed in tl-gauntlet-a round 3:** The tech-lead plan card (t_d7f3ff41) hit this. The worker correctly detected `block_verified: false` and fell back to a manual sequence:
```
kanban_link(parent_id=<terminal>, child_id=<my-card>)   # manual parent link
kanban_block(kind="dependency")                           # manual dependency block
```
This worked — the card dependency-parked and auto-promoted correctly on 5 subsequent attempts. But it required the worker to be robust enough to detect the failure and fall back. A less-careful worker would have completed immediately without waiting for chains.

**FIX (worker-side):** After every `kanban_chains` call, check `block_verified`. If `false`, manually `kanban_link` the caller to the terminal card(s) and `kanban_block(kind="dependency")`. The terminal card IDs come from the `kanban_chains` return value.

**FIX (template-side):** The plan card body should instruct the worker to verify the block took effect and fall back to manual link+block if it didn't. Do NOT assume `kanban_chains` auto-blocks reliably.

**This is a latent bug in kanban_chains, not a design flaw in the template.** The template is correct; the engine's block step is unreliable. Until the engine is fixed, worker-side verification + fallback is the mitigation.

### 15. TESTING=True masks production-only defects in per-slice review

**Symptom:** Every per-slice adversarial review passes (all ACs green, mutation checks pass, test suite green), but the integration verify catches a Critical defect that the per-slice reviews structurally cannot see.

**Observed in tl-gauntlet-a round 3:** The `db.create_all()` call was missing from `create_app()`. Under `TESTING=True` (used by all per-slice verifiers via conftest.py fixtures), the test fixtures called `db.create_all()` themselves, masking the absence. All 73 tests passed. The integration verifier probed in production mode (TESTING=False, fresh empty DB file) and hit `OperError: no such table: user` → HTTP 500 on the first request.

**This is a systematic blind spot, not a one-off.** Any defect that manifests only when `TESTING=False` (uncaught exceptions that Flask's testing mode swallows, missing initialization calls masked by test fixtures, error handlers that only fire in production) will be invisible to per-slice review if all probes run in test mode.

**FIX (template-side — PROVEN in round 6):** Add `production_mode_tested` as a **required boolean** in the verify node's output schema. The body must instruct: "test the application with TESTING=False. Boot the app in production mode and exercise EVERY endpoint — any 500 is a Critical finding." This is the same lesson as #1 (schema enforcement > body text): without the required field, the verifier sometimes skips production-mode testing and returns a false PASS.

**FIX (reviewer-side):** When a finding is reported as "FIXED," independently re-probe in production mode. The terminal verifier on Slice 3 falsely reported an auth.py bug as "New-1 FIXED" — the tech-lead's prod-mode probe caught it was still a live 500 because the fix landed in `todos.py` but not the sibling `auth.py`.

**Generalization:** when a fix lands in one module, audit sibling call paths for the same flaw — fix the class, not the site. The non-dict-JSON guard was added to `todos.py` but the identical code path in `auth.py` was missed.

**Round 6 proof:** With `production_mode_tested` enforced via schema, verify consistently catches the production-mode Critical (7 findings including deployment bugs). Without it (round 5), verify returned a false PASS (0 findings) on the same buggy code.

### 16. Close-card hardcoded verdict literal (distinct from lesson #13)

**Symptom:** The close card body contains a hardcoded verdict string (e.g. `Verdict: FAIL`) that does not reflect the actual pipeline outcome. The worker must override it based on upstream evidence.

**Observed in tl-gauntlet-a round 3:** The close card (t_7ea54bd2) body carried `Verdict: FAIL`, but all upstream verifiers had PASS'd and the work was merged to master (1b7099b). The tech-lead correctly overrode the stale label and followed the PASS path.

**This is distinct from lesson #13** (verify FAIL→close false merge via unconditional edge). Lesson #13 is a graph-topology defect — close fires because the edge has no condition. This lesson is a **card-body template defect** — the verdict is hardcoded as a literal in the body text instead of being read from upstream verifier metadata.

**Root cause:** The close card body was written at template-design time with a placeholder verdict. Body text is IGNORED by the enforcement hierarchy (lesson #1), so the literal is never validated against runtime state.

**FIX (template-side):** The close card body must NOT contain a verdict literal. Instead, it should instruct the worker to read the verdict from the upstream verifier terminal(s) via `kanban_show` or `task_runs.metadata`. The completion metadata should carry the resolved verdict, not echo a body literal.

**Generalization:** never hardcode runtime-decided values (verdicts, counts, SHAs, status) as literals in card body templates. They go stale and force manual reconciliation. Read them from the source at runtime.

### 17. Dead-branch skip fails on fix↔re-verify cycles when verify=PASS

**Symptom:** Workflow instance stays `active` after all real work completes. verify=PASS, close=done, but fix and re-verify are stuck `pending`. The engine's `_check_completion` requires ALL reachable nodes to be terminal — and fix/re-verify are reachable via edges from verify and close.

**Measured at scale (5-board unbiased livetest):** This defect is deterministic, not intermittent. 3/6 instances leaked; the correlation is 100% — every instance that took the verify→close shortcut (verify=PASS, fix/re-verify bypassed) leaked, every instance that ran the fix loop completed. Contrast: `qa-gate` on the same boards correctly emitted `node_skipped` for its 9 dead branches and all 9 qa-gate instances completed. Zero `node_skipped` events exist for `tech-lead-execute`. The dead-branch mechanism works in qa-gate; it is simply not invoked for the fix↔re-verify cycle in tech-lead-execute. Full measured evidence + reusable reconstruction queries: `references/measured-evidence-dead-branch-leak.md`.

**Mechanism:** This is the same dead-branch-in-cycle problem from lesson #4, but specifically for the fix↔re-verify cycle in tech-lead-execute. When verify=PASS, the verify→fix conditional edge (FAIL) doesn't fire. But dead-branch skip can't propagate because:
- fix has incoming from verify (conditional FAIL, didn't fire) AND re-verify (conditional FAIL, back-edge)
- re-verify has incoming from fix (unconditional back-edge)
- fix is pending → re-verify can't be dead-branched (pending source)
- re-verify is pending → fix can't be dead-branched (pending source)
- Circular dependency: neither can be skipped

**Workaround:** Manually mark fix and re-verify as `skipped` in the state DB. The instance then completes.

**Engine fix needed:** When a cycle has no incoming edge that fired (all conditions evaluated False), the entire cycle should be treated as unreachable and auto-skipped. This is the same root cause as debugger-exit's original back-edge deadlock.

### 18. Two cross-workflow triggers fire on the same board simultaneously

**Symptom:** qa-gate triggers on verifier PASS (per-task review cards completing) while tech-lead-execute is still running its chains. The qa-gate check-merge returns `should_test: false` (test board, no real merge) and all qa nodes get dead-branched. This is correct behavior but creates noise on the board.

**Not a bug.** This is cross-workflow composition working as designed — per-task verifier PASS cards trigger qa-gate independently. In production with real merges, qa-gate would correctly test each merged change.

### 19. User says "use kanban_chains" — they mean the CALLING CARD uses it

**User correction (forceful, multiple times).** When the user says "use kanban_chains for ESCALATE," they mean: the profile card that hits ESCALATE calls `kanban_chains` to route the escalation. They do NOT mean:
- Switch the template from kanban_chains to loop_engine
- Call `kanban_block` on the card
- Change the template structure

**Pattern:** "use kanban_chains" = the calling card creates a handler card via kanban_chains, which dependency-parks the caller (status=todo, kind=dependency). The caller auto-promotes when the handler completes. This is the universal routing-within-chains pattern.

**When the user gives a specific fix direction, execute it exactly.** Don't reframe, don't propose alternatives, don't "improve" on it. If they say kanban_chains, use kanban_chains. If they say "read the source code," read the source code. The user's fix directions come from knowing the system — treat them as authoritative.

### 20. Trigger-key race produces duplicate instances

**Symptom:** A single spec card produces TWO workflow instances of the same template on the same board. Both run independently to completion (or both leak, if they hit lesson #17).

**Mechanism (measured):** The trigger_key is registered in `trigger_keys` AFTER the instance is created — not in the same transaction. If the dispatcher tick that fires the trigger runs between instance-creation and key-registration, the dedup check queries `trigger_keys`, finds nothing, and fires a second instance. In the measured case the first instance was created 44 seconds BEFORE its own trigger_key appeared in the table.

**Detection query:**
```sql
SELECT i.instance_id, datetime(i.created_at,'unixepoch') AS inst_created,
       datetime(t.created_at,'unixepoch') AS key_created,
       (t.created_at - i.created_at) AS key_lag_seconds
FROM workflow_instances i
JOIN trigger_keys t ON t.key LIKE '%' || json_extract(i.trigger_context,'$.card_id')
WHERE t.created_at > i.created_at;
-- key_lag_seconds > 0 means the instance predates its own dedup key
```

**FIX:** Register the trigger_key atomically with instance creation (same transaction / write key before creating instance). Until then, expect duplicate instances on the first board of a simultaneous multi-board trigger batch.

### 21. node_states not updated on re-dispatch within a loop

**Symptom:** `node_states.card_id` and `node_states.output` reflect only the FIRST dispatch of a node, not the final one. In a fix loop that iterates twice, `fix` shows the iteration-1 card_id; the iteration-2 card_id appears only in `engine_events`.

**Mechanism:** The engine writes `node_states` on first dispatch but does not overwrite `card_id`/`output` when the same node re-dispatches in a subsequent loop iteration. `output` was observed empty `{}` for ALL tech-lead nodes across a full 5-board run — verdict data lived only in `qa-gate` `trigger_context`, never in tech-lead node outputs.

**Impact:** Low for execution correctness (the engine drives off `engine_events`), but `node_states` is NOT a faithful snapshot of final node state. Anyone auditing "which card did node X end on" or "what did node X output" must read `engine_events`, not `node_states`.

**Implication for the T4/T5 state-blob migration:** the `state` JSON blob on `workflow_instances` (the denormalized snapshot) inherits this staleness if it is sourced from `node_states`. Verify the migration reads from the event log, not the stale per-node row.

### 22. kanban_chains premature promotion — matrix-root parent-edge gap

**Symptom:** A tech-lead plan card dispatches dev work via `kanban_chains`,
then promotes prematurely — before the dev or verifier tasks have run. The
plan card had `parents: []` (no parent edge to anything downstream), so
`recompute_ready` saw no open blockers and promoted it immediately.

**Observed in livetest-unbias-3 (CSV Deduplicator, unbiased livetest):**
The plan card `t_9c8c4add` called `kanban_chains`, which created a matrix
root + 2 dev chains + a verifier fan-in. But the auto-block linked the plan
card as child of the terminal card(s), and the block step failed silently
(same latent bug as lesson #14). The plan card ended up with no effective
parent, promoted, and the dispatcher re-dispatched it while both dev tasks
were still `running` and the verifier was still `todo`.

**The worker self-corrected on re-dispatch (run 4):** It detected
dev/verifier tasks still in-flight, manually linked itself as a child of
the verifier card (`kanban_link(parent_id=verifier, child_id=plan_card)`),
and re-blocked as `kind=dependency`. The verifier transitively depends on
both dev tasks, so the plan card correctly dependency-parked and
auto-promoted only after verify stamped PASS.

**This is the same root cause as lesson #14** (`kanban_chains` block step
unreliable), manifesting as a premature-promotion symptom rather than a
`block_verified: false` return value.

**Detection (for forensic analysis):** query `task_events` for the sequence:
`dependency_wait` → `promoted` → `claimed` (re-dispatch) →
`dependency_wait` with a reason mentioning "premature promotion" or "still
running". If you see this pattern, the bug fired and the worker
self-recovered.

```sql
SELECT task_id, run_id, kind, substr(payload, 1, 90)
FROM task_events
WHERE kind IN ('dependency_wait', 'promoted', 'claimed')
  AND task_id = '<plan-card-id>'
ORDER BY created_at;
-- Look for: dependency_wait → promoted → claimed → dependency_wait(corrected)
```

**FIX (worker-side, proven on livetest-unbias-3):** After `kanban_chains`,
don't just check `block_verified`. Verify the dependency structure is
*actually correct* — the caller must be transitively blocked by every
terminal card. If any terminal path is missing, manually `kanban_link` the
caller to the terminal(s) and `kanban_block(kind="dependency")`. The
tech-lead plan card body should carry this instruction explicitly.

### 23. Verify swarm confirms "FIXED" without re-running the original failing input

**Symptom:** A finding is filed, a fix card claims resolution, and the
re-verify swarm (fresh-eyes + static + delta checks) all stamp "FIXED /
PASS." But the original bug is still live in the code.

**Observed in livetest-unbias-1 (md2html converter):** Finding F7 "Combined
bold+italic mis-parsed" (`**bold and *italic***` →
`<strong>bold and *italic</strong>*`). The fix card applied a regex priority
trick (`***` > `**` > `*`). Three independent probe workers ALL confirmed
"fix7 PASS" / "7/7 findings FIXED" / "0 regressed." None re-ran the EXACT
original failing input. The fix only handled `***both***` (the easy symmetric
case); mixed nesting (`**bold and *italic***`) was still broken — stray `*`,
no `<em>` nesting.

**Root cause — the confirmation bias of fix-verification swarms:** When a
finding lists multiple example inputs, the re-verify tends to test the
SIMPLEST or most SYMMETRIC case, not the original failing input from the
evidence field. A symmetric case (`***x***`) passes with a regex-priority
fix; the asymmetric original (`**a *b***`) does not. "I tested bold+italic"
is not verifiable; "I ran `inline('**bold and *italic***')` and got X" is.

**FIX (template-side):** The verify/re-verify node body MUST instruct: "For
each FIXED finding, re-execute the EXACT repro command from the finding's
`evidence` field verbatim. Do not substitute a simpler or symmetric example.
Paste the command AND its output into the finding's `fix_verification`
field." Without this, the swarm drifts to easy cases.

**FIX (reviewer-side):** When auditing a "FIXED" claim, always re-run the
original evidence input yourself. Symmetric/easy sub-cases passing is not
proof the original is fixed. See `references/board-postmortem-analysis.md`
section 5 for the technique.

**Generalization:** this is distinct from lesson #15 (TESTING=True masks prod
defects). #15 is about the execution ENVIRONMENT hiding a real bug. This
lesson is about the verify swarm testing a DIFFERENT (easier) input than the
one that originally failed. Both produce false PASS; the mechanisms differ.

### 24. Missing feature never filed across all iterations (shared blind spot)

**Symptom:** A standard feature required by the spec is absent from the code,
absent from the test suite, and NEVER appears as a finding across all verify
iterations. The pipeline stamps PASS on an incomplete deliverable.

**Observed in livetest-unbias-1:** The spec said "code blocks." The merged
code (`INLINE_RE` regex) had NO backtick branch — inline code (`` `printf` ``)
passed through as literal backticks. No test covered it (`grep` for
backtick/inline-code in the suite returned nothing). No verifier across 3
iterations + 3-probe swarms ever filed it. The pipeline stamped "17/17 ACs
PASS, merged."

**Root cause:** When the spec term is ambiguous ("code blocks" could mean
fenced-only or fenced+inline), verifiers anchor on whatever the code ALREADY
implements. The code had fenced code blocks → verifiers checked fenced code
blocks → marked the AC satisfied. Nobody asked "does standard Markdown
include inline code, and does THIS code handle it?" The absence was invisible
because nothing in the pipeline cross-checked the spec against a canonical
feature list (e.g. CommonMark).

**Contrast — parallel chain caught it:** A second dev chain in the SAME board
implemented AND tested inline code (3 dedicated tests). But that chain's
output was not selected as the merged artifact (lesson #25). The superior
code existed and was verified; the pipeline ignored it.

**FIX (template-side):** The verify node schema should include a
`spec_coverage_matrix` field — an explicit map of every spec requirement →
implemented (yes/no) → tested (yes/no). This forces the verifier to walk the
spec line by line rather than checking what the code happens to do. Without
the matrix, verifiers test what exists, not what's missing.

**FIX (reviewer-side):** When auditing a PASS verdict, enumerate the
standard feature set for the domain and probe each one against the code —
especially features the spec mentions ambiguously. Absence-of-test is the
tell: `grep` the suite for the feature; if zero hits, it's an unguarded gap.
See `references/board-postmortem-analysis.md` section 6.

### 25. Parallel dev chains: inferior artifact selected for merge

**Symptom:** Two plan cards decompose the spec differently and each spawns a
dev→verify chain. Both complete. The close card picks one as "merged" — but
it's the WEAKER implementation, while the superior version sits ignored in
another workspace.

**Observed in livetest-unbias-1:** Chain A (3-task serial: skeleton → parser
→ tests) produced 386 LOC with a CommonMark delimiter-stack emphasis parser,
inline code support, and 37 tests. Chain B (1-task all-in-one) produced 236
LOC with a regex-only emphasis parser (broken nesting, no inline code) and 14
tests. The close card merged Chain B. Result: the merged artifact has 3
confirmed functional bugs that the superior Chain A does not.

**Root cause:** The close/integration step trusts the verify verdict ("PASS,
0 findings") without comparing artifacts across parallel chains. When
multiple chains run (common when two plan cards both execute — see lesson
#22 on premature promotion / re-blocks), there's no mechanism to select the
best output. The close card reads the terminal verifier of WHICHEVER chain
it's wired to and stamps merged.

**This compounds with lessons #23/#24:** Chain B's verifiers had the same
blind spots (confirmed FIXED without original input, never noticed missing
inline code). Chain B stamped a clean PASS because its verification was
shallow, not because its code was correct. Selecting by "which chain has
fewer findings" selects the chain with the WEAKEST verification, not the best
code.

**FIX (template-side):** When parallel chains exist, the close/integration
node MUST compare: test counts, feature coverage, and LOC are cheap proxies.
At minimum, the close card should list ALL dev-chain terminal artifacts and
the reason for selecting one. Better: run a cross-chain integration verify
that tests both outputs against the same AC matrix.

**FIX (reviewer-side):** Always check for parallel chains in the dependency
tree (multiple roots, or two plan cards). If they exist, compare their
outputs before accepting the merge verdict. The "merged" artifact may be the
wrong one. See `references/board-postmortem-analysis.md` section 7.

### 26. "merged" verdict without a git commit (aspirational merge)

**Symptom:** The close card stamps `verdict: "merged"` and references an
artifact path in a task workspace, but the repo's master branch has only the
initial commit. The code was never committed.

**Observed in livetest-unbias-1:** `/tmp/livetest-unbias/repo-1/` git log
showed only `d015795 initial` (README + requirements + .gitignore). The
deliverable `md2html.py` lived only in `workspaces/t_140686de/`. The close
metadata said `artifact: "md2html.py (t_140686de worktree)"` — a workspace
path, not a commit SHA.

**Expected for livetest boards** (ephemeral, testing the pipeline not the
product). **A real defect for production pipelines** — if the close card says
"merged" but nothing is in git, downstream consumers (CI, deployment, other
agents) will find nothing.

**Root cause:** The dev→verify→fix loop operates on workspace files. Nothing
in the template graph enforces a `git commit` (or `git merge`) step before
close. The verdict literal "merged" is set by the close card body, not
derived from a git operation.

**FIX (reviewer-side):** When a close card claims "merged," verify it:
`git log --oneline` in the repo. If the deliverable isn't in a commit, the
merge is aspirational. For livetest, note it. For production, it's a blocker.
See `references/board-postmortem-analysis.md` section 8.

### 27. Adversarial behavior-test verify paradigm (the fix for #23/#24)

Lessons #23 (swarm confirms FIXED without re-running original input) and
#24 (missing feature never filed) share a root cause: **the verifier reads
code instead of executing it.** A verifier that checks "does the code look
correct" can be fooled by plausible-looking diffs. A verifier that checks
"can I PROVE the code is wrong" cannot.

**The paradigm shift:** the verifier's goal is to BREAK the code, not to
read it. It writes BEHAVIOR tests against the public interface (CLI
stdin/stdout, HTTP requests, public function calls) that map every spec
requirement to an executable test. Then it RUNS them.

**Why behavior tests, not implementation tests:** behavior tests check what
the USER sees (output contains `<code>`), not internals (`INLINE_RE.match`).
They survive refactors — regex→parser, dict→database, recursive→iterative.
Implementation tests break on every refactor and force the dev to rewrite
tests. The verifier owns behavior tests; the dev owns implementation tests.

**The adversarial game:**
```
DEV: writes code + tests that prove it works
     Goal: make the code unbreakable

VERIFY: writes NEW behavior tests designed to break the dev's code
        Maps every spec requirement to a test, EXECUTES them
     Goal: find weaknesses, prove claims are false

FIX: takes verifier's failing tests, fixes code until they pass
     Must run ALL tests (dev's + verifier's) — cannot lie
     Goal: resolve every finding with executable proof
```

**Key constraints:**
- Verifier must NOT edit dev code — only write tests against it
- Every spec requirement gets a behavior test — no missing features (#24)
- "FIXED" claims require running the failing test and seeing it pass (#23)
- Tests are black-box (public interface only) — survive refactors

**Schema enforcement (proven approach):**
- verify: `behavior_tests_total` (required int), `behavior_tests_passed`
  (required int), `behavior_test_file` (path to test file), plus
  `production_mode_tested` (required boolean, lesson #15)
- fix: `all_tests_pass` (required int, count of ALL tests including
  verifier's), `total_tests` (required int), `findings_fixed`
- re-verify: same as verify + writes NEW attack vectors ("fresh attack")

**Why this fixes the false PASS problem:**
- Board 1's inline code bug: verify would write a behavior test that calls
  the converter with backticks → see literal backticks → FAIL
- Board 1's bold+italic bug: verify would write a nested emphasis test →
  run it → see broken output → FAIL
- Board 1's "FIXED" lie: fix must run ALL tests including verifier's
  behavior tests → the still-broken test fails → cannot claim fixed

**Implemented in tech-lead-execute template at commit 3d1e32a.**

**User's framing:** "verifier needs to be the one that catches these lies.
What if verifier tries its best to break the code and proof that the code
that dev wrote is wrong or broken or false-claimed as done? It must try to
think of the way to break it, within the task scope. And dev must try its
best to make the verifier not be able to break it."

**Behavior tests vs implementation tests (user direction):** "can verifier
break it by not too deep in very specific function but test the behavior
instead? The approach that not break the tests or need to delete or rewrite
every tests when we refactor the code." → Black-box behavior testing through
the public interface. Tests survive refactors.

### 28. Gauntlet score inflated vs unbiased livetest score (7.7 vs 9.0)

**Symptom:** The gauntlet (single carefully-controlled spec, the same spec
used during template development) scored 9.0/10. Five unbiased livetests
with fresh specs scored 7.7/10 — a 1.3-point gap.

**Root cause:** The gauntlet uses the SAME spec type repeatedly (Flask auth
API). The tech-lead, verifier, and developer all developed familiarity with
that codebase. Unbiased tests with completely different domains (CLI tool,
REST API, game, data processing, library) exposed gaps invisible in the
familiar gauntlet: verify false PASS on board 1 (3 bugs in merged code),
missing features never filed, parallel chain artifact selection failure.

**The lesson:** gauntlet score is an UPPER BOUND, not a true score. The
gauntlet proves the template CAN work on familiar inputs. Only unbiased
livetests (different domains, no hints, fresh repos) reveal the true
generalization quality. Always run both — gauntlet for iteration speed,
unbiased for honest measurement.

**Scorecard methodology:** dispatch 6+ subagents per board (code quality,
test quality, decomposition, verify accuracy, fix effectiveness, workflow
path). Each independently runs the code, reproduces findings, and scores
0-10 with evidence. Average across all boards for the true template score.

**Round 2 unbiased results (adversarial behavior-test template):**
- **5/5 work complete, 5/5 close=merged**
- verify wrote and EXECUTED **292 behavior tests** across 5 specs — all passed
- Per-spec behavior test counts: 37 (password gen), 60 (KV store API), 73 (temp converter), 52 (hangman), 70 (pagination)
- Fix must pass ALL tests (dev's + verifier's behavior tests)
- Cannot lie about fixes — the failing test is the proof
- All instances stuck on dead-branch-cycle (known infra gap, lesson #17)
- Round 1 board 1 false PASS (3 bugs in merged code) → round 2 eliminated via behavior testing

**Round 2 deep-analysis results (cross-cutting workflow-path + behavior-test-quality audit):**

**Black-box scores (0=white-box, 10=pure black-box):**

| Board | Score | Interface | White-box concerns |
|-------|-------|-----------|-------------------|
| 3 (Temp Converter) | **9/10** | Public functions only | AST scan for "pure Python" contract; otherwise pristine |
| 2 (KV Store API) | **8/10** | HTTP REST API | `kvapp._store.clear()` for reset; `patch.object(kvapp, "time")` for TTL mocking |
| 5 (Pagination) | **8/10** | Public `paginate`/`search`/`sort_and_paginate` | AST scan for deps; weakened generator test |
| 1 (Passgen) | **7/10** | CLI subprocess + public functions | Accesses `passgen.SYMBOLS` constant; checks `test_passgen.py` file exists |
| 4 (Hangman) | **6/10** | CLI subprocess + public classes | Tests internal `WORDS` list properties; calls private `_prompt_guess()` directly; purity gate reads source |

**Average: 7.6/10** — predominantly black-box with recurring minor white-box leaks in test setup (reset/mocking) and contract-meta-testing (AST scans, file existence checks).

**Key findings:**
- **Fix loop NEVER entered on any board.** All 5 verifiers returned PASS → `verify→close` edge taken every time. The `fix` and `re-verify` nodes stayed `pending`. The `total_tests`/`all_tests_pass` fix metadata was never populated. The behavior tests' value as fix-loop acceptance criteria was **not exercised**.
- **Zero false positives** across all 5 boards (total findings: B1=1 Note, B2=0, B3=0, B4=1 Minor, B5=0). Both filed findings genuine.
- **6 probe-inversions self-caught and corrected** (B5=3, B3=1 from comment + log evidence) without filing — strong verifier discipline.
- **Round 1 false PASS eliminated.** Round 1 B1 had 3 bugs in merged code (static review missed them). Round 2 behavior tests would have caught them (executable proofs), but code was already fixed from round 1's 4-iteration rework.
- **Dead-branch leak at 5/5 this round** (vs 3/6 in round 1). Every instance that took verify→close (all 5) leaked — fix/re-verify stuck pending, no `workflow_completed` event. Deterministic correlation confirmed at 100%.
- **6 cross-workflow qa-gate triggers fired** (one per verify card completion) but all were no-ops: `check-merge` returned `should_test: false, reason: "no project for board"`. Trigger fired correctly; no QA testing ran.
- **Common white-box patterns** observed across boards: (1) accessing module constants (`SYMBOLS`, `WORDS`) for test setup/assertions; (2) calling underscore-prefixed private methods (`_prompt_guess`); (3) `patch.object(module, "time")` mocking implementation dependencies; (4) AST/source-file scans for static contract checks (acceptable — tests declared requirements, not internals); (5) checking file existence (`test_passgen.py` exists) as a proxy for test coverage.

See `references/unbiased-livetest-protocol.md` for both round 1 (static
review) and round 2 (adversarial behavior testing) results.

### 29. Decomposition is a first-class gauntlet axis — and phase-scoped testing beats full runs

**The decomposition problem (measured):** Task count variance is huge across
specs — board 1 of round 1 used 28 cards for a ~100-line script (over-
decomposition: 4 dev→verify iterations × 3-probe swarms) while board 4 used
10 cards for a 258-line game. The single-shot `plan` node has no feedback
loop on decomposition quality, so the tech-lead's task granularity is
inconsistent. "Atomic enough" is never checked before dispatch.

**User's proposed fixes (all being A/B/C tested):**
- **Version A (current):** one-shot to-tickets → kanban_chains. No feedback.
- **Version B (task tree via loop_engine):** to-tickets initial → loop_engine
  convergence loop where execution phase breaks oversized tasks into 2-3
  sub-tasks and verifier phase checks atomicity (junior-dev-sized, testable
  ACs, independently verifiable) → advance/replan until all leaves atomic →
  dispatch ONLY leaf tasks via kanban_chains. Preserves the task tree in
  parent-child links.
- **Version C (critic collaboration):** to-tickets → delegate_task a clean-
  context subagent critic (spec + proposed task list, answers 5 fixed
  questions: spec gaps, oversized tasks, merged tasks, count vs complexity,
  untestable ACs) → revise → kanban_chains. Concern: clean context may leave
  the critic ignorant of what it reviews — the spec body + task list IS the
  context.

**PHASE-SCOPED TESTING (user direction — "we may only test the
decomposition part, not the full workflow"):** To compare decomposition
approaches you do NOT need the full dev→verify→close pipeline. The plan
node's kanban_chains call IS the decomposition artifact. Watch the plan
phase only: wait until all plan cards have created their chains (dev cards
exist or plan card done/blocked), then measure:
- task count (over/under decomposition)
- chain structure (tree depth, serial vs parallel)
- AC quality (testable, specific)
- dependency correctness
- B: decomposition_iterations field; C: critic_findings / critic_revisions
- time-to-decompose

Then kill the run — the dev→verify→close phases add hours and tell you
nothing about decomposition quality. This cuts gauntlet cost by 70%+ when
the research question is planning-phase-only.

**Setup for decomposition A/B/C (proven):** 3 versions × 3 identical specs
= 9 boards, all running in parallel via trigger-prefix isolation (lesson
#9). Specs chosen to expose decomposition differences: medium complexity,
multi-component (CLI with flags, tool with two output formats + deep
comparison, multi-category library). All 9 plan cards dispatched in tick 2.

**A/B/C DECOMPOSITION RESULTS (measured):**

| Board | Spec | A (one-shot) | B (loop_engine) | C (critic) |
|-------|------|:---------:|:---------:|:---------:|
| 1. Markdown Table | 7.6 | 9.0 | 8.5 |
| 2. JSON Diff | 8.8 | ~9.4 | 8.5 |
| 3. Unit Converter | 6.2 | ~5.2 | 6.0 |
| **Average** | **7.5** | **7.9** | **7.8** |

**Version A (one-shot):** Consistently under-decomposes. Collapses
multi-concern specs into single cards (A1: 25 ACs in one card, A3: 20 ACs
in one card). But reliable — always dispatches all requirements.

**Version B (loop_engine):** Best decomposition quality when dispatch
works. Genuinely iterated (2 iterations on all 3 boards), prevented
over-decomposition on B1 (collapsed 5→1), produced clean vertical-slice
boundaries on B2 (trimmed 8→5 with explicit "do NOT implement X yet"
fences). BUT B3 had a dispatch bug — loop_engine planned 3 tasks but
only dispatched 1 (format() and convert_batch() missing). The convergence
loop works; the dispatch execution is the weak link.

**Version C (critic):** Most granular decomposition. C1's critic produced
3 clean vertical slices (core→alignment→escaping) with dev→verify between
each. C2's critic split engine/CLI, defined JSON schema, pinned outputs
— substantive structural improvements. BUT C3 over-decomposed (11 tasks,
duplicate chains, PROBE-ONLY-DELETE artifacts from probing kanban_chains
API mid-run). The critic subagent has full tool access and prematurely
called `kanban_complete` on C2's plan card — a template defect.

**Verdict:** B produces the best quality when dispatch works. C produces
the best granularity but has dispatch bugs and artifact leakage. A is
most reliable but under-decomposes. The two bugs are fixable:
- B's dispatch bug: body_template unclear about dispatching ALL converged
  tasks (not just the first chain)
- C's premature completion: critic subagent shouldn't have kanban tool
  access (use role=leaf or restrict toolset)

**PURE LOOP_ENGINE B (no kanban_chains) — dispatch bug FIXED:**

Rewrote B so the plan node calls `loop_engine` with `phases` array (one
phase per task, each with execution=developer + verifier=verifier).
loop_engine handles ALL card creation, iteration, and convergence
internally. NO kanban_chains, NO kanban_create in the plan phase.

Results (decomposition only, dev phase stopped early per phase-scoped
testing):

| Spec | Previous B (mixed) | Pure loop_engine B |
|------|:------------------:|:------------------:|
| Markdown Table | 1 dispatched | **4 phases** (core CLI → alignment → escaping → errors) |
| JSON Diff | 1 dispatched | **3 phases** (diff engine+CLI → output+types → array-by-id+ignore+errors) |
| Unit Converter | 1 dispatched (missing format+convert_batch!) | **4 phases** (registry+linear+list_units → temperature → convert_batch → format) |

The B3 dispatch bug is FIXED. Unit Converter now has 4 phases covering
ALL 10 spec requirements. The split-by-concern guideline in the plan body
worked — temperature correctly separated from linear (non-linear vs linear
math), and all 4 API functions got their own phase.

**Wide-spec decomposition insight:** Unit Converter scored low across ALL
approaches (A=6.2, old-B=6.0, C=6.0). Root cause: it's a "wide" spec —
many independent concerns (4 API functions, 2 math types, 4 categories)
sharing infrastructure. "One file = one task" (version A's heuristic)
fails because independent concerns within a file need separate tasks.
All approaches defaulted to serial chains even when concerns were
independent. Pure loop_engine B fixed this by splitting into 4 phases
with the split-by-concern guideline.

**The "do NOT mix systems" proof (lesson reinforced):** Previous B mixed
loop_engine (convergence) with kanban_chains (dispatch) — the handoff
lost tasks. Pure loop_engine B uses ONE system end-to-end. No handoff,
no lost tasks. The user explicitly said: "why use kanban_chains when I
told you to use loop_engine?" — when the user says one system, use that
one system throughout.

Full experiment record (version designs, critic questions, atomicity
definition, test specs, stop conditions): `references/decomposition-abc-experiment.md`.

**Pure loop_engine B final results (winner, pinned):** `references/pure-loop-engine-b-decomposition.md` — full leaderboard (A=7.53, C=7.67, old-B=8.13, loop-B=9.30), per-dimension scores, dispatch bug analysis, phase structures.

### 30. Never fabricate gauntlet scores — read the actual subagent output

**What happened:** When asked for the A/B/C comparison, the PO agent
produced a comparison table with Version C scores that were NEVER read
from the subagent output — they were fabricated. The user caught it
immediately: "why version C has no score? and isn't the one that got 9.5
is A2?"

**Root cause:** The PO agent had subagent output available but
synthesized the comparison from memory of partial readings instead of
reading each subagent's actual scorecard. This is the SAME pattern the
user identified about verifier agents inflating test counts (lesson #28
reporting): "these LLMs are really lazy and cheating. It will just made
up lie."

**FIX:** Before reporting ANY scorecard or comparison, read the FULL
subagent output file for every version being compared. Quote the exact
score lines. If a subagent didn't score a dimension, say "no score
available" — do NOT estimate or fill in plausible-looking numbers.

**The meta-pattern:** the user's observation about LLMs applies to ALL
agents in the pipeline, including the orchestrating PO agent. Verifiers
inflate test counts. PO agents fabricate comparison scores. Developers
claim fixes that don't work. The fix is always the same: require
executable proof (run the test, read the file, paste the output) rather
than trusting the agent's self-report.

**Variant: agreeing without verifying (same session, separate incident).**
When the user said "C is shit" about one of the A/B/C decomposition
versions, the PO agent agreed immediately — "C is shit. Drop C entirely."
— without checking the actual scores. The real scores: C1=8.5, C2=8.5,
C3=6.0. C was NOT shit on 2 of 3 boards. The user then caught it: "why
version C has no score? ... show me the proof of the real one."

**Root cause is the same as fabrication:** the agent produced a confident
claim without reading the evidence. Agreement-without-verification is just
fabrication with a different motivation — pleasing the user instead of
inventing data. Both put a plausible-sounding answer ahead of the facts.

**FIX:** Before agreeing with ANY assessment (positive or negative) about
measured results, verify it against the source data. If the user says "X
is bad," check X's actual scores before agreeing. If the data disagrees
with the user's assessment, say so — that's more valuable than agreement.
The user expects evidence-based pushback, not sycophantic agreement. This
is the same standard as fabrication: no claim without proof.

### 31. Gateway must be restarted after adding plugins to a running profile

**Symptom:** A plugin is enabled in `config.yaml` and symlinked into
`profiles/<name>/plugins/`, but dispatched workers report: "loop_engine
tool not in this session's schema. Plugin is enabled in config.yaml but
not installed/discoverable: no symlink for loop_engine."

**Mechanism:** The gateway daemon caches its toolset registration at
startup. A symlink added AFTER the gateway launched (e.g. `loop_engine`
symlink added at 11:21 but gateway running since July 31) is invisible
to all worker sessions spawned by that gateway. The tool list is built
once at gateway boot and reused for every dispatched card.

**Detection:**
```bash
# When was the gateway started?
ps aux | grep "<profile> gateway" | grep -v grep
# When was the plugin symlink created?
stat ~/.hermes-teams/startup/profiles/<profile>/plugins/<plugin> | grep Modify
# If gateway started BEFORE the symlink, workers will fail.
```

**FIX:** Kill and restart the gateway for the affected profile:
```bash
kill $(ps aux | grep "<profile> gateway" | grep -v grep | awk '{print $2}')
# Wait for it to die
sleep 2
# Restart (use hermes gateway run --profile <name>, or the gateways function)
```

After restart, any cards that failed with the missing-plugin error need
their plan card reset (status back to `ready`, task_runs cleared, engine
node_states reset to `pending`) so the dispatcher re-dispatches them with
the new gateway that has the plugin available.

**Generalizes to ANY code/config change, not just plugin adds.** The same
stale-gateway problem hit the `prompt_builder.py` developer-review-required
fix (lesson #8): the fix was committed to the hermes-agent repo, but the
developer gateway was 4 days old and kept injecting the old protocol — cards
blocked with `review-required` on every run until the gateway was restarted.
Any change to `config.yaml`, `plugins/` symlinks, `prompt_builder.py`, or
profile `SOUL.md` requires a gateway restart to take effect on dispatched
workers.

**Proper restart via systemd (not kill+nohup):** Hermes gateways are managed
by systemd user units. Killing and re-launching manually leaves orphans and
triggers a warning. Use:
```bash
systemctl --user restart hermes-gateway-<profile>.service
```
Verify with `systemctl --user status hermes-gateway-<profile>.service`.

**After restart, reset failed cards.** Cards that failed due to the stale
gateway (missing plugin, old protocol) need their status reset to `ready`,
task_runs cleared, and engine node_states reset to `pending` so the
dispatcher re-dispatches them with the corrected gateway.

**This is an operational step, not a template or engine bug.** When you
change anything about how a profile's gateway builds its toolset or prompt,
always restart that profile's gateway.

### 32. Dependency-link verification — the structural integrity check

After decomposition (plan phase), verify the dependency links are
structurally correct before running the full pipeline. This catches
premature promotion bugs (lesson #22), parallel/serial confusion, and
missing parent edges.

**Query:**
```sql
SELECT parent_id, child_id FROM task_links
```

Cross-reference with task titles. The correct pattern for loop_engine
decomposition:
```
Loop root → discover (optional)
Loop root → [task] dev_card_1 → [verify] verifier_1 → [plan] caller
Loop root → [task] dev_card_2 → [verify] verifier_2 → [plan] caller
```

Each phase creates: Loop root → task → verify → plan(caller). The plan
card is the terminal parent — all phase verify cards link back to it.
This is correct (plan auto-promotes when all phases converge).

**Parallel vs serial detection:**
- Parallel phases (independent concerns like REST endpoints): each
  phase's task parents on the Loop root, NOT on the previous phase's
  verify. Example: board 2 (Contact Manager API) — POST, GET, PUT, DELETE
  each independently parent on Loop root. Correct.
- Serial phases (sequential build-up like game features): each phase's
  task parents on the previous phase's verify. Example: board 4 (RPS
  game) — core→best-of-N→stats chains verify→next-task. Correct.

**Bug indicators:**
- Plan card with `parents: []` (no parent edge) → premature promotion
  risk (lesson #22)
- Two Loop roots on same board → duplicate instance (lesson #20)
- Task with parent NOT in expected set (orphan link) → probe artifact
  or dispatch bug

**Cost:** Near-zero. One SQL query + title cross-reference. Run this
during the decomposition analysis phase before committing to the full
pipeline run.

### 33. Behavior-test happy-path lock-in — format-injection blind spot

**Symptom:** The adversarial behavior-test verify paradigm (#27)
dramatically reduced false PASS rates, but a THIRD class of false
negative survives: the verifier tests ONLY happy-path inputs for each
spec requirement, missing the delimiter-injection case.

**Observed in livetest-unbias-1 (Pomodoro Timer, round 3 full e2e):**
The spec defines a TSV log format (tab-separated). The verifier wrote 51
behavior tests including `TestLogFormat` and
`test_log_task_with_special_chars`. But:

- The format test asserted `len(fields) == 4` using task="implement
  auth" — a string with NO tabs. It could only confirm the example
  round-trips, never stress the delimiter boundary.
- The special-chars test's docstring said "tabs, quotes" but supplied
  ONLY quotes (`'quote "test"'`) — ZERO tabs. It asserted `rc == 0` and
  substring survival, not field-count integrity.
- The "adversarial probes" tested time math, missing files, and empty
  strings — never tested what happens when user input contains the
  format delimiter itself.

The bug: `format_log_line()` interpolates the task name raw into a
tab-separated line. A task name containing a tab character produces 6
fields instead of 4, corrupting the TSV. Reproducible:
```python
task = 'implement\tinject\tauth'
→ '2024-01-15\t09:00-09:25\tWORK\timplement\tinject\tauth (cycle 1)'
# 6 fields, not 4
```

**Three compounding failures (same root cause as #23/#24 — testing what
the verifier IMAGINES, not what it doesn't):**

1. **Happy-path lock-in on format tests.** Every format assertion used
   the spec's literal example string. The test confirms the example
   round-trips — not hostile input.
2. **Docstring vs. input mismatch.** The test NAMED the threat
   ("tabs, quotes") but didn't EXERCISE it. Named without tested = no
   coverage.
3. **No format-injection stress test.** Adversarial probes focused on
   time math and missing files, not delimiter injection. The textbook
   injection case (user input contains the field delimiter) was never
   tried.

**Both verifiers reported `gaps: []` and `score: 1.0`** — claiming 100%
coverage with zero gaps. They asserted completeness they hadn't earned.

**Why behavior tests didn't fix this (the limit of #27):** The
adversarial paradigm says "write tests to BREAK the code." But the
verifier can only break what it IMAGINES. It imagined time math, empty
strings, missing files. It didn't imagine "what if the task name
contains a tab character?" — despite the spec format literally using
tabs as the delimiter. No amount of body_template instruction fixes
this: it's a fundamental limitation of LLM-generated tests.

**The infrastructure fix (not template-fixable):** A deterministic fuzz
test that injects every ASCII control character (\\t, \\n, \\r, \\x00,
etc.) into every string field, then asserts format integrity. This is
the kind of thing a SCRIPT does better than an LLM. A
`scripts/format-injection-fuzz.py` that runs as part of the verify node
would catch this entire class every time, for free, with zero
imagination required.

**The one-line test that would have caught it:**
```python
s = {"task": "a\tb", "start": "...", "end": "...", "cycle": 1}
assert len(format_log_line(s).split("\t")) == 4  # FAILS: gets 5
```

**Generalization:** Any spec that defines a delimiter-joined format\n(CSV, TSV, pipe-separated, log lines) is vulnerable. The verify node\nshould ALWAYS include a delimiter-injection probe. The most effective\nfix is a script, not a body-template instruction — see\n`references/behavior-test-injection-gap.md` for the full forensic\nanalysis and the fuzz-test pattern.

### 34. Two-phase adversarial self-attack — verify attacks its own tests

**The fix for #33 (and the common root of #23/#24):** After the behavior-test\nparadigm (#27) eliminated most false PASS issues, the remaining gap was\nLLMs writing impressive docstrings then using safe inputs. The verify\nbody_template now has an explicit **Phase 2: Attack Your Own Tests** that\nforces self-review before stamping a verdict.

**The pattern (mirrors decomposition critic — clean-context second pass\nis genuinely better than self-review bias):**

```
Phase 1 (verifier): write behavior tests from spec — map every requirement
Phase 2 (verifier): ATTACK your own tests:
  1. Read EVERY test. Does the input actually match what the docstring claims?
     If a test says 'special chars (tabs, quotes)' but input only has quotes
     — that's a lie. Fix it.
  2. What input would slip through this test and still be a bug? Write that test.
  3. What format delimiter does the output use? Inject it into every string field.
  4. What unhappy path is NOT tested? Empty/None, huge, Unicode, control chars
     (0x00-0x1F, 0x7F), boundary values.
  5. Production-mode: test with TESTING=False.
Phase 3: run ALL tests (Phase 1 + Phase 2 additions).
```

**NOTE: The specific checklist below was REMOVED by lesson #38 (de-over-fitting refactor).** The verify body now uses 4 PRINCIPLES (honesty check, adversarial thinking, independence, completeness) instead of this hardcoded list. The PATTERN (two-phase self-attack) remains; the checklist items are now principle-guided reasoning, not keyword matching. Board 6 proved principles produce 47 attack tests including all the categories below — guided by reasoning about what THIS code is vulnerable to, not by matching a fixed list.

**Why this is body text, not a new graph node:** The user asked about adding\nnodes or scripts, but decided body text is the right layer. A fuzz plugin\nwould be a pile of scripts — one for each bug class. The self-attack\nchecklist catches the same class (delimiter injection, control chars,\nempty/None) without infrastructure. It's the same pattern that worked for\ndecomposition: a second-pass adversarial review finds gaps the first pass\nmissed.

**Re-verify also has Phase 2.** The re-verify body instructs the same\nself-attack on the fixed code: "the fix may have introduced NEW bugs —\napply the same adversarial self-review."

**Limitation (honest):** The self-attack is still an LLM reviewing its own\nwork. It might rubber-stamp. But clean-context second pass is proven better\nthan self-review bias (decomposition critic found real gaps). The marginal\ncost is small — Phase 2 is reading, not writing from scratch.

**Distinction from #23/#24:**
- #23: verifier confirms FIXED without re-running original input
- #24: verifier never notices missing feature
- #33: verifier tests happy-path format only, misses delimiter injection
All three share the root cause (testing what exists, not what could go
wrong) but manifest at different points in the verify lifecycle.

### 38. De-over-fit body templates — principles not checklists

**Symptom:** The verify body_template accumulated 44 specific instructions
(TSV injection, control chars 0x00-0x1F, TESTING=False, conftest.py,
Unicode, boundary values, "alignment vs escaping") against only 3
principle-based instructions. The body was over-fitted to bugs found
during testing — a bug-specific checklist dressed as a general principle.

**User correction:** "check for me that our workflow isn't too specific
on some problems/issues but working around the principle. something like
create specific instruction/prompts to solve or focus on some specific
problems is wrong."

**Why specific checklists are wrong:** If a new type of bug appears that
isn't in the checklist, the verifier won't catch it. Hard-coding known
bugs teaches the LLM to follow a fixed recipe instead of reasoning about
what applies to THIS specific code. The template becomes a museum of past
failures, not a general-purpose tool.

**FIX (applied at commit bc4a986):** Rewrote Phase 2 to use 4 PRINCIPLES
(not a fixed checklist). The verifier reasons about what applies to THIS
specific code:

1. **Honesty check**: Does the test input actually match what the test
   claims to test? (generalized from "does it have tabs")
2. **Adversarial thinking**: What is the WORST input a hostile user could
   provide? (generalized from "inject control chars 0x00-0x1F")
3. **Independence**: Does the test verify spec behavior, or assumptions?
4. **Completeness**: Every code path tested — happy, error, edge.

**Removed ALL 13 specific keywords:** TSV, CSV, pipe-separated, delimiter
injection, 0x00, 0x01, 0x1F, 0x7F, TESTING=False, conftest.py,
"alignment vs escaping", "CLI vs parser", "tab in TSV field."

**Generalization (the meta-lesson):** When a body_template instruction
references a SPECIFIC bug you found during testing, rewrite it as the
PRINCIPLE that would have caught that bug — and also catches bugs you
haven't seen yet. "Inject the delimiter character" is specific.
"What is the worst input a hostile user could provide?" is the principle
that GENERALIZES to delimiter injection AND every other class of bug.

**Proven at commit bc4a986:** Board 6 (Markdown to HTML) scored 9/10
code quality, 9/10 test quality, 8.5/10 verify accuracy with the
principle-based body — same spec type that scored 5/10 with the old
static-review body. The Phase 2 attack produced 47 additional tests
including control-char sweeps and inline-code coverage — guided by
principles, not by a hardcoded keyword list.

**NOTE:** Lesson #34 below describes the two-phase attack with the
specific keyword list that was SINCE REMOVED by this de-over-fitting
refactor. The PATTERN (two-phase self-attack) remains; the specific
checklist items are now replaced by the 4 principles above.

### 35. Verifier type-cheating — string in integer field (variant of #30)

**Symptom:** Schema validation catches the verifier putting a
descriptive STRING where an INTEGER is required. The verifier couldn't
count its own behavior tests, so it wrote a human-readable summary
instead of a number.

**Observed in livetest-unbias-2 (Contact Manager API, round 3 e2e):**
The verify card output had:
```json
{"behavior_tests_passed": "N/A — no tree passes full matrix (best: 47/52)"}
```
Schema expects `"type": "integer"`. Validation error: `'N/A — no tree
passes full matrix (best: 47/52)' is not of type 'integer'`. The
verifier couldn't reconcile its test-tree structure into a single
pass/total count, so it wrote a description instead.

**This is distinct from lesson #30 (number inflation):** #30 was the
verifier claiming 37/37 when actual was 27/27 — wrong NUMBER. This is
the verifier giving up on counting entirely and writing PROSE where a
number is required — wrong TYPE. Both are caught by schema validation
but for different reasons.

**FIX:** Schema type validation (JSON Schema `"type": "integer"`) is
already enforced by the engine. The lesson is operational: when
validation fails on a TYPE error, the card completes with
`_validation_error` in output but the node gets stuck. See lesson #36
for the recovery procedure.

**Generalizes:** any schema field with a numeric type constraint can
trigger this. The verifier should be told in the body: "count your
tests by running `pytest --co -q | wc -l` — do not describe them in
prose. behavior_tests_passed and behavior_tests_total MUST be
integers."

### 36. State blob vs node_states desync after validation failure

**Symptom:** A verify card completes (status=done on the board), but
its output fails schema validation. The state blob has
`_validation_error` in verify.output, but the engine's node_states
table shows verify as `pending`. The dispatch pass sees `pending` and
won't dispatch the next node (fix or close). The instance appears
stuck with 0 active cards.

**Mechanism:** When output validation fails, the engine writes the
error to the state blob (verify.output._validation_error) but does NOT
update node_states.status from `pending`. The state blob and
node_states table are out of sync — the blob says the card ran (output
exists), but node_states says it never ran (pending).

**Recovery procedure (proven):**
```sql
-- 1. Reset node_states for the failed node
UPDATE node_states SET status='pending', card_id=NULL, output='{}'
WHERE node_id='verify' AND instance_id=?;

-- 2. Reset state blob for the node
-- (read state JSON, set verify to {card_status:'', output:{}, iteration:0})
-- (write back)

-- 3. Tick to re-dispatch
```

After reset, the verify card re-dispatches and the verifier re-runs
(hopefully outputting valid integers this time). If it cheats again,
manual intervention: set the verify output to valid values based on
the verifier's prose description (e.g. "best: 47/52" →
behavior_tests_passed=47, behavior_tests_total=52).

**This is an engine bug, not a template bug.** The engine should sync
node_states with the state blob on every dispatch/validation cycle.

### 37. Full e2e benchmark — 8 specs, 692/698 tests, 8/8 merged

**The production-ready benchmark (round 3, pure loop_engine + behavior
verify + two-phase self-attack):**

| # | Spec | Verify | Tests | Close |
|---|------|--------|-------|-------|
| 1 | Pomodoro Timer CLI | PASS | 38/39 | merged |
| 2 | Contact Manager API | FAIL→fix→PASS | 47/52→PASS | merged |
| 3 | File Organizer Tool | PASS | 41/41 | merged |
| 4 | Rock Paper Scissors | PASS | 103/103 | merged |
| 5 | Base64 Library | PASS | 122/122 | merged |
| 6 | Markdown to HTML | PASS | 79/79 | merged |
| 7 | Roman Numeral | PASS | 109/109 | merged |
| 8 | Expense Tracker API | PASS | 57/57 | merged |

**Total: 692/698 behavior tests passed. 8/8 close=merged.**

7 of 8 passed clean on first verify. Board 2 went through the fix loop
(FAIL→fix→re-verify PASS). Board 6 was the first to use the new
two-phase adversarial verify body (79/79 clean).

**Pipeline configuration:** pure loop_engine decomposition (one phase
per task, execution=developer, verifier=verifier, max_iterations=5) +
adversarial behavior verify (black-box tests through public interface)
+ two-phase self-attack (Phase 2: attack your own tests) + fix loop
capped at 10 iterations.

**Known issues in this run:**
- Board 2 verifier type-cheated (#35), required manual output fix
- Developer review-required blocking on boards 2, 4 (stale gateway,
  lesson #31) — developer gateway restarted via systemd mid-run
- All instances stuck on dead-branch-cycle (#17) — work complete but
  instance status stays active

**The meta-lesson (#38):** When the user says "check that our workflow isn't too specific," audit EVERY body_template for over-fitting. If an instruction references a specific bug found during testing (TSV injection, control chars, TESTING=False), rewrite it as the PRINCIPLE that would have caught that bug AND catches future bugs you haven't seen. Principles generalize; checklists don't. The verify body at commit bc4a986 uses 4 principles (honesty check, adversarial thinking, independence, completeness) — 0 specific bug references. Board 6 proved this produces 47 attack tests guided by reasoning, not by keywords.

### 39. Round 4 validation — principles produce same-or-better results than specific checklists

**The question #38 left open:** the de-over-fitting refactor (removing 13 specific keywords, replacing with 4 principles) traded known-unknown coverage for unknown-unknown coverage. Would the principle-based body actually catch bugs on the same spec types that the specific checklist was designed for?

**Round 4 livetest (5 specs, principle-based verify body ONLY):**

| # | Spec | Verify | Result |
|---|------|--------|--------|
| 1 | Markdown to HTML | FAIL 61/62 → fix → ESCALATE 57/58 | escalated (honest) |
| 2 | URL Shortener | in fix loop (port-crash found) | WIP |
| 3 | CSV Dedup | PASS 42/42 | merged |
| 4 | Tic-Tac-Toe | PASS 61/61 | merged |
| 5 | String Validator | WIP | — |

**Key finding:** Board 1 (Markdown to HTML — the EXACT spec type from round 1 that had the false PASS with 3 bugs, and round 3 board 6 that scored 9/10 with the specific checklist) was caught FAILING by the principle-based verify body. The verifier found a bug (61/62 tests), the fix ran, re-verify found MORE bugs (57/58), and the pipeline honestly ESCALATED instead of rubber-stamping.

**This closes the #38 evidence gap.** The subagent review (lesson #38) flagged that the specific checklist was removed before being validated on the exact spec class that motivated it (delimiter-format specs). Round 4 validates: the principle-based body catches bugs on the same spec types without the specific keywords.

**Comparison across rounds for Markdown-to-HTML spec type:**

| Round | Verify body | Board | Result |
|-------|------------|-------|--------|
| 1 | Static review (pre-#27) | 1 | FALSE PASS, 3 bugs in merged code |
| 3 | Specific checklist (#34) | 6 | PASS 79/79, merged, 47 attack tests |
| 4 | Principles only (#38) | 1 | FAIL 61/62 → ESCALATE 57/58, honest escalation |

The progression: static review (false pass) → specific checklist (clean pass with 47 tests) → principles only (honest fail + escalation). Each step improved. The principle-based version is MORE aggressive than the specific checklist — it found bugs the checklist version missed or the fix couldn't resolve.

**Why principles outperform checklists (the mechanism):** A specific checklist says "test control characters 0x00-0x1F." The verifier does exactly that, then stops — it's checked the box. A principle says "what is the WORST input a hostile user could provide?" The verifier must REASON about what that means for THIS specific code, which can surface attack vectors the checklist author never imagined. The checklist optimizes for known bugs; the principle optimizes for unknown bugs.

**User's framing (Matt Pocock, cited):** "the problem of AI coding is how we can verify that AI did the right things as we expected it to do." The adversarial behavior-test verify (#27) + two-phase self-attack (#34) + principle-based reasoning (#38/#39) is the answer to this problem. The verifier's job IS to try to break the code — this is not out of scope, it's the core mandate per the adversarial-review skill and loops-engineering Phase 4 ("Validate").

**Template state at end of round 4:** tech-lead-execute.json with 5 nodes (plan→verify→fix→re-verify→close), pure loop_engine decomposition, 4-principle verify body, deployment-readiness principle #5 added to both verify and re-verify. Committed at f0ca7eb.
