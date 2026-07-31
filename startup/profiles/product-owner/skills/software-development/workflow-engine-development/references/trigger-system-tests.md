# Trigger-System Tests

12 adversarial tests targeting the engine's **trigger subsystem** — the path
that detects completed kanban cards and starts workflow instances in response.
This is distinct from the other adversarial rounds:

- **graph-pathology** attacks the *shape* of the workflow graph.
- **data-corruption** attacks the *content* of individual fields.
- **state-lifecycle** attacks the state persistence layer *one operation at a
  time* (single-threaded disagreement).
- **concurrency** attacks what happens when control flows *overlap in time*.
- **trigger-system** (this file) attacks the **card-completion →
  workflow-start coupling**: how completed cards are discovered, matched
  against trigger conditions, and turned into instances.

The core surface is `runtime._check_triggers` / `_matches_trigger` /
`_start_from_trigger`, `kanban_adapter.find_recent_completions`, and
`StateDB._trigger_key_exists` / `_record_trigger_key`. These tests found **6
real bugs** and documented several more as weaknesses.

## The bug taxonomy (trigger-specific)

| Failure mode | Bug | Where it lives in this engine |
|---|---|---|
| **Trigger storm data loss** | 100 matching cards, only 20 ever fetched | `find_recent_completions`: hardcoded `LIMIT 20` in SQL — 80% of completions silently dropped under load |
| **Trigger-everything bomb** | empty `condition: {}` matches ALL completed cards on ALL boards | `_matches_trigger`: empty dict → `for` loop body never runs → falls through to `return True`. A misconfigured template is a DoS. |
| **Cross-board contamination** | trigger fires for a card on an unrelated board | `_boards_to_check`: returns ALL dirs under `KANBAN_HOME`; no per-workflow board scoping |
| **Flat metadata lookup** | `metadata.a.b.c` matches a flat key `'a.b.c'`, never a nested dict | `_matches_trigger`: `field = key.split('.', 1)[1]` → `meta.get(field)` is flat, no nested traversal |
| **NULL completed_at invisible** | `status='done'` + matching metadata but `completed_at IS NULL` → never triggers | `find_recent_completions`: `WHERE completed_at > ?` — SQL `NULL > N` is NULL (falsy), so the card is silently skipped |
| **Runaway self-trigger** | engine-created card (`wf:` idempotency key) re-triggers the workflow | `_check_triggers`: no filter on `idempotency_key LIKE 'wf:%'` — the engine's own completed node cards match its own trigger condition |
| **Scalar-only equality** | `metadata.verdict: 'PASS'` does not match card verdict `['PASS','FAIL']` | `_matches_trigger`: `meta.get('verdict') != expected` is exact-scalar only; no `'in'`/membership semantics |
| **Uncaught table-missing crash** | corrupted/dropped `trigger_keys` table crashes `tick()` | `_record_trigger_key`: no `try/except` (unlike `_trigger_key_exists` which catches `OperationalError`) — instance is created, then the key write raises, propagating out |
| **Dead `status` filter** | `condition: {status: 'todo'}` can never fire | `find_recent_completions` SQL is `WHERE status='done'`; the Python-side status filter is dead code for non-`done` values |

Generalize the trigger-system audit: for every step of the
discover → match → start pipeline, ask "what can make a matching card be
missed (false negative) or a non-matching card be started (false positive)?"
The discover step is bounded by a SQL `LIMIT` and a `NULL`-sensitive
timestamp predicate; the match step falls through to True on empty input and
only does flat/scalar comparison; the start step has no origin-board or
engine-origin filter and an unguarded DB write.

## The 12 tests

### test_adv_trigger_storm_100_cards → BUG (intentional failing assertion)

100 matching completed cards in one tick. `find_recent_completions` has
`LIMIT 20`, so only 20 are ever fetched — the adapter drops 80% of
completions *before* the trigger matcher even runs. The test asserts the
**correct** behavior (100 starts) so it FAILS loudly, documenting the
data-loss gap. Fix: paginate the query, or raise/remove the LIMIT and rely on
the `trigger_keys` dedup to bound work.

### test_adv_trigger_empty_condition_matches_all → BUG (documented, passing)

`condition: {}` (empty dict). `_matches_trigger` iterates
`condition.items()`; an empty dict means the loop body never runs, so it
falls through to `return True` for EVERY completed card. Three cards with
wildly different assignees/metadata all trigger. A misconfigured template is
a trigger-everything DoS. Fix: reject empty conditions at template load, or
require at least one key.

### test_adv_trigger_cross_board → BUG (documented, passing)

A card completing on board B triggers a workflow that "belongs" to board A.
`_boards_to_check()` returns every directory under `KANBAN_HOME`; there is no
notion of a workflow being scoped to one board/project. The started instance
is even created on the wrong board. Fix: scope each workflow template to a
board (or board allow-list) in the template, and filter `_boards_to_check`
to only those.

### test_adv_trigger_self_trigger_engine_card → BUG (documented, passing)

A workflow whose node assigns to `verifier` with verdict `PASS` — matching
its own trigger condition. After the engine creates and completes the node
card (idempotency key `wf:...`), that card matches the trigger and starts a
NEW instance. `_check_triggers` does NOT filter cards by the `wf:` idempotency
prefix. The per-card dedup (`trig:{wf}:{card}`) blocks the *same* card twice
but a node card CAN trigger on the next tick → runaway loop. Fix: skip any
card whose `idempotency_key` starts with `wf:` in `_check_triggers`.

### test_adv_trigger_card_completed_at_null → BUG (documented, passing)

A card with `status='done'` + matching metadata but `completed_at IS NULL`.
`find_recent_completions` SQL is `WHERE completed_at > ?`. In SQL,
`NULL > N` evaluates to NULL (falsy), so the card is **invisible** to
triggers. Fix: use `WHERE (completed_at > ? OR completed_at IS NULL)` for
done cards, or guarantee `completed_at` is never NULL at completion time.

### test_adv_trigger_dotted_metadata_key → BUG (documented, passing)

Two sub-cases:
- Card metadata `{"a": {"b": {"c": "deep"}}}` (nested dict) against condition
  `metadata.a.b.c: "deep"` → **does NOT match**. `_matches_trigger` does
  `field = key.split('.', 1)[1]` (→ `"a.b.c"`) then `meta.get(field)` — a flat
  lookup. No nested traversal.
- Card metadata `{"a.b.c": "deep"}` (flat key with dots in its name) against
  the same condition → **DOES match** — surprising and likely unintended.

Fix: split the full dotted path and walk the nested dict; reject keys with
dots in their literal name at template validation.

### test_adv_trigger_metadata_list_value → BUG (documented, passing)

Card verdict is `['PASS', 'FAIL']` (a list); condition expects `'PASS'`.
`meta.get('verdict') != expected` → `['PASS','FAIL'] != 'PASS'` → True →
returns False → no trigger. A card that *semantically* contains `'PASS'`
silently fails because the matcher only supports exact scalar equality. Fix:
add membership semantics (`expected in value` when value is a list), or
document the scalar-only contract loudly.

### test_adv_trigger_keys_table_corrupted → BUG (documented, passing)

Drop the `trigger_keys` table, then tick. `_record_trigger_key` has **no
`try/except`** (unlike `_trigger_key_exists`, which catches
`OperationalError`). The `OperationalError` propagates out of
`_check_triggers` and crashes `tick()` — AFTER the instance was already
created. Next tick re-triggers → unbounded growth. Fix: wrap
`_record_trigger_key` in `try/except sqlite3.OperationalError` mirroring
`_trigger_key_exists`.

### test_adv_trigger_missing_metadata_path → OK (passing)

Condition references `metadata.nonesuch`; card has no such field.
`meta.get('nonesuch')` → `None != 'value'` → returns False → no trigger.
Safe. Kept as a regression guard.

### test_adv_trigger_duplicate_conditions_two_workflows → OK (passing)

Two workflows with the SAME trigger condition both fire for one card. Dedup
key is per-workflow (`trig:{wf.id}:{card.id}`), so one completed card starts
TWO instances. This is arguably intended composition, but a config error
(two identical triggers) silently doubles work. Documents the behavior.

### test_adv_trigger_dedup_hides_concurrent_cards → OK (passing)

Two cards completing at the SAME second both trigger. Dedup is card-scoped
(`trig:{wf}:{card.id}`), not timestamp-scoped, so both fire. Kept as a
regression guard — if someone "optimizes" the dedup to be timestamp-based,
this catches it.

### test_adv_trigger_status_filter_redundant → OK (passing)

`condition: {status: 'todo'}` can NEVER fire because `find_recent_completions`
SQL is `WHERE status='done'`. The Python-side status filter is dead code for
non-`done` values — a silent dead trigger. Documents the behavior.

## Runner wiring

These tests are registered via a dedicated `run_trigger_storm_tests()` helper
(mirroring the `run_data_corruption_tests()` pattern), NOT added to the main
`tests = [...]` list. The runner calls it after `run_data_corruption_tests()`
and folds the (passed, failed, count) into the totals. Keep this pattern for
new trigger-system batches so the main list stays readable.

## Pitfalls specific to trigger-system testing

- **The `LIMIT 20` is the first thing to probe.** It's not in the engine's
  Python — it's a hardcoded SQL clause in the adapter. A storm test (100+
  matching cards) is the only way to surface it; single-card tests will
  always pass. Always include a storm-scale test in this category.
- **Use a fresh `FakeWorld` when re-testing the same trigger after a tick.**
  The `trigger_keys` table records dedup state that survives across ticks
  within one `FakeWorld`. To test "does the SAME card/condition trigger
  again under variant Y," spin up a second `FakeWorld` rather than relying
  on the first tick's dedup state.
- **Insert NULL `completed_at` via raw SQL, not `make_fake_card`.** The test
  helper defaults `completed_at` to `now`; to probe the NULL path you must
  bypass the helper and `INSERT` the row directly with an explicit `NULL`.
- **For cross-board tests, create the second board under the same patched
  `KANBAN_HOME`** via `make_fake_board(world.tmpdir, "other-board")`. The
  engine's `_boards_to_check()` walks `KANBAN_HOME`, so the second board is
  automatically discovered — that's the bug surface.
- **Self-trigger tests need three ticks, not two.** Tick 1: external card
  triggers → instance starts. Tick 2: node dispatches (creates `wf:` card).
  Then you manually complete the `wf:` card. Tick 3: the engine's OWN card
  matches the trigger → new instance. Skipping tick 2 leaves the node card
  in `todo`, which doesn't match a `status:'done'` trigger.
- **Reuse the existing `FakeWorld` and `make_fake_card` from `test_engine.py`.**
  Do not reinvent them — the runner imports the module, so your tests must
  use the same fixture names. (An earlier iteration built a standalone
  `FakeWorld` in a separate file; that was merged into the shared fixture
  when appended.)
