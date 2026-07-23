# 2-Card Pipeline Architecture (grill → build)

## Why split into 2 cards

The original pipeline had ONE card per idea that did everything: grill + build + README + portfolio. This had problems:

1. **Grill failures wasted build time** — if the grill killed the idea, 30 min of grill time was already spent with no abort signal
2. **Block/reclaim bug hit the whole card** — builder blocked the card during grill, dispatcher reclaimed after 1h, fresh session had to reconstruct both grill state AND build state
3. **Context bloat** — grill RPC state, PO sessions, branch files, AND prototype code all in one session

## The split

```
GRILL CARD (parent):
  reads dossier → grills with PO → outputs grill-decisions.md → completes
  Loads: self-grill + grill-rpc-ops
  Output: ~/projects/<slug>/grill-decisions.md
  Does NOT build prototype

BUILD CARD (child, auto-promotes when grill completes):
  reads grill-decisions.md → loads venture-prototype skill
  → POC gate (if technical risk) → picks type → builds → README → portfolio
  Loads: venture-prototype
  Output: ~/projects/<slug>/prototype/ + ~/projects/<slug>/README.md
  Does NOT re-grill
```

## Chaining

Cards chain at two levels:
- **Within an idea**: grill card → build card (build waits for grill via `--parent`)
- **Across ideas**: idea 2's grill card → idea 1's build card (sequential, one at a time)

This means 20 cards total for 10 ideas, but still only 1 active at any time.

## venture-prototype skill

The build card loads `venture-prototype` which owns:
- POC gate (check riskiest assumption — technical → POC first, market → skip)
- Prototype type selection (HTML / API / CLI / concierge — not everything is a web app)
- README template (9 sections, mandatory, with click-by-click "How to Review")
- Verify checklist before card completion

## queue-builds.sh changes

The script now creates 2 `hermes kanban create` calls per idea:
1. Grill card (chained to previous idea's build card via `--parent`)
2. Build card (chained to grill card via `--parent`)

Dedup check looks for slug in existing card titles (both "Grill:" and "Build prototype:" prefixes).
