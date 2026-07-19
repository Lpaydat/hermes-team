---
name: venture-grill
description: "PO uses grill-with-docs to interview VB (venture-builder) over intercom about the project VB wants to build."
---

# Venture grill

Triggered by a `[grill]` kanban card. The venture **slug** is in the body.

Force-load `grill-with-docs` (`grilling` + `domain-modeling`) and follow it to
interview VB over intercom. Record decisions in `docs/ventures/<slug>/CONTEXT.md`.

Reach VB: `intercom`, `to: venture-builder`, `topic: <slug>`, action `ask`. If
`ask` errors `target_not_connected`, resend as `send` with `spawn: true`.

When done, `kanban_complete`.
