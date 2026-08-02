# Design Review: Stateless Graph Engine — State Correctness & Concurrency

> **Reviewer focus:** state correctness and concurrency risks in `DESIGN-stateless-graph.md`.
> **Baseline:** current `runtime.py` (tick loop, `_check_instance`, `StateDB`), `model.py` (`evaluate_condition`).
> **Verdict:** The design is architecturally sound and the LangGraph analogy is apt, but **the single-JSON-blob state model introduces concurrency hazards that the current per-row UPSERT model does not have.** The design doc does not specify how the blob is read-modified-written, and the proposed tick ordering (SYNC → WALK → DISPATCH → SAVE) has at least three windows where correctness breaks. Two are **CRITICAL**.

---

## Summary table

| # | Concern | Risk | Block merge? |
|---|---------|------|--------------|
| 1 | Read-modify-write of the state blob is non-atomic | **CRITICAL** | Yes |
| 2 | SYNC + WALK span a check-then-act race vs. the board | **CRITICAL** | Yes |
| 3 | Back-edge reset loses the old card's output mid-window | **HIGH** | Yes |
| 4 | Exit-node completion model: cyclic graphs with no exit | **MEDIUM** | No (fixable in validation) |
| 5 | Crash between WALK and SAVE — partial dispatch lost | **HIGH** | Yes |
| 6 | Condition engine: `AND`/`OR` + numeric, no precedence/short-circuit spec | **MEDIUM** | No |

---

## Concern 1 — Read-modify-write of the state blob is non-atomic

**Risk: CRITICAL**

### The scenario

The design replaces the `node_states` table with a single JSON column on `workflow_instances` (DESIGN lines 124–141). The current per-node `update_node_state` (runtime.py:369–408) is an atomic single SQL `INSERT … ON CONFLICT … DO UPDATE` with `COALESCE` — it merges field-by-field **inside one statement**, so two concurrent callers updating *different fields* of the same node never clobber each other. That property is lost with a blob.

The tick is specified as (DESIGN lines 83–96):
```
1. LOAD state from DB        ← SELECT
2–5. SYNC / WALK / DISPATCH  ← mutate in-memory dict
6. SAVE state to DB          ← UPDATE row SET state = ?
```

Steps 1 and 6 are **separate SQL statements on separate connections**. The in-memory dict between them is the only thing carrying state. Now consider two ticks overlapping:

| Time | Tick A | Tick B |
|------|--------|--------|
| t1 | `SELECT state` → state₀ | |
| t2 | | `SELECT state` → state₀ |
| t3 | mutate → state₀ + {nodeX dispatched} | |
| t4 | | mutate → state₀ + {nodeY done} |
| t5 | `UPDATE … SET state = A` | |
| t6 | | `UPDATE … SET state = B` ← **overwrites A; nodeX dispatch lost** |

Tick B never saw nodeX's dispatch. Its `UPDATE` writes a blob that omits it. On the next tick, nodeX appears un-dispatched and is dispatched *again* → duplicate card (only saved by idempotency-key dedup at `find_cards_by_idempotency_key`, runtime.py:1048), or worse, a second iteration key if the graph walk already bumped the iteration counter.

### Why the existing locks don't save you

- `self._tick_lock` (runtime.py:521, threading.Lock) is **process-local**. Two `Engine` processes on the same machine bypass it entirely.
- `fcntl.flock(LOCK_EX | LOCK_NB)` (runtime.py:538) is process-wide but **non-blocking and advisory**: a second tick *returns immediately* ("SKIP tick", runtime.py:540) rather than waiting. So under the *current* model a second tick simply doesn't run — no concurrency. **But the design doc re-orders the work into one big read-modify-write, and if anyone ever (a) makes the flock blocking, (b) runs the tick in multiple threads without the Python lock propagating, or (c) introduces an out-of-band writer (a manual `hermes workflow reset` CLI command touching the blob), the lost-update is silent and unrecoverable** — there's no per-field merge to fall back on.

More concretely: the design explicitly keeps `kanban_adapter.py` as "board truth" and says a card flipping done→todo must be reflected (DESIGN lines 85–88). That means **something outside the engine writes to the board** between ticks. The same will be true of the state blob the moment any admin/CLI command touches it.

### Fix (pick one, must be in the design)

**Option A — Optimistic concurrency (preferred, low cost):**
Add a `version INTEGER` column to `workflow_instances`. The SAVE becomes:
```sql
UPDATE workflow_instances
SET state = ?, version = version + 1
WHERE instance_id = ? AND version = ?   -- ? = version read at LOAD
```
If `cursor.rowcount == 0`, another tick won the race → discard this tick's mutations and let the next tick re-run against fresh state. No data lost; at worst a redundant tick. This is the standard LangGraph/STM pattern and matches the "stateless graph" framing.

**Option B — Single-writer enforcement (simpler, what you effectively have today):**
Make the flock *blocking* (`LOCK_EX` without `LOCK_NB`) and document that exactly one engine process may tick at a time, ever. Then the blob is safe *within the engine*. Still need optimistic versioning to guard against out-of-band CLI writers, so this is really A+B.

**Option C — Keep per-node rows, just drop the `status` enum.**
If the real complaint is the `NodeStatus` enum (DESIGN lines 37–44), you can remove the enum without collapsing to a blob: store `card_status`, `output`, `iteration` as columns and keep the atomic `COALESCE` UPSERT. You lose the "one row" simplicity but keep the lost-update resistance you have today. Worth weighing against the stated ~800-line rewrite.

**The design must state which option is chosen and why.** Right now it's unspecified, which means the implementer will almost certainly ship a naive `SELECT … <mutate> … UPDATE` and inherit this bug.

---

## Concern 2 — SYNC vs. WALK check-then-act race with the board

**Risk: CRITICAL**

### The scenario

Step 2 (SYNC, DESIGN lines 85–88) reads each card's *current* status from the board into `state.nodes[node_id].card_status`. Step 3 (WALK) then decides dispatch/completion based on that synced status. Steps 2 and 3 are not transactional with respect to the kanban DB — they can't be, the board is a separate SQLite file (`board_db_path`, runtime.py:33,595).

Concrete break: a card is `done` at SYNC time (t1). The WALK at t2 reads `card_status == "done"`, validates the output, marks the node done, and marks the *instance* complete (exit-node rule, DESIGN lines 113–118). Between t1 and the instance-completion check, a human reopens the card → it flips to `todo`. The engine has already declared the instance `completed`. On the next tick, `load_active_instances()` no longer returns it (runtime.py:324–325 filters `status = 'active'`), so the regression is never observed. **The workflow is marked done while its exit card is open.**

The current engine has a weaker version of this (PHASE 1b, runtime.py:762–783, only *warns* on regression) but it never *completes* on a regressed card because completion re-checks the board (runtime.py:987–1003). The design removes that re-check — the completion model is "all exit nodes have reachable `done` cards" (DESIGN line 116) decided from state, not re-read from the board at the completion instant.

### Fix

1. **Re-read exit-node cards at the moment of declaring completion**, exactly as the current code does (runtime.py:988–1003). The design's completion check must explicitly say: "re-fetch each exit node's card from the board; if any is non-`done`, do not complete." Call this the **completion fence**. Cheap (a handful of `get_card` calls) and closes the window for the most damaging outcome (false completion).
2. For non-exit nodes, accept that SYNC is a snapshot — that's fine, it'll be corrected next tick. The critical invariant is only that **completion is never falsely asserted**.

Add a line to the design under "Completion model": *"Before transitioning to `completed`, re-read every exit node's card status from the board (completion fence). A regressed card prevents completion."*

---

## Concern 3 — Back-edge reset loses the old card's output mid-window

**Risk: HIGH**

### The scenario

DESIGN lines 148–153 describe the dev↔verifier loop:
```
Tick: review card is "done" with verdict=FAIL
Walk:  edge review→build (condition: FAIL) fires
       build is "done" but a back-edge is active → reset build
       iteration 0→1, new card created (idem key has iter1)
```

"Reset build" means: clear `state.nodes.build` so the WALK sees it as needing dispatch, bump iteration, and create a fresh card. The old card (iter 0) had `output: {branch: "feat"}` that downstream nodes may still reference. Two problems:

1. **Output loss during the gap.** Between the reset (iteration bumped, old entry superseded) and the new card completing, `state.nodes.build.output` is either wiped (so `ctx["nodes.build.output.branch"]` becomes empty → downstream templates get blank values, model.py:252 strips unresolved `${...}` to "") or frozen at the stale iter-0 value (so downstream briefly sees a branch that the *new* build hasn't produced yet). The design says "keep only latest output per node" (DESIGN line 221) — that's the wipe variant. Either way there's a window where the graph is internally inconsistent.

2. **What triggers the reset?** The review card going `done` with `verdict=FAIL`. But the review node itself is `done`. If the back-edge resets `build` but leaves `review` done, the *next* tick's WALK sees `review` done + `build` redispatched — fine. But if `review`'s output is what `build`'s new card needs as input (e.g., the review comment), and `build` iter-1 dispatches in the *same* tick as the reset, the dispatch uses `ctx` built *before* the reset resolved the new inputs. Order-of-operations inside one tick matters enormously here and the design doesn't pin it.

### Fix

1. **Pin the within-tick order explicitly:** SYNC → detect back-edges & compute resets → apply resets to state (bump iteration, preserve old output under an `iterations[]` array, clear *active* output) → rebuild `ctx` from post-reset state → WALK dispatch decisions → DISPATCH. The design's numbered list (lines 83–96) folds resets into "WALK" (step 3c) which runs *concurrently* with dispatch decisions (3b). Separate them.
2. **Never wipe old output** — move it to `state.nodes.build.iterations[0]` and keep `state.nodes.build.output` pointing at the *current* iteration. When iter-1 completes, it overwrites `.output`. During the gap, `.output` holds the last-known-good value, which is far less dangerous than empty (downstream nodes shouldn't be dispatching during the gap anyway, since `build` is mid-flight). This also satisfies the audit-trail goal (DESIGN line 109) without the "cap at 10" hack.
3. **Add an invariant test:** after a back-edge fires, no downstream node dispatches in the same tick using pre-reset context.

---

## Concern 4 — Exit-node completion: cyclic graph with no exit nodes

**Risk: MEDIUM**

### The scenario

DESIGN lines 113–118: a workflow completes when all **exit nodes** (nodes with no outgoing edges) have reachable done cards. The design's own Risks section (lines 225–226) acknowledges that "a cyclic graph with no exit condition loops forever" and proposes "require iteration cap on back-edges (validation at load time)."

But consider a graph that is *fully* cyclic — every node has an outgoing edge, so there are **zero exit nodes**. The completion rule "all exit nodes done" is vacuously true (all zero of them). The instance completes **immediately on the first tick**, before doing any work. This is detectable at template-load time but the design doesn't say the loader rejects it.

Worse: a graph with an exit node that is *unreachable* from any entry node (e.g., orphaned leaf) would also complete immediately if that orphan is somehow marked done, or hang forever if it's never dispatched.

### Fix

At template load (`store.py`, DESIGN line 26 "unchanged" — but it *must* change), add structural validation:
1. **Reachability:** every node must be reachable from at least one entry node (no incoming edges).
2. **Exit-node existence:** the graph must have ≥1 exit node *unless* an explicit `exit_condition` is declared on the workflow (DESIGN line 118, option 3).
3. **Termination:** every back-edge (edge whose `to_node` is an ancestor of `from_node`) must be guarded by a condition that references an iteration cap, *or* the workflow must declare `exit_condition`. Reject at load otherwise.

The design mentions (3) in Risks but doesn't make it a hard validation gate. It must be a gate, not a mitigation, because a non-terminating loop silently burns ticks forever (or, with zero exit nodes, completes instantly).

---

## Concern 5 — Crash between WALK and SAVE: partial dispatch lost

**Risk: HIGH**

### The scenario

The tick creates cards (step 4, DISPATCH) as a side effect against the *board* DB, then saves engine state (step 6, SAVE) to the *state* DB. These are two different SQLite files and two different transactions. If the process crashes (OOM, kill, power) after a card is created on the board but before the state blob is saved:

- The card exists on the board with idempotency key `wf:<inst>:<node>:iter1`.
- The state blob still shows iteration 0 / node not dispatched.
- Next tick: SYNC sees no card for the node (the node has no `card_id` in state to sync from). WALK decides to dispatch again. `find_cards_by_idempotency_key` (runtime.py:1048) finds the iter-0 card, not iter-1, because the idem key includes iteration and state still says iteration 0. **A second iter-1 card is created** (or the dedup misses it because the key differs by the not-yet-incremented iteration). Two cards for the same logical step.

The current engine has the same two-DB structure but mitigates it: `update_node_state` is called *immediately after* card creation within `_dispatch_node` (runtime.py:1050–1052, 1112), in the same tick, so the window is small and each dispatch is individually persisted. The design's "SAVE once at the end" **widens the window to the entire tick**.

### Fix

1. **Persist state after each dispatch**, not once at the end. This is the current behavior and it's correct. The design's "step 6: SAVE state to DB" should be reframed as "state is persisted incrementally as mutations occur (dispatch, completion, reset); the tick has no single save point." This keeps each mutation durable before the next begins.
2. If incremental persistence is rejected for performance, then **make card creation and state-save atomic-ish**: write the state blob *first* (mark node dispatched with the intended idem key), then create the card. On restart, a dispatched-but-card-missing node is retried and `find_cards_by_idempotency_key` dedups. The key insight: **the state must reflect the intent to dispatch before the card exists, not after**, so a crash leaves a re-dispatchable node rather than an orphan card.

Either way, the design's "SAVE at the end" (line 95) is wrong and must be corrected.

---

## Concern 6 — Condition engine upgrade: AND/OR + numeric, unspecified semantics

**Risk: MEDIUM** (not concurrency, but correctness of the routing that the whole state model depends on)

### The scenario

DESIGN lines 168–178 propose splitting on ` AND `/` OR ` and evaluating each clause. Current `evaluate_condition` (model.py:256–286) is regex-based, one operator per pass, returns `False` on any unrecognized form.

Unspecified hazards:
- **Precedence:** `A AND B OR C` — is that `(A AND B) OR C` (C-shortcircuit) or `A AND (B OR C)`? "Split on AND/OR" without a grammar means the implementer picks one arbitrarily; a wrong choice silently routes edges incorrectly (e.g., the escalate edge in DESIGN lines 162–166 fires at the wrong iteration).
- **Numeric comparison types:** `${nodes.build.iteration} < 3` — iteration is stored as a JSON number, but the current engine stringifies everything (`str(context.get(...))`, model.py:279). `"2" < "10"` is `False` in Python but `"2" < "10"` is lexicographically also False in SQL. Numeric `<` on stringified values will compare as strings → `10 < 3` is True (lexicographically "1" < "3"). **Silent wrong routing.**
- **No `NOT`, no parentheses, no `>=` token in the regex** — the design's own example (DESIGN line 159) uses `>=` which the current regex (model.py:282, matches `!=` only) won't parse.

### Fix

1. Specify the grammar explicitly in the design: left-to-right with `AND` binding tighter than `OR` (the common convention), no parens. Document it.
2. **Type-coerce before numeric comparison.** When a clause matches `<`, `<=`, `>`, `>=`, attempt `float()` on both sides; fall back to string compare only if both fail. Never stringify-then-compare numbers.
3. Add `>=`, `<=`, `>` operators to the regex set. The current four-operator set is insufficient for the iteration-cap pattern the design itself relies on (DESIGN lines 156–166).
4. Unit test the condition engine in isolation against the design's own loop example before wiring it into the WALK.

---

## Minor observations (not blocking)

- **State blob growth** (DESIGN risk 1, line 219): the "cap at 10 iterations" is a band-aid. Keeping a structured `iterations[]` per node (Concern 3 fix #2) with a retention policy (drop iterations older than N, keep latest output) is cleaner and auditable.
- **`status` field on `RunState`** (DESIGN line 71): the instance-level `status` ("active/completed/failed") is fine and mirrors the current column. But note the design keeps `completed_at` *outside* the blob (line 72 says it's on the dataclass; the DB column already exists, runtime.py:118). Be explicit that instance lifecycle columns stay as columns and only `nodes` becomes the blob — otherwise the migration (DESIGN lines 128–139) is ambiguous about what moves.
- **Zombie guard removed** (DESIGN lines 44, "Zombie guards stay but checks state, not status"): the current zombie guard (runtime.py:584–591) relies on `completed_at`. With the blob, ensure `completed_at` is still a column (it is) and the guard reads it, not the blob. The design says "checks state" which is ambiguous — clarify it checks the instance row, not `RunState`.

---

## What the design must specify before implementation

1. **State persistence strategy** for the blob: optimistic versioning (Concern 1, Option A) vs. single-writer lock vs. per-node rows. Currently unspecified.
2. **Completion fence:** re-read exit-node cards from board before declaring complete (Concern 2).
3. **Within-tick ordering:** back-edge resets must run before `ctx` rebuild and dispatch decisions (Concern 3).
4. **Template-load validation:** reachability, exit-node existence, back-edge termination (Concern 4) — as hard gates.
5. **Persistence timing:** incremental per-mutation, not one end-of-tick save (Concern 5).
6. **Condition grammar and numeric type coercion** (Concern 6).

Without items 1, 2, and 5, the rewrite will regress correctness that the current per-row-UPSERT engine currently has. I'd block merge on those three.

---

*File references are to `runtime.py` and `model.py` at `~/.hermes-teams/.worktrees/wf-dispatch/startup/scripts/workflow_engine/` and to line numbers in `DESIGN-stateless-graph.md` as read.*
