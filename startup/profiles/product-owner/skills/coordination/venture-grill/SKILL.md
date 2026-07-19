---
name: venture-grill
description: "PO uses grill-with-docs to interview VB (venture-builder) over intercom about the project VB wants to build."
---

# Venture grill

Triggered by a `[grill]` kanban card. The venture **slug** is in the body.

Force-load `grill-with-docs` (`grilling` + `domain-modeling`) and follow it to
interview VB over intercom.

## Multi-pass — record evidence, don't self-assess "done"

This grill loops across multiple PO sessions. Each iteration you grill VB,
record state in `~/.venture-builder/<slug>/CONTEXT.md`, then `kanban_complete`.
A separate **scanner agent** (not you) reads your CONTEXT.md and decides
whether a next grill question remains or the venture is genuinely resolved.

So your job per iteration: **record claims with their evidence status** — do
NOT self-assess convergence. In CONTEXT.md (alongside the glossary):
- Mark every load-bearing claim as **evidenced** (cite the source) or as
  **assertion / hypothesis / TBD / to-be-tested** (no evidence yet).
- Do NOT write a "we're done" postscript that buries unevidenced claims. The
  scanner judges done-ness from what is evidenced; if you bury a gap the grill
  keeps looping anyway. Naming a test (defining a gate, a falsification) is not
  answering it.

The scanner reads your CONTEXT.md as-is (the grill_followup plugin mirrors
writes to `~/.venture-builder/<slug>/` so they survive task cleanup) — write
wherever grill-with-docs directs; persistence is handled.

Reach VB: `intercom`, `to: venture-builder`, `topic: <slug>`, action `ask`. If
`ask` errors `target_not_connected`, resend as `send` with `spawn: true`.

When done, `kanban_complete`.
