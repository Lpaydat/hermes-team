# kanban_group — SPEC (agreed 2026-08-17, build next)

Deterministic group wiring plugin. Pure **shape**: creates marker cards and
dependency links; never executes, spawns, or completes work. Workflows keep
owning "how" (templates); cards keep owning "what". Built on the hardened
kanban_chains implementation baseline (150s subprocess timeouts, no-raise,
retry ×2 with backoff, every link verified, structured errors with repair
instructions).

## Interface

```json
group_cards({
  "key": "milestone-2-barrier",          // REQUIRED — idempotency anchor
  "board": "auto",                        // HERMES_KANBAN_BOARD env, or explicit
  "members": [                            // REQUIRED ≥1 — the group's real work
    {"card": "t_a1", "done": "t_g1"},     // card to BLOCK : marker meaning done
    "t_x9"                                // shorthand: card is its own marker
  ],
  "pre": [                                // ordered stages before ANY member unlocks
    {"gate": "t_qadone1"},                //   existing card — wait on completion
    {"assignee": "qa", "title": "...", "body": "...", "skills": []}  // or create
  ],
  "post": [                               // after ALL member done-markers (fan-in)
    [{"assignee": "verifier", "...": "..."},
     {"assignee": "qa", "...": "..."}]    // sub-list = parallel
  ],
  "await_caller": false                   // park calling card until post completes
})
```

Returns always-structured JSON: `{status: wired|recovered|error, group_key,
pre[], members[], post[], links[{parent,child,verified}], graph (mermaid),
error?{code,message,repair}}`. Never raises to the agent.

## Semantics contract

1. Unlock: member becomes ready only when EVERY pre stage marker is done
   (AND). Stage sub-lists parallel, stage array sequential.
2. Fan-in: post stage starts only when ALL member `done` markers done;
   post stages sequential, sub-lists parallel.
3. Idempotency: `key` derives deterministic card idempotency keys
   (`group:<key>:pre:0`, `group:<key>:post:1:0`, …). Same key re-invoke →
   same ids, `status:"recovered"`, zero duplicates. RETRY IS ALWAYS SAFE.
4. Ordering: create all → link all → verify every link → report. Failed
   link = structured error naming both cards + exact repair. No silent no-ops.
5. No side effects beyond declared shape. Never completes/blocks members.
   `await_caller` opt-in only.
6. Boundary validation: members ≥1, ids exist, created cards use real
   profiles or the `workflow-gate` lane (nonspawnable), cycle rejection
   surfaced as structured error.

## Why card/done pairs

Two kinds of completion exist since ticket serialization: trigger stubs
complete in seconds (meaningless); gates are the truth. The caller states
the truth explicitly. Shorthand covers plain work cards.

## Consumers

- Milestone barrier (immediate): route-milestone calls
  `group_cards(key:"m<N>", members: entry stubs+gates, pre:[{gate: qa-done-(N-1)}])`
  + milestone-gate gains a final `gate-close` node that completes the
  `[qa-done-NN]` card (created upfront by route-milestone on the
  workflow-gate lane; id embedded in milestone card body "QA gate: t_x").
  Entry ticket of milestone N+1 = blocked-by contains no same-milestone ticket.
- User-defined group workflows (future): releases, soak tests, sign-offs.

## Test plan (real kanban_db kernel, harness = test_ticket_serialization.py)

unlock semantics; fan-in; parallel sub-lists; idempotent re-invocation
(byte-same); partial-link failure → structured error + recovery; cycle
rejection; workflow-gate lane nonspawnable; await_caller park→promote;
template pins after route-milestone/gate-close rewiring. Then live 2-milestone
validation: M2 tickets must not fire until M1's qa-done closes.

## Context

- Design agreed in session (user: "FAANG quality, predictable and reliable").
- Prior art: user's old machine had a group plugin that crashed (pre-hardening
  subprocess/link class); kanban_chains' 2026-08-15 lock-race fix is the cure.
- Ticket gates + workflow-gate lane: live-proven wf-livetest5/6 + mdoutline.
