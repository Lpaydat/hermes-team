# Self-Grill Kanban Card Blocking — 2026-07-23 E2E Finding

## The bug

During a self-grill session, the builder calls `kanban_block(kind='needs_input')`
when PO asks a question. This blocks the card, stops heartbeats, and triggers a
dispatcher reclaim after ~28 min (1h stale timeout minus grace period).

## Why it's wrong

In a self-grill, the builder IS the founder. There is no human gate to wait for.
The builder should answer PO's question immediately via the RPC mechanism
(answer.sh / hermes --resume) and continue the grill.

## Impact

- LeadPilot (card 1): blocked at 23:26, reclaimed at 00:21 (~55 min lost)
- WhatsApp Shared Inbox (card 4): blocked at 00:56, pending reclaim
- Each reclaim cycle wastes ~30 min (stale timeout + re-dispatch + context reload)

## What the builder does instead of blocking

1. PO asks question via RPC output
2. Builder reads the question from the RPC output or grill state file
3. Builder drafts answer as founder (with conviction, using dossier as evidence)
4. Builder sends answer via answer.sh or `hermes --resume` directly
5. Repeat until grill converges (no pending/active branches)
6. Build prototype
7. Update portfolio
8. kanban_complete

The card stays in `running` from claim to completion. Heartbeat every few minutes
so the dispatcher knows the session is alive.

## Why the builder blocked (root cause analysis)

The builder loaded the kanban task protocol which says "block on genuine ambiguity
or when you need a human decision." The self-grill SKILL.md said "answer as founder"
but did NOT explicitly say "do not block the card." The builder followed the kanban
protocol literally — it interpreted PO's question as "needs founder input" and blocked.

The fix is an explicit instruction in self-grill SKILL.md: the self-grill flow has
no human-in-the-loop. The builder is the founder. Never block.
