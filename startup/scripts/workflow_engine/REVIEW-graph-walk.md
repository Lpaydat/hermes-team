# Review: Stateless Graph Engine — Graph Walk Algorithm Correctness

**Reviewer focus:** edge semantics, back-edge detection, ordering, foreach, subworkflows.
**Verdict:** The design's *direction* (stateless graph, stateful blob) is sound, but the **graph-walk algorithm itself is unspecified**. Five of the hardest correctness problems the current engine already solves are either unaddressed or actively regressed by the schema change. Each is fixable, but the design must be amended before implementation, not discovered during it.

References use `DESIGN` = `DESIGN-stateless-graph.md`, `RT` = `runtime.py`, `M` = `model.py`.

---

## 1. EDGE SEMANTICS — **NO** (the algorithm is missing)

**Gap.** The design says "walk the graph against state to determine what to do next" (`DESIGN:89`) and "(graph, state) → actions, a pure function" (`DESIGN:98`), but never defines the function. The current engine has carefully tested AND/OR semantics at `RT:796-863`:

- **Unconditional edge** (`e.condition is None`) → **AND**: *all* unconditional sources must be `DONE` (`RT:810-829`). This is **convergence** — two parallel branches fanning into one node require *both* before the target runs.
- **Conditional edge** (`e.condition` set) → **OR**: *any* source `DONE` + `condition` passes activates the target (`RT:832-845`). This is the **conditional diamond** — `review→ship` on `PASS`, `review→fix` on `FAIL`.
- Activation rule (`RT:849`): `unconditional_ok AND (conditional_ok OR not conditional)`.
- Dead-branch skip (`RT:853-860`): if all sources reached terminal but none activated, the node is `SKIPPED` so the workflow can still complete.

The design's only hint is the loop example (`DESIGN:148-166`), which shows a single back-edge firing — it implies "any edge whose condition passes activates the target" (pure OR). That is **wrong for convergence** and would change behavior of every existing DAG that fans in.

**Concrete risk.** Template `dev-pipeline` style graphs (plan→{backend,frontend}→integrate) have two unconditional edges into `integrate`. Under a naive OR walk, `integrate` fires as soon as *either* branch is done. The current engine requires *both*. The test suite would catch it, but the design text would lead an implementer to ship the wrong thing.

**Fix.** Add an explicit "Activation" subsection to the design that restates the rule in terms of the new state blob, replacing `status == DONE` with "node has a card in terminal state AND its output is read into state":

> A node `N` is *dispatchable* when, over its set of incoming edges:
> - Let `U` = unconditional incoming edges, `C` = conditional incoming edges.
> - `U_sat` = every `e ∈ U` has its source "done" (output present in state).
> - `C_sat` = some `e ∈ C` has its source done AND `evaluate(e.condition, state)` is true.
> - Dispatchable iff `U_sat AND (C_sat OR C is empty)`.
> - "Done" = the source node has reached a terminal card state with valid output read into `state.nodes[src].output`.

This is a literal port of `RT:847-849` with `DONE` redefined as "has output in state." The "dead-branch skip" rule (`RT:853-860`) must also be ported or exit-node completion (`DESIGN:112-121`) deadlocks on unsatisfiable conditional branches.

---

## 2. BACK-EDGE DETECTION — **NO** (undefined; the load-time check is hand-waved)

**Gap.** The design says "build is done but a back-edge is active → reset build" (`DESIGN:152`) and "reset done node when back-edge fires" (`DESIGN:92c`) — but **never defines what makes an edge a back-edge**. Three candidate definitions give different behavior:

1. *"Any edge whose target already has output in state."* — runtime/state-based. But in a stateless walk you reset exactly the nodes you're about to fire; "target has output" is the trigger, not a property of the edge. This conflates detection with effect.
2. *"Any edge that creates a cycle in the template graph."* — structural, detectable at load time. This is the right definition but the design only mentions cycle detection in **Risks** (`DESIGN:225-226`) as "require iteration cap on back-edges (validation at load time)" — it never says *how* a cycle is found, nor that a back-edge IS a cycle-closing edge.
3. *"Any conditional edge."* — wrong; conditional edges are also used for forward diamonds (review→ship/fix with no loop).

**Current engine has zero loop support** — confirmed by grep: `iteration` appears nowhere in `runtime.py` except a foreach docstring (`RT:1098`); there is no cycle detection, no reset. So the design is inventing this from scratch and must specify it fully.

**Fix.** Add a "Back-edges" section:

> **Definition.** A back-edge is an edge `e = (from, to)` such that `to` can already reach `from` in the template graph (i.e., `e` closes a cycle). Equivalently, `e` is a back-edge iff adding it to the spanning forest creates a cycle.
>
> **Detection (load time).** Tarjan SCC (or DFS with coloring) on the template's edge set. Every edge whose endpoints lie in the same SCC is a back-edge. Store the back-edge set on the loaded `Workflow` (annotate `Edge` with `is_back_edge: bool` computed in `Workflow.from_dict`, `M:137-148`).
>
> **Walk behavior.** When walking, a back-edge `(from, to)` whose `condition` evaluates true AND whose `from` is done means: `to` must be **reset** — drop its current output/card, bump `state.nodes[to].iteration`, and let the normal dispatch rule re-fire it next tick with the iteration-aware idempotency key. Forward edges never reset.
>
> **Validation (load time).** Reject any back-edge lacking either (a) an iteration-cap clause in its condition, or (b) an alternative forward exit out of the cycle. This is the `DESIGN:225` mitigation, made enforceable.

Without structural detection, the walk cannot distinguish "review→fix is a forward diamond edge" from "review→build is a loop back-edge" — they look identical (conditional edge into a node that may or may not have output yet).

---

## 3. ORDERING / TWO-PHASE TICK — **PARTIAL** (the phase split exists but is under-specified, and back-edge reset breaks it)

**Gap.** The current engine deliberately runs **PHASE 1 (completions) before PHASE 2 (dispatch)** (`RT:617` vs `RT:784`). The payoff: when `review` flips to DONE-FAIL inside phase 1, the phase-2 dispatch loop *immediately* sees the updated state and can fire `review→fix` in the **same tick** (`RT:791` re-iterates `wf.nodes` after `ns.status` was mutated in place at `RT:753`). This halves latency on the hot path.

The design lists six tick steps (`DESIGN:83-96`) but conflates them: step 3 "WALK" does both "should it dispatch?" (3b) and "reset + re-dispatch" (3c) in the same pass, and step 4 "DISPATCH" is listed separately. It does **not** state that completions/read-output (3a) must be fully applied to `state` *before* any activation/reset decision (3b/3c) reads that state. An implementer following the bullets literally could evaluate activation against stale state (output not yet read) and miss the same-tick dispatch.

**Worse for loops:** the reset step (3c) *mutates* state (drops output, bumps iteration) while the walk is still iterating nodes. If `build` is reset before `review`'s activation is checked, or vice versa, ordering within the walk becomes load-bearing and undefined.

**Fix.** Make the phase boundary explicit and non-negotiable in the design:

> **Tick = three sequential passes over nodes, each completing fully before the next:**
> 1. **SYNC + READ** — for every node with a card, read current card status/output into `state`. No decisions. (Port of `RT:617-760`.)
> 2. **RESET** — for every back-edge whose condition is true and whose source has output, reset the target (clear output, bump iteration). Compute the reset set *first* from a snapshot, then apply — never reset a node you're about to evaluate for dispatch in the same pass.
> 3. **ACTIVATE + DISPATCH** — for every node, evaluate the activation rule (§1) against the now-stable state; dispatch those that qualify. (Port of `RT:784-973`.)
>
> Within pass 3, node iteration order does not matter for correctness **only because** all state reads in pass 3 are against the snapshot produced by passes 1+2; dispatch side-effects (new cards) are not visible until next tick. State this invariant explicitly. The current engine achieves it by mutating `ns` in place during phase 1 and re-reading `inst.node_states` in phase 2 (`RT:792`); the blob model must preserve "decisions read committed state, never mid-walk mutated state."

Also: the current engine rebuilds `ctx` after a `command` node completes *within* the dispatch loop (`RT:958`, `RT:966`) so downstream nodes in the same tick see the output. Under the blob model this intra-pass context refresh must be specified or command→task chains gain a tick of latency.

---

## 4. FOREACH — **NO** (unmentioned; the `iteration` key collides; node-state shape is undefined)

**Gap.** The word "foreach" does not appear in the design. The current engine has **three** foreach mechanisms, all stateful:

| Variant | Dispatch | Completion check | State shape today |
|---|---|---|---|
| foreach **task** (`RT:1513`) | N cards, idem key `wf:{inst}:{node}:{idx}` | poll all cards done (`RT:637-668`) | `ns.output = {_foreach_cards: [...], results: []}` |
| foreach **command** (`RT:1095`) | run N subprocesses synchronously | immediate | `ns.output = {_foreach_commands: True, results: [...]}` |
| foreach **subworkflow** (`RT:1419`) | N child instances, idem key `wf:{inst}:{node}:sw:{idx}` | poll all children done (`RT:670-710`) | `ns.output = {_foreach_instances: [...], results: []}` |

The design's `RunState.nodes` dict (`DESIGN:63-68`) lists shapes for task/command/subworkflow/wait nodes but **omits foreach entirely**, and the foreach-completion logic in PHASE 1 (`RT:637-710`) is in the very block the design says to "rip out" (`DESIGN:40-44`).

**Key collision.** The design introduces `state.nodes[node_id].iteration` for loops (`DESIGN:105`). Foreach nodes already use `item_index` (`RT:1471`, `RT:1555`). If a foreach node is *also* inside a loop (review FAIL → re-run the foreach), the node needs both an outer `iteration` (loop lap) and per-item indices. The design's single `iteration` field doesn't model this. Worse, the foreach idempotency keys above are **not** iteration-aware, so a loop that re-enters a foreach node would find the *old* cards via `find_cards_by_idempotency_key` and never re-dispatch.

**Fix.** Add a "Foreach" section:

> - A foreach task node's state entry: `{cards: [...], results: [...], iteration: <lap>}`. The dispatch idempotency key becomes `wf:{inst}:{node}:iter{iteration}:{idx}` — note the `iteration` segment so a back-edge reset (which bumps `iteration`) produces a fresh card set.
> - Foreach completion = all `cards` are in terminal state with valid output; aggregate into `results` (port `RT:637-668`).
> - Foreach command and foreach subworkflow keep their current completion semantics, ported to read from `state` instead of `node_states`.
> - `evaluate_condition` and the activation rule treat a foreach node like any task node: dispatchable when its incoming edges satisfy §1, "done" when all items are done.
> - Explicitly list foreach in the "What we keep / port" table (`DESIGN:22-33`) — right now it reads as if foreach is deleted.

---

## 5. SUBWORKFLOW BLOCKING — **NO** (no per-node lifecycle field; and the schema change breaks the completion read)

**Gap A — no blocking state.** The current engine blocks a subworkflow node by leaving it in `DISPATCHED` status with `_child_instance` in output (`RT:1648-1655`); each tick, PHASE 1 finds `status == DISPATCHED` and calls `_check_subworkflow_completion` (`RT:624-635`). The design **removes the status field** (`DESIGN:37-39`) and gives no replacement signal. The walk's activation rule (§1) would see a subworkflow node with no output and **re-dispatch it every tick**, spawning duplicate child instances. The design's own `RunState.nodes` comment says subworkflow nodes carry `{child_instance_ids, outputs}` (`DESIGN:66`) — but if `outputs` is empty while waiting, what stops re-dispatch? There's no "in-flight" marker.

**Gap B — schema breaks the read.** `_check_subworkflow_completion` reads the child's outputs via `SELECT node_id, output FROM node_states WHERE instance_id = ? AND status = 'done'` (`RT:1690`), and the foreach-subworkflow completion does the same (`RT:687`). The design **drops the `node_states` table** (`DESIGN:138`). After migration, both queries hit a nonexistent table. The design never says how a parent reads a child's outputs from the new single-row `state` blob — yet this is the *only* cross-instance state read in the engine and it's load-bearing for every subworkflow and foreach-subworkflow template.

**Fix.**

> - Add an explicit node-lifecycle field to each `state.nodes[node_id]` entry: `phase: "pending" | "running" | "done" | "failed"`. This is **not** the removed `NodeStatus` enum — it's derived each tick purely from card/child state, never persisted as a transitions-to-fight. The activation rule dispatches only nodes with `phase == "pending"`; subworkflow nodes flip to `running` when the child is spawned and to `done` when the child completes. This closes Gap A without reviving the monotonic-status bug.
> - For Gap B, specify the cross-instance read against the new schema: `SELECT state FROM workflow_instances WHERE instance_id = ?`, then `json.loads(row["state"])["nodes"]` to collect child node outputs. Port `_check_subworkflow_completion` (`RT:1659-1741`) and the foreach-subworkflow loop (`RT:670-710`) to this read. Note this couples parent and child through the `workflow_instances` row, not a side table — simpler, but the design must say so.
> - The completion model (`DESIGN:112-121`) must add: a subworkflow/foreach node counts as "reached terminal" only when `phase == "done"` (child/children complete), not merely when dispatched.

---

## Cross-cutting issues found while reading

- **`evaluate_condition` upgrade is under-scoped.** `DESIGN:171-178` proposes splitting on ` AND `/` OR ` and evaluating clauses, but the loop example (`DESIGN:159`) needs `${nodes.build.iteration} < 3` — numeric `<`/`>=`. `M:256-286` only handles `==`/`!=`/`exists`/`is empty` and `re.match` (anchored, single-operator). The "+40 lines" estimate (`DESIGN:204`) is optimistic for AND/OR *plus* numeric ops *plus* mixed-type coercion (iteration is int, verdict is str). Specify: clause grammar, type coercion rules, and operator precedence (AND binds tighter than OR? left-to-right?). Without this, two templates can write the same condition two ways and get different results.
- **Idempotency key regression for non-loop nodes.** `DESIGN:104-107` makes *every* node's key `wf:{inst}:{node}:iter{iteration}`. For the 11 existing DAG templates `iteration` is always 0, so keys change from `wf:{inst}:{node}` (`RT:1045`) to `wf:{inst}:{node}:iter0`. In-flight instances at migration time would lose their card association. Either keep the old key when `iteration == 0`, or document a one-time migration.
- **Zombie/deleted-board guards.** `DESIGN:43-45` says the deleted-board guard "stays but checks state, not status." But the guard at `RT:584-601` checks `inst.completed_at` and `board_db_path(inst.board).exists()` — neither involves node status. Re-verify these guards survive the rewrite; they're easy to drop and they prevent infinite zombie cycling.

---

## Summary scorecard

| # | Concern | Design addresses? | Severity |
|---|---|---|---|
| 1 | Edge semantics (AND/OR, convergence, diamonds) | **NO** | High — silent behavior change for DAGs |
| 2 | Back-edge detection | **NO** | High — loops cannot be implemented as written |
| 3 | Two-phase tick ordering | **PARTIAL** | Medium — invariant unstated; reset breaks it |
| 4 | Foreach (task/command/subworkflow) | **NO** | High — feature dropped from design entirely |
| 5 | Subworkflow blocking + cross-instance read | **NO** | High — schema change breaks existing reads |

**Recommendation:** Do not approve for implementation until §1 (activation rule), §2 (back-edge definition + load-time SCC), and §5 (per-node `phase` field + new-schema child read) are written into the design. §3 and §4 can be specified during implementation with test gates, but should still be added to the doc. The ~800-line runtime rewrite estimate (`DESIGN:205`) is reasonable *only if* these algorithms are nailed down first; otherwise expect significant rework once the test suite (correctly) fails on convergence and subworkflow cases.
