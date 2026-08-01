# Engine Hard Capability Constraints — Approach A vs Approach B

Analysis date: 2026-08-02
Engine: `~/.hermes-teams/startup/scripts/workflow_engine/`
Files read in full: `runtime.py` (2055 lines), `model.py` (286), `kanban_adapter.py` (238), all 11 templates in `templates/`.

---

## The two approaches under evaluation

- **Approach A** — ONE big workflow template containing the entire dev pipeline (plan→dev→verify→ship/fix→escalate) as a single directed graph with conditional edges.
- **Approach B** — MANY small workflow templates, one per agent (dev template, verifier template, QA template...), linked via `card_completed` triggers: a dev card completing fires the verifier template, the verifier PASS fires the QA template, etc.

---

## Summary table

| Feature | Approach A (one big graph) | Approach B (many small, trigger-linked) | Code evidence |
|---|---|---|---|
| **(1) Cycles / dev↔verify loop** | **NEEDS CODE** — engine is a DAG, no cycle support | **NEEDS CODE** — no cross-workflow re-entrant loop | `runtime.py:849,853-859` (single activation decision per tick); `:984-1009` (terminal-state completion) |
| **(2) Triggers supported** | N/A (no trigger) | **PARTIAL** — assignee, status, metadata.\*, title_prefix/not | `runtime.py:1908-1933` (`_matches_trigger`) |
| **(2b) Triggers missing** | N/A | **NEEDS CODE** — no `parent_workflow`, `metadata.iteration_count`, numeric/range, OR-of-conditions | `runtime.py:1908-1933` |
| **(3) Cross-workflow triggering** | N/A | **PARTIAL** — works for *externally* created cards; engine cards blocked when parent has explicit edges | `runtime.py:1783-1800` |
| **(4) Node types needed** | **SUPPORTED** — task, command, subworkflow, wait, foreach all exist | **PARTIAL** — no "loop"/"retry" node; everything else supported | `model.py:47`; `runtime.py:922-973` |
| **(5) Conditional edges** | **PARTIAL** — `== 'x'`, `!= 'x'`, `exists`, `is empty` only | **PARTIAL** — same 4 ops in trigger conditions | `model.py:256-286` (`evaluate_condition`) |
| **(6) Foreach subworkflow** | **SUPPORTED** (helps composition) | **SUPPORTED** (this IS Approach B's composition primitive) | `runtime.py:1419-1511` |

Detail for each cell below.

---

## (1) CYCLES — the dev↔verifier iteration loop

### Can the engine express a loop today? **No.**

The engine is a **DAG executor**. Node status is a one-way state machine: `PENDING → DISPATCHED → {DONE, FAILED, SKIPPED}` (`runtime.py:43-48`). There is **no transition back to PENDING** anywhere in the code. Once a node reaches a terminal state it is never re-run within the same instance.

**What happens if an edge points back to an earlier node** (e.g. `fix → review`)?
1. The activation check (`runtime.py:847-863`) only looks at `incoming` edges to a PENDING node. A node already DONE/DISPATCHED is skipped (`:793`: `if ns.status != PENDING: continue`).
2. Even if you could reset `review` to PENDING, the `idempotency_key` guard in `_dispatch_node` (`:1045-1053`: `idem_key = f"wf:{instance_id}:{node.id}"` then `find_cards_by_idempotency_key`) would find the *old* card and return its id — **the same card**, not a fresh review. The fix would never be re-reviewed.
3. The completion check (`runtime.py:978-984`) marks the whole instance complete when *all* nodes hit a terminal state. A loop can never "all terminal."

**Proof from the shipped template** — `dev-review-loop.json` is the engine author's own attempt at dev↔verify. It does **not** loop. It unrolls: `build → review → fix → re-review → ship` (5 linear nodes, `:5-41`). The re-review is a *separate node* with its own id, card, and idempotency key. A second failure after `re-review` would silently dead-end — no `re-review-2` exists. This is the engine's hard limit: **iteration must be unrolled at template-authoring time, with a fixed maximum number of rounds.**

### Approach A
**NEEDS CODE.** A "loop until PASS" with an unknown iteration count cannot be expressed. You'd either (a) unroll N times (template bloat, fixed ceiling), or (b) require new code: a node-status reset + a fresh-idempotency-key-on-re-entry mechanism + a cycle-aware completion predicate ("all *active* nodes terminal" rather than "all nodes terminal").

### Approach B
**NEEDS CODE.** Cross-workflow re-entrant loops also don't exist. A `dev-done` trigger firing `verify-template`, whose `verify-FAIL` would need to fire `dev-template` *again* — but:
- The new dev card has a fresh id/idempotency key (good — no dedup collision), **but**
- There is no iteration counter carried across workflows, no "this is fix attempt #3" state, and
- The self-trigger guard (`:1783-1800`, see §3) would need careful design to avoid infinite trigger chains.
The trigger mechanism gives you *transitions* but not a *bounded loop with state*.

**Verdict: cycles are the single biggest blocker for both approaches. Neither can express "iterate dev↔verify until PASS or N attempts."**

---

## (2) TRIGGERS

### Supported conditions (read `_matches_trigger`, `runtime.py:1908-1933`)
| Key | Behavior | Line |
|---|---|---|
| `assignee` | exact match on `card.assignee` | `:1911-1913` |
| `status` | exact match on `card.status` | `:1914-1916` |
| `metadata.verdict` | match on `metadata['verdict']` | `:1917-1920` |
| `metadata.<field>` | generic metadata field match | `:1921-1925` |
| `title_prefix` | `card.title.startswith(expected)` | `:1926-1928` |
| `title_not_prefix` (and `title_not_prefix2`...) | negation of prefix | `:1929-1932` |

All conditions are **AND-ed** (`return False` on any mismatch, `return True` at end). There is **no OR** and **no negation** except title prefix negation.

Trigger *sources* (`model.py:12`, `runtime.py:1765,1833`): `card_completed`, `bead_ready`, `manual`.

### Approach A
Doesn't use triggers (manual/parent-spawned start). **N/A.**

### Approach B
**PARTIAL.** The supported conditions are enough for simple routing:
- `dev-template` completes → verifier card has `assignee=dev` → fire `verify-template` ✅
- verifier completes with `metadata.verdict=PASS` → fire `qa-template` ✅ (this is exactly `qa-loop.json`)
- verifier `metadata.verdict=FAIL` → fire `fix-template` ✅

**MISSING for Approach B** (would need code):
1. **No iteration count.** You cannot express "fire fix-template only if `iteration_count < 3`". There's no counter trigger key. The dev↔verify loop cannot self-terminate via triggers — it will fire fix-template on every FAIL forever.
2. **No numeric/range comparison.** `evaluate_condition` (model.py:256-286) supports only `==`, `!=`, `exists`, `is empty` on strings. No `>`, `<`, `>=`. So "failures >= 3 → escalate" is not expressible.
3. **No OR of conditions.** All trigger keys AND. You can't say "verdict=FAIL OR verdict=BLOCKED".
4. **No `parent_workflow` / `parent_instance` condition.** You can't scope a trigger to "only fire for cards created by the dev pipeline" — relies on `title_prefix` heuristics instead (fragile; see `qa-loop.json` using `title_not_prefix` to exclude probes).

**Verdict: triggers cover the happy-path forwarding (B's core mechanic) but lack the bounded-loop / escalation conditions B also needs.**

---

## (3) CROSS-WORKFLOW TRIGGERING (self-trigger guard, lines 1783-1800)

This is the critical section for Approach B. The logic:

```python
if card.idempotency_key and card.idempotency_key.startswith("wf:"):
    instance_part = idempotency_key.split(":")[1]          # e.g. "1717_dev-pipeline_ab12"
    if f"_{wf.id}_" in instance_part:
        continue                                           # SAME workflow — block (self-trigger)
    # cross-workflow: find parent_wf_id by heuristic (longest non-digit chunk)
    parent_wf = self.store.load(parent_wf_id)
    if parent_wf and parent_wf.edges:
        continue                                           # parent has explicit edges — block
```

### When does a card_completed trigger from workflow X fire for workflow Y?
- **Card NOT created by the engine** (no `wf:` idempotency key, e.g. a manually created card or one a human made): **fires freely** — `_matches_trigger` runs. This is the intended path for trigger-based composition and works.
- **Card created by the engine, same workflow** (`instance_part` contains `_Y_` where Y is the triggering workflow): **blocked** (self-trigger prevention).
- **Card created by engine workflow X, and X has explicit edges**: **blocked**, because the comment says "if the card's parent workflow uses explicit edges, [it] handles routing internally" (`:1791-1800`). The trigger-based workflow is assumed redundant.
- **Card created by engine workflow X, and X has NO explicit edges** (implicit depends_on only): **allowed** (backward-compat).

### Approach B
**PARTIAL — works only if templates use implicit depends_on, not explicit edges.**
This is a **direct conflict** with Approach B as typically specified. If you write `verify-template.json` with `"edges": [...]` (the cleaner, recommended form — used by `dev-review-loop.json`, `builder-grill-build.json`, `builder-single.json`, etc.), then a card created by `verify-template` will **NOT** fire any downstream `card_completed` trigger. The guard treats explicit-edge workflows as "self-contained" and suppresses trigger propagation.

To make Approach B work today, every small template must:
- avoid the `"edges"` array entirely and use `depends_on` + `condition` (implicit), OR
- ensure the completing card is created outside the engine (manual / `kanban_create` from inside an agent).

The `parent_wf_id` extraction itself is **heuristic and fragile** (`:1793-1796`): it picks the first chunk in the instance id that is "not `wf`, not empty, not all-digit, length > 3." Workflow ids shorter than 4 chars or containing digits would break the heuristic, causing either false-blocks or false-alloweds.

**Verdict: Approach B's defining mechanic — engine-created card in workflow X triggering workflow Y — is actively suppressed when templates use the (recommended) explicit-edges form. This is a real, current-code blocker, not hypothetical.**

---

## (4) NODE TYPES

Node types (model.py:47, dispatched in runtime.py:922-973):
- `task` — creates a kanban card for a profile (`_dispatch_node`, `:1033`)
- `command` — runs a shell command synchronously, no card (`_run_command_node`, `:1171`)
- `subworkflow` — starts a child workflow, blocks until complete (`_dispatch_subworkflow_node`, `:1607`)
- `wait` — polls a condition each tick (`_check_wait_node`, `:1260`)
- `foreach` — modifier on task/subworkflow/command: one card/instance per list item (`_dispatch_foreach_node` `:1513`, `_dispatch_foreach_subworkflow` `:1419`, `_run_foreach_command` `:1095`)

Plus `card_mode` for tasks: `template` | `delegate` | `chain` (`:1057-1093`, `:1294`, `:1338`).

### Approach A
**SUPPORTED for the linear parts.** plan/dev/verify/ship are all `task` nodes; conditional routing uses edges (§5). Build steps can be `command`. Waiting for external merge can use `wait`. **Missing: a "loop" or "retry" node type** — there is no node whose semantics are "re-run node X until condition Y or N times." The dev↔verify loop (§1) cannot be a node.

### Approach B
**SUPPORTED** — each small template is 1-2 `task` nodes; cross-template linking uses triggers. No new node type needed for the happy path. Same missing-loop-type caveat if you want intra-template retries.

**Verdict: node types are sufficient for both; neither approach is blocked on node types. The gap is control-flow (loops), not node vocabulary.**

---

## (5) CONDITIONAL EDGES (AND/OR semantics, lines 803-863)

### Edge routing semantics (`runtime.py:810-849`)
- **Unconditional edges** (no `condition` field) into a node: **ALL sources must be DONE** (AND / convergence). Sources that are SKIPPED/FAILED are ignored (`:824-825, 842`).
- **Conditional edges** into a node: **ANY source DONE + condition passes** activates the node (OR / conditional-diamond routing). First match wins (`break` at `:841`).
- Activation rule (`:849`): `unconditional_ok AND (conditional_ok OR no conditional)`.
- If all sources reach terminal state but none activated → node is **SKIPPED** (`:853-859`).

### Can they express the required routing? **PARTIAL.**
| Required edge | Expressible? | Why |
|---|---|---|
| review PASS → ship | ✅ | `${nodes.review.output.verdict} == 'PASS'` |
| review FAIL → fix | ✅ | `${nodes.review.output.verdict} == 'FAIL'` |
| iteration ≥ 3 → escalate | ❌ | `evaluate_condition` has no `>=`; only `==`/`!=`/`exists`/`is empty` |

`evaluate_condition` (model.py:256-286) regex-matches exactly four forms:
- `${var} == 'value'`
- `${var} != 'value'`
- `${var} exists`
- `${var} is empty`

Any other expression returns `False` (`:286`). There is **no numeric comparison, no boolean AND/OR within a single condition, no `in`, no substring match.** A condition like `${nodes.review.output.failures} >= 3` silently evaluates to False and the node is skipped — a dangerous silent-misroute.

### Approach A
**PARTIAL.** PASS→ship and FAIL→fix work (the `dev-review-loop.json` template proves it, `:45-48`). Escalation-on-N-failures does **not** — you'd need new code in `evaluate_condition` (numeric ops) plus an iteration counter somewhere in context.

### Approach B
**PARTIAL.** Trigger conditions have the same operator limits (actually worse: `_matches_trigger` does exact equality on string fields only, no `exists`/`is empty`). `metadata.verdict == 'PASS'` works; `metadata.failures >= 3` does not.

**Verdict: conditional routing covers the binary PASS/FAIL diamond for both approaches, but neither can express count-based escalation without new code in `evaluate_condition`.**

---

## (6) FOREACH SUBWORKFLOW (`_dispatch_foreach_subworkflow`, lines 1419-1511)

Spawns one **independent** child workflow instance per list item. No barrier — item A's build starts as soon as its own grill finishes, without waiting for item B's grill (per the docstring, `:1422-1426`). Parent node completes when ALL children complete (`:702-709` in `_check_instance`).

### Approach A
**SUPPORTED — helps.** Foreach-subworkflow is the natural way to compose: the big pipeline could have a `spawn_verify_subworkflows` node that fans out. But this is really just a composition primitive; it doesn't solve the loop problem (each child is itself a DAG).

### Approach B
**SUPPORTED — this is essentially what Approach B *is*.** `builder-grill-build.json` is a textbook Approach-B template: a command node parses ideas, then a `foreach` + `subworkflow` node spawns one `builder-single` per idea (`builder-grill-build.json:14-24`). Each `builder-single` runs grill→build→handoff independently. **The engine already does fan-out-to-many-small-workflows today.** The fan-in (children completing → parent node done) also works.

**What foreach-subworkflow does NOT give Approach B:**
- **No fan-in *across* template types.** A foreach-subworkflow spawns N instances of the *same* child template (`workflow_ref`, `:1447`). It cannot say "spawn 1 dev + 1 verifier + 1 qa." That requires either (a) a child template that itself chains dev→verify→qa (which is Approach A), or (b) trigger-based linking (§3, blocked for explicit-edge templates).
- **No re-entry / loop.** Each child runs once.

**Verdict: foreach-subworkflow fully supports the fan-out pattern B relies on, but the *sequential chaining* (dev→verify→qa) within or across items still needs either explicit edges in one template (A) or working cross-workflow triggers (B, blocked per §3).**

---

## Cross-cutting: the dealbreakers

1. **No bounded loop, anywhere.** The engine is a DAG. dev↔verify iteration (the core of a dev pipeline) cannot be expressed in either approach without new code: a node-status reset, a re-entry idempotency scheme, and a cycle-aware completion check. The shipped `dev-review-loop.json` is proof — it unrolls to a fixed, finite node list and dead-ends on a 2nd failure.

2. **Cross-workflow triggering is suppressed for explicit-edge templates (§3).** Approach B's literal definition ("small templates linked via card_completed triggers") is **blocked by current code** if those templates use the recommended `edges` form. Only implicit-`depends_on` templates propagate triggers. This is an active conflict, not a missing feature.

3. **No numeric conditions (§5).** "escalate after 3 failures," "skip if findings_count > 5" — none expressible. `evaluate_condition` and `_matches_trigger` are string-equality-only. Silent-False-on-unknown is a misroute risk.

## What works today without code changes
- Linear pipelines with conditional diamonds (PASS→ship | FAIL→fix) — `dev-review-loop.json`.
- Fan-out: one template spawning N independent identical children — `builder-grill-build.json` → `builder-single.json`.
- Trigger-based forwarding for **manually created** (non-engine) cards or implicit-edge engine templates — `qa-loop.json`.
- Subworkflow composition with input/output mapping (`:1459-1468`, `:1706-1721`).
- Hard output validation (JSON Schema) blocking downstream on garbage output (`:726-748`).

## What needs new code (for either approach)
| Gap | Where | What to add |
|---|---|---|
| Cycles / loop node | `runtime.py` state machine (`:43-48`), activation (`:791-863`), completion (`:978-984`) | reset node to PENDING, fresh idempotency on re-entry, "active nodes all terminal" completion |
| Cross-workflow trigger for explicit-edge templates | `runtime.py:1791-1800` | drop the `parent_wf.edges` block, or add an opt-in `propagate_triggers: true` template flag |
| Numeric conditions | `model.py:256-286` (`evaluate_condition`), `runtime.py:1908-1933` (`_matches_trigger`) | `>=`, `<=`, `>`, `<` operators |
| Iteration counter in trigger/context | `_start_from_trigger` (`:1977`), trigger context | carry `iteration_count` across trigger firings |
| OR / complex trigger conditions | `runtime.py:1908-1933` | nested condition dict or expression evaluator |
