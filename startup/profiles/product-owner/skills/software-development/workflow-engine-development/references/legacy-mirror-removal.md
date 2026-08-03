# Legacy Mirror Removal — _mirror_legacy_to_blob → _update_blob_after_dispatch

> T10 complete (bead hermes-teams-4qke). 21/21 green.
> Committed on `feat/workflow-dispatch`.

## What changed

The old `_mirror_legacy_to_blob` re-read the entire `node_states` row from
the DB after every dispatch to mirror card_id, card_status, output, done
flags into the blob. This created a triple-representation hazard: the DB
table, in-memory `inst.node_states`, and the state blob all held node state,
and keeping them consistent was fragile.

The new `_update_blob_after_dispatch(inst, node, ns, ok, msg)` writes blob
fields directly based on the dispatch return values + board lookups. The
dispatch methods still call `update_node_state` for backwards compat, but
the blob is authoritative.

## Three pitfalls discovered during the mirror removal

### Pitfall 1 — wait node `ok=False` means "still waiting", not "failed"

The initial implementation had `if not ok: ns["failed"] = True`. But for
wait nodes, `ok=False` means the condition hasn't resolved yet — the node
should stay pending, not be marked permanently failed. Fix: handle wait
nodes BEFORE the `not ok` check. Wait nodes only set `done: True` when
`ok=True` (condition resolved).

### Pitfall 2 — transient dispatch failures must stay pending

When `create_card` returns `(False, "database is locked")`, the node should
retry on the next tick. The initial `ns["failed"] = True` on `not ok`
permanently killed the node — `test_card_creation_fails` (retry-after-failure
test) broke. Fix: transient failures (card creation errors) return early
WITHOUT setting `failed`. Only validation failures (schema mismatch,
missing inputs) set `failed: True`, and those happen in the activation pass
before `_update_blob_after_dispatch` is called.

### Pitfall 3 — command/wait output must be read from node_states

Command nodes run synchronously and write their output to `node_states` via
`update_node_state`. The blob update must read that output back:
`legacy = self._load_one_node_state(...)` → `ns["output"] = dict(output)`.
Without this, downstream nodes referencing `${nodes.cmd.output.*}` get empty
strings.

## Pattern — dispatch result types and their blob semantics

| Node type | `ok` | `msg` | Blob action |
|-----------|------|-------|-------------|
| task (single card) | True | card_id | `ns["card_id"]=msg`, `ns["card_status"]=board.status` |
| task (single card) | False | error msg | no-op (stay pending, retry) |
| foreach task | True | card count | read `_foreach_cards` from legacy, set `ns["cards"]`+`ns["card_statuses"]` |
| foreach subworkflow | True | child count | read `_foreach_instances` from legacy, set `ns["child_instance_ids"]` |
| single subworkflow | True | child_id | read `_child_instance` from legacy, set `ns["child_instance_id"]` |
| command | True | stdout | `ns["done"]=True`, read output from legacy |
| wait | True | resolved | `ns["done"]=True`, read output from legacy |
| wait | False | unresolved | NO-OP (stay pending) |

## General lesson — `ok=False` has three meanings

In the dispatch architecture, `ok=False` from a dispatch method can mean:
1. **Transient failure** (card creation error) → stay pending, retry next tick
2. **Still waiting** (wait node condition unresolved) → stay pending, no flag set
3. **Permanent failure** (validation) → set `failed: True`

The blob update function must distinguish all three. The initial implementation
conflated 1 and 3, breaking retry-after-failure. The fix: `_update_blob_after_dispatch`
handles wait nodes first (case 2), then returns early on `not ok` (case 1),
and never sets `failed: True` itself (case 3 is handled in the activation pass).
