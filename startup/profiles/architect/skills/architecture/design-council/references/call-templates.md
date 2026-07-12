# `kanban_chains` + evaluator + intercom call templates for design-council v2

`kanban_chains` creates the topology atomically and parks the caller (you) in dependency-wait until the terminal step completes; idempotent. Plugin: `startup/plugins/kanban_chains/`. Step fields: `assignee`, `title`, `body` (required), optional `skills`. With no `after`, you block on each chain terminal and synthesize yourself on resume.

**v2 change (evaluator):** after each synthesis, you create an **evaluator card** (the independent judge). The evaluator scores across the five rubric dimensions ([`evaluator-rubric.md`](evaluator-rubric.md)) and returns an output schema with a verdict (`improve | converged | regressed`). You act on the verdict: improve → targeted critique; converged → interview + ADR; regressed → revert to best-so-far.

**v2 change (no subagents — multi-researcher fan-out).** Every agent in the design-council loop is a kanban card dispatched by the gateway. NO agent spawns background subagents — they are fragile (concurrency-starvation under parallel load + solo budget-exhaustion, where one background subagent burns the whole iteration budget alone) and not how this team works. You (the architect) decompose the research into **parallel sub-topics, one researcher card each** (standard: 2, high: 3, critique: one per evaluator flag; low stays 1 for cost-discipline). You pick the sub-topics in your decomposition step from the decision + the architectural dimensions that apply. Each researcher card names a SPECIFIC sub-topic and carries this clause verbatim: *"Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find."*

**Root-cause override — the researcher's own skill is neutralized here.** The `researcher` profile's `research` skill describes background-subagent fan-out as its normal mode. **Inside the design council that is forbidden** — the architect does the decomposition into parallel cards, not the researcher into background subagents. This is a structural fix at the actual leak source, not a card-body incantation.

Every other card in the loop (peer perspective, red-team, evaluator, PO review, synthesis) carries the short form: *"Do NOT spawn background subagents — work directly in your session."* Researcher cards are independent — each researches its own sub-topic from primary sources and does **not** read the other researcher cards' working; you synthesize across them (same independence rule as peer perspectives, which read the blackboard but not each other).

## Low stakes — floor (no evaluator, no PO interaction)

```python
kanban_chains({
  "goal": "Council: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <THE ONE SUB-TOPIC>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <the single sub-topic the decision turns on>. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — <DECISION>",
       "body": "Independent take. Read the blackboard; do not read sibling perspectives. Do NOT spawn background subagents — work directly in your session. State your recommendation and the one risk you'd flag." }],
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "low" } }
})
# You are parked. On promotion: read both, synthesize, write the ADR. No evaluator, no PO step.
# Low stakes = 1 round, 1 researcher card (a throwaway doesn't earn a fan-out — cost-discipline);
# the floor IS the ceiling.
```

## Standard — diverge → synthesize → evaluate → (improve loop) → interview → ADR

### Round 1 — diverge (no `after`)

**Decompose before the call:** from the decision statement + the architectural dimensions it touches (data model, security/auth, infrastructure/deployment, API surface, cross-cutting), pick **2 sub-topics** that together cover the decision's research surface. Name each concretely — not "research X" but "research X: <the specific angle>".

```python
kanban_chains({
  "goal": "Council: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <SUB-TOPIC 1>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <specific sub-topic, e.g. 'algorithm semantics across nginx limit_req vs app-level vs Redis token bucket'>. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <SUB-TOPIC 2>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <specific sub-topic, e.g. 'multi-tenant cost/scale at 1000 tenants, PII-aware'>. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — <DECISION>",
       "body": "Independent. Read blackboard; do not read siblings (other perspectives OR researcher cards). Do NOT spawn background subagents — work directly in your session." }],
    # +1 peer when complexity is high
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "standard" } }
})
# On promotion: read BOTH researcher cards + the perspective, SYNTHESIZE a design-doc version, then create the EVALUATOR card below.
```

### Evaluator card — after each synthesis (standard: single judge)

A card you create (via `kanban_create` or as a worker in a `kanban_chains` call) after synthesizing. The judge is the `verifier` profile — an independent context, never your reasoning trace.

```python
kanban_create({
  "title": "[evaluate] Round <N> — <DECISION>",
  "assignee": "verifier",
  # NO parents field! Setting parents: ["<your-task-id>"] creates a CIRCULAR
  # DEADLOCK: the evaluator can't promote to ready until your task is done,
  # but your task is blocked waiting for the evaluator. Create with no parents,
  # then kanban_block(kind="dependency") on your own task to park yourself.
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
Do NOT spawn background subagents — judge directly in your session.
"""
})
# THEN park yourself (blocks your task until the evaluator completes):
kanban_block(kind="dependency", reason="waiting_for_evaluator:<evaluator-task-id>")
```

- **PITFALL:** Do NOT pass `parents: ["<your-task-id>"]` on the evaluator card. This creates a circular deadlock — the evaluator cannot promote to `ready` until your task is `done`, but your task is blocked waiting for the evaluator. Create the evaluator with no parents, then `kanban_block` your own task.
- **On the evaluator's return (re-dispatch):** read the verdict. `improve` → targeted critique round (below). `converged` → interview + ADR. `regressed` → revert to best-so-far, re-evaluate or proceed to ceiling.
- **Store the best-so-far:** keep the design-doc version with the highest `overall`. This is the revert target and the eventual ADR basis.

### Critique round — round 2+ when verdict is `improve` (targeted by evaluator flags)

Emit **one researcher card per evaluator flag** (each flag gets its own focused resolution, in parallel), plus the red-team. If the evaluator raised 2 flags, that's 2 researcher cards; if 1 flag, 1 researcher card. No severity filter — one card per flag, period; the noise floor already gates convergence (a minor-only state converges and never reaches critique). Each researcher card names the SPECIFIC flag it resolves and is told not to spawn subagents. The researcher cards are parallel and independent — none reads the others' working.

```python
kanban_chains({
  "goal": "Council critique round <N>: <DECISION>",
  "chains": [
    # One researcher card PER evaluator flag — repeat this block once per flag:
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Resolve flag — <DIMENSION>: <SHORT FLAG>",
       "body": "Evaluator flag: '<issue + citation>'. The current design is weak here: <detail>. YOUR FOCUSED TASK: resolve THIS specific flag with evidence. Research it from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    # ...repeat the researcher block above once per flag, naming each flag...
    [{ "assignee": "architect",
       "title": "Red-team round-<N-1> for <DECISION> — keyed to evaluator flags",
       "body": "Attack the prior design specifically on: <list the evaluator's flagged_weaknesses>. Name failure modes, missing alternatives, thinnest evidence. Read blackboard; do not read siblings. Do NOT spawn background subagents — work directly in your session." }],
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": <N>, "stakes": "standard" } }
})
# On promotion: synthesize the improved version, create ANOTHER evaluator card (same template, round <N>).
# Compare the new overall to the best-so-far. If higher → new best-so-far. If lower → DISCARD, revert.
```

## High stakes — full fan-out + PO review + ensemble evaluator

### Round 1 — diverge + synthesis + PO review (fan-out with `after`)

**Decompose before the call:** from the decision statement + the architectural dimensions it touches, pick **3 sub-topics** that together cover the decision's research surface (high-stakes decisions usually span ≥3 dimensions — that is why the tier gets 3). Name each concretely.

```python
kanban_chains({
  "goal": "Council (high-stakes): <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <SUB-TOPIC 1>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <specific>. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <SUB-TOPIC 2>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <specific>. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>: <SUB-TOPIC 3>",
       "body": "Decision: <one-line>. Constraints: <from brief>. YOUR FOCUSED SUB-TOPIC: <specific>. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective A — <DECISION>", "body": "Independent. Read blackboard; do not read siblings (other perspectives OR researcher cards). Do NOT spawn background subagents — work directly in your session." }],
    [{ "assignee": "architect",
       "title": "Perspective B — <DECISION>", "body": "Independent. Read blackboard; do not read siblings (other perspectives OR researcher cards). Do NOT spawn background subagents — work directly in your session." }],
    # + a 3rd peer for safety/brand-critical decisions
  ],
  "after": [
    { "assignee": "architect",
      "title": "Synthesize <DECISION> -> proposal + gaps",
      "body": "Weigh >=2 alternatives against research (ALL 3 sub-topics) + perspectives. Output: chosen decision, residual gaps. This becomes the design-doc version for the evaluator. Do NOT spawn background subagents — work directly in your session." },
    { "assignee": "product-owner",
      "title": "PO review (product fit) — <DECISION>",
      "body": "Read the synthesis. Judge PRODUCT FIT only: does it serve the user/business and honor the stakes? Confirm, or request changes with reasons. Do not assess technical correctness — that's the evaluator's job. Post your verdict + any constraints to the blackboard. Do NOT spawn background subagents — work directly in your session." },
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "high" } }
})
# On promotion: read all 3 researcher cards + perspectives + synthesis + PO review. Then create the ENSEMBLE EVALUATOR (3 cards).
```

### Ensemble evaluator — 3 independent judges (high stakes)

Create **three** evaluator cards (same body template as the standard evaluator card, but each is a separate `verifier` session with an independent context). On return:

1. **Average** the three `overall` scores → ensemble overall.
2. **Union** the `flagged_weaknesses` (dedupe by citation).
3. **Critical-flag agreement:** if any judge scored correctness ≤ 2 (a critical flag), ALL THREE must agree it's a real critical for it to block convergence. A single-judge critical that the other two don't see → treated as important (the noise-floor protection at scale).
4. **Convergence:** ensemble overall ≥ 4.0 AND no agreed-critical → converged. Otherwise → `improve` (targeted critique, re-evaluate with a fresh ensemble).

### High-stakes critique round

Same shape as the standard critique round — **one researcher card per evaluator flag** (parallel, each resolving its flag from the ensemble's unioned flags) + the red-team — but `after: [re-synthesis, PO review]`, and the evaluator is a fresh ensemble of 3.

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

Stakes **standard**. Before round 1, decompose rate-limiting into 2 sub-topics from its dimensions: sub-topic 1 = algorithm/approach trade-offs (nginx `limit_req` vs app-level vs Redis token bucket — algorithm + burst handling); sub-topic 2 = multi-tenant + PII dimension (per-tenant vs shared limits, tenant-id/PII in keys, isolation at 1000 tenants). Together they cover the decision surface.

```python
# Diverge
kanban_chains({
  "goal": "Council: rate-limiting strategy",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research rate-limiting: algorithm trade-offs (limit_req vs token bucket vs app-level)",
       "body": "Decision: rate-limiting strategy. Constraints: PII-aware, 1000 tenants, <budget>. YOUR FOCUSED SUB-TOPIC: algorithm/approach trade-offs — what algorithm does nginx limit_req actually implement, burst handling, Redis token-bucket semantics. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research rate-limiting: multi-tenant isolation + PII in keys",
       "body": "Decision: rate-limiting strategy. Constraints: PII-aware, 1000 tenants, <budget>. YOUR FOCUSED SUB-TOPIC: multi-tenant + PII dimension — per-tenant vs shared limits, what goes in the key (tenant-id / PII?), isolation under noisy-neighbour load. Research THIS sub-topic from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Perspective — rate-limiting", "body": "Independent. Read blackboard; do not read siblings (other perspectives OR researcher cards). Do NOT spawn background subagents — work directly in your session." }],
  ],
  "blackboard": { "extra": { "decision": "rate-limiting", "round": 1, "stakes": "standard" } }
})
# On promotion: synthesize design-doc v1. Create evaluator card.
```

Evaluator returns: `overall: 3.2, flagged_weaknesses: [{dimension: correctness, issue: "conflates limit_req (leaky) with token bucket", severity: critical, citation: "§ Decision: 'token-bucket via limit_req'"}], verdict: improve`

Critique round — **one researcher card per flag** (here, 1 flag → 1 researcher card) + red-team:

```python
kanban_chains({
  "goal": "Council critique round 2: rate-limiting",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Resolve flag — correctness: limit_req leaky vs token bucket",
       "body": "Evaluator flag: 'conflates limit_req (leaky) with token bucket' (§ Decision). YOUR FOCUSED TASK: resolve THIS specific flag — what algorithm does nginx limit_req actually implement, and what are the implications for burst handling? Research it from primary sources; do not read the other researcher cards' working — the architect synthesizes across all of you. Do NOT spawn background subagents — research directly in your session; if too broad, narrow it and post what you find. Post findings + citations to the blackboard." }],
    [{ "assignee": "architect",
       "title": "Red-team round-1 rate-limiting — keyed to correctness flag",
       "body": "The evaluator flagged: 'conflates limit_req (leaky) with token bucket'. Attack the prior design on this point. Read blackboard; do not read siblings. Do NOT spawn background subagents — work directly in your session." }],
  ],
  "blackboard": { "extra": { "decision": "rate-limiting", "round": 2, "stakes": "standard" } }
})
# On promotion: synthesize design-doc v2 (corrected algorithm). Create evaluator card (round 2).
```

Evaluator returns: `overall: 4.1, delta_vs_last: +0.9, flagged_weaknesses: [{dimension: consequences, issue: "cost number vague", severity: minor}], verdict: converged` → proceed to interview + ADR. (The minor flag is below the noise floor; it doesn't block convergence.)

## Notes

- **No subagents — every agent is a card.** No agent in the design-council loop (architect, researcher, verifier, product-owner) spawns background subagents; every agent is a kanban card dispatched by the gateway. The research fan-out is parallel researcher cards (one per sub-topic at round 1; one per evaluator flag at critique), not subagent spawns. Subagents starve under concurrency and burn the iteration budget solo; board cards do neither and survive session boundaries.
- **Root-cause override.** The `researcher` profile's `research` skill describes background-subagent fan-out as its normal mode. Inside the design council that is **forbidden** — the architect does the decomposition into parallel cards, not the researcher into background subagents. This neutralizes the leak at its source, not just in card-body text.
- **Researcher independence.** Each researcher card is a separate spawned session, independent like the peer cards — it researches its own sub-topic from primary sources and does **not** read the other researcher cards' working. You (the architect) synthesize across all of them. Do not let one sub-topic's framing bleed into another.
- **Coverage is the architect's job.** The union of sub-topic cards must cover the decision's research dimensions. If a dimension the decision touches is left without a card, that is a decomposition defect — fix it before dispatching; do not hope a researcher roams into it. The evaluator scores the synthesis, not the decomposition's completeness.
- **Idempotent recovery.** Interrupted after the call? Re-dispatch resumes your session; calling `kanban_chains` again with the same goal recovers the topology rather than duplicating cards.
- **Peer independence.** Each `assignee: "architect"` chain is a separate spawned session (no live architect gateway), so perspectives are genuinely independent — they share only the blackboard.
- **Evaluator independence.** The evaluator is the `verifier` profile — a separate spawned session. It sees only the design-doc version + the rubric, never your synthesis reasoning. This is the maker/checker separation applied to design.
- **Best-so-far tracking.** Keep the design-doc version with the highest evaluator `overall`. On regression (delta < 0), discard the regressed version and revert. The best-so-far is the ADR basis.
- **Do not call `kanban_complete` while parked.** You auto-promote when the terminal step completes; only then evaluate → decide → interview → write the ADR.