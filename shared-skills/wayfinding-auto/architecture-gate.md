# Architecture gate — full procedure

On-demand detail for the `Map completion → architecture gate` section of `SKILL.md`. Follow
this when a map's frontier empties, BEFORE any to-tickets / tracer-cutting work. The architect
owns the architecture verdict; PO stays the product authority (never assigns the tier or writes
the ADR).

Wire the gate in this order — the **blocked-by edge FIRST**, so a session death mid-setup
leaves a safe, visible deadlock (to-tickets blocked) rather than an ungated proceed.

## 1. Create the gate bead

One bead per completed spec — its id is the gate handle. bead-sync closes it when the gate
card is done.

## 2. Block to-tickets on it FIRST

Make the to-tickets / tracer-cutting work **blocked-by** the gate bead:

```bash
bd dep add <to-tickets-bead> <gate-bead>
```

The to-tickets bead is now immediately blocked and cannot be dispatched ungated — even if the
next step never runs.

## 3. Raise the gate card

Only now create the **architecture gate card**:

- `--assignee architect`
- `--workspace dir:<venture>`
- force-load the gate + design skills: `--skill architecture-gate --skill codebase-design --skill domain-modeling`
- idempotency key `bead-<gate-bead>` so completion is durable.

The body carries the map pointer + the completed spec path and instructs the gate to:

- triage by blast radius,
- produce the tier's artifact:
  - **T0** — none,
  - **T1** — one ADR,
  - **T2** — escalate; a T2 card is left **blocked** (not completed), so the gate bead stays
    open,
- stamp the spec's architecture sections surgically (leave the product sections untouched),
- complete with the gate's completion-contract metadata.

## Resolution

When the architect completes the gate card (T0/T1), **bead-sync** closes the gate bead and
unblocks to-tickets — which then proceeds and **inherits** the gate's tier + ADR list from the
stamped verdict.

## Ownership and idempotency

The gate card is created by PO (this doctrine), never by the engine: the engine's dispatch
skips any bead that already has a `bead-<id>` card, so a re-run never duplicates the gate.
Keep it to ONE gate card per completed spec — wire the blocked-by edge, raise the card, then
complete your own map card.
