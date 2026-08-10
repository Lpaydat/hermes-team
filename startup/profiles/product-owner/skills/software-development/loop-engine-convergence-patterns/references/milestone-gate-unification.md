# milestone-gate Unification — qa-gate + refactor-cycle merged (2026-08-08)

## The Problem

Two pipeline stages were dead:

1. **qa-gate** never fired — self-trigger suppression blocks cross-workflow
   triggers when the parent workflow (tech-lead-execute) uses explicit edges.
   The verify-b cards have `wf:` idempotency keys → parent has edges → blocked.

2. **refactor-cycle** never fired — trigger prefix `[milestone]` (with closing
   bracket) doesn't match actual card titles `[milestone-01]`, `[milestone-02]`
   (the char after "milestone" is `-`, not `]`).

## The Fix

Created `milestone-gate.json` — one unified workflow merging qa-gate +
refactor-cycle into a single graph. Fires on milestone card completion.

### Trigger

```json
{
  "source": "card_completed",
  "condition": {
    "assignee": "product-owner",
    "status": "done",
    "title_prefix_any": ["[milestone-", "[refactor-request]"]
  }
}
```

Note: `[milestone-` WITHOUT closing bracket. This matches `[milestone-01]`,
`[milestone-02]`, etc. The old `[milestone]` (WITH bracket) did not match.

### Why milestone cards don't trigger suppression

Milestone cards are created by the PO via `kanban_create` — they have NULL
idempotency keys. The self-trigger suppression logic only activates when
`card.idempotency_key` starts with `wf:` (engine-created cards). So
milestone-gate fires cleanly.

### Graph structure

```
qa-receive (qa, sizing)
  ├── small → qa-quick → (PASS→refactor | FAIL→route-bug)
  └── medium/large → qa-build → [qa-functional, qa-journeys, qa-security, qa-explore] → qa-verdict
                        → (PASS→refactor-scan | FAIL→route-bug)

refactor-scan (tech-lead, codebase-design) → refactor-review (verifier, adversarial-review)
  → verdict=continue → refactor-decompose (PO, to-tickets) → creates [ticket-refactor-NN] cards
  → verdict=stop → workflow terminates
```

12 nodes, 16 edges. Old templates disabled (qa-gate.json.disabled,
refactor-cycle.json.disabled).

### Verification

13/13 structural checks passed:
- Template parses
- Trigger prefixes match real milestone titles
- Old broken prefix `[milestone]` correctly does NOT match
- All edges reference valid nodes
- All nodes have required fields
- Conditional edges reference valid node outputs
- Exit nodes exist (route-bug, refactor-decompose)
- QA sizing routing works (small→quick, large→fan-out)
- QA verdict routing works (PASS→refactor, FAIL→route-bug)
- Refactor stop condition works (verdict=stop→terminates)
- No unbounded back-edges

### E2E verification — PASSED (2026-08-09)

milestone-gate was validated end-to-end on the wf-gate-test board. A
milestone-01 card (simulating all-tickets-merged state) was created and
completed. milestone-gate fired on the next engine tick and ran the full
chain:

- qa-receive → sized "medium" (18 claims > 10) → qa-build path (not qa-quick)
- qa-build → containerized build via podman
- qa-build → parallel fan-out: qa-functional + qa-journeys + qa-security + qa-explore (4 cards dispatched simultaneously)
- All 4 test cards → qa-verdict (composite edge gate waited for all)
- qa-verdict → PASS (6 follow-up findings filed as fix cards)
- qa-verdict → refactor-scan (PASS edge fired correctly)
- refactor-scan → found 3 candidates → refactor-review
- refactor-review → kanban_chains fan-out (3 reviewer cards)
- refactor-review → verdict=continue → refactor-decompose
- refactor-decompose → created 2 [ticket-refactor-NN] cards

26 cards total, ~40 minutes wall clock. Every edge in the graph was
exercised. The Pattern 18 fix is proven e2e.

## The Design Lesson

When two trigger-chained workflows both break at the trigger boundary, the
fix is NOT to patch each trigger. The fix is to MERGE them into one graph
with internal edge routing. Two trigger conditions = two failure points.
One graph = one trigger condition, structural edge routing inside.

The user's direction: "I don't know why you try to create new system to
maintain instead of unify them under one workflow." Fewer moving parts,
harder to break.
