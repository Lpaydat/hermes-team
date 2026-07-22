# HN Signal Library — Founder Distribution Pain

Verified HN threads (via Algolia API, 2026-07-23) for the "indie builders can't distribute" cluster. Reusable across dossiers about founder marketing, cold-start, distribution, and go-to-market pain.

## Canonical "build/distribute inversion" signals

| ObjectID | Title | Points | Comments | Date | Why it matters |
|----------|-------|--------|----------|------|----------------|
| `48787370` | "I can build anything, but only the void sees it" | 9 | 22 | 2026-07-04 | The canonical trigger. OP built 10+ products/month, none find users. Explicitly wants to pay someone for distribution. |
| `48942096` | "I built it and nobody came. What got you your first users?" | 11 | 29 | 2026-07-17 | Launch-to-silence experience. Top comment: "so much saturation and noise... impossible to generate organic traffic anymore." |
| `47800507` | "How did you get your first users with zero audience?" | 20 | 21 | 2026-04-16 | Cold-start problem. Key quote: "The hard part is not building a working product. The hard part is finding people to use it." |
| `42557947` | "How to learn marketing and sales as a solo entrepreneur?" | **497** | **203** | 2024-12-31 | Highest-engagement Ask HN in the cluster. Confirms mass (not niche) pain. Full of "hire someone" / "find a co-founder" advice — confirming supply gap. |
| `46412006` | "How do you get visibility if you're suuuuper bad at marketing?" | 13 | 22 | 2025-12-28 | Engineer-mindset can't translate to distribution. |

## "Launch hype ≠ sustainable distribution" signals

| ObjectID | Title | Points | Comments | Date | Why it matters |
|----------|-------|--------|----------|------|----------------|
| `45632846` | "I analyzed why 34 products that hit #1 on PH never made $1k MRR" | 6 | 0 | 2025-10-19 | Launch spike → no staying power. |
| `41611934` | "1000+ visitors but 1 customer, how to get more conversions?" | 6 | 9 | 2024-09-21 | Traffic doesn't convert. |
| `44672905` | "I built a tool that hit $516 MRR with no ads" | 1 | 0 | 2025-07-24 | Counter-signal: community distribution CAN monetize. |
| `44170619` | "Reaching my first 100 users without money or audience (at 10K users now)" | 35 | 11 | 2025-06-03 | Success case: Reddit "Build in Public" + "Startup Community" → 100 users in 2 weeks → 10K. |

## "Distribution is the bottleneck" structural signals

| ObjectID | Title | Points | Comments | Date | Why it matters |
|----------|-------|--------|----------|------|----------------|
| `46693828` | "The Startup Graveyard" (Loot Drop — loot-drop.io) | 66 | 48 | 2026-01-20 | **1,209 dead startups, $40B+ burned VC.** The concrete "200 dead startups" instantiation. |
| `41709429` | "Sometimes the product innovation is the distribution" (interconnected.org essay) | 123 | 31 | 2024-10-01 | Key insight: "go-to-market is an opaque process... the product would suddenly become much more interesting with a distribution twist." |
| `44737677` | "Reddit and Perplexity got us leads faster than Google ever did" | 8 | 1 | 2025-07-30 | Community channels beat search for early B2B. |

## Vibecoding / build-cost-collapse context (why-now)

| ObjectID | Title | Points | Comments | Date |
|----------|-------|--------|----------|------|
| `46765460` | "After two years of vibecoding, I'm back to writing by hand" | 865 | 634 | 2026-01-26 |
| `45320431` | "Vibe coding cleanup as a service" | 250 | 144 | 2025-09-21 |
| `43739037` | "Vibe Coding is not an excuse for low-quality work" | 259 | 200 | 2025-04-19 |
| `46227422` | "Vibe coding is mad depressing" | 263 | 159 | 2025-12-11 |

## Fetching patterns

```bash
# Search Ask HN for distribution pain (last 2 years)
curl -s "https://hn.algolia.com/api/v1/search?query=how%20to%20get%20users&tags=ask_hn&numericFilters=created_at_i%3E1719792000&hitsPerPage=20" | jq -r '.hits[] | "\(.points)pts | \(.num_comments)c | \(.created_at) | \(.objectID) | \(.title)"'

# Full thread with top comments
curl -s "https://hn.algolia.com/api/v1/items/47800507" | jq -r '.children[]? | select(.text != null) | "\(.author): \(.text)"'
```

**Note**: Reddit was inaccessible (403/429 on all curl, RSS, and browser attempts). The spec referenced r/SaaS and r/SideProject signals that could not be re-verified live. HN Algolia fully compensated as the primary source.
