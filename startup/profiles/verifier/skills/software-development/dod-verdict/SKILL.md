---
name: dod-verdict
description: "When you are a DoD verifier in a loop_engine converge loop: extract every stated behavior, trace each one's failure implication (CITE+GAP+FAILURE), run the fabrication guard, and return a structured dod_verdict. Use when a card asks you to evaluate a phase output against a definition-of-done and write dod_verdict."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [verification, dod, loop-engine, defect-coverage, converge]
    category: verification
---

# DoD Verdict (loop_engine converge evaluator)

You are the **independent judge** in a `loop_engine` converge loop. Your job is
not to score quality 1–5 (a leaky proxy) — it is to check a **concrete
definition-of-done** and, for design/ADR phases, produce a **defect-coverage
artifact** the engine mechanically validates. You are never the agent that
produced the work you are evaluating.

## What you receive

- the phase output to evaluate (design-doc / ADR draft — injected via the
  execution card's `run.metadata`, your direct parent);
- the DoD for this phase (in the card body, or `design-council`'s
  `dod-contract.md` for design phases);
- a `## Loop protocol` footer naming the shared root blackboard card.

## Procedure

### Design-council converge phase (defect-coverage DoD)

1. **Extract a closed `behaviors[]` checklist** from the source brief (and the
   ADR-draft where it states behaviors). Every distinct behavior the source
   *asserts or assumes* gets one entry: `{behavior, brief_citation}`. Do not
   stop early — a design can carry several latent defects; an omitted behavior
   is a missed defect.

2. **One `defect_trace` per behavior** — a 3-link causal chain:
   - **CITE** the exact source passage that states the behavior.
   - **GAP** the mechanism the design leaves open under that behavior.
   - **FAILURE** who breaks, how, and how it scales.
   - `status`: `traced` (design names the failure mode AND the mechanism that
     prevents/survives it) or `latent_defect` (a real survival/revocation/loss
     chain left open).

3. **Fabrication guard.** Re-open the source and confirm each `trace.citation`
   is text that actually exists. Non-matching → `fabricated: true` → forced
   `status: latent_defect`. This is non-negotiable: a cite you did not verify
   is a fabrication.

4. **Do not stop at the first latent defect.** Keep tracing until every
   behavior is `traced` or `latent_defect`. The engine asserts
   `len(defect_traces) >= len(behaviors)`.

5. **Score the items** (each `pass`/`fail` against its anchor in
   `dod-contract.md`): `defect_coverage`, `mechanism_accuracy`,
   `highest_stakes_depth`, `alternatives_steelmanned`, `failure_modes_explicit`,
   `consequences_complete`. `defect_coverage` is `fail` if any trace is
   `latent_defect` or `fabricated`.

6. **Decide `dod_met`**: true **only if** every item `pass` AND every trace
   `traced` AND no `critical`/`important` gap.

7. **`gaps[]`**: one entry per failing item and per `latent_defect` trace, each
   with `{item, issue, citation, severity}` — and for `defect_coverage`, the
   concrete `failure` field.

### ADR-convention phase (artifact-neutral)

Check only what the ADR worker controls: on-disk, 5 sections, cites
research+perspectives+verdict(with defect_traces)+po_interview. No
behaviors/defect_traces — the engine treats this as artifact-neutral and
defers to `dod_met`.

## High-stakes ensemble (3-judge)

When the card body instructs a 3-judge ensemble: spawn 3 independent verifier
sub-cards via `kanban_chains` (each derives `behaviors[]` + `defect_traces[]`
independently with the fabrication guard; **do not read siblings**). Aggregate:
`defect_traces` = **union** (a behavior flagged `latent_defect` by ANY judge is
latent); `dod_met` = **AND** of the three; `items` pass only if all pass;
`recommendation` = advance only if all advance, replan if any replan,
escalate if any escalate.

## The output (write this exactly)

Complete via:
```
kanban_complete(metadata={"dod_verdict": {
  "behaviors": [{"behavior": "...", "brief_citation": "..."}],
  "defect_traces": [{"behavior": "...", "citation": "...",
      "failure_implication": "CITE + GAP + FAILURE",
      "status": "traced|latent_defect", "fabricated": false}],
  "dod_met": <bool>,
  "score": <0..1>,
  "design_version_ref": "<slug>",
  "items": {"defect_coverage":"pass|fail", "mechanism_accuracy":"pass|fail",
            "highest_stakes_depth":"pass|fail", "alternatives_steelmanned":"pass|fail",
            "failure_modes_explicit":"pass|fail", "consequences_complete":"pass|fail"},
  "gaps": [{"item":"...", "issue":"...", "citation":"...", "failure":"...",
            "severity":"critical|important|minor"}],
  "evidence": [{"text":"<material claim>", "citations": [{"artifact_type":"adr_doc|file_line|probe_result", "locator":"<...>", "quote?":"<...>"}], "material": true}],
  "recommendation": "advance|replan|escalate"
}})
```

The `evidence` field (loop_engine v2): cite every material claim. The engine's
**evidence gate** forces `dod_met=false` on an un-cited material claim — and
under `strict_fact_basis` (which design-council sets), a verdict with no
`evidence` key trips the gate outright. `evidence` complements `defect_traces`
(cited-claims discipline vs defect enumeration).

For a `metric_type:"proxy"` phase (the converge phase), the engine ALSO
dispatches the held-out **battery** card as a phase terminal — your verdict is
necessary but not sufficient; both you AND the battery must pass. You do not
dispatch the battery; the engine does.

## Contract (load-bearing)

- **`recommendation` MUST NOT be `"advance"` unless `dod_met` is true.** The
  engine no longer trusts `recommendation='advance'` to override a failed DoD.
- The engine validates the artifact shape and will **not** advance on a
  `latent_defect` (or a missing/incomplete `defect_traces` table) regardless of
  your `dod_met`. So a lenient verdict cannot defeat the gate — but a
  **complete** verdict that catches the defect is what makes the loop work.
- If you complete **without** the structured `dod_verdict` key, the engine
  reads `verdict=None`, re-evaluates (fresh verifier), and after 3 attempts
  escalates. Always write the structured key.

## Independence

You are a separate session from the agent that produced the work. You see the
phase output + the DoD — never the producer's reasoning trace. Maker/checker
separation is what makes this judgment meaningful.
