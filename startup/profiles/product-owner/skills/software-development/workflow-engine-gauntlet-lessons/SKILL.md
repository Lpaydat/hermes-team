---
name: workflow-engine-gauntlet-lessons
description: "Proven pitfalls and fixes from live-testing workflow templates with kanban_chains, loop_engine, and dynamic dev cards. Load when debugging a template that deadlocks, fires too early, crashes on ESCALATE verdicts, produces false PASS results, leaks active instances after close, or spawns duplicate instances. 28 lessons from 14+ gauntlet rounds across 5 templates, including TWO measured 5-board unbiased livetests (10 total specs). Includes the adversarial behavior-test verify paradigm (#27) — the fix for false PASS from static review — and the claimed-vs-actual score gap (#28). User iteration cap preference: 10 (not 3)."
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
- 4/5 work complete (board 1 hit review-required block again)
- verify now writes behavior tests and EXECUTES them
- Fix must pass ALL tests (dev's + verifier's behavior tests)
- Cannot lie about fixes — the failing test is the proof

See `references/unbiased-livetest-protocol.md` for both round 1 (static
review) and round 2 (adversarial behavior testing) results.

