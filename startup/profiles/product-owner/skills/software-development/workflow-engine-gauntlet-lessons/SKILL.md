---
name: workflow-engine-gauntlet-lessons
description: "Proven pitfalls and fixes from live-testing workflow templates with kanban_chains, loop_engine, and dynamic dev cards. Load when debugging a template that deadlocks, fires too early, crashes on ESCALATE verdicts, or produces false PASS results. 19 lessons from 14+ gauntlet rounds across 5 templates. Round 6 unbiased livetest: 5 different spec types (CLI, REST API, game, data tool, validation library) — all decomposed and built autonomously with no hints. User iteration cap preference: 10 (not 3)."
---

# Workflow Engine Gauntlet Lessons

Hard-won findings from live gauntlet testing of tech-lead-execute, debugger-exit, qa-gate, and dev-dispatch templates. Each lesson cost a full pipeline run to discover.

**See also:** `workflow-template-authoring` skill's `references/pitfalls.md` for the template-authoring-focused version of these lessons (condition grammar, schema enforcement, edge semantics).

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
| Profiles with access | All 13 | architect, builder, debugger (+ tech-lead if enabled) |

**Rule:** kanban_chains for parallel fan-out and dev→verify pairs (ESCALATE now fixed via kanban_chains routing). loop_engine for complex multi-phase convergence (architect gates, debug converge loops). If you're building a workflow template that dispatches dev work, use kanban_chains — the template can't predict task count or dependency structure at design time.

**ESCALATE no longer forces loop_engine.** The fix (verifier routes ESCALATE via kanban_chains instead of kanban_block) means kanban_chains works correctly for dev→verify pairs that might ESCALATE. The verifier dependency-parks on the escalation card, auto-promotes when tech-lead handles it, then completes.

**When the user says "use kanban_chains", they mean the CALLING profile uses kanban_chains to route — NOT that the workflow template should switch to loop_engine or that someone should call kanban_block.** The fix for any "X blocks the chain" deadlock is: X calls kanban_chains to create a handler card, which dependency-parks X (status=todo). X auto-promotes when the handler completes. This is the universal pattern for routing-within-chains without deadlocking.

### 9. Two templates with same trigger fire on same card

You cannot run A and B template versions in parallel — both templates with the same `card_completed` trigger condition will fire on the same card in the same tick. Use sequential testing (run A, disable, reset, run B) or add board-scoped trigger conditions if the engine supports them.

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

**Symptom:** The close card body contains a hardcoded verdict string (e.g. `Verdict: FAIL`) that does not reflect the actual pipeline outcome. The worker must override it based on upstream evidence.

**Observed in tl-gauntlet-a round 3:** The close card (t_7ea54bd2) body carried `Verdict: FAIL`, but all upstream verifiers had PASS'd and the work was merged to master (1b7099b). The tech-lead correctly overrode the stale label and followed the PASS path.

**This is distinct from lesson #13** (verify FAIL→close false merge via unconditional edge). Lesson #13 is a graph-topology defect — close fires because the edge has no condition. This lesson is a **card-body template defect** — the verdict is hardcoded as a literal in the body text instead of being read from upstream verifier metadata.

**Root cause:** The close card body was written at template-design time with a placeholder verdict. Body text is IGNORED by the enforcement hierarchy (lesson #1), so the literal is never validated against runtime state.

**FIX (template-side):** The close card body must NOT contain a verdict literal. Instead, it should instruct the worker to read the verdict from the upstream verifier terminal(s) via `kanban_show` or `task_runs.metadata`. The completion metadata should carry the resolved verdict, not echo a body literal.

**Generalization:** never hardcode runtime-decided values (verdicts, counts, SHAs, status) as literals in card body templates. They go stale and force manual reconciliation. Read them from the source at runtime.
