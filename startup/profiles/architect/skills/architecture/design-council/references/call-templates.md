# `kanban_chains` + intercom call templates for design-council

`kanban_chains` creates the topology atomically and parks the caller (you) in dependency-wait until the terminal step completes; idempotent. Plugin: `startup/plugins/kanban_chains/`. Step fields: `assignee`, `title`, `body` (required), optional `skills`. With no `after`, you block on each chain terminal and synthesize yourself on resume.

## Low stakes — floor (no PO interaction)

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
# You are parked. On promotion: read both, synthesize, write the ADR. No PO step.
```

## Standard — live intercom interview before the ADR (no `after`)

```python
kanban_chains({
  "goal": "Council: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>", "body": "..." }],
    [{ "assignee": "architect",
       "title": "Perspective — <DECISION>",
       "body": "Independent. Read blackboard; do not read siblings." }],
    # +1 peer when complexity is high
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "standard" } }
})
# On promotion: read research + perspective, run the intercom INTERVIEW below, then synthesize + write ADR.
```

## High stakes — full fan-out, synthesis + PO review per round

```python
kanban_chains({
  "goal": "Council (high-stakes): <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research <DECISION>", "body": "..." }],
    [{ "assignee": "architect",
       "title": "Perspective A — <DECISION>", "body": "Independent. Read blackboard; do not read siblings." }],
    [{ "assignee": "architect",
       "title": "Perspective B — <DECISION>", "body": "Independent. Read blackboard; do not read siblings." }],
    # + a 3rd peer for safety/brand-critical decisions
  ],
  "after": [
    { "assignee": "architect",
      "title": "Synthesize <DECISION> -> proposal + confidence + gaps",
      "body": "Weigh >=2 alternatives against research + perspectives. Output: chosen decision, confidence (H/M/L), residual gaps." },
    { "assignee": "product-owner",
      "title": "PO review (product fit) — <DECISION>",
      "body": "Read the synthesis. Judge PRODUCT FIT only: does it serve the user/business and honor the stakes? "
              "Confirm, or request changes with reasons. Do not assess technical correctness — that's the critic's job. "
              "Post your verdict + any constraints to the blackboard." },
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": 1, "stakes": "high" } }
})
# On promotion: read research + perspectives + synthesis + PO review. Decide (step 4).
# If a critique round runs, it reuses after:[re-synthesis, PO review].
# Before the final ADR, run the intercom INTERVIEW below.
```

## Critique round — round 2+ when confidence is not High (high stakes adds PO review)

```python
kanban_chains({
  "goal": "Council critique round <N>: <DECISION>",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research the gap: <GAP FROM LAST ROUND>",
       "body": "Resolve this specific gap with evidence; post to blackboard." }],
    [{ "assignee": "architect",
       "title": "Red-team the round-<N-1> proposal for <DECISION>",
       "body": "Attack the prior decision. Name failure modes, missing alternatives, thinnest evidence. Read blackboard; do not read siblings." }],
  ],
  # high stakes only:
  "after": [
    { "assignee": "architect", "title": "Re-synthesize <DECISION> -> revised proposal + confidence + gaps", "body": "..." },
    { "assignee": "product-owner", "title": "PO review (product fit) — round <N>", "body": "Judge product fit of the revised synthesis." },
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "<slug>", "round": <N>, "stakes": "<tier>" } }
})
```

## Intercom INTERVIEW — standard + high, before the ADR (step 5)

A tool call you make on resume, *not* part of `kanban_chains`. The PO is idle (no live session); the broker spawns a PO session to receive the ask and reply.

```
intercom:
  action: ask                     # blocks for the reply — the broker spawns the offline PO
  to:     startup/product-owner   # qualified form — bare names route wrong
  topic:  <the card's intercom topic>
  content: "Before I write the ADR for <DECISION>: my lean is <proposal>, grounded in
            <research + perspective>. Open trade-off: <the genuine product call, e.g.
            strictness vs UX>. What is the product priority here? Any constraint I'm missing?"
```

- **`ask` blocks** until the PO replies (the broker spawns the PO, which answers via `action: reply`). Returns within ~30s.
- **Timeout → re-ask or block the card `needs_input`.** Never write the ADR without the PO's input. Cite the interview in the ADR's Citations.

## Worked example — high-stakes B2B multi-tenancy

Stakes **high** (customer PII + billing, hard-to-reverse). Round 1:

```python
kanban_chains({
  "goal": "Council (high-stakes): multi-tenancy + data isolation for B2B SaaS",
  "chains": [
    [{ "assignee": "researcher", "skills": ["research"],
       "title": "Research shared-DB-with-tenant_id vs schema-per-tenant vs DB-per-tenant for PII + isolation + cost",
       "body": "PII isolation, backup/restore granularity, migration cost, <budget>. Post to blackboard." }],
    [{ "assignee": "architect", "title": "Perspective A — multi-tenancy", "body": "Independent. Read blackboard; do not read siblings." }],
    [{ "assignee": "architect", "title": "Perspective B — multi-tenancy", "body": "Independent. Read blackboard; do not read siblings." }],
  ],
  "after": [
    { "assignee": "architect", "title": "Synthesize multi-tenancy -> proposal + confidence + gaps", "body": "..." },
    { "assignee": "product-owner", "title": "PO review (product fit) — multi-tenancy",
      "body": "Judge product fit: enterprise customer expectations, isolation-as-a-feature, pricing-tier implications." },
  ],
  "blackboard": { "spec_path": "<brief>", "env_facts": "<constraints>", "extra": { "decision": "multi-tenancy", "round": 1, "stakes": "high" } }
})
# If confidence M/L (e.g. "cross-tenant leak risk unproven"), run a critique round on that gap.
# Before the ADR: intercom INTERVIEW the PO on isolation-vs-cost trade-off. Then write the ADR.
```

## Notes

- **Idempotent recovery.** Interrupted after the call? Re-dispatch resumes your session; calling `kanban_chains` again with the same goal recovers the topology rather than duplicating cards.
- **Peer independence.** Each `assignee: "architect"` chain is a separate spawned session (no live architect gateway), so perspectives are genuinely independent — they share only the blackboard.
- **PO is online.** The product-owner gateway is live; the intercom `ask` and PO review cards route to it.
- **Do not call `kanban_complete` while parked.** You auto-promote when the terminal step completes; only then interview + synthesize + write the ADR.
