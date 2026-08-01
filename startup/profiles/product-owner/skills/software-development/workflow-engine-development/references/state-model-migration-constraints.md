# State Model Migration Constraints — what's load-bearing if you change it

> Distilled from a backwards-compat review (2026-08-02) of the proposed stateless-graph redesign (`DESIGN-stateless-graph.md`). When a change touches NodeStatus, the `node_states` table, or the completion model, these are the constraints that will bite. Quantified against the real codebase + 317-test suite.

## 1. The `node_states` table is consumed by raw SQL across the test suite

`DROP TABLE node_states` (as the redesign proposes) does **not** just affect the engine — the test suite reads it directly. As of review date:

- **57 `FROM node_states` query sites across 10 test files** (test_engine.py: 27, test_command_adversarial.py: 9, test_command.py: 5, test_adversarial.py: 5, test_concurrency_standalone.py: 3, test_wait_adversarial.py: 3, test_subworkflow.py: 1, test_wait.py: 1, test_unhappy.py: 1, test_dataflow.py: 2).
- Pattern: `SELECT output FROM node_states WHERE node_id='X'` then `json.loads(...)`. These hard-fail with `sqlite3.OperationalError: no such table` the moment the migration runs.
- **Fix pattern:** add a backwards-compat read shim on `StateDB` (e.g. `state_snapshot(instance_id) -> dict[node_id, {card_id, output, status}]`) mirroring the old rows, then rewrite the query sites to call it. Mechanical but mandatory — price it at ~150–200 LoC, not "rewrite internals."

## 2. NodeStatus is on import lines — removing it fails whole modules at load

The enum is imported by 3 test modules at module top:
- `test_engine.py` (104 tests), `test_subworkflow.py` (7), `test_adversarial.py`.

Deleting `NodeStatus` from `runtime.py` → `ImportError` at collection time → **all tests in those files fail before any test body runs** (118+ tests), not just the ~5 in-body assertions (`ns.status == NodeStatus.FAILED` etc.).
- **Fix:** keep a deprecated re-export shim for one release cycle, or enumerate the import-fix explicitly in the migration plan.

## 3. Completion model: SKIPPED is terminal — this is load-bearing

`runtime.py:977`: `terminal_states = {DONE, FAILED, SKIPPED}`. The `all_done` check (L979) completes the workflow when **every** node reaches a terminal state.

This is not incidental — it is what makes exclusive conditional branches work. Consider `check → (ship if PASS | fix if FAIL)`:
- On PASS: `ship` DONE, `fix` SKIPPED. Both terminal → workflow completes.
- `test_dead_branch` (test_engine.py:1313) and `test_explicit_edges_conditional` (test_explicit_edges.py:65) **assert** `WORKFLOW COMPLETE` with a skipped branch.

**Any redesign that changes completion to "all EXIT (leaf) nodes done/failed" will break this** — a skipped leaf node is neither done nor failed, so the workflow hangs. Equivalence between "all nodes terminal" and "all exit nodes terminal" holds **only if no SKIPPED node is a leaf**, which exclusive conditionals violate by construction.

**Proof of non-equivalence:** old completes when `∀n: status(n) ∈ {DONE,FAILED,SKIPPED}`; new (exit-node) completes when `∀ leaf: status ∈ {DONE,FAILED}`. These differ exactly when `∃ leaf: status = SKIPPED`, i.e. whenever a conditional branch that was skipped is itself a leaf.

**Fix for any new completion rule:** define terminal-for-exit = {done, failed, skipped}, OR prove no skipped node can be a leaf (false for current templates).

## 4. Unreachable / deadlocked nodes block completion today (and tests assert it)

Current `all_done` requires EVERY node terminal, including unreachable ones. Two tests assert the *hang* as correct behavior:
- `test_adv_graph_disconnected_node` (test_engine.py:2155): entry `e→f` plus unreachable cycle `x↔y`. Asserts `not WORKFLOW COMPLETE` and `len(active)==1`.
- `test_adv_graph_conflicting_diamond` (test_engine.py:2214): diamond `a→(b,c)→d` with exclusive conditions. Asserts non-completion.

A redesign using reachability-based completion (ignore unreachable components) would **change these outcomes**. Decide deliberately: preserve the hang (define reachability conservatively) or accept the behavior change and rewrite these tests. Don't claim "all tests pass unchanged."

## 5. DB migration of ACTIVE instances needs explicit backfill

`ALTER TABLE workflow_instances ADD COLUMN state TEXT NOT NULL DEFAULT '{}'` gives existing active instances an empty state blob. Without a backfill step that reads existing `node_states` rows into the new JSON, active instances lose their `card_id` mapping → orphaned cards on the board → re-dispatch creates duplicate cards (fresh iteration-0 idempotency keys).

**Required migration sequence:**
1. Stop the engine cron.
2. File-backup the state DB.
3. `ALTER TABLE ... ADD COLUMN state`.
4. Backfill (Python, not pure SQL — it's a JSON aggregation): `SELECT instance_id, node_id, status, card_id, output FROM node_states GROUP BY instance_id` → `json.dumps(...)` → `UPDATE workflow_instances SET state=?`.
5. Verify migrated instance count.
6. Only then `DROP TABLE node_states`.

## 6. `dev-review-loop.json` is a DAG, not a true loop

Despite the name, it models iteration as a **forward** chain: `build→review→fix→re-review→ship`, all forward edges, conditional on verdict. Each node runs once. Confirmed by reading the template. So "all 11 shipped templates are DAGs" is a true statement — but a redesign's loop feature has zero existing templates to exercise it, so loop tests must be net-new (the redesign's test plan acknowledges this).

## How to verify a "backwards compatible" claim against this engine

1. `search_files(output_mode='count', pattern='node_states')` across the test dir — gives the raw-SQL blast radius.
2. `search_files(output_mode='count', pattern='NodeStatus')` — gives the import + assertion blast radius.
3. Find tests asserting non-completion / deadlock (`grep "WORKFLOW COMPLETE"` + read the `assert not` cases) — these are the proof of current edge-case semantics.
4. State the minimal case where old and new models diverge; cite the test that asserts the old outcome.
