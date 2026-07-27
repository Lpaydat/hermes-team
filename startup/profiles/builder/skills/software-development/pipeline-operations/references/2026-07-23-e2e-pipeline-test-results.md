# E2E Pipeline Test Results (2026-07-23/24)

**Session:** Full pipeline E2E test — gateway restart, queue-builds.sh, builder sessions, grill, prototype, portfolio, card done, chain promotion across 10 cards.

## Cards completed during this test

| # | Card | Score | Status | Prototype |
|---|------|-------|--------|-----------|
| 1 | LeadPilot | 21/25 | done | 2 files, 64K |
| 2 | OSINT Desk | 20/25 | done | 3 files, 72K |
| 3 | SMB Bookkeeping | 20/25 | done | 2 files, 68K |
| 4 | WhatsApp Shared Inbox (ReplyDeck) | 19/25 | done | 2 files, 56K |
| 5 | Indie Builder Distribution | 19/25 | blocked (reclaim loop) | in progress |
| 6-10 | remaining | 18-19/25 | todo | pending |

## Card 1: LeadPilot (21/25) — COMPLETE

- **Started:** 23:16, **Completed:** 00:23 (1h7m)
- **Grill:** 14 design decisions locked across 5 branches (statistical-evidence, willingness-to-pay, customer-acquisition, technical-feasibility, prototype-scope)
- **Result:** Single-file clickable demo (landing page + interactive dashboard + aha-moment simulator). Verified in browser. Portfolio updated.
- **Prototype:** ~/vault/ventures/prototypes/leadpilot-local-smb-lead-gen/ (index.html 57KB + README.md)
- **11 comments** documenting grill progression (Q1 to Q8+ with batch answers)

## Card 4: WhatsApp Shared Inbox (19/25) — COMPLETE (after 2 reclaim cycles)

Most rigorous grill observed. PO:
- Caught factor-of-10 math error ($2000 x $0.10 = $200, not $20)
- Scraped 941 existing Shopify App Store WhatsApp apps live
- Proved founder "be first in category" claim was false
- Scraped Zoko live listing, proved founder wrong on every differentiation claim
- Found $36/mo gap (not "2-3x cheaper" narrative) against 4.9-star, 378-review incumbent

This card cycled through blocked twice before completing. Each reclaim cycle wasted ~1h.

## Issues observed and fixes applied

### 1. Builder blocks card during self-grill (FIXED in skill)
- Root cause: self-grill skill did not say "do not block." Builder followed kanban protocol literally.
- Symptom: Card stuck in blocked status, no heartbeats, dispatcher reclaim after ~1h.
- Fix: Added "NEVER block the kanban card during self-grill" section to self-grill/SKILL.md.
- Applied: 2026-07-24. Cards 6+ should benefit.

### 2. PO launch with --cli hangs (FIXED in skill)
- Root cause: grill-rpc-ops recipe showed bare hermes --cli without timeout.
- Symptom: --cli mode hangs silently for 200-300s. Builder assumed failure, killed PO, retried.
- Fix: Updated recipe to `timeout 600 hermes -p product-owner --cli 2>&1 | tail -80`.
- Note: Initial fix used 300s timeout. User corrected to 600s minimum: "just thinking alone can go up to 300s."
- Applied: 2026-07-24. Patched grill-rpc-ops/SKILL.md directly via patch tool (pinned skill refuses skill_manage).

### 3. queue-builds.sh eval quoting bug (FIXED)
- Root cause: `eval hermes kanban ... $ARGS` splits multi-line body on spaces.
- Fix: Pass --body directly as quoted argument, no eval.
- Applied: 2026-07-24.

### 4. Two prototype directories per idea (NOT YET FIXED)
- idea-bank.md slug vs builder-created dir slug mismatch.
- Fix needed: normalize slugs.

## Timing data

| Phase | Duration |
|-------|----------|
| PO first response | 120-300s (glm-5.2 thinking latency) |
| Full grill (10-14 decisions, 5 branches) | ~40-50 min |
| Prototype build | ~5-10 min (single HTML file) |
| Portfolio update + card complete | ~2 min |
| Total per card (no reclaim) | ~50-60 min |
| Total per card (with 1 reclaim cycle) | ~90-110 min |
| Dispatcher reclaim trigger | ~1h without heartbeat (stale_timeout default) |

## Sequential chain verified

All 10 cards linked parent to child. Auto-promotion confirmed across 4 transitions:
- Card 1 done -> Card 2 auto-promoted -> dispatcher claimed within seconds
- Card 2 done -> Card 3 auto-promoted
- Card 3 done -> Card 4 auto-promoted
- Card 4 done -> Card 5 auto-promoted

Each promotion spawns a fresh builder process (new PID, new session, fresh skill load).

## Dispatcher reclaim recovery pattern

When a builder blocks the card:
1. Card enters blocked status, heartbeats stop
2. Builder process continues running (futex_wait on subprocess)
3. After ~1h, dispatcher reclaims (re-queues as ready, no failure counter)
4. New builder session spawns (fresh PID, fresh skill load)
5. Previous grill state preserved in kanban comments (builder reads comments on startup)
6. Builder continues grill from where it left off

Natural recovery, no manual intervention needed, but wastes ~1h per occurrence.

## PO grill quality benchmarks

PO does not just ask questions. It independently verifies founder claims using web tools:
- Scraped live competitor listings (Shopify App Store, Zoko page)
- Caught math errors (factor-of-10 in unit economics)
- Verified pricing claims against actual tiers
- Found false "be first in category" claims with live app counts

This is the grill core value. Decision density: 10-14 decisions / 5 branches / ~50 min per idea.
