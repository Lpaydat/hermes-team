# Verified Landscape — SEO-Spam-Free / Alternative Search Engines

**Verified:** 2026-07-25
**Reusable for:** any search-engine, answer-engine, web-index, meta-search, or "SEO-spam-free" venture dossier. Also relevant to any dossier that needs to cite a competitor's paying-user count or revenue when the company is private and doesn't publish financials.
**Extraction methods used:** HN Algolia API (engagement + founder quotes); GitHub API (OSS repo health/stars); browser_navigate on self-disclosed-metrics pages; curl + JSON-LD/regex on pricing pages.

## The landscape (five monetization tiers)

| Tier | Players | Monetization | Index? | Surviving? |
|------|---------|-------------|--------|-----------|
| Subscription search | Kagi | Paid tiers | Own + sourcing | ✅ Growing |
| Independent index (ads) | Brave, Mojeek, DDG | Ads / API / browser bundle | Own (Brave/Mojeek) / Bing-backed (DDG) | ✅ Brave+DDG scale |
| Metasearch (OSS) | SearXNG | Non-profit / donation | Aggregates | ✅ Healthy OSS |
| Non-profit indie index | Marginalia, Mwmbl | Grants + donations | Own (small) | ⚠️ Grant-funded / stalled |
| AI answer engines | Perplexity, You.com | Subscription + B2B API | Aggregate + LLM | ✅ Perplexity scale; You.com pivoted to B2B |
| Niche / legacy | Gibiru, TinySearch, Arlong | VPN upsell / none | Proxy/OSS | ⚠️ Legacy / nascent |
| DEFUNCT | Neeva | Subscription | Own | ❌ Shut down May 2023 |

## Live-verified data per player

### Kagi — the only proven subscription search engine

- **Pricing (browser-verified, kagi.com/pricing):** Trial Free (100 searches); Starter $5/mo (300); Professional $10/mo (unlimited); Ultimate $25/mo (unlimited + premium AI). "Fair pricing" = not charged in months you don't use it.
- **Users/revenue (browser-verified, kagi.com/stats, 2026-07-25):** **73,426 paying members**; 9,554 families; 397 teams; 3,229 Orion+; **~1,021,200 queries/day**. Member count trended +410/mo over the prior 14 days (73,016 → 73,426).
- **Revenue triangulation:** blended ~$10 ARPU × 73,426 members ≈ **$730K/mo ≈ $8.7M ARR**. Kagi does not publish revenue; this is an estimate from the live-disclosed member count × pricing.
- **HN signal:** $10/mo launch thread = 1,748pts (HN 37603905); canonical comparison thread = 950pts (HN 38821248).
- **Net read:** works at boutique scale; hard ceiling (~73K after 4+ yrs); top-of-funnel choked by the 100-search paywall.

### Brave Search — independent index, privacy ads

- **Pricing:** Free, ad-supported. Search Premium (ad-free sub) exists but price could NOT be verified live (help page slug returns 404; appears restructured). Revenue: privacy ads + Brave Search API ($3–$5/1k dev queries) + browser bundle.
- **Traffic:** passed 2.5B queries mid-2022 (HN 31837865); own index since Apr 2023 (HN 35730711, 704pts); now web-scale.
- **Positioning (verified, brave.com/search/):** explicitly markets "without big tech's SEO spam" and compares itself against Google + DDG.
- **Net read:** only major own-index besides Google/Bing/Yandex; Goggles (community ranking) is novel but low adoption.

### DuckDuckGo — scale without independence

- **Pricing:** Free, ad-supported.
- **Traffic:** **100M+ daily searches** (HN 29724593); **+28% visits in May 2026** after Google pushed AI Mode (HN 48296649, 1,075pts) — event-driven switching is real.
- **Critical weakness:** **Bing-dependent** (re-ranks Microsoft's index). Inherits Bing's spam. Not spam-free, just Bing + privacy wrapper. 2023 settlement over browser tracking (HN 37660565) dented privacy brand.

### SearXNG — the OSS metasearch standard

- **GitHub (live):** **34,371★**, 3,179 forks, AGPL-3.0, last push 2026-07-24 (yesterday). Actively maintained.
- **Model:** Free, no monetization. Volunteer + donation funded. One maintainer publicly left 2025 (HN 44114492).
- **Net read:** privacy maximalism + huge OSS community (used as plumbing by Perplexica etc.), but **no business model = no sustainability path**.

### Marginalia Search — anti-commercial index, grant-funded

- **GitHub (live):** **1,884★**, AGPL, last push 2026-07-24. Solo developer.
- **Funding:** **FUTO Grant** (2023, HN 37519982) + **NLnet grant** (2023, HN 34945541). No ads, no sub.
- **Net read:** conceptually closest to "spam-free by construction" (downranks commercial web); grant runway is finite; serves a community not a market.

### Mwmbl — stalled non-profit

- **GitHub (live):** **1,828★**, AGPL, last push 2026-07-21. Passed **100M pages** (HN 38151036, Nov 2023) — not visibly surpassed since. HN engagement dropped (209pts → 36pts → single digits). Labor of love without viability path.

### You.com — PIVOTED entirely to B2B API (consumer abandoned)

- **Consumer search:** **No consumer pricing anymore** (browser-verified, you.com/pricing). Pivoted to API-only.
- **API pricing (live):** Web Search $5/1k calls; Contents $1/1k pages; Research $12/1k (Lite); Finance Research $110/1k. $100 free credit. SOC2-certified.
- **Why it matters:** a $20M+ funded consumer search startup concluded consumer search doesn't pay and pivoted to infra. **This pivot IS the signal** (see "consumer→B2B pivot detection" technique).
- **Trust damage:** caught injecting tracking beacons in browser extension (HN 34798078).

### Perplexity — AI answer engine (not classic search)

- **Pricing:** Perplexity Pro ~$20/mo (consumer page fully **Cloudflare-blocked** — 403 to curl AND browser; could not verify live this session). API verified: Search API $5/1k requests (docs.perplexity.ai).
- **Scale:** $9B+ valuation; tens of millions of users; VC war chest.
- **Controversies:** lied about user agent (HN 40690898, 626pts); Amazon demanded stop to AI shopping agent (HN 45814461) → court order against it (HN 47327309).
- **Net read:** summarizes whatever the web contains (incl. spam); different product category; unit economics unproven at $20/mo given inference cost.

### Neeva — the cautionary tale (DEFUNCT)

- **Funding:** ~$77M (Sequoia, Greylock). Built a real, independent index praised on HN: *"a real search engine (unlike DDG which is a shim on Bing) comparable to Google."*
- **Pricing was:** $4.95/mo basic / $9.95/mo premium.
- **Shut down:** May 2023 (HN 36016250, 46pts; blog thread 36013783, 373pts).
- **THE critical quote (founder Sridhar Ramaswamy, HN 36013783):** *"Contrary to popular belief, convincing someone to pay for a better experience was actually a less difficult problem compared to getting them to try a new search engine in the first place."*
- **Cite this as:** the single most important data point in the landscape. A well-funded, high-quality subscription search engine failed on DISTRIBUTION, not product or price.

### Mojeek — quiet independent index (15+ yrs)

- **Index (live, mojeek.com/about):** **9 billion pages** (2025). Genuine own spider.
- **Model:** Free + Mojeek Ads + Web Search API + "Focus" product.
- **Net read:** 15 years of effort = tiny share. Proves the distribution ceiling for independent indexes.

### Gibiru — legacy privacy proxy

- **(live, gibiru.com):** "Uncensored Anonymous Search Engine — Protecting your privacy since 2009." VPN upsell monetization. No own index. Fringe positioning; dated UX.

### TinySearch — name collision (NOT one competitor)

Two unrelated HN projects share the name: 2020 personal-websites tool (4pts) and 2026-06-30 token-efficient agent research tool (3pts). **Neither is a consumer search competitor** — the name collision is a research trap.

### Arlong (Reddit r/SideProject) — could NOT verify live

Referenced as a dev's OSS privacy search engine at ~9k searches/day. **No HN/GitHub presence found under "Arlong"; Reddit blocked.** Flagged unverified per no-fabrication rule. Even if real, 9k/day = 0.03% of Kagi's volume. Signal of *demand* (people build this), not *viability*.

## Monetization-model verdict (the key synthesis)

Five models; only three survive at scale. For any spam-free-search venture dossier, lead with this:

1. **Consumer subscription** — works at boutique scale (Kagi ~$8.7M ARR) but **failed at venture scale** (Neeva $77M → dead). Hard ceiling.
2. **Privacy-respecting ads** — works at scale (DDG 100M/day) but requires browser bundle (Brave) or third-party index (DDG←Bing). Not spam-free by definition.
3. **B2B API / infrastructure** — the most viable monetization for search tech in 2026. You.com validated by pivoting to it. WTP proven from AI-agent builders ($5–$110/1k).
4. **Grants/donations** — works for passion projects (Marginalia, Mwmbl, SearXNG); not venture-scale; finite runway.
5. **AI answer subscription** (Perplexity) — different category; unit economics unproven.

## The whitespace

**No player owns "spam-free as the PRIMARY product."** Each compromises somewhere (ads, upstream index, niche-only, or summarizes spam rather than filtering it). The gap is NOT technology (a spam classifier is buildable); it's (a) a revenue model that survives Neeva's distribution failure and (b) distribution without a browser bundle. Strongest viable wedge per the evidence: **B2B "spam-free search API" for AI agents** (proven WTP), not consumer subscription.

## Source references (verified live 2026-07-25 unless flagged)

| Source | URL / ID | Method |
|---|---|---|
| Kagi pricing | kagi.com/pricing | Browser |
| Kagi live stats | kagi.com/stats | Browser |
| Kagi $10/mo thread | HN 37603905 | HN Algolia |
| Brave Search product page | brave.com/search/ | Browser |
| Brave own-index milestone | HN 35730711 | HN Algolia |
| SearXNG GitHub (34,371★) | api.github.com/repos/searxng/searxng | GitHub API |
| Marginalia GitHub (1,884★) | api.github.com/repos/MarginaliaSearch/MarginaliaSearch | GitHub API |
| Marginalia FUTO grant | HN 37519982 | HN Algolia |
| Mwmbl GitHub (1,828★) | api.github.com/repos/mwmbl/mwmbl | GitHub API |
| You.com pricing (API only) | you.com/pricing | Browser |
| Perplexity API pricing | docs.perplexity.ai/docs/getting-started/pricing | Browser |
| Perplexity consumer pricing | perplexity.ai/pricing | **Cloudflare-blocked, not verified** |
| Neeva shutdown | HN 36016250, 36013783 | HN Algolia |
| DDG 100M/day | HN 29724593 | HN Algolia |
| DDG +28% post-Google-AI | HN 48296649 | HN Algolia |
| Mojeek 9B pages | mojeek.com/about/ | Curl |
| Gibiru homepage | gibiru.com | Curl |
| Compare Google/Bing/Kagi/Marginalia/Mwmbl | HN 38821248 | HN Algolia |
| Arlong (Reddit) | reddit.com | **Reddit blocked, not verified** |
