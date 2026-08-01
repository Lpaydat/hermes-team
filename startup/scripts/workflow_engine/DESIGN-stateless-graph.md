# Stateless Graph Engine — Design Doc (v2)

> Branch: `feat/workflow-dispatch`
> Date: 2026-08-02
> Status: REVISED — addresses 5 reviewer reports (concurrency, graph-walk, backcompat, trigger, scope)
> Supersedes: v1 (same file, replaced in-place)

## Problem

The current engine assigns a monotonic status to each node
(pending→dispatched→{done,failed,skipped}). This is MORE restrictive than the
kanban cards it sits on top of (which can cycle backwards: done→todo,
running→blocked→ready). This mismatch is why loops don't work — a DONE node is
frozen forever, and back-edges (review FAIL → dev fix) have no effect.

## Design: stateless graph, stateful runs

**Borrow from LangGraph:** the graph (workflow template) is pure routing logic.
The instance (run) carries ALL mutable state. Each tick, the engine walks the
graph against the current state to determine what to do next — no node-status
field, no status transitions to fight.

---

## What we keep (preserved verbatim or near-verbatim)

The rewrite removes the **status model** only. All other engine logic is
orthogonal to status and must be ported. This is the complete inventory.

### Core modules

- `model.py` — Workflow/Node/Edge/Trigger dataclasses, `resolve_template`,
  `evaluate_condition` (upgraded, see §Condition Engine). The graph definition
  IS the stateless routing logic. **New:** `Edge.is_back_edge` computed at load
  time (see §Back-Edges).
- `store.py` — TemplateStore. **New:** load-time validation (reachability, exit-
  node existence, back-edge caps — see §Validation).
- `kanban_adapter.py` — board interface. Unchanged (reads are card truth).

### Dispatch logic (8 shapes — ALL preserved)

The tick's dispatch step must branch on node type + card mode exactly as the
current engine does. These ~850 lines are orthogonal to the status model.

| Shape | Current method | Dispatch mechanism | Completion path |
|-------|---------------|-------------------|-----------------|
| task (template mode) | `_dispatch_node` | single card, idempotent | sync card status from board |
| task (delegate mode) | `_dispatch_delegate_node` | meta-card, profile creates children | sync card status |
| task (chain mode) | `_dispatch_chain_node` | parent + N children via `--parent` | sync parent card status |
| foreach task | `_dispatch_foreach_node` | N cards, one per item | sync ALL cards (aggregate) |
| foreach command | `_run_foreach_command` | N subprocesses, inline | immediate (synchronous) |
| foreach subworkflow | `_dispatch_foreach_subworkflow` | N child instances | poll all children done |
| command | `_run_command_node` | single subprocess, inline | immediate (synchronous) |
| wait | `_check_wait_node` | poll condition each tick | condition passes |
| subworkflow | `_dispatch_subworkflow_node` | single child instance | poll child done |

All 9 shapes port with one change: idempotency keys become iteration-aware
(see §Idempotency). The dispatch topology (how cards are shaped, how children
link) is unchanged.

### Validation (preserved)

- **Output schema validation** — hard validation of card metadata against
  `node.output.schema`. Keep as a gate on "is this output usable downstream."
  Applies to task nodes, foreach task nodes, and subworkflow mapped outputs.
- **Input schema validation** — `node.input.schema` required-field check against
  context before dispatch (runtime.py:887-920). **Must be preserved** — dropping
  it is a correctness regression (nodes dispatch with blank bodies instead of
  failing fast).
- **Subworkflow output_mapping** — the 5-step child completion logic
  (read child outputs → build context → map via output_mapping → validate
  against schema → mark done/failed). Ported to read from the new state schema
  (see §Cross-Instance Reads).

### Triggers (preserved + guard fix)

- `card_completed`, `bead_ready`, `manual` — same detection logic.
- **Self-trigger guard** — REWRITTEN (see §Self-Trigger Guard Fix).
- Trigger-key dedup (`trigger_keys` table) — independent of node/card state,
  preserved unchanged.
- **Per-iteration re-trigger semantics:** each iteration of a node produces a
  distinct card and thus a distinct completion event. Any `card_completed`
  trigger matching that card shape fires once per iteration. Workflows needing
  once-per-logical-change firing must dedup in their own trigger condition
  (e.g. a merge-commit sha), not per-card.
- `bead_ready` trigger enrichment — add title/description/labels to context
  (latent gap, fix as part of this rewrite since dispatch needs it).

### Guards (preserved, restated for stateless model)

- **Deleted-board guard** (runtime.py:593-601): if `board_db_path(inst.board)`
  doesn't exist, mark instance complete. Unchanged — reads instance row, not
  node status.
- **Zombie guard** (runtime.py:584-591): if `completed_at` is set but instance
  is active, re-mark completed. Unchanged — reads `completed_at` column (kept as
  a DB column, not in the blob).
- **Stale-node filtering** (runtime.py:611-615, 344-356): if template is edited
  to remove a node, prune its entry from state. New mechanism: diff
  `state.nodes` keys against `wf.nodes` IDs each tick; drop orphan keys. Keep
  the `node_ids` snapshot column on `workflow_instances` as the anchor.

### Other preserved logic

- Engine event log (`engine_events` table) — unchanged.
- GC (trigger_keys, completed instances, watermarks) — preserved + blob trim
  (see §GC).
- Helpers: `_boards_to_check`, `_board_to_project_dir`,
  `_first_active_project_dir`, `_extract_metadata`, `_create_instance`,
  `_is_instance_active`, `start_manual` — ported verbatim.
- Concurrency locks: `threading.Lock` (in-process) + `fcntl.flock`
  (cross-process) — preserved.

---

## What we rip out

- `NodeStatus` enum (pending/dispatched/done/failed/skipped)
- `NodeState` dataclass with `status` field
- `node_states` table with status column
- All status-transition logic:
  - PHASE 1 completion marking (runtime.py:618-760)
  - PHASE 1b regression detection (runtime.py:762-783) — replaced by SYNC step
  - The monotonic dispatch guard `if ns.status != PENDING: continue`
- `NodeStatus` kept as a **deprecated alias shim** for one release cycle so test
  imports don't break at module load (3 test files import it).

---

## What we replace it with

### RunState (the "langgraph state")

```python
@dataclass
class RunState:
    """All mutable state for one workflow instance."""
    instance_id: str
    workflow_id: str
    board: str
    project_dir: str
    trigger_context: dict
    parent_instance_id: str | None
    created_at: int

    # Per-node execution state — keyed by node_id.
    # Shape varies by node type (see §Node State Shapes).
    nodes: dict[str, dict] = field(default_factory=dict)

    # Instance lifecycle (stays as DB columns, NOT in the blob)
    status: str = "active"  # active, completed, failed
    completed_at: int | None = None

    # Optimistic concurrency version (see §State Persistence)
    version: int = 0
```

**Important:** `status`, `completed_at`, and `version` are DB COLUMNS on
`workflow_instances`, not keys in the JSON blob. Only `nodes` and
`trigger_context` live in the blob. This keeps lifecycle queries (load active,
GC completed) as simple SQL without JSON parsing.

### Node state shapes (per node type)

```python
# task node (template/delegate/chain modes)
{
    "card_id": "abc123",
    "card_status": "done",       # synced from board each tick
    "output": {"verdict": "PASS", "merged_sha": "..."},
    "iteration": 0,              # bumped on back-edge reset
    "iterations": [],            # audit trail: [{card_id, card_status, output}, ...]
}

# command node (inline, synchronous)
{
    "output": {"exit_code": 0, "stdout": "..."},
    "done": True,                # set when command completes
}

# wait node (polls condition)
{
    "resolved": False,           # set True when condition passes
}

# subworkflow node (single child)
{
    "child_instance_id": "wf_...",
    "outputs": {},               # mapped from child via output_mapping
    "done": False,               # set True when child completes
}

# foreach task node (N cards)
{
    "cards": ["abc", "def", "ghi"],
    "card_statuses": ["done", "done", "running"],
    "results": [{...}, {...}],
    "iteration": 0,
    "iterations": [],
}

# foreach subworkflow node (N children)
{
    "child_instance_ids": ["wf_...", "wf_..."],
    "results": [{...}, {...}],
    "iteration": 0,
}
```

The `iterations[]` audit trail is capped at 10 entries (oldest dropped). The
`output` field always points to the current iteration's output. During a reset
gap (iteration bumped, new card not yet done), `output` holds the last-known-
good value — never wiped to empty.

### Derived node phase (replaces NodeStatus)

The graph walk derives a **phase** for each node each tick, purely from state.
This is NOT persisted — it's computed fresh every tick:

```python
def node_phase(node, node_state, ctx) -> str:
    """Derive a node's phase from its state. Never persisted.
    Returns: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
    """
    # command/wait: check explicit done flag
    if node_state.get("done"):
        return "done"
    if node.type in ("command", "wait"):
        return "done" if node_state.get("done") else "pending"

    # subworkflow: check child completion
    if node.type == "subworkflow" or (node.foreach and node.type == "subworkflow"):
        if node_state.get("done"):
            return "done"
        if node_state.get("child_instance_id") or node_state.get("child_instance_ids"):
            return "running"
        return "pending"

    # foreach task: check all cards done
    if node.foreach and node.type == "task":
        statuses = node_state.get("card_statuses", [])
        if statuses and all(s in ("done", "archived") for s in statuses):
            return "done"
        if node_state.get("cards"):
            return "running"
        return "pending"

    # task (single card): check card status
    card_status = node_state.get("card_status", "")
    if card_status in ("done", "archived"):
        return "done"
    if card_status == "blocked":
        return "running"  # blocked is a form of in-flight
    if card_status in ("todo", "ready", "running"):
        return "running"
    if node_state.get("card_id"):
        return "running"

    # No card yet — check if it should be skipped (dead branch)
    return "pending"
```

This replaces the monotonic NodeStatus with a derived value. A task node going
done→todo on the board naturally transitions from `done` back to `running` to
`pending` as the graph walk re-evaluates. No frozen states.

---

## The tick: three sequential passes

Each tick, for each active instance, the engine runs three passes. Each pass
completes fully before the next begins. **Decisions in pass 3 read committed
state from passes 1+2, never mid-walk mutations.**

### Pass 1: SYNC (read board truth into state)

```
For each node in the workflow template:
  1. If node is stale (not in template) → prune from state.nodes
  2. If task node with card_id → read card from board, update card_status
  3. If card is done/archived AND output not yet read → read metadata, validate
     against output.schema. If valid → store output in state. If invalid →
     mark node as failed (set output._validation_error).
  4. If subworkflow node with child_instance_id → check child status, read
     mapped outputs if child completed (see §Cross-Instance Reads)
  5. If foreach task → sync all card statuses, aggregate results when all done
  6. If foreach subworkflow → check all child statuses, aggregate when all done
```

No decisions, no dispatch. Just syncing board truth into state.

### Pass 2: RESET (handle back-edges)

```
Compute reset set from a SNAPSHOT of state (never mutate during computation):
  For each back-edge (from, to) where:
    - node_phase(from) == 'done'
    - evaluate(back_edge.condition, ctx) == True
    - node_phase(to) in ('done', 'failed')  ← only reset terminal nodes
  → add `to` to reset set

Apply resets:
  For each node in reset set:
    1. Move current {card_id, card_status, output} to iterations[] (audit trail, cap 10)
    2. Clear card_id, card_status
    3. Bump iteration += 1
    4. Keep output pointing at last-known-good value (don't wipe)
```

Computed first, applied second — never reset a node while evaluating it.

### Pass 3: ACTIVATE + DISPATCH (walk graph, create cards)

```
Rebuild ctx from post-reset state.
For each node in the workflow template:
  phase = node_phase(node, state.nodes[node_id], ctx)

  if phase in ('done', 'failed', 'skipped'):
    continue  # terminal, nothing to do

  if phase == 'running':
    continue  # card/child in flight, wait

  # phase == 'pending' — check if it should dispatch
  if not _activation_rule_satisfied(node, state, ctx):
    # Check if it should be SKIPPED (dead branch)
    if _all_incoming_terminal_and_none_fired(node, state, ctx):
      state.nodes[node_id]["skipped"] = True  # marks phase as 'skipped'
    continue

  # Input schema validation (fail fast)
  if node.input and node.input.schema:
    missing = _check_required_inputs(node, ctx)
    if missing:
      state.nodes[node_id]["failed"] = True
      state.nodes[node_id]["output"] = {"_validation_error": f"missing: {missing}"}
      continue

  # Dispatch by type (8 shapes — see §Dispatch Logic)
  _dispatch_by_type(node, state, ctx)
  # State is persisted AFTER each dispatch (see §State Persistence)
```

### Completion check (after pass 3)

```
exit_nodes = [n for n in wf.nodes if no outgoing edges]

# Completion fence: re-read board truth for EVERY exit node (not cached state).
# Must handle all node types, not just single-card task nodes.
for exit_node in exit_nodes:
  ns = state.nodes[exit_node.id]

  if exit_node.foreach and exit_node.type == "task":
    # FOREACH exit node: re-read ALL card statuses from board
    for card_id in ns.get("cards", []):
      card = get_card(board, card_id)  # FRESH read
      if not card or card.status not in ("done", "archived"):
        return  # don't complete — a foreach card regressed or not done

  elif exit_node.type == "subworkflow" or (exit_node.foreach and exit_node.type == "subworkflow"):
    # SUBWORKFLOW exit node: re-read child instance status from state DB
    for child_id in ([ns.get("child_instance_id")] if ns.get("child_instance_id")
                     else ns.get("child_instance_ids", [])):
      child_status = _read_instance_status(child_id)  # SELECT status, fresh
      if child_status != "completed":
        return  # don't complete — child not done yet

  elif ns.get("card_id"):
    # SINGLE-CARD task exit node: re-read the card from board
    card = get_card(board, ns["card_id"])  # FRESH read, not cached state
    if not card or card.status not in ("done", "archived"):
      return  # don't complete — card regressed or not done

  # command/wait exit nodes: synchronous, no board race — skip fence

# All exit nodes terminal?
for exit_node in exit_nodes:
  phase = node_phase(exit_node, state.nodes[exit_node.id], ctx)
  if phase not in ("done", "failed", "skipped"):
    return  # not ready

# Check reachability: every pending non-exit node must be reachable
# from a done node via active edges. Unreachable pending nodes are
# orphans (disconnected components) — ignore them (or they'd hang forever).

Instance completes.
```

**Terminal-for-exit = {done, failed, skipped}.** A skipped exit node (dead
branch from a conditional diamond) does NOT block completion. This preserves
the current SKIPPED semantics (runtime.py:977).

**Reachability:** disconnected components (orphan subgraphs) do not block
completion. Only exit nodes reachable from at least one dispatched/done node
are counted. This preserves `test_adv_graph_disconnected_node` behavior.

---

## Activation rule (edge semantics)

Direct port of runtime.py:796-863, restated for the stateless model:

```
A node N is dispatchable when, over its set of incoming edges:
  Let U = unconditional incoming edges (no condition)
  Let C = conditional incoming edges (has condition)

  U_sat = every e in U has source phase in {done, failed, skipped}
          (terminal — but for unconditional AND, all must be DONE specifically)
  CORRECTION: U_sat = every e in U has source phase == 'done'

  C_sat = some e in C has source phase == 'done'
          AND evaluate(e.condition, ctx) is True

  Dispatchable iff U_sat AND (C_sat OR C is empty)

  If U is empty and C is empty → entry node, always dispatchable
```

**Dead-branch skip:** if all incoming sources are terminal (done/failed/skipped)
but none activated the node (U_sat false, C_sat false), the node is SKIPPED:

```
_all_incoming_terminal_and_none_fired(node):
  for each incoming edge e:
    src_phase = node_phase(e.from_node, ...)
    if src_phase not in ('done', 'failed', 'skipped'):
      return False  # something still pending
  # All terminal but none fired → dead branch
  return True
```

This propagates skips downstream: a node whose only source is skipped becomes
all-terminal-none-fired → itself skipped.

---

## Back-edges

### Definition

A back-edge is an edge `(from, to)` such that `to` can already reach `from` in
the template graph (i.e., the edge closes a cycle).

### Detection (load time)

Tarjan's strongly-connected-components (SCC) algorithm on the template's edge
set. Every edge whose endpoints lie in the same SCC is a back-edge.

```python
# In Workflow.from_dict (or a post-load annotation step):
def _annotate_back_edges(workflow):
    sccs = tarjan_scc(workflow.nodes, workflow.edges)
    node_to_scc = {n.id: scc_id for scc_id, scc in enumerate(sccs) for n in scc}
    for edge in workflow.edges:
        edge.is_back_edge = node_to_scc.get(edge.from_node) == node_to_scc.get(edge.to_node)
```

Stored on the loaded `Workflow` object (computed once, not per tick). Templates
without cycles have zero back-edges — zero overhead.

### Walk behavior

When a back-edge `(from, to)` has:
- `node_phase(from) == 'done'`
- `evaluate(back_edge.condition, ctx) == True`

Then `to` is reset (pass 2): bump iteration, archive current state to
`iterations[]`, clear active card. The normal dispatch rule re-fires it next
tick with a fresh iteration-aware idempotency key.

Forward edges never reset.

---

## Validation (load time)

At template load (`store.py`), after parsing:

1. **Reachability:** every node must be reachable from at least one entry node
   (node with no incoming edges). Unreachable nodes = template error.
   Exception: `entry_nodes` declared explicitly on the workflow.

2. **Exit-node existence:** the graph must have ≥1 exit node (no outgoing
   edges) UNLESS the workflow declares an explicit `exit_condition`.

3. **Back-edge termination:** every back-edge must have either:
   - A condition clause matching `iteration` (regex: `\$\{.*iteration.*\}\s*[<>=]`)
   - OR an explicit `max_iterations` field on the edge
   Reject at load otherwise. Prevents infinite loops.

4. **No-underscore invariant:** workflow IDs must not contain `_` (the
   self-trigger guard parser depends on it). Reject at load.

These are HARD gates — invalid templates are rejected, not warned.

---

## Idempotency keys (iteration-aware)

### Grammar

```
wf:<instance_id>:<node_id>[:iter<N>][:<suffix>]
```

Where:
- `instance_id` = `wf_<ts>_<wf.id>_<uuid>` (underscores, not colons)
- `node_id` = the node ID from the template
- `iter<N>` = present only when iteration > 0 (iteration 0 omits the suffix
  for backwards compatibility with existing in-flight instances)
- `<suffix>` = foreach index (`:0`, `:1`), chain (`:chain:0`), subworkflow
  (`:sw:0`)

### Ordering rule

`iter` comes BEFORE item-specific suffixes:
```
wf:<inst>:<node>:iter2:0      # foreach item 0, iteration 2
wf:<inst>:<node>:iter2:chain:0  # chain child 0, iteration 2
wf:<inst>:<node>:iter2:sw:0    # subworkflow child 0, iteration 2
```

### Backwards compatibility

For iteration 0, the key is identical to the current format
(`wf:<inst>:<node>` with no `:iter0`). In-flight DAG instances survive
unchanged.

---

## Self-trigger guard fix

### Current bug

The guard (runtime.py:1783-1800) parses the idempotency key heuristically,
splitting on `_` and guessing which chunk is the workflow ID. Fails for:
- Short workflow IDs (≤3 chars) — UUID misidentified as workflow ID
- Future underscore-containing IDs — parser picks wrong chunk

### Fix: deterministic parse

Replace the heuristic with a grammar-based parse:

```python
def _extract_parent_workflow(idempotency_key: str) -> str | None:
    """Extract parent workflow ID from an engine-created card's idem key.

    Grammar: wf:<instance_id>:<node_id>[:iter<N>][:<suffix>]
    Where instance_id = wf_<ts>_<wf.id>_<uuid>  (underscores)
    """
    parts = idempotency_key.split(":")
    if len(parts) < 2 or not parts[1].startswith("wf_"):
        return None  # not an engine card

    instance_id = parts[1]
    inst_chunks = instance_id.split("_")  # ["wf", ts, wf.id..., uuid]

    if len(inst_chunks) < 4:  # wf + ts + at least 1 wf.id chunk + uuid
        return None

    ts = inst_chunks[1]
    uuid_ = inst_chunks[-1]
    # wf.id = everything between ts and uuid, rejoined with _
    parent_wf_id = "_".join(inst_chunks[2:-1])

    return parent_wf_id
```

This handles hyphenated IDs, short IDs, and the iteration suffix uniformly
because it's bounded by the known `wf_` prefix and trailing UUID, not by fuzzy
"looks like a word" guessing.

### Test requirement

Table-driven test covering all 6 key shapes:
```
wf:wf_123_dev-review-loop_abc12345:review         → dev-review-loop
wf:wf_123_dev-review-loop_abc12345:review:iter2   → dev-review-loop
wf:wf_123_dev-review-loop_abc12345:review:0       → dev-review-loop (foreach)
wf:wf_123_dev-review-loop_abc12345:review:chain:0 → dev-review-loop
wf:wf_123_dev-review-loop_abc12345:review:sw:0    → dev-review-loop
wf:wf_123_qa_x1y2z3:check                         → qa (short ID, no crash)
```

---

## State persistence (optimistic versioning)

### The problem

A single JSON blob read-modify-write is non-atomic. Two overlapping ticks can
clobber each other (tick A reads state₀, tick B reads state₀, A writes, B
writes over A → A's changes lost).

### Fix: optimistic concurrency

Add a `version INTEGER` column to `workflow_instances`:

```sql
ALTER TABLE workflow_instances ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
```

The SAVE becomes:

```sql
UPDATE workflow_instances
SET state = ?, version = version + 1
WHERE instance_id = ? AND version = ?   -- ? = version read at LOAD
```

If `cursor.rowcount == 0`, another tick won the race → discard this tick's
mutations. No data lost; at worst a redundant tick next cycle.

### Incremental persistence (not end-of-tick save)

State is persisted **after each dispatch**, not once at the end. This preserves
the current engine's behavior (each dispatch is individually durable via
`update_node_state` called immediately after card creation).

The tick has no single save point — mutations are flushed as they occur. On
crash recovery, a dispatched-but-card-missing node is retried and idempotency
dedup catches it.

### Dispatch sequence (crash-safe ordering)

Each dispatch follows this exact sequence, which makes the crash-safety
argument explicit:

1. **Compute idempotency key** from `instance_id + node_id + iteration`
   (plus foreach/chain/sw suffix if applicable).
2. **Dedup lookup** — `find_cards_by_idempotency_key(key)`. If a card exists,
   adopt it (set `card_id` in state), persist state, done.
3. **Create card** on the board (only if no existing card found).
4. **Set `card_id` and `card_status`** in state.
5. **Persist state immediately** (incremental save, version-bumped).

Crash at any point leaves a recoverable state:
- Crash before step 3: no card created, state unchanged → re-dispatch next tick.
- Crash after step 3, before step 5: orphan card exists with the idem key.
  Next tick: state has no `card_id` → re-dispatch → dedup lookup (step 2)
  finds the orphan card → adopts it. **No duplicate.**
- Crash after step 5: state and board are consistent.

This ordering (dedup-lookup → create → save-state) ensures a crash never
produces a duplicate card, because the idem key is deterministic and the
dedup lookup always runs before creation.

### Version bump on each incremental save

After each successful incremental SAVE, update the in-memory `state.version`
to the new DB value (`version + 1`) so the next incremental save in the same
tick passes its own guard. On `rowcount == 0` (lost the race), abort the tick
— already-committed saves from this tick remain durable, and idempotency-key
dedup prevents duplicate cards on re-dispatch next tick.

---

## Cross-instance reads (subworkflow completion)

### The problem

The current `_check_subworkflow_completion` reads child outputs via:
```sql
SELECT node_id, output FROM node_states WHERE instance_id = ? AND status = 'done'
```

After dropping `node_states`, this query hits a nonexistent table.

### Fix: read from child's state blob

```python
def _read_child_outputs(child_instance_id: str) -> dict:
    """Read a child instance's node outputs from its state blob."""
    conn = _connect(state_db_path)
    row = conn.execute(
        "SELECT state, status FROM workflow_instances WHERE instance_id = ?",
        (child_instance_id,)
    ).fetchone()
    conn.close()

    if not row or row["status"] != "completed":
        return {}  # child not done yet

    state = json.loads(row["state"])
    child_nodes = state.get("nodes", {})

    # Collect outputs from all child nodes
    outputs = {}
    for node_id, node_state in child_nodes.items():
        output = node_state.get("output", {})
        for k, v in output.items():
            outputs[f"nodes.{node_id}.output.{k}"] = v

    return outputs
```

The parent reads the child's `workflow_instances.state` JSON blob directly.
Coupled through the instance row, not a side table — simpler.

The 5-step child completion logic (read outputs → build context → map via
output_mapping → validate against schema → mark done/failed) is preserved,
ported to read from this function.

---

## Condition engine upgrade

### Grammar

```
condition := clause (AND clause)* (OR clause)*
clause    := var operator value
var       := ${path.to.value}
operator  := == | != | < | <= | > | >= | exists | is empty
value     := 'string' | number
```

- `AND` binds tighter than `OR` (standard convention)
- Left-to-right evaluation within same precedence
- No parentheses (keep it simple)
- Short-circuit: `A AND B` — if A is false, don't evaluate B

### Type coercion

When operator is `<`, `<=`, `>`, `>=`:
1. Attempt `float()` on both sides
2. If both succeed → numeric comparison
3. If either fails → fall back to string comparison
4. **Never stringify-then-compare numbers** (avoids "10" < "3" = True bug)

### New operators

Add `<`, `<=`, `>`, `>=` to the regex set. Current set (`==`, `!=`, `exists`,
`is empty`) is insufficient for iteration caps.

### Implementation

Split on ` OR ` → OR groups. Split each on ` AND ` → AND clauses. Evaluate each
clause with the existing regex approach (extended for numeric ops). Combine:
any OR group true → true; all AND clauses in a group true → group true.

---

## DB migration

### The problem

`ALTER TABLE + DROP TABLE node_states` with no backfill destroys active
instances. The cron is running — in-flight instances lose all node state.

### Migration procedure

1. **Stop the engine cron** before running migration.
2. **Backup the state DB** (`cp workflow-state.db workflow-state.db.bak`).
3. **Add columns:**
   ```sql
   ALTER TABLE workflow_instances ADD COLUMN state TEXT NOT NULL DEFAULT '{}';
   ALTER TABLE workflow_instances ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
   ```
4. **Backfill** (Python, not pure SQL — it's a JSON aggregation):
   ```python
   for inst in active_instances:
       node_rows = SELECT node_id, status, card_id, output FROM node_states WHERE instance_id = ?
       state_blob = {}
       for row in node_rows:
           state_blob[row.node_id] = {
               "card_id": row.card_id,
               "card_status": <lookup from board>,
               "output": json.loads(row.output),
               "iteration": 0,
               "_legacy_status": row.status,  # for debugging
           }
       UPDATE workflow_instances SET state = ? WHERE instance_id = ?
   ```
5. **Verify** — log count of migrated instances, spot-check a few.
6. **Drop** (only after verification):
   ```sql
   DROP TABLE node_states;
   ```
7. **Restart cron.**

### NodeStatus deprecation shim

Keep `NodeStatus` as a deprecated alias in `runtime.py` for one release cycle:

```python
# Deprecated — kept for backwards compat. Will remove in next release.
class NodeStatus:
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
```

This prevents 3 test modules from failing at import. Tests are migrated to the
new API incrementally.

---

## GC (blob trim)

The existing GC (trigger_keys, completed instances, watermarks) is preserved.
New: **blob trimming for active instances with many iterations.**

```python
def _trim_blob(state: dict, max_iterations: int = 10):
    """Trim iterations[] to max_iterations entries per node."""
    for node_id, node_state in state.get("nodes", {}).items():
        iterations = node_state.get("iterations", [])
        if len(iterations) > max_iterations:
            node_state["iterations"] = iterations[-max_iterations:]
```

Called once per tick during GC (pass 0). Resolves the audit-trail vs latest-only
contradiction: keep latest 10 iterations for audit, always keep current output.

For completed instances, GC deletes the entire row (blob and all) after 7 days
— same as current behavior.

---

## Revised scope estimate

| Component | v1 claim | Revised | Why |
|-----------|---------|---------|-----|
| model.py | +40 | ~60 | AND/OR + numeric + type coercion + terminality helper |
| runtime.py | ~800 net | ~1600-1900 net | 850 lines dispatch/validation/card-mode preserved + 300 lines new walk/sync/trim |
| main.py | +10 | +20 | cmd_list reads from blob, status display |
| Tests | ~500 | ~700-900 | 200 lines mechanical rewrite (57 node_states queries) + loop tests across variants |
| Migration | 0 | ~80 | Backfill script + NodeStatus shim |
| **Total** | **~1300** | **~2500-3000** | ~2× the v1 estimate |

The runtime GROWS, not shrinks. ~850 lines of dispatch topology is preserved
verbatim; ~300 lines of new walk/sync/trim logic is additive. The 2055-line
engine becomes ~1700-1900 lines + ~900 lines of tests.

---

## Test strategy

### 1. Backwards compat (existing tests must pass)

- **57 node_states queries** → rewrite to use a `state_snapshot()` helper that
  reads from the new blob. Mechanical, ~200 lines across 10 files.
- **5 NodeStatus assertions** → rewrite to use `node_phase()` derived value.
- **NodeStatus imports** → kept working via deprecation shim.
- **Completion semantics** → 3 tests change outcome (skipped-exit-node). Rewrite
  assertions to match new (correct) behavior. Document each change.

### 2. New loop tests

- build→review→FAIL→build(iter1)→review→PASS (basic loop)
- Iteration cap: iter≥3 → escalate edge fires, retry edge stops
- Foreach inside a loop: foreach task re-dispatches with iter suffix
- Back-edge without cap → rejected at load time

### 3. Condition engine tests

- `AND`/`OR` precedence
- Numeric comparison (`< 3`, `>= 3`) with int and string values
- Type coercion edge cases

### 4. Self-trigger guard tests

- Table-driven test covering all 6 key shapes (see §Self-Trigger Guard Fix)
- Short workflow IDs, hyphenated IDs, iteration suffixes

### 5. Concurrency tests

- Optimistic versioning: two ticks write, one wins, one retries
- Incremental persistence: crash between dispatch and save

### 6. Migration tests

- Backfill from node_states → state blob (round-trip)
- In-flight DAG instance survives migration unchanged

---

## What we are NOT doing

- Not building a visual dashboard. CLI + event log stays.
- Not changing the template JSON format. Existing templates load unchanged.
- Not adding cross-workflow loop iteration caps (within-workflow only; cross-
  workflow caps live in the handoff medium — bead metadata or shared key).
- Not adding a `reset_node` API. Resets happen automatically via graph walk.

---

## Risks

1. **State blob size** — capped at 10 iterations per node (~10KB worst case
   for 20-node graph). Acceptable. GC trims active instances; deletes completed.
2. **Graph walk cost** — 20 nodes × 1-min ticks = negligible. Tarjan SCC runs
   once at load, not per tick.
3. **Optimistic versioning retries** — under normal single-writer operation
   (fcntl lock), version conflicts are rare. The version guard is defense-in-
   depth against out-of-band writers (CLI commands, manual edits).
4. **Migration window** — cron must be stopped during cutover. If an instance
   is mid-flight, its cards continue running on the board; the engine just
   doesn't tick until migration completes. No work is lost.
5. **Cross-workflow loops uncapped** — the QA↔bug↔fix chain has no native
   iteration cap. If needed, it must live in bead metadata. Documented, not
   solved here.
