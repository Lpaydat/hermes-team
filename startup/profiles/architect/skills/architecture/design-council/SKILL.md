---
name: design-council
description: Run an irreversible design decision through a research-backed council before recording the ADR. Use when you owe an architecture decision or ADR, or when a design-it-twice comparison is called for — any design output that must not come from one agent's memory alone.
---

A design decision owed by the architect is **council** work, not memory retrieval. The council **fans out** research and peer-architect perspectives via `kanban_chains`, which **parks** the architect until they complete — so the ADR is built from research, critique, and a live PO discussion, never from one agent's training memory. The virtue here is *predictability*: the same process on every decision.

**Leading words.** *council* — the multi-perspective deliberation. *parked* — your card blocked in dependency-wait by `kanban_chains`, auto-promoted when the terminal step completes. *stakes* — the project's value/risk tier, **declared by the PO on the design card** (low / standard / high); sets the council tier *and* the PO's role. *floor* / *ceiling* — the minimum and maximum council effort. *diverge* (round 1, independent perspectives) → *critique* (round 2+, adversarial) → *synthesize*. *review* — a PO card checking a synthesis for **product fit** (high stakes, each round). *interview* — a live intercom `ask` with the PO before the ADR (standard + high). *blackboard* — the shared root card `kanban_chains` creates.

## Decompose into decisions — and check coverage

Break the design into decisions (one ADR each), one **phase** at a time. Use the architectural dimensions as a **coverage checklist**, not as fan-out cards: data model, security/auth, infrastructure/deployment, API surface, cross-cutting. Ensure your decision set covers each dimension that applies.

## The loop — one decision

1. **Assess.** Take **stakes** from the card (PO-declared). Rate complexity by the blast-radius instinct. Stakes fixes the council tier *and* the PO-interaction model (rubric below). You may escalate a decision above the project tier with reason.
   *Done when:* stakes, complexity, council shape, and PO-interaction model are all recorded.

2. **Diverge.** Call `kanban_chains` with the round-1 shape for your tier — **standard**: research + peer chains, **no `after`** (you synthesize). **High**: research + peer chains + `after: [synthesis, PO review]` (a peer synthesizes, the PO reviews it). Park.
   *Done when:* `kanban_chains` returned and your card is in dependency-wait. You wrote nothing, and you did not call `kanban_complete` — you auto-promote when the terminal step completes.

3. **Read inputs.** On re-dispatch, read research + perspectives (+ the synthesis and PO *review* at high stakes). Form proposed decision + **confidence** (H/M/L) + residual **gaps**.
   *Done when:* you can state the proposal, your confidence, and each gap.

4. **Decide.** High confidence → step 5. Medium/Low, and a round remains → run a *critique* round (`kanban_chains`: targeted research + red-team; high stakes adds `after: [re-synthesis, PO review]`); return to step 3. Ceiling → step 5 with residual risks.

5. **Interview the PO** (standard + high; **skip at low stakes**). Use the intercom tool with **`action: ask`** to `startup/product-owner` on the card's topic with your open trade-off questions. The PO has no live session, so the broker spawns one to receive the ask and reply — **`ask` blocks for the reply** (returns within ~30s). Fold the reply into the decision. **If the ask times out, re-ask or block the card `needs_input` — never write the ADR without the PO's input.**
   *Done when:* the PO has replied (or the card is blocked awaiting them).

6. **Record the ADR.** Write to `docs/adr/` per `docs/agents/adr-convention.md` (Context / Alternatives Considered / Decision / Consequences / Citations). Cite research, perspectives, synthesis, PO *review*(s) (high), and the PO *interview*. Ceiling hit → add a *Residual risks* section and block `needs_input`.
   *Done when:* ADR on disk, all council inputs cited, convention sections present, and — if the ceiling was hit — the card is blocked for review.

## The floor

Every ADR is the output of at least one council round — **≥1 research card + ≥1 peer-architect perspective**, with you parked throughout, never memory-only. Low stakes meets this with the minimum (research + 1 peer, no PO interaction).

## The ceiling

Max **3 rounds** per decision. Confidence still not high at the ceiling → record the ADR with a *Residual risks* section and block `needs_input`.

## Rubric — stakes sets the tier, the council shape, and the PO's role

| Stakes (PO-declared) | Council shape | PO interaction |
|---|---|---|
| **Low** (prototype / internal / throwaway) | 1 research + 1 peer, 1 round | none |
| **Standard** (default) | 1 research + 1 peer (+1 if high complexity), ≤2 rounds | **interview** — one live intercom `ask` before the ADR |
| **High** (revenue / safety / brand / hard-to-reverse) | 1 research + 2-3 peers + critic, ≤3 rounds; `after:[synthesis, PO review]` per round | **review** card after each synthesis (product fit) **+ interview** (live ask) before the ADR |

The PO *review* judges **product fit only** — does the synthesis serve the user/business and honor the stakes? Technical correctness is the critic's job, not the PO's.

## Building the `kanban_chains` call + the intercom `ask`

Templates (floor / standard / high-stakes / critique / PO-review / intercom-ask) with a worked example are in [`references/call-templates.md`](references/call-templates.md). Inline essentials:

- **chains** run in parallel — one chain per perspective. The researcher chain carries `skills: ["research"]`. Each peer-architect body says *"read the blackboard; do not read sibling perspectives."*
- **Standard:** no `after` → you synthesize after the intercom *interview*.
- **High:** `after: [synthesis, PO review]` per round → a peer proposes, the PO reviews it for product fit, then you resume.
- **Interview:** intercom `ask` to `startup/product-owner` on the card's topic; block; timeout → re-ask or block (never proceed without PO input).
- Use `kanban_chains` exclusively — never `delegate_task`. Board cards survive session boundaries and are observable; subagents do not and are not.
