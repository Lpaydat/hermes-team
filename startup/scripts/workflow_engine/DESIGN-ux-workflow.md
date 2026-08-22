# UX/UI Design Workflow — SPEC (agreed 2026-08-20, build on feat/ux-workflow)

Extends the proven pipeline (v0.1.0) with a design phase. Doctrine unchanged:
cards say WHAT, workflows say HOW, gates between them are deterministic.

User's decisions (agreed in session):
- **When**: design gate BEFORE UI tickets + design-QA AFTER build (both).
- **Artifacts**: ALL four layers (they compose — see below).
- **Scope**: auto-detect UI projects (architect stamps artifact_type).
- **Approval**: adversarial review, fully autonomous (same doctrine as QA).

## The layered artifact chain (why all four work together)

Each layer constrains the next; later layers are checkable proofs of earlier ones:

1. **Adopt a component system** (e.g. Tailwind + shadcn) — base decision, from
   tech-preferences.json; everything downstream inherits it.
2. **UI spec + wireframes** (markdown) — screens, states (empty/error/loading),
   flows. Source of truth. Pure prose + ASCII/mermaid — agents read/write natively.
3. **Design tokens** (design-tokens.json) — colors/spacing/type, mostly inherited
   from #1, customized per project. Becomes a build constraint.
4. **HTML mockups** — assembled from #1 components + #3 tokens per screen of #2.
   Screenshot-able: the adversarial reviewer CHECKS the spec visually, not just
   reads it. Mockup HTML is close to the app's real UI layer.

## Pipeline shape

```
spec → architect ──(artifact_type: webapp|TUI)──→ route-design:
                                                  1. create [design-done] gate upfront
                                                  2. fire design-gate workflow
                                                  3. dependency-park until gate closes
design-gate workflow (designer lane):
   d1 choose-system  → d2 spec+wireframes → d3 tokens → d4 mockups+screenshots
   → d5 adversarial review (verifier, 4 probes):
        state-coverage     every screen has empty/error/loading states
        a11y               contrast basics, focus order, text alternatives
        consistency        mockups vs tokens vs adopted system
        spec-traceability  every user story has a screen; every screen traces back
   → PASS: design-close completes [design-done] via CLI (gate-close pattern)
   → FAIL: findings → designer revises (capped loop, y51 round-N pattern)
[design-done] closes ──group_cards──→ holds ALL UI tickets (pre=[{gate}])
build → milestone-gate gains design-visual phase (UI milestones only):
   screenshot RUNNING app vs mockups → diff + heuristics → findings filed like QA
```

## Reuse vs new

| Piece | Reuses (proven) | New |
|---|---|---|
| Barrier | kanban_group, workflow-gate lane | nothing |
| Design workflow | milestone-gate shape (phases → review → close) | design-gate.json |
| Entry hook | dev-dispatch routing | route-design node; architect emits artifact_type |
| Post-build check | QA phase pattern + bundled browser plugins | design-visual phase |
| Reviewer | verifier lane + probe fan-out | design-heuristics skill |
| Designer | designer profile (exists) | 3 skills: ui-spec, tokens, mockup+browser |

## Semantics contract

1. **One design gate per project** (v1): all UI ticket triggers parent on
   [design-done] via group_cards pre=[{gate}] — same wiring as qa-done barriers.
2. Non-UI projects never see the design phase (architect's artifact_type routes).
3. FAIL holds the gate (by design — same as QA FAIL); revisions loop is capped.
4. design-close completes the gate via `hermes kanban complete` CLI — NEVER the
   worker tool (control-lane ownership, same rule as gate-close/ticket gates).
5. Design-QA findings route exactly like QA findings (severity → fixer lanes).

## Build order

1. design-gate.json template + route-design node + design-visual phase
2. designer profile skills (ui-spec, tokens, mockup+browser) + browser plugin enable
3. tech-preferences.json: design-system recipes entry
4. Template pins in test_ticket_serialization.py (+ all-conditional merge rule
   for any new merge nodes — the 61ca761 lesson)
5. Kernel tests: gate wiring, park-until-design, FAIL-holds
6. Live validation: disposable board, small webapp spec, NO hints — prove UI
   tickets held until [design-done] closes, then design-QA diffs built app vs mockups

## Open questions (answer before/during build)

- Per-milestone design (M2 adds screens) vs once-per-project: v1 = once; revisit
  when a livetest shows M2+ UI churn.
- Default component system for tech-preferences (Tailwind+shadcn? plain CSS
  reset for CLIs-adjacent TUIs?) — architect picks per project.
- Mockup screenshot tooling: bundled browser-use vs browserbase (browserbase is
  remote; browser-use may need an API key) — verify what works locally FIRST.

## Context

- Agreed after v0.1.0 (grp-lt1 proven: barriers live, 500/500 cards).
- The mockup-screenshot loop is the same trust pattern as code: prose spec is
  the claim, rendered pixels are the proof.
