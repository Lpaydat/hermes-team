# Trigger Composition Semantics — cross-workflow card handoffs

> Empirically verified 2026-08-02 against the real engine (runtime.py, kanban_adapter.py, test_composition.py harness). Full approach comparison (A/B/C): `startup/scripts/workflow_engine/docs/approach-c-analysis.md`.

## 1. The self-trigger guard (runtime.py `_check_triggers`, ~L1783)

When a completing card has an idempotency key starting with `wf:` (i.e. ANY card created by an engine task node), three checks gate every `card_completed` trigger:

1. **Same-workflow self-trigger → always blocked.** If `_{wf.id}_` appears in the instance part of the key.
2. **Cross-workflow + parent has explicit `edges` → blocked.** The parent workflow id is extracted from the instance key (`wf_<ts>_<wfid>_<uuid>`), the parent's CURRENT template is loaded, and if it declares `edges: [...]` the trigger is skipped ("parent handles routing internally").
3. **Cross-workflow + parent has NO explicit edges → allowed.** The backward-compat path for trigger-based composition (single-node / depends_on-only workflows).

**Probe result (`scripts/probe-trigger-guard.py`, two cases, real engine):**
- construction.json WITH explicit edges: verifier node card completes `verdict=PASS` → **qa-loop trigger does NOT fire** (0 instances).
- same construction WITHOUT edges (implicit `depends_on`): **trigger fires** (1 instance).

**Implications for template design:**
- A goal workflow that uses edges internally CANNOT hand off via a `card_completed` trigger on any of its own node cards. Its terminal card is unreachable by triggers.
- Handoff paths that work today: (a) trigger on AGENT-created cards (kanban_chains children, verifier fix cards — no `wf:` key → guard skipped); (b) subworkflow nodes (parent blocks on child instance — not trigger-based, guard-free); (c) `bead_ready` triggers (bead-mediated, guard-free).
- Planned but **NOT implemented**: `idempotency_key_template` (per-node custom card key). MIGRATION-PLAN.md and skill references treat it as load-bearing, but `model.py`/`runtime.py` have 0 hits — classic dead-field trap (see `references/dead-field-grep-technique.md`). With it, a terminal "export port" node could carry a non-`wf:` key (e.g. `qa-merge-<bead>`) and escape the guard while intermediate nodes keep `wf:` keys (nothing else triggerable).
- The guard couples templates at runtime: adding an `edges` block to workflow X silently disables every trigger that fired on X's cards. Trigger behavior depends on OTHER templates' current edge declarations — a trigger-level test is the only guard.

## 2. No loops — monotonic node states

> **Changing the state model?** The `node_states` table, `NodeStatus` enum, and `{DONE,FAILED,SKIPPED}` terminal set are load-bearing across the 317-test suite in non-obvious ways (57 raw-SQL sites, 3 import-line failures, completion-semantics tests that assert deadlock). See `references/state-model-migration-constraints.md` before redesigning completion, dropping the table, or removing the enum.
>
> **A stateless-graph redesign is under review** that would remove `NodeStatus` and add iteration-aware keys (`wf:{instance}:{node}:iter{N}`). Two interactions to check before it lands: (a) the new keys survive the self-trigger guard above *only by accident of placement* — a short workflow id (≤3 chars) still misclassifies the uuid as the parent workflow id (infinite-loop vector); (b) each iteration card is a distinct completion event, so any *cross-workflow* `card_completed` trigger matching that node fires **once per iteration**, not once per logical change. See `references/iteration-key-guard-interaction.md` for the full empirical analysis + deterministic-parse fix.

- Node status is one-way: pending → dispatched → done/failed/skipped. PHASE 2 only dispatches PENDING nodes; DONE nodes never re-run; cycles are not expressible.
- `dev-review-loop.json` is the canonical unroll: FAIL→fix→re-review unrolled exactly once; a second FAIL is terminal (workflow completes with a FAILED node).
- Iteration (dev↔verifier, debugger converge) MUST live inside an opaque node card (profile runs kanban_chains/loop_engine; parent card goes blocked→done; engine never peers inside — "static-dynamic coexistence") or in trigger-spawned fresh instances (agent-created cards only, given the guard).
- `foreach` is parallel fan-out, not iteration.

## 3. Trigger footguns (all live in code)

| Footgun | Where | Consequence |
|---|---|---|
| Dedup is per (trigger workflow, card): `trig:{wf.id}:{card.id}` | runtime.py `_check_triggers` | One card CAN trigger several workflows, but two verifier PASS cards on the same merge → TWO QA instances. Old cron deduped `qa-merge-<sha>`; engine does not. Tighten conditions (e.g. `metadata.merged: true`). |
| `TRIGGER_LOOKBACK_SECS = 3600` + `LIMIT 200` in `find_recent_completions` | runtime.py / kanban_adapter.py | Engine outage >1h silently loses triggers. No catch-up. |
| Trigger key recorded before instance creation (separate connections) | runtime.py `_check_triggers` | Crash between key-record and instance-create orphans the key → workflow never starts for that card. Documented in a code comment. |
| No `workflow_completed` trigger source | model.py `Trigger` | Cannot trigger on "instance finished" — only on one of its CARDS (hence terminal-node-export design), `bead_ready`, or manual. |
| Cross-workflow recursion NOT deduped | test_composition.py test 3 | A→B→A mutual triggers grow unbounded (bounded only by ticks). Avoid mutual-trigger cycles by construction. |
| Condition matching is convention-based | `_matches_trigger` | assignee/status/metadata.*/title_prefix/title_not_prefix only — no regex, no metadata negation. Couples workflows via metadata key spelling + card titles. |

## 4. Probing engine behavior — reuse the test harness

Do NOT hand-roll probes against the live board. `test_composition.py` (in the engine package) ships a `FakeWorld` fixture: temp boards with the real SQLite schema, monkey-patched `KANBAN_HOME` + `create_card`, manual `tick()`. Pattern:
1. `world.add_template({...})` — write workflow JSONs to a temp templates dir.
2. `world.start("workflow-id", context={...})` — manual instance start.
3. `world.tick()` → assert on action strings (DISPATCHED / DONE / STARTED).
4. `world.complete_card(card_id, metadata={...})` — simulate an agent completing (direct DB write: status='done' + task_runs row).
5. Assert instance counts via `get_instance_count(state_db, workflow_id)`.

`scripts/probe-trigger-guard.py` is a ready-made two-case probe (edges vs no edges) — extend it for any new trigger/guard question.

## 5. When a change alters a key format — reproduce the guard parser in isolation

The self-trigger guard reverse-engineers the parent workflow id out of idempotency keys via a heuristic (`split("_")`, walk chunks, first one that's non-`wf`, non-empty, non-digit, `len > 3`). This is fragile by construction. Whenever a change touches key grammar (new suffix, new node type, new iteration scheme), don't reason about whether it "probably" still works — **copy the parse logic verbatim into a throwaway snippet and run it against every existing key shape plus the proposed new ones.** The output distinguishes *preserved by design* from *preserved by accident*. Two failure modes to look for:

- **Misclassification:** the heuristic picks the wrong field as the parent workflow id (e.g. a short workflow id ≤3 chars is skipped by the `len > 3` test, so the 8-char uuid hex gets picked instead → `store.load` returns None → edge-check skipped → trigger fires when it should block → infinite loop).
- **Accidental survival:** the new format survives only because the new suffix lands in a segment the parser never reads (e.g. `:iter{N}` appends after the node id, so the instance segment is untouched). This is a finding, not a pass — it breaks the day placement changes.

If the guard is reverse-engineering information the engine already owns, recommend replacing the heuristic with a deterministic parse keyed on the documented grammar (instance_id is `wf_<ts>_<wf.id>_<uuid>`, where `wf.id` may contain hyphens but not underscores — enforce that invariant at template load). See `references/iteration-key-guard-interaction.md` for a worked example.
