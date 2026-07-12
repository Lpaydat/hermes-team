# `kanban_chains` + evaluator + intercom call templates for design-council v2

`kanban_chains` creates the topology atomically and parks the caller (you) in dependency-wait until the terminal step completes; idempotent. Plugin: `startup/plugins/kanban_chains/`. Step fields: `assignee`, `title`, `body` (required), optional `skills`. With no `after`, you block on each chain terminal and synthesize yourself on resume.

**v2 change:** after each synthesis, you create an **evaluator card** (the independent judge). The evaluator scores across the five rubric dimensions ([`evaluator-rubric.md`](evaluator-rubric.md)) and returns an output schema with a verdict (`improve | converged | regressed`). You act on the verdict: improve → targeted critique; converged → interview + ADR; regressed → revert to best-so-far.

## Low stakes — floor (no evaluator, no PO interaction)

```python
kanban_chains({
  "goal": "Council: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: options, prior art, evidence",
       "body": "Decision: <one-line>. Constraints: <from brief>. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — <DECISION>",
       "body": "Independent take. Read the blackboard; do not read sibling perspectives. State your recommendation and the one risk you'd flag." }],
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "low" } }
})
# You are parked. On promotion: read both, synthesize, write the ADR. No evaluator, no PO step.
# Low stakes = 1 round; the floor IS the ceiling.
```

## Standard — diverge → synthesize → evaluate → (improve loop) → interview → ADR

### Round 1 — diverge (no `after`)

```python
kanban_chains({
  "goal": "Council: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>",
       "body": "Decision: <one-line>. Constraints: <from brief>. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — <DECISION>",
       "body": "Independent. Read blackboard; do not read siblings." }],
    # +1 peer when complexity is high
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "standard" } }
})
# On promotion: read research + perspective, SYNTHESIZE a design-doc version, then create the EVALUATOR card below.
```

### Evaluator card — after each synthesis (standard: single judge)

A card you create (via `kanban_create` or as a worker in a `kanban_chains` call) after synthesizing. The judge is the `verifier` profile — an independent context, never your reasoning trace.

```python
kanban_create({
  "title": "[evaluate] Round <N> — <DECISION>",
  "assignee": "verifier",
  "body": """You are the INDEPENDENT EVALUATOR for a design-council round.
Score the design-doc version below across five rubric dimensions.

DESIGN DOC (round <N>):
<your synthesized design-doc version — the full text>

RUBRIC: load startup/profiles/architect/skills/architecture/design-council/references/evaluator-rubric.md
Score each dimension 1-5 against the concrete anchors. Every score ≤ 4 needs a flagged_weakness citing the exact passage.

Return this output schema (and nothing else):
{
  "round": <N>,
  "design_version": "<slug>",
  "dimension_scores": {"correctness":..., "depth":..., "alternatives":..., "edge_cases":..., "consequences":...},
  "overall": <mean>,
  "delta_vs_last": <null on round 1, else overall_N - overall_{N-1}>,
  "flagged_weaknesses": [{"dimension":"...", "issue":"...", "severity":"critical|important|minor", "citation":"..."}],
  "verdict": "improve | converged | regressed",
  "notes": "..."
}

Grounded flags only — cite the passage. Unanchored flags will be discarded as noise.
""",
  "parents": ["<your-task-id>"]   # park yourself
})
```

- **On the evaluator's return:** read the verdict. `improve` → targeted critique round (below). `converged` → interview + ADR. `regressed` → revert to best-so-far, re-evaluate or proceed to ceiling.
- **Store the best-so-far:** keep the design-doc version with the highest `overall`. This is the revert target and the eventual ADR basis.

### Critique round — round 2+ when verdict is `improve` (targeted by evaluator flags)

```python
kanban_chains({
  "goal": "Council critique round <N>: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research the gap: <SPECIFIC FLAG FROM EVALUATOR>",
       "body": "Resolve this specific gap with evidence; post to blackboard. Evaluator flag: '<issue + citation>'. The current design is weak here: <detail>." }],
    [{ "assignee": "architect",
       "title": "Red-team round-<N-1> for <DECISION> — keyed to evaluator flags",
       "body": "Attack the prior design specifically on: <list the evaluator's flagged_weaknesses>. Name failure modes, missing alternatives, thinnest evidence. Read blackboard; do not read siblings." }],
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": <N>, "stakes": "standard" } }
})
# On promotion: synthesize the improved version, create ANOTHER evaluator card (same template, round <N>).
# Compare the new overall to the best-so-far. If higher → new best-so-far. If lower → DISCARD, revert.
```

## High stakes — full fan-out + PO review + ensemble evaluator

### Round 1 — diverge + synthesis + PO review (fan-out with `after`)

```python
kanban_chains({
  "goal": "Council (high-stakes): <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>",
       "body": "..." }],
    [{ "assignee": "architect",
       "title": "Perspective A — <DECISION>", "body": "Independent. Read blackboard; do not read siblings." }],
    [{ "assignee": "architect",
       "title": "Perspective B — <DECISION>", "body": "Independent. Read blackboard; do not read siblings." }],
    # + a 3rd peer for safety/brand-critical decisions
  ],
  "after": [
    { "assignee": "architect",
      "title": "Synthesize <DECISION> -> proposal + gaps",
      "body": "Weigh >=2 alternatives against research + perspectives. Output: chosen decision, residual gaps. This becomes the design-doc version for the evaluator." },
    { "assignee": "product-owner",
      "title": "PO review (product fit) — <DECISION>",
      "body": "Read the synthesis. Judge PRODUCT FIT only: does it serve the user/business and honor the stakes? Confirm, or request changes with reasons. Do not assess technical correctness — that's the evaluator's job. Post your verdict + any constraints to the blackboard." },
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "high" } }
})
# On promotion: read research + perspectives + synthesis + PO review. Then create the ENSEMBLE EVALUATOR (3 cards).
```

### Ensemble evaluator — 3 independent judges (high stakes)

Create **three** evaluator cards (same body template as the standard evaluator card, but each is a separate `verifier` session with an independent context). On return:

1. **Average** the three `overall` scores → ensemble overall.
2. **Union** the `flagged_weaknesses` (dedupe by citation).
3. **Critical-flag agreement:** if any judge scored correctness ≤ 2 (a critical flag), ALL THREE must agree it's a real critical for it to block convergence. A single-judge critical that the other two don't see → treated as important (the noise-floor protection at scale).
4. **Convergence:** ensemble overall ≥ 4.0 AND no agreed-critical → converged. Otherwise → `improve` (targeted critique, re-evaluate with a fresh ensemble).

### High-stakes critique round

Same as the standard critique round, but `after: [re-synthesis, PO review]`, and the evaluator is a fresh ensemble of 3.

## Intercom INTERVIEW — standard + high, before the ADR (step 5)

A tool call you make on resume, *not* part of `kanban_chains`. The PO is idle (no live session); the broker spawns a PO session to receive the ask and reply.

```
intercom:
  action: ask                     # blocks for the reply — the broker spawns the offline PO
  to:     startup/product-owner   # qualified form — bare names route wrong
  topic:  <the card's intercom topic>
  text:   "Before I write the ADR for <DECISION>: the evaluator converged at round <N>
           (overall <score>). My lean is <proposal>, grounded in <research + perspective>.
           Open trade-off: <the genuine product call>. What is the product priority here?
           Any constraint I'm missing?"
```

- **`ask` blocks** until the PO replies (the broker spawns the PO, which answers via `action: reply`). Returns within ~30s.
- **Timeout → re-ask or block the card `needs_input`.** Never write the ADR without the PO's input. Cite the interview in the ADR's Citations.
- **Known limitation:** if the offline-spawn path is broken (bead `hermes-teams-4hf`), the ask may return `[target_not_connected]`. Per the skill: block `needs_input`, do not shortcut.

## Worked example — standard-stakes rate-limiting with the evaluate loop

Stakes **standard**. Round 1:

```python
# Diverge
kanban_chains({
  "goal": "Council: rate-limiting strategy",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research rate-limiting: nginx limit_req vs app-level vs Redis token bucket",
       "body": "PII-aware, 1000 tenants, <budget>. Post to blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — rate-limiting", "body": "Independent. Read blackboard; do not read siblings." }],
  ],
  "blackboard": { "extra": { "decision": "rate-limiting", "round": 1, "stakes": "standard" } }
})
# On promotion: synthesize design-doc v1. Create evaluator card.
```

Evaluator returns: `overall: 3.2, flagged_weaknesses: [{dimension: correctness, issue: "conflates limit_req (leaky) with token bucket", severity: critical, citation: "§ Decision: 'token-bucket via limit_req'"}], verdict: improve`

Critique round (targeted at the conflation flag):

```python
kanban_chains({
  "goal": "Council critique round 2: rate-limiting",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research the gap: limit_req semantics (leaky vs token bucket)",
       "body": "Evaluator flagged a correctness conflation. Resolve: what algorithm does nginx limit_req actually implement? What are the implications for burst handling? Post to blackboard." }],
    [{ "assignee": "architect",
       "title": "Red-team round-1 rate-limiting — keyed to correctness flag",
       "body": "The evaluator flagged: 'conflates limit_req (leaky) with token bucket'. Attack the prior design on this point. Read blackboard; do not read siblings." }],
  ],
  "blackboard": { "extra": { "decision": "rate-limiting", "round": 2, "stakes": "standard" } }
})
# On promotion: synthesize design-doc v2 (corrected algorithm). Create evaluator card (round 2).
```

Evaluator returns: `overall: 4.1, delta_vs_last: +0.9, flagged_weaknesses: [{dimension: consequences, issue: "cost number vague", severity: minor}], verdict: converged` → proceed to interview + ADR. (The minor flag is below the noise floor; it doesn't block convergence.)

## Notes

- **Idempotent recovery.** Interrupted after the call? Re-dispatch resumes your session; calling `kanban_chains` again with the same goal recovers the topology rather than duplicating cards.
- **Peer independence.** Each `assignee: "architect"` chain is a separate spawned session (no live architect gateway), so perspectives are genuinely independent — they share only the blackboard.
- **Evaluator independence.** The evaluator is the `verifier` profile — a separate spawned session. It sees only the design-doc version + the rubric, never your synthesis reasoning. This is the maker/checker separation applied to design.
- **Best-so-far tracking.** Keep the design-doc version with the highest evaluator `overall`. On regression (delta < 0), discard the regressed version and revert. The best-so-far is the ADR basis.
- **Do not call `kanban_complete` while parked.** You auto-promote when the terminal step completes; only then evaluate → decide → interview → write the ADR.
