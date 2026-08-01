# Iteration-Key ↔ Self-Trigger Guard Interaction

> Distilled from a trigger/handoff review (2026-08-02) of the proposed stateless-graph redesign (`DESIGN-stateless-graph.md`). The redesign introduces iteration-aware idempotency keys (`wf:{instance}:{node}:iter{N}`). This doc analyzes how those keys interact with the load-bearing self-trigger guard (`runtime.py` ~L1783–1800) and what breaks.

## The guard's parse logic (current)

When a completing card's idempotency key starts with `wf:`, the guard extracts the **instance segment** as `key.split(":")[1]` — which is the full `instance_id` (`wf_<ts>_<wf.id>_<uuid>`). It then:

1. **Same-workflow block:** `if f"_{wf.id}_" in instance_part: continue`
2. **Cross-workflow heuristic:** split `instance_part` on `_`, walk chunks, pick the first that is `not in ("wf","")`, `not chunk.isdigit()`, and `len(chunk) > 3` → treat as parent workflow id → load it → if it has explicit `edges`, block.

## Key grammar inventory (all 6 shapes)

| Shape | Format | Where |
|---|---|---|
| task node | `wf:{instance}:{node}` | runtime.py:1045 |
| foreach item | `wf:{instance}:{node}:{idx}` | runtime.py:1558 |
| chain child | `wf:{instance}:{node}:chain:{idx}` | runtime.py:1385 |
| subworkflow item | `wf:{instance}:{node}:sw:{idx}` | runtime.py:1477 |
| trigger dedup | `trig:{wf.id}:{card}` | runtime.py:1802 |
| **NEW iteration** | `wf:{instance}:{node}:iter{N}` | DESIGN:106 |

The iteration suffix is appended **after the node id**. This means `key.split(":")[1]` (the instance segment) is **unchanged** by `:iter{N}`.

## Empirical parse result (reproduced in isolation)

Running the actual guard logic against every shape + edge cases:

```
CURRENT simple task node          CROSS  -> 'dev-review-loop'       OK
CURRENT cross dev-review→qa-loop  CROSS  -> 'dev-review-loop'       OK
NEW iter suffix (iter0/iter2)     CROSS  -> 'dev-review-loop'       survives
FOREACH key (4-part)              BLOCK-same                          OK
SUBWORKFLOW key (5-part)          CROSS  -> 'dev-pipeline'          OK
CHAIN child key (5-part)          CROSS  -> 'dev-pipeline'          OK
HYPHEN multi-segment wf id        CROSS  -> 'tech-lead-build'       survives (hyphens ≠ underscores)
SHORT wf id (≤3 chars)            CROSS  -> 'abc12345'   ←  WRONG (uuid picked as wf id)
```

**Verdict:** the iteration keys survive the guard *for the common case* — but by **accident of placement**, not by design. Two real failures remain.

## Failure A — index-suffix ordering is unspecified

The redesign never says where `:iter{N}` goes relative to existing suffixes. A foreach item re-dispatching at iteration 2 could be `wf:i:n:idx:iter2` or `wf:i:n:iter2:idx`. Either keeps the instance segment intact, but the heuristic's "first chunk >3 chars, non-digit" now has more chunks to misclassify. This is a coordination risk across dispatch + trigger + foreach that must be pinned down before implementation.

## Failure B — short-workflow-id misclassification (infinite-loop vector)

A workflow id ≤3 chars (e.g. a hypothetical `qa`) causes the heuristic to skip it (fails `len > 3`) and pick the **8-char uuid hex** as the parent workflow id. `store.load('<uuid>')` returns None → `parent_wf` is falsy → the edge-check is skipped → the trigger **fires when it should be blocked**. Not introduced by the redesign, but the redesign is the moment to fix it.

## Recommended fix — deterministic parse (closes A + B)

Stop reverse-engineering information the engine already owns. The instance_id has a known grammar: `wf_<ts>_<wf.id>_<uuid>`, where `wf.id` may contain hyphens but **not underscores** (enforce this invariant at template load — reject `_` in workflow ids).

```python
parts = idempotency_key.split(":")
if len(parts) < 2 or not parts[1].startswith("wf_"):
    return ALLOW  # not an engine card
instance_id = parts[1]
chunks = instance_id.split("_")     # ["wf", ts, <wf.id parts...>, uuid]
ts   = chunks[1]
uuid = chunks[-1]
parent_wf_id = "_".join(chunks[2:-1])  # rejoins hyphenated ids intact
```

This handles hyphenated ids, short ids, and the iteration suffix uniformly — because the instance segment is bounded by the known `wf_` prefix and trailing uuid, not by a fuzzy "looks like a word" guess. Pair with an assertion in `_create_instance` that `wf.id` has no `_`.

## Per-iteration re-trigger semantics (behavior change)

Under the redesign, a looping node dispatches multiple cards (iter0, iter1, …). Each completed iteration card is a **distinct completion event** with a distinct card id → distinct `trig:{wf}:{card}` dedup key. Consequences:

- **Same-workflow:** blocked by the guard (concern above). Safe.
- **Cross-workflow:** any OTHER `card_completed` workflow matching that node's card shape fires **once per iteration that matches**. Example: `dev-review-loop`'s `review` node at iteration 2 completes `verdict=PASS` → `qa-loop` triggers. Today (DAG, one card) this fires once. Under loops, it fires once *per PASSing iteration* — potentially multiple QA cards for one logical change.

This is arguably correct (each iteration is a real merge candidate) but is a behavior change the operator should opt into, not discover in production. Workflows that must fire once-per-logical-change need a dedup key in their own trigger condition (e.g. a merge-commit sha), not per-card.

## Cross-workflow loop boundary

The redesign's loop solution (iteration counter in `state.nodes[node_id].iteration`, back-edge conditions) is **strictly within-workflow** — it requires a single `RunState`. The production QA→bug→fix→QA loop crosses **four workflow instances** plus a `bd` bead boundary:

```
verifier PASS → qa-loop instance → QA FAIL (files bug bead)
  → bead ready → dev-fix instance → dev done → verifier instance
  → verifier PASS → qa-loop instance (again)
```

No single `RunState` spans this. No back-edge exists across templates. The iteration cap machinery does not apply. If a cap is needed across workflows, it must live in the **handoff medium** (bead metadata: a `review_count` field the verifier increments and the dispatch trigger checks), not in any one graph. An uncapped cross-workflow loop is an infinite-trigger risk.

## How to reproduce this analysis for any key-grammar change

1. Inventory every key shape (search `idem_key\s*=` and `f"wf:` in runtime.py).
2. Copy the guard's parse logic verbatim into a standalone Python snippet.
3. Build a table: one row per key shape × edge case (hyphenated id, short id, each suffix).
4. Run it. Any row where the extracted parent_wf_id is wrong (None when it should resolve, or a uuid/non-wf-id string) is a false-allow or false-block vector.
5. If the guard survives only because of incidental placement, flag it — it will break when placement changes.

See `scripts/probe-trigger-guard.py` for the existing two-case probe; extend it with an iteration-key case.
