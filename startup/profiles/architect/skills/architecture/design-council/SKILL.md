---
name: design-council
description: Run an irreversible design decision through a research-backed council with an independent evaluator before recording the ADR. Use when you owe an architecture decision or ADR, or when a design-it-twice comparison is called for — any design output that must not come from one agent's memory alone.
---

A design decision owed by the architect is **council** work, not memory
retrieval. The council **fans out** research and peer-architect perspectives
via `kanban_chains`, which **parks** the architect until they complete — so the
ADR is built from research, critique, and a live PO discussion, never from one
agent's training memory.

The iteration signal is an **independent evaluator** (the `verifier` profile)
scoring the design across five rubric dimensions — not the architect's
self-confidence. The loop **improves → evaluates → keeps or discards →
converges**, monotonically: a round that regresses is reverted, not
accumulated. (autoresearch's improve→measure→keep/discard, applied to design
quality.)

**Leading words.** *council* — the multi-perspective deliberation. *parked* —
your card blocked in dependency-wait by `kanban_chains`, auto-promoted when the
terminal step completes. *stakes* — the project's value/risk tier, **declared
by the PO on the design card** (low / standard / high); sets the council tier,
the evaluator model, the max rounds, *and* the PO's role. *floor* / *ceiling*
— the minimum and maximum council effort. *diverge* (round 1, independent
perspectives) → *critique* (round 2+, adversarial, targeted by evaluator
flags) → *synthesize* → *evaluate*. *review* — a PO card checking a synthesis
for **product fit** (high stakes, each round). *interview* — a live intercom
`ask` with the PO before the ADR (standard + high). *blackboard* — the shared
root card `kanban_chains` creates. *best-so-far* — the highest-scoring
design-doc version; the revert target when a round regresses. *plateau* — the
score delta below which two consecutive rounds signal convergence.

## Decompose into decisions — and check coverage

Break the design into decisions (one ADR each), one **phase** at a time. Use
the architectural dimensions as a **coverage checklist**, not as fan-out
cards: data model, security/auth, infrastructure/deployment, API surface,
cross-cutting. Ensure your decision set covers each dimension that applies.

## The loop — one decision

1. **Assess.** Take **stakes** from the card (PO-declared). Rate complexity by
   the blast-radius instinct. Stakes fixes the council tier, the evaluator
   model, the max rounds, *and* the PO-interaction model (rubric below). You
   may escalate a decision above the project tier with reason.

   *Done when:* stakes, complexity, council shape, evaluator model, max rounds,
   and PO-interaction model are all recorded.

2. **Diverge.** Call `kanban_chains` with the round-1 shape for your tier —
   **standard**: research + peer chains, **no `after`** (you synthesize).
   **High**: research + peer chains + `after: [synthesis, PO review]` (a peer
   synthesizes, the PO reviews it for product fit). Park.

   *Done when:* `kanban_chains` returned and your card is in dependency-wait.
   You wrote nothing, and you did not call `kanban_complete` — you auto-promote
   when the terminal step completes.

3. **Read inputs → synthesize → evaluate.** On re-dispatch, read research +
   perspectives (+ the synthesis and PO *review* at high stakes). Synthesize
   your design-doc version, then **create the evaluator card** (the judge
   scores it across the five rubric dimensions — see
   [`references/evaluator-rubric.md`](references/evaluator-rubric.md)). Park
   again until the evaluator returns its verdict.

   *Done when:* the evaluator's output schema is in hand — `overall`,
   `delta_vs_last`, `flagged_weaknesses`, `verdict`.

4. **Decide — keep / discard / converge.** Act on the evaluator verdict:

   - **`improve`** (score rose, or a critical/important flag remains, and a
     round remains within the max) → run a **targeted critique round** on the
     evaluator's flagged weaknesses (`kanban_chains`: targeted research +
     red-team keyed to the specific flags). Store this version as the new
     *best-so-far* if it scored higher. Return to step 3.
   - **`converged`** (overall ≥ 4.0, zero critical/important flags, *or*
     plateau over 2 rounds) → proceed to step 5. The best-so-far version is
     the ADR basis.
   - **`regressed`** (delta < 0) → **discard** this round's changes: revert to
     the best-so-far design-doc version. Do not accumulate a bad round. Return
     to step 3 with the reverted design, OR if max rounds is hit, proceed to
     step 5 with the best-so-far and a *Residual risks* section.
   - **Ceiling (max rounds) hit without convergence** → proceed to step 5 with
     the best-so-far; record a *Residual risks* section listing the
     evaluator's remaining flags.

   *Done when:* you have either converged (proceeding to step 5) or hit the
   ceiling (proceeding to step 5 with residual risks).

5. **Interview the PO** (standard + high; **skip at low stakes**). Use the
   intercom tool with **`action: ask`** to `startup/product-owner` on the
   card's topic with your open trade-off questions. The PO has no live session,
   so the broker spawns one to receive the ask and reply — **`ask` blocks for
   the reply** (returns within ~30s). Fold the reply into the decision. **If
   the ask times out, re-ask or block the card `needs_input` — never write the
   ADR without the PO's input.**

   *Done when:* the PO has replied (or the card is blocked awaiting them).

6. **Record the ADR.** Write to `docs/adr/` per `docs/agents/adr-convention.md`
   (Context / Alternatives Considered / Decision / Consequences / Citations).
   Cite research, perspectives, synthesis, the **evaluator verdict** (overall
   score, flags resolved, convergence round), PO *review*(s) (high), and the PO
   *interview*. Ceiling hit → add a *Residual risks* section (the evaluator's
   remaining flags) and block `needs_input`.

   *Done when:* ADR on disk, all council inputs + evaluator verdict cited,
   convention sections present, and — if the ceiling was hit — the card is
   blocked for review.

## The floor

Every ADR is the output of at least one council round — **≥1 research card +
≥1 peer-architect perspective**, with you parked throughout, never
memory-only. Low stakes meets this with the minimum (research + 1 peer, 1
round, no evaluator, no PO interaction). The evaluator is the *iteration
signal* — the floor is a single round, so at low stakes the floor IS the
ceiling; the evaluator is not spawned.

## The ceiling

Max rounds are **stakes-scaled** (rubric below). Convergence is the evaluator's
call: plateau (score delta < threshold over 2 rounds) or overall ≥ 4.0 with
zero critical/important flags. Ceiling hit without convergence → record the ADR
with a *Residual risks* section (the evaluator's remaining flags) and block
`needs_input`.

## Keep/discard — the best-so-far version

Each round produces a design-doc version. The architect maintains a
**best-so-far** (the version with the highest evaluator `overall`). When a
round **regresses** (delta < 0), the architect discards that round's changes
and reverts to the best-so-far — the design monotonically improves; bad rounds
are undone, not accumulated. v1's critique rounds only stacked; v2 can say
"that round made it worse, revert." The best-so-far is the ADR's basis at
convergence or ceiling.

## Rubric — stakes sets the tier, evaluator, max rounds, and PO's role

| Stakes (PO-declared) | Council shape | Evaluator | Max rounds | PO interaction |
|---|---|---|---|---|
| **Low** (prototype / internal / throwaway) | 1 research + 1 peer, 1 round | **none** (1 round, converges immediately) | 1 | none |
| **Standard** (default) | 1 research + 1 peer (+1 if high complexity), ≤3 rounds | **single judge** (`verifier`) | 3 | **interview** — one live intercom `ask` before the ADR |
| **High** (revenue / safety / brand / hard-to-reverse) | 1 research + 2-3 peers + critic, ≤5 rounds; `after:[synthesis, PO review]` per round | **ensemble of 3** (`verifier` ×3, averaged) | 5 | **review** card after each synthesis (product fit) **+ interview** (live ask) before the ADR |

The evaluator's **plateau threshold** (standard): score delta < 0.3 over 2
consecutive rounds → converged. High-stakes ensemble: convergence requires
*agreement* — no judge disagrees on a critical flag, and the averaged overall
≥ 4.0.

The PO *review* judges **product fit only** — does the synthesis serve the
user/business and honor the stakes? Technical correctness is the evaluator's
job, not the PO's.

## Building the `kanban_chains` call + the evaluator card + the intercom `ask`

Templates (floor / standard / high-stakes / critique / evaluator / ensemble /
PO-review / intercom-ask) with a worked example are in
[`references/call-templates.md`](references/call-templates.md). Inline
essentials:

- **chains** run in parallel — one chain per perspective. The researcher chain
  carries `skills: ["research"]`. Each peer-architect body says *"read the
  blackboard; do not read sibling perspectives."*
- **Evaluator card** (standard + high, after each synthesis): a card assigned
  to `verifier` with the design-doc version + a pointer to
  `references/evaluator-rubric.md`. The evaluator returns the output schema;
  you act on the verdict (step 4). **At high stakes, fan out 3 evaluator
  cards** (the ensemble); average the scores, union the flags, require
  agreement on criticals.
- **Standard:** no `after` → you synthesize after the intercom *interview*,
  then the evaluator scores the synthesis.
- **High:** `after: [synthesis, PO review]` per round → a peer proposes, the PO
  reviews it for product fit, then the evaluator scores.
- **Interview:** intercom `ask` to `startup/product-owner` on the card's topic;
  block; timeout → re-ask or block (never proceed without PO input).
- Use `kanban_chains` exclusively — never `delegate_task`. Board cards survive
  session boundaries and are observable; subagents do not and are not.
