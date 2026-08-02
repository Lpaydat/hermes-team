# Scope Completeness Review: Stateless Graph Engine Design

> **Reviewer mandate:** Has the design accounted for ALL the logic in the current
> 2055-line `runtime.py`, or is the ~1300 line estimate naive?
>
> **Bottom line up front:** The design's *core idea* (stateless graph, stateful
> run, status-free node model) is sound and correct. But the estimate is
> **naive**. The doc systematically under-counts the logic that must survive the
> rewrite because it frames the problem as "rip out NodeStatus + node_states
> table" when the real surface area is 8 dispatch methods, 3 card modes, input
> validation, 4 node types, foreach fan-out, subworkflow composition, trigger
> suppression, and several subtle guards. A realistic estimate is **~2200–2600
> net lines for runtime + model**, not ~800. Details below.

---

## Method-by-method inventory of the current engine

To judge scope completeness I enumerated every method the rewrite must account
for. This is the ground truth the design doc is bidding against.

| # | Method | Lines | What it does | Design mentions it? |
|---|--------|------:|--------------|:---:|
| 1 | `tick` | 523–575 | Lock, GC, check instances, check triggers | ✅ (steps 1–6) |
| 2 | `_check_instance` | 577–1031 | Zombie guard, deleted-board guard, stale-node filter, PHASE 1 completion (5 branches), PHASE 1b regression, PHASE 2 dispatch (7 branches), completion check, event logging | ❌ collapsed to "walk graph" |
| 3 | `_dispatch_node` | 1033–1093 | Card dispatch + 3-way `card_mode` branch | ❌ (card_mode absent) |
| 4 | `_dispatch_delegate_node` | 1294–1336 | delegate mode meta-card | ❌ |
| 5 | `_dispatch_chain_node` | 1338–1417 | chain mode parent+children | ❌ |
| 6 | `_dispatch_foreach_node` | 1513–1605 | foreach → N task cards | ❌ (mentioned generically) |
| 7 | `_dispatch_foreach_subworkflow` | 1419–1511 | foreach → N child instances | ❌ |
| 8 | `_run_foreach_command` | 1095–1169 | foreach → N shell commands | ❌ |
| 9 | `_run_command_node` | 1171–1256 | single shell command node | ❌ |
| 10 | `_check_wait_node` | 1260–1292 | poll condition node | ❌ |
| 11 | `_dispatch_subworkflow_node` | 1607–1657 | spawn single child instance | ❌ |
| 12 | `_check_subworkflow_completion` | 1659–1741 | poll child + output_mapping + validation | ❌ |
| 13 | `_check_triggers` | 1757–1836 | card_completed trigger + self-trigger suppression | ✅ ("same detection") |
| 14 | `_check_bead_trigger` | 1840–1906 | bead_ready trigger | ✅ ("same detection") |
| 15 | `_matches_trigger` | 1908–1933 | trigger condition matching | ✅ |
| 16 | `_start_from_trigger` | 1977–1991 | build trigger context + create instance | ✅ |
| 17 | helpers `_boards_to_check`, `_board_to_project_dir`, `_first_active_project_dir`, `_extract_metadata`, `_create_instance`, `_is_instance_active`, `start_manual` | 1743–2055 | board/project mapping, metadata parse, instance factory, manual start | ✅ (kept implicitly) |

**That is 8 dispatch-family methods (rows 3–12) the design's single "DISPATCH"
step must absorb.** The design's risk section says "graph walk cost scales with
graph size" but never enumerates that the walk itself must dispatch task /
command / wait / subworkflow / foreach(task) / foreach(command) /
foreach(subworkflow) / delegate / chain. This is the single biggest blind spot.

---

## Concern-by-concern verdict

### 1. Dispatch modes (template / delegate / chain) — **NO**

The design does not mention `card_mode` anywhere. Yet `model.py:43` defines it
and `runtime.py:1057-1061` branches on it:

```python
if node.card_mode == "delegate":
    return self._dispatch_delegate_node(...)
elif node.card_mode == "chain":
    return self._dispatch_chain_node(...)
else:  # "template"
    # single card
```

- **delegate** (`runtime.py:1294-1336`): creates a meta-card; the profile
  creates child cards itself (the dev-dispatch pattern). ~43 lines.
- **chain** (`runtime.py:1338-1417`): parses a JSON list of child specs from
  the body, creates a parent + N children linked via `--parent`, idempotency
  per child index. ~80 lines.

These are not "status logic" — they are **card-creation topology** and must be
preserved verbatim. The stateless model changes *when* dispatch fires (graph
walk) but not *how* cards are shaped. The design's tick step 4 ("DISPATCH — for
nodes that should run, create cards") silently assumes one shape per node. It
needs a `node.card_mode` branch.

**Impact on estimate:** +120 lines of dispatch logic the design didn't count.

### 2. Input schema validation — **NO**

`runtime.py:887-920` validates `node.input.schema` (the `required` list)
against context before dispatch, resolving each required input through
`node.input.sources` mappings. On failure it marks the node FAILED with
`_validation_error` so downstream never advances. ~34 lines.

The design's "What we keep" list explicitly keeps **output** schema validation
("hard validation of card metadata against `node.output.schema`") but says
nothing about **input** validation. The tick description has no input-validation
step. This will silently regress: a node whose required input isn't resolvable
will dispatch a card with a blank/unresolved body instead of failing fast.

**Impact on estimate:** +40 lines, and it's a correctness regression, not just
a line-count miss.

### 3. Stale node filtering (template edited after instance creation) — **NO**

Two places:
- `runtime.py:611-615` (in `_check_instance`): filters node_states whose node_id
  is no longer in the template's node set.
- `runtime.py:344-356` (in `load_active_instances`): filters against the
  `node_ids` snapshot recorded at creation time.

The design's `RunState.nodes` dict is keyed by node_id and persisted as a JSON
blob. **If a node is removed from the template, its entry sits in the blob
forever** — the design has no mechanism to prune it. Worse, the blob is the
*only* representation of state (no separate node_states table to JOIN against),
so there's no cheap "which of these keys are still valid" query; the engine must
diff blob keys against `wf.nodes` every tick.

The `node_ids` snapshot column on `workflow_instances` (model.py migration at
`runtime.py:168-169`) is also unmentioned. The design's schema change (lines
124–139) drops `node_states` but doesn't say whether `node_ids` survives. It
should — it's the stale-detection anchor.

**Impact on estimate:** +30 lines for a `sync_state_to_template(wf, state)`
step the design omits from the tick.

### 4. Zombie / deleted-board guards — **PARTIAL / contradictory**

The design says (line 44): "rip out zombie guards" but (line 45):
"deleted-board guard stays but checks state, not status." These two statements
are in tension and under-specified.

Current zombie guard (`runtime.py:584-591`): if `completed_at` is set but the
instance is somehow active again, refuse to dispatch and re-mark completed. The
detection key is **`completed_at` on the instance row**, which the design keeps
(`RunState.completed_at`). So "checks state, not status" is achievable — but the
design doesn't actually describe the mechanism, and it's unclear whether "rip
out zombie guards" means *this* guard or some other guard.

Deleted-board guard (`runtime.py:593-601`): if `board_db_path(inst.board)`
doesn't exist, mark complete to stop zombie cycling. This is independent of
node status and must clearly survive. The design keeps it, correctly, but
buries the decision in a parenthetical.

**What's missing:** a clear statement of *which* guards are ripped vs. kept, and
the detection condition for each in the stateless model. As written, a
developer could reasonably interpret "rip out zombie guards" as removing the
`completed_at` re-mark, which would reintroduce the phantom-work bug.

**Impact on estimate:** neutral on lines, but a spec-ambiguity risk that needs
resolution before implementation.

### 5. GC and the state blob — **PARTIAL**

Current GC (`runtime.py:454-512`) deletes four things: `trigger_keys`,
`workflow_instances` (old completed), their `node_states` rows, and
`trigger_watermark`. It returns per-table counts.

The design drops `node_states`, so GC no longer deletes node rows — but **the
state blob grows with iterations**. The design's own Risk #1 acknowledges this
("cap stored iterations at 10, keep only latest output per node") but:
- There is no GC step in the tick (steps 1–6 omit cleanup entirely).
- The cap-and-trim logic is not in the estimate (+0 lines).
- "keep only latest output per node" is **incompatible with audit trail**
  ("The old card stays in state for audit trail," line 109) — you can't keep
  the audit trail AND prune to latest-only. Pick one; the doc holds both.

Bigger point: blob GC is now an in-process JSON rewrite (load blob → trim → save)
per aging instance, not a bulk `DELETE`. For an instance with 50 iterations
across 8 nodes that's a ~10 KB blob parse+rewrite every tick on every aging
instance. The design's claim that cleanup is "a few DELETEs" is no longer true
once node state lives in a blob.

**Impact on estimate:** +40 lines for blob trimming + a perf caveat the design
should flag.

### 6. The 8 dispatch methods vs. one "DISPATCH" step — **NO**

Counted above. The design's tick step 4 is one bullet. The current engine has:

| Node type | Dispatch method | Completion path |
|-----------|-----------------|-----------------|
| task (template) | `_dispatch_node` | PHASE 1 single-card |
| task (delegate) | `_dispatch_delegate_node` | PHASE 1 single-card |
| task (chain) | `_dispatch_chain_node` | PHASE 1 single-card (parent) |
| foreach task | `_dispatch_foreach_node` | PHASE 1 `_foreach_cards` branch |
| foreach command | `_run_foreach_command` | inline DONE |
| foreach subworkflow | `_dispatch_foreach_subworkflow` | PHASE 1 `_foreach_instances` branch |
| command | `_run_command_node` | inline DONE |
| wait | `_check_wait_node` | inline DONE |
| subworkflow | `_dispatch_subworkflow_node` + `_check_subworkflow_completion` | PHASE 1 `_child_instance` branch |

That's **9 distinct node-dispatch shapes** and **4 distinct completion paths**
(subworkflow-child, foreach-cards, foreach-instances, single-card). The
stateless graph walk must still branch on all of these at dispatch time and at
"sync card truth" time. The design's `(graph, state) → actions` purity claim
hides ~450 lines of type-specific logic.

The `RunState.nodes` comment (line 65-67) *hints* at this ("For task nodes:
{card_id, ...}; For command nodes: {output, exit_code}; For subworkflow: {...}")
but never says the walk must dispatch differently per type. A reader could
implement the whole walk as "if no card, create a card" and break command,
wait, foreach, and subworkflow nodes.

**Impact on estimate:** this is the core of the underestimate. ~450 lines of
dispatch + completion logic must be ported essentially as-is (they're
orthogonal to the status model). The design counted them as "rewrite ~1000 →
~800 net"; the honest accounting is "rewrite ~1000 → ~1100 net" because the new
state-sync + iteration-reset machinery is additive on top of preserved dispatch.

### 7. Edge routing semantics — **PARTIAL / underspecified**

The design says "Are its dependencies met (edges satisfied)?" (tick step 3b).
The current edge logic (`runtime.py:796-863`) is the single most intricate
non-status code in the engine, and the stateless model doesn't simplify it:

- **Unconditional edges → AND semantics**: ALL sources must be done (convergence).
- **Conditional edges → OR semantics**: ANY source done + condition passes.
- **SKIPPED/FAILED sources are ignored** (terminal-but-didn't-run).
- If all sources are terminal but none activated → the node is **SKIPPED**
  (`runtime.py:853-860`), and SKIPPED propagates downstream.

The stateless model has no `SKIPPED` state (it's a NodeStatus being ripped).
So how does the new walk decide a node is "not going to run" vs. "waiting"?
The design's completion model (line 113) says "all EXIT nodes reached done" —
but a node whose only incoming edges are all conditional-and-false will never be
done and never be dispatched. Under the current engine it's SKIPPED so the
workflow can complete. Under the proposed model it's... stuck? The completion
check would hang.

This is a **genuine semantic gap**, not just an under-count. The stateless walk
needs an equivalent of SKIP propagation (e.g., "a node is terminal if it's done
OR all its incoming edges are terminal and none fired"). The design doesn't
specify this.

**Impact on estimate:** +60 lines for a stateless terminality/SKIP rule, plus a
spec gap to close.

### 8. Trigger self-trigger suppression — **NO**

`runtime.py:1783-1800` is ~18 lines of subtle logic: if a completed card's
idempotency_key starts with `wf:`, parse the parent instance+workflow out of it
and (a) block same-workflow self-triggers, (b) block cross-workflow triggers if
the parent uses explicit edges. This prevents engine-created cards from
re-triggering workflows and creating duplicate work.

The design says triggers are kept with "same detection" — but this suppression
logic is not "detection," it's a guard layered on top of matching. If it's
dropped, every card the engine creates (task, foreach, delegate, chain) will
re-trigger any matching `card_completed` workflow. That's a correctness
regression that could cause infinite trigger loops.

**Impact on estimate:** neutral on lines (kept implicitly), but it's an
unflagged regression risk.

### 9. Subworkflow output mapping & validation — **NO**

`_check_subworkflow_completion` (`runtime.py:1659-1741`) does, on child
completion:
1. Read child's done-node outputs.
2. Build child context.
3. Map via `node.output_mapping` (or flatten if absent).
4. **Validate mapped output against `node.output.schema`** → FAILED if invalid.
5. Mark parent node DONE/FAILED.

The design keeps output validation generally but never shows how a subworkflow
node's mapped output flows through the same gate. In the stateless model the
"sync child truth" step needs to reproduce all five sub-steps. The `RunState`
sketch doesn't model `output_mapping` at all.

**Impact on estimate:** +40 lines, and it's part of the subworkflow path the
design's walk must carry.

### 10. Idempotency-key namespaces — **PARTIAL**

The design introduces iteration-aware keys: `wf:{instance}:{node}:iter{N}`
(line 106). Good. But the current engine already uses *multiple* key shapes:
- task: `wf:{instance}:{node}`
- foreach item: `wf:{instance}:{node}:{idx}`
- chain child: `wf:{instance}:{node}:chain:{idx}`
- foreach subworkflow: `wf:{instance}:{node}:sw:{idx}`
- trigger: `trig:{wf}:{card}` and `trig:{wf}:bead:{id}`

The self-trigger suppression (concern #8) *parses* these shapes. Adding `:iter{N}`
changes the parse. The design doesn't reconcile the iteration suffix with the
existing index suffixes (does a foreach item at iteration 2 become
`wf:i:n:idx:iter2` or `wf:i:n:iter2:idx`?). This is a concrete schema decision
that affects the trigger parser.

**Impact on estimate:** small on lines, but a coordination risk across dispatch
+ trigger + foreach.

---

## Is the ~1300 line estimate realistic?

**No.** Here's the line-level reconciliation.

### What the design claims (table, lines 202-208)

| Component | Claimed |
|-----------|--------:|
| model.py (condition engine) | +40 |
| runtime.py (rewrite ~1000 → ~800 net) | ~800 net |
| main.py | +10 |
| tests | ~500 |
| **Total** | **~1300** |

### What the honest accounting looks like

**model.py — +40 claimed → +50 realistic.**
The `AND`/`OR` + numeric `<`/`>=` upgrade is real (+40), but you also need a
SKIP-equivalent / terminality predicate for the walk (concern #7) which is most
naturally a model-level helper (+10).

**runtime.py — ~800 net claimed → ~1600–1900 net realistic.** Breakdown:

| Logic block | Current LOC | Preserved? | Est. net |
|-------------|------------:|:----------:|---------:|
| StateDB → blob refactor | ~410 | rewrite | ~250 (simpler, no joins) |
| tick + locks + GC | ~90 | rewrite | ~120 (add blob trim) |
| `_check_instance` orchestration (sans PHASE 1 status) | ~180 | rewrite | ~140 |
| **Dispatch methods (8 shapes)** | ~450 | **port verbatim** | ~450 |
| **card_mode branch (template/delegate/chain)** | ~120 | **port verbatim** | ~120 |
| **Completion paths (single, foreach-cards, foreach-instances, child)** | ~120 | **port + restate** | ~130 |
| Edge routing + SKIP propagation | ~70 | port + add stateless terminality | ~130 |
| **Input schema validation** | ~34 | **port** | ~34 |
| Stale-node sync to template | ~20 | new | ~30 |
| Trigger system (5 methods) | ~150 | port | ~150 |
| Helpers (board/project/instance/start_manual) | ~110 | port | ~110 |
| Event logging | ~20 | port | ~20 |
| **Subtotal runtime** | | | **~1684** |

The design's "~800 net" assumes the only thing changing is the status model and
the DB schema. In reality ~840 lines of dispatch/validation/card-mode logic are
**orthogonal to the status model and must be ported near-verbatim**; they don't
shrink because the graph is stateless. The new machinery (state sync, iteration
reset, stateless terminality, blob trim) is ~+300 additive. Net: the runtime
*grows*, not shrinks.

**main.py — +10 claimed → +20 realistic.** Reading from the blob changes
`cmd_list` and the status display; minor but not zero.

**tests — ~500 claimed → ~700–900 realistic.** The design's test plan (keep DAG
tests, add loop tests, add regression tests) is sound, but preserving external
behavior across 8 dispatch shapes + 4 completion paths while rewriting internals
means the internal-assertion rewrite is larger than "rewrite assertions." Adding
loop tests across command/wait/subworkflow/foreach variants (not just task) is
where the real line count hides.

### Revised total

| Component | Revised |
|-----------|--------:|
| model.py | ~50 |
| runtime.py | ~1600–1900 |
| main.py | ~20 |
| tests | ~700–900 |
| **Total** | **~2400–2900** (vs ~1300 claimed — roughly **2×**) |

This is still a worthwhile rewrite — the stateless model genuinely fixes loops
and eliminates the status-fighting bug class. But it is **not** a simplification
that nets out at 1300 lines. It's a re-architecture that preserves ~850 lines of
dispatch topology, adds ~300 lines of new walk/sync machinery, and keeps all the
trigger/validation/GC surface.

---

## Spec gaps to close before implementation

These are decisions the design defers or contradicts; each can block or misdirect
implementation:

1. **card_mode (template/delegate/chain)** — must be explicitly preserved in the
   walk's dispatch step. (Concern #1)
2. **Input schema validation** — add a tick step or fold into dispatch. (Concern #2)
3. **Stale-node pruning in the blob** — define when/how blob keys are diffed
   against the current template. (Concern #3)
4. **Zombie vs. deleted-board guards** — list each guard and its stateless
   detection condition explicitly. (Concern #4)
5. **GC of the blob** — tick step 0 must include blob trim; resolve the
   audit-trail vs. latest-only contradiction. (Concern #5)
6. **SKIP propagation / stateless terminality** — a node with all conditional
   edges false must be considered terminal or the workflow hangs. (Concern #7)
7. **Self-trigger suppression** — must survive the rewrite; not "same detection."
   (Concern #8)
8. **Subworkflow output_mapping + validation** — the walk's child-sync step must
   reproduce all 5 sub-steps. (Concern #9)
9. **Idempotency key namespace** — reconcile `:iter{N}` with existing `:idx`,
   `:chain:idx`, `:sw:idx` suffixes; update the trigger parser. (Concern #10)

---

## Verdict

- **Core design: sound.** Stateless graph + stateful run is the right call for
  loops. Ripping NodeStatus is correct.
- **Scope estimate: naive by ~2×.** The design treats this as a status-model
  rewrite (~800 net) when ~850 lines of dispatch/card-mode/validation topology
  must be ported verbatim and ~300 lines of new walk/sync/trim logic is additive.
- **7 of 10 concerns are outright misses** (card_mode, input validation, stale
  nodes, the 8 dispatch shapes, self-trigger suppression, subworkflow mapping,
  GC-of-blob); 2 are contradictory (zombie guards, audit-vs-trim); 1 is
  under-specified (edge routing / SKIP).
- **Recommendation:** approve the *direction*, send the doc back for a scope
  revision that (a) enumerates the 8 dispatch shapes + 4 completion paths as
  explicit preservation items, (b) adds input validation + stale-node sync +
  blob-trim to the tick, (c) resolves the 9 spec gaps, and (d) re-estimates to
  ~2400–2900 total. The 2055-line current engine is being rewritten *and
  extended*, not compressed.
