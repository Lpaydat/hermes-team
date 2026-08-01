# Approach C Analysis — Multiple Goal-Bounded Workflows, Composed via Card Handoffs

> **Date:** 2026-08-02 · **Grounding:** runtime.py, model.py, kanban_adapter.py, store.py, templates (qa-loop.json, builder-grill-build.json, builder-single.json, dev-review-loop.json, dev-pipeline.json), README.md, MIGRATION-PLAN.md, docs/handoff-analysis.md, plus an **empirical probe** against the real engine (see §4).
> **Approach C:** each workflow has a CLEAR GOAL and contains the SEVERAL agents needed to achieve it as nodes with explicit edges; workflows are COMPOSED via card_completed triggers (workflow X completes a card → trigger starts goal workflow Y).

---

## 0. TL;DR

C is the right target **shape** — it is the only approach that matches the user's core migration principle ("ONE junction at a time, prove before moving on") while still giving the pipeline visible structure. But the engine as it exists today **silently blocks C's own composition mechanism**: `runtime.py:1783-1800` suppresses `card_completed` triggers on cards created by any workflow that declares explicit edges (verified empirically — see §4). Every goal workflow in C uses explicit edges internally, so every cross-workflow handoff dies unless the terminal node's card escapes the `wf:` idempotency-key guard. Two small, already-anticipated engine features unblock it: `idempotency_key_template` (referenced as load-bearing in MIGRATION-PLAN.md §7 but **not implemented** — 0 hits in engine code) plus keeping/loosening the guard. Second finding: the engine cannot express unbounded loops (node states are monotonic, no re-dispatch, no cycles), so the dev↔verifier iteration and debugger converge loops **must** stay inside opaque node cards (the "static-dynamic coexistence" pattern), which means C's "several agents cooperate as nodes" is only true at coarse junctions, not inside orchestration loops.

---

## 1. How C Works — Decomposition of the 9 Handoffs

Engine primitives available (from code): **edges** (explicit `edges[]` with conditions; AND-semantics for unconditional fan-in, OR/diamond for conditional edges; SKIPPED/FAILED sources ignored), **node types** (task, subworkflow, command, wait, foreach), **triggers** (`card_completed`, `bead_ready`, manual), **schemas** (hard output validation → node FAILED), **idempotency** (per-card `wf:` keys + `trigger_keys` dedup), **state** (workflow_instances, node_states, engine_events).

Proposed goal decomposition and handoff split (using the handoff inventory from docs/handoff-analysis.md):

| Goal workflow | Internal EDGES (agents cooperate) | External TRIGGER handoffs (between goals) |
|---|---|---|
| **planning.json** (goal: spec+design+tickets) | PO grill/spec node → architect node (opaque design-council) → PO to-tickets node (H01, H02, plus grill→spec) | Start: manual / user request. **Exit: beads** created by to-tickets → `bead_ready` fires construction (H07). |
| **construction.json** (goal: merged feature) | tech-lead contract node → developer node → verifier node (H10–H12); PASS→merge handoff node (H16 source) | Start: `bead_ready` (H07). **Exit PASS:** verifier merge card → qa-loop trigger (H16). **Exit FAIL/ESCALATE:** verifier FAIL card or tech-lead escalation card → bug-fix trigger (H13/H14 → H08). |
| **qa.json / qa-loop** (goal: verified artifact) | QA node (+ optional swarm) (H18 internal) | Start: verifier/debugger merge card trigger (H16). **Exit FAIL:** QA files bug bead → `bead_ready` bug-router → bug-fix (H17/H08). Spec findings → PO bead (H19). |
| **bug-fix.json** (goal: proven fix) | debugger node (opaque loop_engine) → verifier merge node (H20–H22) | Start: bug bead (`bead_ready`) or FAIL card (`card_completed`) (H08/H13). **Exit:** merge card → QA re-verify trigger (H24/H16); exit-B gate card → architect (H23, manual). |

Net: **≈12 internal edges, ≈7 external triggers** — vs Approach A's ~20 edges in one graph, vs Approach B's ~27 triggers and ~27 single-node workflows. C concentrates the engine's edge machinery where cooperation is real (planning diamond, construction chain, PASS/FAIL diamonds) and uses triggers only at goal boundaries.

### Concrete template sketch — the construction → QA handoff

**construction.json** (goal: merged feature; edges inside; the terminal node is the workflow's "export port"):

```json
{
  "id": "construction",
  "name": "Construction — one feature merged to master",
  "trigger": { "source": "bead_ready", "condition": { "type": "feature" } },
  "nodes": [
    { "id": "tl_contract", "profile": "tech-lead", "skill": "loops-engineering",
      "body_template": "Bead ${trigger.bead_id}: discover → plan → write contract. Complete with contract_ref." },
    { "id": "dev_work", "profile": "developer", "skill": "developer-loop",
      "body_template": "Implement ${nodes.tl_contract.output.contract_ref} on a branch. Complete with branch_name.",
      "depends_on": ["tl_contract"] },
    { "id": "verify", "profile": "verifier", "skill": "adversarial-review",
      "body_template": "Review ${nodes.dev_work.output.branch_name}. FAIL→fix→re-review is YOUR loop (create fix cards). Merge on PASS. Stamp metadata: {verdict, merged_sha}.",
      "depends_on": ["dev_work"],
      "idempotency_key_template": "qa-merge-${trigger.bead_id}" },
    { "id": "notify_qa", "type": "command",
      "command": "hermes kanban comment ${trigger.bead_id} 'construction complete: ${nodes.verify.output.merged_sha}'",
      "depends_on": ["verify"] }
  ],
  "edges": [
    { "from": "tl_contract", "to": "dev_work" },
    { "from": "dev_work", "to": "verify" },
    { "from": "verify", "to": "notify_qa", "condition": "${nodes.verify.output.verdict} == 'PASS'" }
  ]
}
```

**qa-loop.json** (existing template, unchanged) fires on the verify card: `card_completed {assignee: verifier, metadata.verdict: PASS}`. The **load-bearing detail**: `idempotency_key_template` on the terminal node gives the card a non-`wf:` key (`qa-merge-<bead>`), so it escapes the self-trigger guard (§4) **and** matches the old cron's `qa-merge-<sha>` dedup convention for coexistence. Intermediate nodes keep `wf:` keys, so no accidental cross-workflow firing from mid-pipeline cards. **This field does not exist in the engine yet** (see §4) — it is the #1 prerequisite.

---

## 2. Loops: dev↔verifier and debugger converge

**The engine cannot express iteration.** Node status is monotonic (pending → dispatched → done/failed/skipped); PHASE 2 only dispatches PENDING nodes; a DONE node is never re-dispatched; there is no cycle support. `dev-review-loop.json` proves the workaround: the FAIL→fix→re-review loop is **unrolled exactly once** in the template — and even there, a second FAIL on re-review is terminal (no edge back to review), so the workflow just completes with a FAILED node. `foreach` is parallel fan-out, not iteration.

Consequences for C:
- **dev↔verifier iteration must live inside a node card** (the verifier node's card stays `running`/`blocked` while it creates fix cards via `kanban_create`, exactly as H13 works today; the engine sees one node, completes it when the loop converges). This is the documented "static-dynamic coexistence" pattern (engine README §Dynamic Workflow Support, lines 559-572).
- **Debugger converge must live inside the debugger node card** (loop_engine, H20–H22). The bug-fix workflow's edges only cover the single-pass tail (debugger node → verifier merge node).
- Alternative for fixed small loops: unroll (dev-review-loop style), but cap it — beyond 1-2 unrolled iterations the template explodes and every unroll is a new card cost.
- Trigger-spawned iteration (each FAIL card starts a fresh fix instance) works today only for agent-created FAIL cards (no `wf:` key) — which is the status quo — and is blocked for engine-node FAIL cards by the same guard (§4).

So: **C is a good fit for the coarse loop boundaries, a non-fit for the inner loops — the inner loops stay profile-managed, and that is correct** (handoff-analysis H10–H13, H20–H22 explicitly recommend "stays as-is").

## 3. The 3 Orchestrators (architect design-council, tech-lead kanban_chains, debugger loop_engine)

C does not fight them **provided each stays ONE opaque node** whose card runs the dynamic pattern (`blocked`→`done`; engine never peers inside). That is precisely what the engine README's static-dynamic coexistence pattern and handoff-analysis's "No — and shouldn't" verdicts (H04, H05, H06, H10–H13, H18, H20–H22) mandate.

C does fight them in its **flat** reading ("tech-lead + developer + verifier as three engine nodes"): flattening kanban_chains/loop_engine into engine nodes breaks (a) atomic authoring (tech-lead writes the contract in the same call that creates dev+verifier cards), (b) convergence judgment (iteration caps, fan-out sizing, RPC interviews with PO — all mid-run decisions), and (c) the FAIL-loop (engine has no loop). Flattening would also hit the guard on every handoff.

**Design rule for C:** orchestration-heavy goals (construction inner loop, bug-fix) = opaque orchestrator node + thin engine edges for the single-pass tail; cooperation-heavy but judgment-light junctions (planning, PASS/FAIL diamonds) = flattened engine nodes. This is C's honest scope: "several agents cooperate per workflow" is true at goal boundaries, not inside convergence loops.

## 4. Cross-Workflow Triggering — the make-or-break detail (empirically verified)

`runtime.py:1783-1800` (self-trigger prevention): when a completing card has an idempotency key starting with `wf:`:
1. If `_{wf.id}_` appears in the instance part → **block** (same-workflow self-trigger).
2. Else extract the parent workflow id from the instance key; if the parent template **has explicit `edges` → block** ("parent has explicit edges — handles routing internally").
3. Only if the parent has **no explicit edges** does the trigger fire (backward-compat for trigger-based composition — i.e., Approach B).

**Empirical probe** (real engine, FakeWorld harness, two runs):

```
CASE 1: construction WITH explicit edges (C shape)
  verifier card idem_key = wf:wf_..._construction_...:verify
  → qa-loop instances: 0   ← trigger SILENTLY BLOCKED

CASE 2: construction WITHOUT edges (implicit depends_on, B shape)
  verifier card idem_key = wf:wf_..._construction_...:verify
  → qa-loop instances: 1   ← trigger fires
```

**C as specified (edges internally + card_completed composition externally) is self-blocking.** Every engine-created card in an edge-using workflow is untriggerable, including its terminal PASS card and its FAIL cards. Resolutions:

- **(a) `idempotency_key_template` on terminal nodes** (recommended): gives the handoff card a non-`wf:` key → guard skipped → trigger fires. Already assumed load-bearing by MIGRATION-PLAN §7 and Phase 0 checklist ("Add `idempotency_key_template` support") but **absent from model.py/runtime.py** (0 grep hits). This is a small, testable feature.
- **(b) Relax the guard** to same-workflow-only blocking: restores the README-documented semantics ("CAN trigger a different workflow"). Risk: double-routing if a source workflow also routes internally to the same destination the trigger targets — needs a convention ("one destination per signal; disable triggers for destinations covered by edges") and the mega-workflow case (A) is exactly what the guard was protecting.
- **(c) Handoffs on agent-created cards**: works today (qa-loop's trigger fires on kanban_chains-created verifier cards — no `wf:` key), which is why the current qa-loop template is "proof" — but it forces the opaque shape everywhere and leaves C with few real multi-agent workflows.

Other trigger edge cases, all live in the code:
- **Dedup is per (trigger workflow, card)**: `trig:{wf.id}:{card.id}`. One card CAN trigger several different workflows (test_composition covers parallel children), and one workflow fires once per card.
- **No workflow-completed trigger source** exists (only card_completed / bead_ready / manual) — you cannot trigger on "construction instance finished"; you must trigger on one of its CARDS. Hence the terminal-node-export design.
- **Recursion is NOT prevented across workflows** (test_composition test 3 finding: A→B→A grows unbounded, bounded only by ticks). C must avoid mutual-trigger cycles by construction.
- **1-hour lookback** (`TRIGGER_LOOKBACK_SECS = 3600`) + `LIMIT 200` per board per tick in `find_recent_completions`: an engine outage >1h silently loses triggers (old cron had the same window — not a regression, but real).
- **Non-atomic dedup window** (documented in code): trigger key recorded before instance creation; crash between = orphaned key, workflow never starts.
- **Merge dedup regression risk**: old cron deduped QA by `qa-merge-<sha>`; the engine dedups per card — two verifier PASS cards (e.g., feature merge + bug-fix merge back-to-back) now yield TWO QA instances. If that's wrong, conditions must be tightened (e.g., `metadata.merged: true` — already recommended in MIGRATION-PLAN §3.6).

## 5. Failure Blast Radius

- **C:** a goal instance completes when ALL nodes are terminal (DONE/FAILED/SKIPPED — runtime.py:977-1009) — a FAILED node does NOT hang the instance, it just marks it completed-with-failure. QA only triggers on PASS, so a failed construction produces no QA card. Recovery paths: FAIL card → bug-fix trigger (works if card is agent-created or carries a custom key; blocked today for flat engine nodes — §4), QA-filed bug bead → bug-fix (works), scanner/escalation (H25, stays as cron safety net), or human. Blast radius = one goal instance; the other goal workflows keep running.
- **A (mega):** same terminal-state semantics but ONE instance is the whole pipeline — a FAILED node permanently kills the downstream of that branch and the entire pipeline's state is one blob. Recovery requires a new instance or human. Worst visibility-per-failure ratio.
- **B (per-agent):** failures are confined to tiny workflows and each FAIL card naturally spawns the next tiny workflow via trigger — the most natural failure recovery, and the reason the guard preserves B.
- **C verdict:** better than A (isolation), slightly worse than B (recovery depends on the §4 fix); with fix (a) in place C's recovery is identical to B's at goal boundaries.

## 6. Independence (the user's core migration principle)

C is the only approach that structurally supports "ONE junction at a time, prove before moving on":
- Templates are **additive** — `TemplateStore` globs `*.json`, hot-reloads on mtime (store.py). Adding planning.json/construction.json doesn't touch anything else; disabling = rename to `.disabled` (documented rollback).
- Each workflow is independently startable/testable: `main.py start <workflow-id>`, per-feature test files (test_explicit_edges.py, test_subworkflow.py, test_composition.py…).
- The 6-template phased plan in MIGRATION-PLAN.md §5 is exactly a C-shaped landing sequence (qa-loop → bug-router → wayfinder → bead-dispatch → human-escalation → blocked-escalation), with the old cron running alongside phase-by-phase.
- **Caveat — hidden coupling:** the §4 guard couples templates at runtime: flipping construction.json from `depends_on` to `edges` (or adding any edge) silently disables qa-loop's trigger. Template changes have cross-workflow effects that only a trigger-level test catches. And the coexistence guarantee ("matching idempotency keys prevent duplicates") is currently **aspirational** — `idempotency_key_template` doesn't exist, so engine cards carry `wf:` keys the old cron doesn't recognize.
- B has the same additive property but 27× the files and no junction to prove (nothing to see in one workflow). A has zero independence — the mega template must be whole or empty (which is exactly what dev-pipeline.json is today: `"nodes": [], "edges": []` — the A approach stalled).

## 7. State & Debugging

- **Per-goal instances** in `workflow_instances` + per-node `node_states` + an `engine_events` audit log (trigger_fired, node_dispatched/done/failed, workflow_started/completed, command_run, gc) with instance/workflow/node/card ids; `main.py list` shows live nodes per instance; `main.py render <id>` emits mermaid per template.
- **C:** "planning done; construction running (tl_contract done, dev_work dispatched, verify pending); qa waiting on trigger" — readable and greppable per goal. Best middle ground.
- **A:** one instance, ~20 node states — complete picture in one place, but a stuck node blocks everything and the instance row is huge.
- **B:** many tiny instances; the pipeline shape is implicit (you must join instances through trigger_context card ids); "where is my feature?" requires assembling the chain by hand.
- All approaches share: no dashboard (SQLite + CLI only), 7-day GC on state (cleanup()), zombie-instance and card-regression guards (runtime.py:584-601, 764-783).

## 8. Does the Existing Proof Already Resemble C?

Partly — and the gap is exactly the §4 guard:

| Existing artifact | What it proves | How C formalizes it |
|---|---|---|
| `builder-grill-build.json` (parent) + `builder-single.json` (child) | Goal-bounded composition via **subworkflow nodes** (parent blocks on child instances; `foreach` fan-out); child has internal edges (grill→build→handoff) | C's intra-goal edges; but composition here is subworkflow (blocking, parent-owned), NOT card_completed triggers. Subworkflow is C's other valid composition mechanism (and it does NOT hit the guard — it's `start_manual`, not triggers). |
| `qa-loop.json` | `card_completed` trigger on verifier PASS | C's cross-goal trigger — **works today only because the verifier card is agent-created (kanban_chains, no `wf:` key)**. It would break the moment a verifier card becomes an engine node in an edge-using workflow (proven in §4). |
| `dev-review-loop.json` | Multi-agent goal workflow (developer+verifier+qa) with conditional diamond: build→review→(PASS→ship \| FAIL→fix→re-review→ship) | The strongest existing C artifact — but QA is INSIDE the workflow (no trigger composition), and the loop is unrolled exactly once. |

So: C is a **formalization of what already works, plus two unproven deltas**: (1) several agents cooperating via edges inside one goal (proven by dev-review-loop for a 3-agent case), and (2) trigger composition on engine-created terminal cards (proven for no-edge workflows only; **not** proven — in fact blocked — for edge-using workflows). The builder pair also demonstrates that C has a second, guard-free composition mechanism (subworkflow) that should be in the toolbox for parent-goal/child-goal relationships.

---

## Strengths of C (grounded)

1. **Matches the migration principle.** Additive templates + per-workflow manual start + per-feature tests + old-cron coexistence (once `idempotency_key_template` lands) = true one-junction-at-a-time adoption. A cannot do this; B fragments it.
2. **Best failure isolation + visibility ratio.** Per-goal instances with per-node state and an event log; a failed goal completes-with-FAILED instead of hanging; other goals unaffected. A has global blast radius; B has no pipeline shape.
3. **Edges where cooperation is real.** The planning chain and PASS/FAIL diamonds get schema-validated, condition-routed edges with hard output validation — the engine's strongest features — instead of B's convention-matching triggers (title prefixes, metadata key spelling) or A's undebuggable graph.
4. **Orchestrators survive.** The three dynamic orchestrators stay opaque nodes (static-dynamic coexistence); C only asks the engine to do what it can do.
5. **Smaller trigger surface than B** (~7 vs ~27): fewer places for the documented trigger footguns (1h lookback, LIMIT 200, non-atomic dedup window, condition overlap → duplicate instances).

## Weaknesses of C (grounded)

1. **Self-blocking composition (critical, verified).** `runtime.py:1783-1800` blocks card_completed triggers on every card of an edge-using workflow — the exact shape C uses. Requires the missing `idempotency_key_template` feature (or a guard change) before ANY two-edge-workflow handoff works; until then C degenerates into B.
2. **No loops.** Monotonic node states, no cycles, no re-dispatch: dev↔verifier iteration and debugger converge must stay inside opaque node cards (or be unrolled once). "Several agents cooperate per workflow" is therefore only true at coarse junctions; C's promise shrinks in the orchestration-heavy goals.
3. **Hidden cross-workflow coupling.** The guard makes trigger behavior depend on OTHER templates' edge declarations (adding an edge to construction silently kills qa-loop); trigger conditions couple workflows by assignee/metadata conventions with no static check; two verifier PASS cards → two QA instances (per-card dedup, no merge-sha dedup). Needs convention + tests, not just templates.
4. **Failure recovery is trigger-dependent.** With the guard as-is, a FAILed flat construction instance triggers nothing and needs a human — worse than B's natural FAIL→fix flow until the §4 fix lands.
5. **Feature debt.** `idempotency_key_template` (assumed load-bearing), `not_labels`/`label_any`/`or_labels_contains`, `task_blocked` source, per-node `board` override — the MIGRATION-PLAN's own Phase 0 checklist — are all unimplemented (verified: 0 hits for `idempotency_key_template` in engine code). C's plan rests on features that don't exist yet.

## Verdict: where C beats A and B, where it loses

- **C beats A decisively.** A's mega graph cannot be adopted incrementally (dev-pipeline.json is still empty; the user already rejected upfront scaffolding), gives no failure isolation, fights the three orchestrators (they must become opaque nodes anyway — at which point A is C with one giant file), and shares C's no-loop limitation. A offers nothing C lacks except single-file totality.
- **C beats B on structure**: fewer triggers, real edges with schema validation at cooperative junctions, per-goal visibility, debuggable pipeline shape. 
- **C loses to B on one axis**: iteration. B's per-card triggers make FAIL→fix→re-verify natural as fresh small instances; C must keep loops profile-managed or unroll. C also currently loses on composition mechanics (the guard), but that is a one-feature fix (`idempotency_key_template`), and B's trigger patterns remain available inside C for agent-created cards.
- **Recommended path:** adopt C with the **C-opaque shape** (orchestrator goals = opaque nodes + thin tail edges; flattened edges only at judgment-light junctions like planning and PASS/FAIL diamonds), land **`idempotency_key_template` + the guard decision as Phase 0 prerequisites** (they are already Phase 0 checklist items), keep the scanner cron as the universal safety net, and keep subworkflow composition (builder pair) as the guard-free alternative for parent-goal/child-goal nesting. C is the right architecture; it just needs two small engine features to stop blocking itself.
