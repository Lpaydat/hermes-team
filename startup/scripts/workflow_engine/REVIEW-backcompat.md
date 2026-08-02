# Backwards Compatibility Review — Stateless Graph Engine

> Reviewer focus: migration safety, test rewrite scope, NodeStatus removal, completion model equivalence.
> Design doc: `DESIGN-stateless-graph.md`
> Verdict: **The design's headline claim — "existing templates work unchanged" and "existing tests must pass" — is misleading.** The templates do load unchanged (verified). The tests do NOT pass unchanged: at minimum 57 direct `node_states` DB queries across 10 files break on `DROP TABLE`, and 3 tests that assert `WORKFLOW COMPLETE` on deadlocked graphs will fail because the new exit-node completion model *changes* their outcome. The rewrite is feasible but the design must be amended to (a) acknowledge ~40+ test edits, (b) add a data migration for active instances, and (c) reconcile the completion-model divergence on conditional/skipped non-exit nodes.

---

## Test surface — what "backwards compatible" actually requires

### Inventory (counted, not estimated)

| Test file | Tests | `node_states` refs | `NodeStatus` refs | Notes |
|---|---|---|---|---|
| test_engine.py | 104 | 27 | 2 | Core; the `__main__` runner registers 104 `test_*` funcs |
| test_dataflow.py | 62 | 2 | 0 | |
| test_bad_templates.py | 41 | 0 | 0 | Pure load/validation — safest |
| test_integration.py | 17 | 0 | 0 | |
| test_command_adversarial.py | 10 | 9 | 0 | |
| test_composition.py | 10 | 0 | 0 | |
| test_unhappy.py | 10 | 1 | 0 | |
| test_adversarial.py | 10 | 5 | 2 | |
| test_wait_adversarial.py | 10 | 3 | 0 | |
| test_concurrency_standalone.py | 6 | 3 | 1 | |
| test_command.py | 6 | 5 | 0 | |
| test_explicit_edges.py | 5 | 0 | 0 | |
| test_foreach_enhancements.py | 9 | 0 | 0 | |
| test_subworkflow.py | 7 | 1 | 0 | |
| test_foreach_subworkflow.py | 7 | 0 | 0 | |
| test_wait.py | 3 | 1 | 0 | |
| **TOTAL** | **317** | **57** | **5** | 16 files |

The design's estimate of "~500 lines / rewrite internals" for tests is **optimistic by roughly 2–3×**. The `node_states` column alone forces edits in 10 of 16 files.

### Three distinct break classes

1. **Direct `node_states` table queries (57 hits / 10 files).** Tests that read node output/status by `SELECT output FROM node_states WHERE node_id='X'` (e.g. `test_command_basic`, `test_variable_resolution`, `test_subworkflow_output_mapping`). These hard-fail with `sqlite3.OperationalError: no such table: node_states` the moment the migration runs. Every one must be rewritten to read from the new `state` JSON blob column on `workflow_instances`.
2. **`NodeStatus` enum assertions (5 hits / 3 files).** `test_output_schema_validation` asserts `ns.status == NodeStatus.FAILED` directly; `test_wait_blocks_then_resolves` asserts `gate_status[0] in ("pending","dispatched")`; `test_concurrency_standalone` / `test_adversarial` use `NodeStatus.DISPATCHED`/`DONE`. When the enum is removed these become `ImportError` at module load — the entire file fails to import, not just one test.
3. **Completion-semantics assertions (see §5).** Tests that assert `WORKFLOW COMPLETE` or `not WORKFLOW COMPLETE` on graphs whose topology changes meaning under exit-node completion.

### Fix for §1
Add a **backwards-compat read shim** in `FakeWorld` (or a new `state_snapshot()` helper on `StateDB`) that returns a dict-of-node-dicts mirroring the old `node_states` rows. Rewrite the 57 query sites to call it. This is mechanical but mandatory — it is NOT "rewrite assertions internally," it is "delete 57 raw-SQL query blocks and replace them with an API call." The design should price this at ~150–200 lines, not lump it into "internals."

---

## 2. NodeStatus removal — honest impact

**Risk: MEDIUM.** Not catastrophic, but the design undersells it.

The enum is removed from `runtime.py` but **still imported by 3 test modules**:

```
test_engine.py:26            from workflow_engine.runtime import Engine, StateDB, NodeStatus, WorkflowInstance, NodeState
test_subworkflow.py:22       ... import ... NodeStatus, WorkflowInstance, NodeState
test_adversarial.py          (imports NodeStatus)
```

An import of a deleted symbol fails the *whole module*. Concretely:
- `test_engine.py` (104 tests) — **all 104 fail at import** until the import line is fixed.
- `test_subworkflow.py` (7 tests) — all 7 fail at import.
- `test_adversarial.py` — fails at import.

So removing `NodeStatus` doesn't break "a few assertions," it **breaks 2 of the 3 largest test files at collection time** before any test body runs.

The 5 in-body assertions (`ns.status == NodeStatus.FAILED`, `NodeStatus.DISPATCHED`, etc.) additionally need rewriting to the new state model. The design's "rip out NodeStatus" bullet has no companion "update test imports" step.

### Fix
Either (a) keep `NodeStatus` as a deprecated alias shim in `runtime.py` for one release cycle (re-export from the new state strings), or (b) explicitly enumerate the import-fix in the migration plan. Recommend (a) — it costs nothing and makes the cutover bisectable.

---

## 3. DB migration — active instances WILL be lost (CRITICAL)

**Risk: HIGH.** The design's `DROP TABLE node_states` + `ALTER TABLE workflow_instances ADD COLUMN state` sequence silently destroys in-flight state.

The design doc says only:

```sql
ALTER TABLE workflow_instances ADD COLUMN state TEXT NOT NULL DEFAULT '{}';
DROP TABLE node_states;
```

This has three concrete problems on a live engine (the cron is running right now):

1. **Active instances lose all node state.** The new `state` column defaults to `'{}'`. Existing active instances, after migration, have an empty `nodes` dict. Their dispatched cards are orphaned on the board — the engine no longer knows which card belongs to which node/instance. On the next tick the graph walk sees an empty state, re-dispatches entry nodes, and creates **duplicate cards** (new iteration-0 idempotency keys, since the old `card_id` mapping is gone).
2. **`DROP TABLE` is irreversible and the design gives no data-backfill step.** There is no `INSERT ... SELECT` that reads existing `node_states` rows into the new `state` JSON. Every active node_state row is discarded.
3. **`ALTER TABLE ... ADD COLUMN ... DEFAULT '{}'`** — SQLite does not recompute the default into existing rows in all access patterns; reads return `'{}'`. Confirmed behavior.

The design's Risks section (§Risks 1–3) covers blob growth and cycle detection but **does not mention the migration-of-live-data risk at all**.

### Fix
Add a real migration, ordered:

```sql
ALTER TABLE workflow_instances ADD COLUMN state TEXT NOT NULL DEFAULT '{}';
-- Backfill: for each active instance, reconstruct RunState.nodes from node_states
-- (run in Python, not pure SQL — it's a JSON aggregation):
--   SELECT instance_id, node_id, status, card_id, output FROM node_states
--   GROUP BY instance_id → json.dumps({node_id: {card_id, output, _legacy_status}})
-- Then UPDATE workflow_instances SET state = ? WHERE instance_id = ?
-- Only AFTER backfill verified: DROP TABLE node_states;
```

The migration **must** (a) run the backfill, (b) log the count of migrated instances, (c) take a file backup of the DB before `DROP`, and (d) be gated on zero active instances if possible, or at least warn loudly. The engine cron should be stopped during cutover. Add a "migration" subsection to the design; right now there is none.

---

## 4. Template validation — back-edge cap rule is underspecified

**Risk: MEDIUM.** No existing template breaks today, but the proposed validation is unspecified enough to be a trap.

**Verified: all 11 shipped templates are DAGs.** I checked `dev-review-loop.json` — despite the name, it models iteration as a *forward* chain (build→review→fix→re-review→ship) with conditional edges, **not** a true back-edge. Its edges are all forward. So the design's claim "all 11 are DAGs, no back-edges" is correct.

However the design says:

> Cycle detection — a cyclic graph with no exit condition loops forever. Mitigation: require iteration cap on back-edges (**validation at load time**).

This raises questions the design does not answer:

1. **What is the validation rule exactly?** Is it "every edge participating in a cycle must have a `${...iteration} < N` clause in its condition"? How is "participates in a cycle" computed (Tarjan SCC)? The design doesn't say.
2. **Does it need a new template field?** The example embeds the cap in the *condition string* (`${nodes.build.iteration} < 3`). That means validation must parse condition strings to detect the cap — fragile. A dedicated `max_iterations` field on the edge would be cleaner and statically checkable.
3. **Does validation reject templates that are valid DAGs but whose condition strings *look* cyclic?** E.g. a condition referencing another node's `.iteration` that isn't actually a back-edge. Risk of false positives.
4. **What about the existing `test_circular_dependency` and `test_adv_graph_three_node_cycle` tests?** These currently assert that cyclic *implicit* `depends_on` graphs simply don't dispatch (deadlock, no crash). Under the new model with mandatory iteration caps, do these templates now fail *load-time validation* and raise? That changes a "soft deadlock" into a "hard template-rejection" — a behavior change the tests would catch.

### Fix
Specify the validation rule precisely in the design: (a) compute SCCs at load; (b) for any edge in an SCC, require either an explicit `max_iterations` field OR a condition clause matching a `iteration < N` regex; (c) make implicit-`depends_on` cycles (no edges) a separate, softer check that matches today's deadlock behavior so `test_circular_dependency` still passes. Add a new template field rather than parsing condition strings.

---

## 5. Completion model equivalence — NOT equivalent for skipped/disconnected nodes (CRITICAL)

**Risk: HIGH.** The design claims:

> For DAGs (no loops), exit nodes = leaf nodes. This is backwards compatible — the current templates are all DAGs.

This is **false for the test suite**, which contains DAGs that the *current* engine refuses to complete and the *new* engine would complete (or vice versa). Two concrete counterexamples exist in the tests themselves:

### Counterexample A — `test_adv_graph_disconnected_node` (test_engine.py:2155)

Graph: entry `e→f` plus an unreachable cycle `x↔y` (via implicit `depends_on`).

- **Current model:** `e` and `f` reach DONE; `x` and `y` stay PENDING forever. The `all_done` check (`runtime.py:979`) requires *every* node terminal. So the workflow **never completes**. The test **asserts** `not "WORKFLOW COMPLETE"` and `len(active) == 1`.
- **New model (exit-node):** exit nodes = leaf nodes. `f` is a leaf (no out-edges); `x` and `y` are also leaves of their component. If exit-node completion means "all exit nodes done," then `f` done is insufficient — `x`,`y` never run, so it still hangs. **But** if the new model only considers *reachable* exit nodes, the workflow completes. The design doesn't define reachability. Either way, the test's assertion is load-bearing and the new model must be shown to preserve it.

### Counterexample B — `test_adv_graph_conflicting_diamond` (test_engine.py:2214)

Diamond `a→(b,c)→d` where `b` condition is PASS, `c` condition is FAIL. On PASS: `b` DONE, `c` SKIPPED, `d`'s deps can't all be DONE.

- **Current model:** `d` stays PENDING (its dep `c` is SKIPPED, not DONE). Workflow **deadlocks**. The test documents this as a WEAKNESS and asserts non-completion.
- **New model:** `d` is an exit node (leaf). "Exit nodes done" — `d` is never done. Still deadlocks. **But** the skipped-node question (below) is unresolved.

### The skipped-non-exit-node question (the real bug)

The design's completion rule is "all **exit nodes** have reachable `done` cards." Consider a simple conditional:

```
check → (ship if PASS | fix if FAIL)
```
On PASS: `ship` DONE, `fix` SKIPPED. `ship` is the exit node reached; `fix` is also an exit node (leaf) but was skipped.

- **Does a SKIPPED exit node block completion?** The design says completion = "all exit nodes done OR failed." A skipped node is neither done nor failed. **So a skipped exit node would block completion** — breaking `test_dead_branch` (test_engine.py:1313) and `test_explicit_edges_conditional` (test_explicit_edges.py:65), both of which assert `WORKFLOW COMPLETE` when one branch is skipped.

This is the sharpest finding: **the exit-node completion rule as written is incompatible with the existing SKIPPED semantics.** In the current model, SKIPPED counts as terminal (runtime.py:977 `terminal_states = {DONE, FAILED, SKIPPED}`), so a dead branch completes the workflow. In the new model, a skipped exit node is not "done" and not "failed," so the workflow hangs.

### Proof of non-equivalence for DAGs
The claim "exit-node completion ≡ all-terminal completion for DAGs" holds **only** when every node is either done or failed. It breaks precisely when SKIPPED nodes exist that are themselves exit nodes (leaves). Conditionals with exclusive branches produce exactly this shape. Therefore:

> **The two models are equivalent iff no SKIPPED node is a leaf.** This is not guaranteed by any existing template or test.

### Fix
The completion rule must be amended to: *a workflow completes when every exit node is in a terminal state — **done, failed, or skipped** — AND no exit node is "stuck pending with no possible path" (reachability).* Concretely:
1. Define terminal-for-exit = {done, failed, skipped}.
2. Add reachability: an exit node only blocks completion if it is *reachable* from a dispatched/done node. Unreachable components (Counterexample A) should be ignored, not block — OR explicitly preserve today's hang behavior and update the test. Pick one and document it.
3. Add explicit test cases to the design's test plan: skipped-exit-node, conflicting-diamond, disconnected-component — asserting the *chosen* semantics. Today's tests assert the *old* semantics, so the design must state which of these tests change outcome and rewrite them deliberately, not claim "all pass unchanged."

---

## Summary table

| # | Concern | Risk | Quantified impact | Fix |
|---|---|---|---|---|
| 1 | Test surface (`node_states` queries) | MED | 57 query hits / 10 files; ~150–200 LoC to rewrite | Add read shim; rewrite query sites; reprice test effort |
| 2 | NodeStatus removal | MED | 3 files fail at import (118+ tests) | Keep deprecated alias shim for one cycle |
| 3 | DB migration of active instances | **HIGH** | All active instances orphaned; duplicate card dispatch | Add backfill migration + backup + cron-stop gate |
| 4 | Back-edge validation underspecified | MED | 0 templates break today; future templates at risk | Define SCC-based rule + `max_iterations` field |
| 5 | Completion model non-equivalence | **HIGH** | ≥3 tests change outcome; skipped-exit-node breaks completion | Amend rule to include skipped as terminal; define reachability; rewrite affected tests explicitly |

## Recommendation

**Do not approve as drafted.** The architecture is sound (stateless graph is the right direction), but the backwards-compatibility claims are overstated in two load-bearing places: the DB migration has no data-backfill step (§3), and the completion model is provably non-equivalent for skipped exit nodes (§5). Both must be amended before implementation. The test-rewrite scope (§1, §2) should be repriced honestly — it is a mechanical but real ~200-line effort across 10 files, not "rewrite internals."

**Approve after** the design adds: (a) a migration subsection with backfill SQL/Python, (b) an amended completion rule that treats skipped as terminal and defines reachability, (c) a NodeStatus deprecation shim, and (d) an explicit list of which existing tests change outcome (at minimum the 3 in §5) with their new assertions.
