# Review — Trigger & Cross-Workflow Handoff Correctness Under the Stateless Model

> Scope: triggers and cross-workflow handoffs in `DESIGN-stateless-graph.md`
> Author: trigger/handoff review pass
> Date: 2026-08-02
> Status: concerns for design approval

## TL;DR

The design says "Triggers — same detection" and otherwise ignores them. Under
the stateless model that is **mostly fine for the trigger-matching layer** but
**silently breaks the self-trigger guard** and leaves **two operational gaps**
(bead-context enrichment, cross-workflow loop semantics). The iteration-aware
key change is the single highest-risk item because it touches the load-bearing
guard without the guard being mentioned anywhere in the rewrite.

| # | Concern | Verdict |
|---|---------|---------|
| 1 | Self-trigger guard vs new `:iter{N}` keys | **NO** — survives by luck, not by design |
| 2 | Trigger context unaffected by state model? | **PARTIAL** — matching is fine; dedup + sync assumptions need a line |
| 3 | Cross-workflow loops (QA fail → bug → fix → re-QA) | **NO** — the design's loop solution is within-workflow only |
| 4 | Hyphenated workflow-id parser bug | **NO** — still present, unrelated to the state change |
| 5 | `bead_ready` trigger context enrichment | **NO** — gap, but currently latent (no template uses it) |

---

## Concern 1 — Self-trigger guard vs the new iteration-aware keys  · **NO**

### What the design does

`DESIGN:100-109` introduces iteration-aware idempotency keys:

```python
iteration = state.nodes[node_id].get("iteration", 0)
idem_key = f"wf:{instance_id}:{node_id}:iter{iteration}"
```

`DESIGN:214` ("Not changing triggers…") implies `_check_triggers()` is carried
verbatim. That carries the self-trigger guard (`runtime.py:1783-1800`) verbatim
too.

### Why it's a gap (verified empirically)

The guard reconstructs the triggering card's parent workflow by splitting the
idempotency key on `:` and extracting `idem_parts[1]` as the **instance part**
(`runtime.py:1784-1786`). The instance part is `wf_<ts>_<wf.id>_<uuid>`. The
guard then walks `_`-chunks to guess the parent workflow id.

I ran the actual parse logic against every key shape in the engine
(task / foreach / chain / subworkflow / new-iter). Results:

```
CURRENT simple task node          CROSS  -> 'dev-review-loop'       ✓ correct
CURRENT cross dev-review→qa-loop  CROSS  -> 'dev-review-loop'       ✓ correct
NEW iter suffix (iter0)           CROSS  -> 'dev-review-loop'       ✓ survives
NEW iter suffix (iter2)           CROSS  -> 'dev-review-loop'       ✓ survives
FOREACH key (4-part)              BLOCK-same                         ✓ correct
SUBWORKFLOW key (5-part)          CROSS  -> 'dev-pipeline'          ✓ correct
CHAIN child key (5-part)          CROSS  -> 'dev-pipeline'          ✓ correct
HYPHEN multi-segment wf id        CROSS  -> 'tech-lead-build'       ✓ survives here
SHORT wf id (≤3 chars)            CROSS  -> 'abc12345'  ←  WRONG (uuid picked)
```

**The iteration suffix is appended *after* the node id (`…:{node}:iter{N}`),
so `idem_parts[1]` (the instance part) is unchanged.** The guard survives the
new format *for the common case*. But that is an accident of placement, not a
design decision, and it leaves two real failures on the table:

**(a) The index-suffix interaction is unspecified.** The engine already uses
`:{idx}` (foreach), `:chain:{idx}` (chain), `:sw:{idx}` (subworkflow). The
design never says where `:iter{N}` goes relative to those. If a foreach item
re-dispatches at iteration 2, is it `wf:i:n:idx:iter2` or `wf:i:n:iter2:idx`?
Either ordering keeps `idem_parts[1]` intact, **but** the guard's "first chunk
longer than 3 chars, non-digit" heuristic now has more chunks to misclassify.
The prior scope-review (`REVIEW-stateless-graph-scope.md:276-280`) flagged this
as a coordination risk; it remains unresolved.

**(b) The short-workflow-id false-classification is real and pre-existing.**
A workflow id ≤3 chars (e.g. a hypothetical `qa` workflow) causes the guard to
pick the 8-char uuid hex as the "parent workflow id" (`'abc12345'` above).
`store.load('abc12345')` returns None, `parent_wf` is falsy, the edge-check at
line 1799 is skipped, and the trigger **fires when it should be blocked**. This
is an infinite-loop vector. Not introduced by the stateless change, but the
rewrite is the moment to fix it.

### Concrete fix

1. **Stop parsing the key heuristically.** The guard is reverse-engineering
   information the engine already has. Replace the substring/chunk walk with a
   deterministic parse keyed on the *documented* key grammar:

   ```python
   # idem key grammar: wf:<instance_id>:<node_id>[:iter<N>][:<suffix>]
   # where instance_id = wf_<ts>_<wf.id>_<uuid>  (underscores, not colons)
   parts = idempotency_key.split(":")
   if len(parts) < 2 or not parts[1].startswith("wf_"):
       return ALLOW  # not an engine card
   instance_id = parts[1]
   inst_chunks = instance_id.split("_")          # ["wf", ts, wf.id..., uuid]
   # wf.id may contain hyphens but NOT underscores; ts and uuid are the
   #   first and last non-"wf" chunks
   ts    = inst_chunks[1]
   uuid_ = inst_chunks[-1]
   parent_wf_id = "_".join(inst_chunks[2:-1])    # rejoins hyphenated ids intact
   ```

   This handles hyphenated ids (`tech-lead-build`), short ids, and the new
   iteration suffix uniformly — because the instance segment is bounded by the
   known `wf_` prefix and the trailing uuid, not by a fuzzy "looks like a word"
   guess.

2. **Enforce the instance-id invariant at creation.** Add an assertion in
   `_create_instance` that `wf.id` contains no `_` (the grammar depends on it).
   Reject underscore-containing workflow ids at template load. This makes the
   parser above provably correct instead of probabilistically correct.

3. **Add a guard test that enumerates every key shape.** The engine has ≥5 key
   grammars today and is adding a 6th. A table-driven test
   (`test_self_trigger_guard.py`) asserting block/allow for each shape —
   including the new `:iter{N}` and the hyphenated-id case — is the only way
   this stops regressing silently. Reference the empirical table above as the
   fixture.

---

## Concern 2 — Trigger context under the state model  · **PARTIAL**

### What the design does

Nothing explicit. `RunState.trigger_context: dict` (`DESIGN:59`) is carried
forward as an opaque blob. `_start_from_trigger()` (`runtime.py:1977-1991`) is
in the "kept implicitly" bucket of the scope review.

### What's actually fine

Trigger *matching* (`_matches_trigger`, `runtime.py:1908-1933`) reads only card
fields (assignee, status, title, metadata). None of that depends on node status
or the `node_states` table. The stateless rewrite does not touch it. ✅

### What needs one line in the design

Two implicit assumptions deserve to be made explicit, because the rewrite
removes the scaffolding that currently makes them true:

**(a) Trigger dedup is independent of node state.** `_check_triggers` records
`trig:{wf}:{card}` in `trigger_keys` *before* creating the instance
(`runtime.py:1819-1824`), and `_check_bead_trigger` does the same
(`runtime.py:1886-1890`). This must survive the rewrite — it is the only thing
preventing a re-trigger storm on every tick. The design's "keep idempotency"
(`DESIGN:31`) covers *card* dedup, not *trigger* dedup. Say so.

**(b) The trigger fires once per card, not once per iteration.** Under the new
model a single node can dispatch multiple cards (iter0, iter1, iter2…). Each
completed iteration card is a *new* completion event flowing through
`find_recent_completions`. The guard blocks same-workflow self-triggers
(concern 1), so within-workflow iteration cards will not re-trigger their own
workflow. **But** they *will* re-trigger any *other* `card_completed` workflow
whose condition matches — once per iteration, because each iteration card has a
distinct `id` and thus a distinct `trig:{wf}:{card}` key.

   Example: `dev-review-loop`'s `review` node at iteration 2 completes with
   `verdict=PASS`. The `qa-loop` workflow triggers on
   `assignee=verifier, metadata.verdict=PASS`. Today (DAG, one card) this fires
   once. Under loops, it fires **once per iteration that PASSes** — potentially
   multiple QA cards for one logical change. The design does not acknowledge
   this. It is arguably *correct* (each iteration is a real merge candidate),
   but it is a behavior change the operator should opt into, not discover in
   production.

### Concrete fix

- Add to `DESIGN` "What we keep → Triggers": *"Trigger-key dedup
  (`trigger_keys` table) is independent of node/card state and is preserved
  unchanged."*
- Add a note under the loop section: *"Each iteration of a node produces a
  distinct card and thus a distinct completion event. Any `card_completed`
  trigger matching that node's card shape will fire once per iteration. Workflows
  that must fire once-per-logical-change need a dedup key in their own trigger
  condition (e.g. a merge-commit sha), not per-card."*

---

## Concern 3 — Cross-workflow loops (the real QA→bug→fix→QA chain)  · **NO**

### What the design does

`DESIGN:143-166` solves the **within-workflow** loop: `build → review → FAIL →
build(iter1)`. Iteration counter lives in `state.nodes[node_id].iteration`,
capped by a back-edge condition. Clean.

### Why it's a gap

The production loop the old cron implemented (`workflow-engine.py:499-560`,
the QA phase) is **cross-workflow**: a verifier card completes → triggers
`qa-loop` → QA finds a bug → files a bead → bead goes ready → dispatches a fix
→ fix merges → re-triggers QA. This loop crosses **four workflow instances**
and a `bd` bead boundary. None of the iteration machinery the design adds
helps here, because:

1. **No shared iteration counter.** `state.nodes[x].iteration` is scoped to one
   `instance_id`. A cross-workflow loop has no single `RunState`. Each hop is a
   fresh instance with `iteration=0`.
2. **No back-edge.** There is no edge from `qa-loop.qa_retest` back to
   `dev-pipeline.build` — they are different templates. The graph-walk reset
   logic (`DESIGN:93c`) cannot fire across templates.
3. **The handoff is carried by `bd` bead state + card metadata, not by edges.**
   The "loop" is really: QA completes with `bug_bead_ids` in metadata → someone
   (PO, or a `bead_ready` trigger) turns that into a new dev task → dev
   completes → verifier completes → QA re-triggers. The cycle is in the
   *system*, not in any one graph.

This is not necessarily a defect — the design explicitly scopes itself to
within-workflow loops and the cross-workflow chain already works today via
triggers. But the design *presents* loops as solved, and an implementer reading
"the dev↔verifier loop is just graph traversal" (`DESIGN:145`) could reasonably
believe the production QA loop is covered. It is not.

### Is cross-workflow better or worse than within-workflow?

**Worse for correctness, better for decoupling.**

- *Worse:* no native iteration cap (concern: infinite QA↔bug ping-pong),
  no single trace id, debugging requires joining `engine_events` across
  instances + `bd` bead history + board cards (the approach-B analysis,
  `analysis/approach-b-distributed-workflows.md:141-148`, calls this out).
- *Better:* each workflow stays simple and independently deployable; a bug in
  the fix loop cannot corrupt the QA workflow's state; the bead acts as a
  durable, human-visible handoff token.

### Concrete fix

- **State the boundary explicitly.** Add to `DESIGN` "What about loops?":
  *"Within-workflow loops (back-edges in one template) are handled by the
  iteration counter. Cross-workflow loops (a completion in workflow A causing a
  future trigger in workflow B) are NOT modeled by the graph; they emerge from
  trigger composition. They have no shared iteration cap and no cross-instance
  trace. If a cap is needed across workflows, it must live in the handoff
  medium (bead metadata or a shared key)."*
- **For the QA↔bug loop specifically:** decide whether iteration capping
  belongs in (a) the bead (a `review_count` field the verifier increments and
  the dispatch trigger checks), or (b) a future "workflow-of-workflows" meta
  template. Option (a) is cheaper and matches how the old cron implicitly
  handled it. Do not leave it undefined — an uncapped cross-workflow loop is an
  infinite-trigger risk.
- **Add a cross-workflow integration test** to the test strategy
  (`DESIGN:188-198`): two templates where B triggers on A's completion, A loops
  internally, and assert how many times B fires. (Answer per concern 2: once
  per matching iteration. The test should *lock that answer in*.)

---

## Concern 4 — Hyphenated workflow-id parser bug  · **NO**

### Status

**Still present, independent of the stateless change.** Confirmed by reading
`runtime.py:1788-1796` and by the empirical run in Concern 1.

### Does the new key format interact with it?

**No — but only because the iteration suffix is appended after the node id.**
The bug is in the `_`-chunk heuristic for extracting the parent workflow id
from the *instance* segment, and the instance segment is untouched by
`:iter{N}`. My empirical test shows `tech-lead-build` is *correctly* extracted
in the simple case — but that is because the heuristic's "first chunk >3 chars,
non-digit" happens to land on `tech-lead-build` as a whole (hyphens are not
`_`, so the chunk survives intact). The bug the approach-B analysis describes
(`analysis/approach-b-distributed-workflows.md:116-117`) would manifest for
**underscore-containing** workflow ids, which the current template set does not
use but nothing prevents.

The real failure mode for hyphenated ids is subtler and still live: if a
workflow id is a *substring* of another (e.g. `qa` vs `qa-loop`), the
`f"_{wf.id}_" in instance_part` same-workflow check at line 1788 can
false-positive or false-negative. The `SHORT wf id` row in my empirical table
shows the downstream consequence (uuid misidentified as workflow id).

### Concrete fix

Same fix as Concern 1, item 1: replace the heuristic parse with the
deterministic `instance_id.split("_")` parse bounded by the known `wf_` prefix
and trailing uuid. That fix closes both the iteration-suffix risk and the
hyphen/short-id misclassification in one change. There is no reason to fix them
separately.

---

## Concern 5 — `bead_ready` trigger context enrichment  · **NO**

### What the design does

Nothing. `_check_bead_trigger` (`runtime.py:1897`) builds:

```python
trigger_ctx = {"bead_id": bead_id, "trigger_source": "bead_ready"}
```

Only `bead_id`. No title, no description, no labels.

### Is it a gap?

**Yes, but latent.** I searched every template: **zero templates currently use
`source: "bead_ready"`**. The only `bead_ready` references are in `README.md`
documentation and the approach-B analysis sketches. The live dispatch path is
`manual` (`builder-queue-builds`) and `card_completed` (`builder-promote`,
`qa-loop`). So today this gap affects nothing in production.

It becomes real the moment someone writes a `bead_ready`-triggered dispatch
template (which is the documented intended use — `README.md:389-395`). A
dispatch node body wanting `${trigger.title}` or `${trigger.description}` gets
empty string (the template resolver strips unresolved vars,
`model.py:252`). The old cron (`workflow-engine.py:313,323`) hand-builds the
bead list with titles directly in Python, sidestepping this. The engine's
template path has no such escape hatch.

### Concrete fix

- In `_check_bead_trigger`, fetch bead detail (the function already runs `bd
  ready --json`; add a `bd show <id> --json` per matching bead, or richer:
  have `bd ready --json` include title/description) and enrich context:

  ```python
  trigger_ctx = {
      "bead_id": bead_id,
      "trigger_source": "bead_ready",
      "title": bead.get("title", ""),
      "description": detail.get("description", ""),
      "labels": bead.get("labels", []),
  }
  ```

- Because this is latent, it does not block the stateless rewrite. But it
  *should* be filed as a follow-up so the first real `bead_ready` consumer
  doesn't silently emit empty-body cards. Recommend a `kanban_create` child
  task rather than scope-creeping the rewrite.

---

## Summary of recommended actions

| Priority | Action | Blocks rewrite? |
|----------|--------|-----------------|
| **P0** | Replace heuristic self-trigger parse with deterministic `split("_")` parse (fixes concerns 1+4) | Yes — do before merge |
| **P0** | Add table-driven guard test covering all 6 key shapes incl. `:iter{N}` and hyphenated ids | Yes |
| **P1** | Add two lines to DESIGN: trigger-key dedup preserved; per-iteration re-trigger semantics | No — spec clarity |
| **P1** | Add DESIGN note scoping loops to within-workflow; cross-workflow caps live in the handoff medium | No — spec clarity |
| **P2** | Enrich `bead_ready` trigger context with title/description/labels | No — latent gap, file follow-up |
| **P2** | Enforce no-underscore invariant on workflow ids at template load | No — hardens the P0 fix |

The design is sound on the state-model side. The trigger/handoff side is
under-specified rather than wrong — except for the self-trigger guard, which
needs the deterministic-parse fix before the iteration keys land.
