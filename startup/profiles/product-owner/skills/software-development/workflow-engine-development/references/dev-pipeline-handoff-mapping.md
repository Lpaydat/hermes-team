# Dev Pipeline Handoff Mapping — Edges vs Triggers (9 Handoffs × 2 Approaches)

> 2026-08-02. Grounded in engine docs: node-types-and-capabilities.md,
> engine-design-decisions.md, and-or-edge-semantics.md, template-patterns.md,
> real-pipeline-pattern.md, cron-to-engine-migration-planning.md.

## Engine facts that decide the mapping

- Node types: task / command / subworkflow / wait. Triggers: card_completed / bead_ready /
  manual (no scheduled — Hermes cron owns scheduling).
- Edges: unconditional = AND (dependency convergence), conditional = OR (diamond routing).
- **Self-trigger prevention:** engine-created cards (`idempotency_key wf:...`) from templates
  WITH explicit edges never fire OTHER workflows' triggers; same-workflow cards always
  blocked; cross-workflow cards from templates WITHOUT edges still fire (backward compat).
  => Trigger chains require agent-created completing cards.
- **mini-pipeline livetest:** an explicit edge (verdict=PASS → QA) and the qa-loop trigger
  (card_completed, verdict=PASS) fired simultaneously for the same handoff — declared
  correct behavior, not a conflict.
- **"Cannot migrate (needs human judgment)":** profile-internal converge loops (debug-loop,
  design-council) — loop_engine handles these.

## The 9 handoffs

| # | Handoff | A: one template, explicit edges | B: per-agent templates, card_completed triggers | Winner | Why |
|---|---------|--------------------------------|------------------------------------------------|--------|-----|
| 1 | PO → Architect (design card + PRD) | Plain static edge; Arch degrades to subworkflow (internal design-council loop) + mode branch | Trigger on design-card completion; needs agent-created card (self-trigger prevention) | Tie (A slight) | Only fully static one-shot handoff — canonical edge |
| 2 | PO → Tech-Lead (dispatch from beads) | Breaks single-instance model — async external feed, each bead = new instance | dev-dispatch.json bead_ready trigger (planned, High) | **B strong** | Event-driven entry is a trigger, not an edge |
| 3 | TL → Developer (kanban_chains card) | Not expressible as edge — card created at runtime, engine sees only root; opaque subworkflow | Chain child card auto-promotes via parent links; zero engine involvement | **B strong** | Static-dynamic coexistence pattern |
| 4 | TL → Verifier (kanban_chains card) | Same as #3 — invisible inside construction subworkflow | Created atomically, parented on dev card; auto-promotes | **B strong** | Board dependency semantics do it for free |
| 5 | Verifier → QA (on PASS) | Conditional edge verdict=PASS → QA (proven livetest) | card_completed + verdict=PASS trigger; **shipped** as qa-loop.json (Phase 1) | Tie | Both proven; pivot handoff between models |
| 6 | Verifier → Developer (on FAIL) | Conditional edge FAIL → fix → re-review: graph cycle (proven dev-review-loop.json); cap = metadata conditions on edges | FAIL trigger → fix card → new dev instance; iteration on card metadata (REVIEW-ITERATION) | **A (slight)** | Only handoff where graph-native loop+counter beats trigger re-entry |
| 7 | QA → Debugger (bug beads auto-routed) | Conditional triage edges in mega-template; but bugs are new instances from multiple sources; graph tangles | bug-router.json: card_completed + type=bug trigger (planned, High) | **B strong** | Auto-routing by external metadata is a global watch |
| 8 | Debugger → Developer (loop_engine fix) | Cannot be an edge — fix cards spawned per hypothesis; converge is LLM reasoning ("cannot migrate") | Debugger's own workflow is loop_engine-driven; fix cards trigger dev instances | **B strong** | Pure-A template literally can't express it |
| 9 | Debugger → Verifier (re-verify) | Edge back INTO construction region: re-entry into earlier stage; instance never completes normally | Trigger on debugger done → re-verify card → fresh verifier instance | **B strong** | Re-entry-as-new-instance is B's native shape |

## The two loop patterns

- **dev ↔ verifier (until PASS or iter ≥ 3):** expressible in BOTH. A: graph cycle via
  conditional edges (proven); cap needs metadata conditions on edges. B: emergent across
  trigger instances, iteration counted on card metadata. A's explicit loop requires Dev/Ver
  as global nodes — incompatible with kanban_chains dynamic trees; taking A's loop means
  abandoning the dynamic tree (role change, not a mapping).
- **debugger converge (reproduce→hypothesize→falsify→converge):** NOT expressible in either
  approach. The converge decision requires reasoning over falsification evidence; a
  declarative condition cannot decide it. Both must treat the debugger as a subworkflow node
  with an agent-managed loop_engine inside — the engine watches only the parent card. This
  IS the "static-dynamic coexistence" pattern.

## Verdict

- Strongly B (6): #2 dispatch feed, #3/#4 dynamic trees, #7 bug routing, #8 converge
  internals, #9 re-verify as new instance.
- Ties (2): #1 (static edge, A slight), #5 (PASS→QA — both proven; shipped as B).
- A (1): #6 FAIL retry loop — the only graph-native handoff.
- Neither (loop level): debugger converge must be agent-managed in both models.

The pipeline is B-shaped: a pure-A global template degenerates into three opaque subworkflow
black boxes (design-council, construction, debugger) plus trigger-style re-entry for dispatch
and bugs — A collapses into B with extra ceremony. The correct hybrid: **explicit edges for
the static skeleton inside a feature instance (#1, #5, #6); triggers for cross-instance entry
and routing (#2, #5, #7, #9); agent-managed loops/trees as subworkflow black boxes
(#3, #4, #8, debugger converge).**
