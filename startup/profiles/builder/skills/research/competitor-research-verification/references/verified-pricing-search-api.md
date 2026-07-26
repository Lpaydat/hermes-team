# Verified Pricing — Search API for AI Agents (and search-index landscape)

Captured 2026-07-25 while building the SEO-Spam-Free Search Engine dossier.
All prices verified live unless noted. **This is a fast-moving market —
re-verify any price >6 months old before quoting it in a dossier.**

This segment barely existed in 2023 and exploded after Microsoft retired the
Bing Search APIs (Aug 11 2025), stranding thousands of products that depended
on Bing results. Any search / web-access / RAG / AI-agent-infrastructure
dossier will hit this landscape.

## Two distinct layers — don't conflate them

1. **Index-owning search engines** (crawl + own index): Brave, Mojeek,
   Marginalia. Few, capital-heavy, slow to build (Mojeek took 16+ yrs to
   ~6B pages). Sell API access as a side channel.
2. **Search-API-for-agents wrappers** (sit atop Google/Bing/own index,
   optimize for AI-agent ergonomics: token-efficiency, structured output,
   prompt-injection defense): Tavily, Exa, You.com, SerpAPI, Serper, + a
   2025-26 entrant wave. Crowded, venture-backed, fast-moving.

A "spam-free search" or "clean search" venture is almost always a **Layer-2
wrapper with a quality/trust differentiator**, not an index build. Price
benchmarks below cover both.

## Verified pricing (live 2026-07-25)

### Search-API-for-agents wrappers (Layer 2)

| Vendor | Price / 1k queries | Model / notes | Source |
|---|---|---|---|
| **Serper.dev** | **$0.30–$1.00/1k** (50k credits=$1/1k, 2.5M=$0.50/1k, 12.5M=$0.30/1k) | Google-scraper wrapper. Cheapest. ToS-grey. | serper.dev — curl+regex on rendered DOM |
| **Exa** | **$7/1k Search, $1/1k Contents, $12/1k Deep Search, $15/1k Monitors, $5/1k Answer**; +$1/1k per result >10; $1/1k AI summaries | Neural search "built for your AI". Cursor uses it. $20 free credits. | exa.ai/pricing — curl returned JS-gated HTML; extracted via `browser_console(expression="document.body.innerText")` |
| **SerpAPI** | **$25 Starter (1k)/mo → $3,750 Cloud 1M/mo** (~$3.75/1k @1M, ~$2.11/1k top tier). "Ludicrous speed" tier ~2× price. 50+ tiers up to Cloud 54M ($424,200/mo). | Google/Bing SERP scraper. Mature. | serpapi.com/pricing — **pricing is embedded as an entity-encoded JSON blob inside inline `<script>` tags / `data-tippy-content` attrs, NOT in rendered DOM.** See SKILL.md "entity-encoded JSON in data-* blobs" pattern. |
| **Tavily** | **Pricing behind auth** — `tavily.com/#pricing` loads via JS hash; `app.tavily.com/pricing` requires login. Per-1k price NOT verified this session. | "Connect your AI agents to the web." **$25M Series A, "2M+ developers," joining Nebius, partners IBM/Databricks/JetBrains.** Endpoints: search/extract/crawl/research. | tavily.com — funding/traction from public homepage; specific $/1k unverified (auth-walled). See SKILL.md "pricing behind auth" pattern. |
| **You.com** | $100 free credits on signup; usage-based credit model after | "Research APIs for real-time web intelligence." Consumer-search pivot to API. | you.com/api — `$100 in complimentary credits` via curl; per-query rate not in static HTML |
| **LLMLayer.ai** | Not verified (HN launch only) | "web search API specifically designed for AI agents and RAG" | HN comment capture only |
| **Crustdata (YC F24)** | Not verified | "Web Search API for Token-Efficient AI Agents" | crustdata.com, Show HN 2026-02 |
| **Seltz** | Not verified | "Fastest, high-quality search API for AI agents" | console.seltz.ai, Show HN 2026-04 |
| **Quercle** | Not verified | "Web Fetch/Search API for AI Agents" w/ prompt-injection defense | quercle.dev, Show HN 2025-12 / 2026-01 |
| **Souko.ai** | Not verified | "Web scraping, search and extraction APIs for AI workflows" | Show HN 2025-07 |
| **ArguSeek** | Not verified | "Agent-first deep-search API for hard-to-find dev answers" | agruseek.com, Show HN 2025-07 |

### Index-owning search engines (Layer 1 — legit, independent upstreams)

| Vendor | Price / 1k queries | Notes | Source |
|---|---|---|---|
| **Brave Search API** | **$3/1k base, $4/1k Summarizer, $5/1k AI Snippets**, +$5/mo free credits, +$5/1M tokens I/O | Own independent index (~20B+ pages). The most-used "legit independent" API. | brave.com/search/api — curl+regex on rendered DOM |
| **Mojeek API** | **£2 CPM Startup, £3 CPM Business, Enterprise custom** (~$2.50–$3.80/1k) | Own crawler, UK-based, ~6B pages. Explicitly allows AI/LLM use + own ad placement. | mojeek.com → /api (via browser; the `/services/search-api/` and `/business/` paths both 404 — **use the homepage nav "API" link or the `/api` path**) |

## WhyNow signals (cite in any search/AI-infra dossier)

- **Bing Search APIs retired Aug 11 2025** (azure.microsoft.com/en-us/updates?id=492574). Stranded DDG, Kagi, and every Bing-wrapper. Triggered the entrant wave above. The single strongest "why now" for any clean-search product.
- **Kagi's index-independence problem** — Kagi's own docs confirm it makes "anonymized requests to traditional search indexes like Google and Bing"; an engineer on HN said Google-API calls are a "major driver" of cost. Validates that even a paid-subscription search leader can't escape upstream dependency.
- **TinySearch (MarcellM01/TinySearch, 165★, created 2026-05)** — "Shrink the web for your local LLMs." Open-source token-efficient web-access pattern; signals agent-ergonomics is a real adoption axis.

## Open-source / own-index references (GitHub, verified 2026-07-25)

| Repo | Stars | What | Notes |
|---|---|---|---|
| searxng/searxng | 34,371 | Meta-search aggregator (no own index) | Python, AGPL-3.0, active. The default "search engine in a day." |
| outpoot/vyntr | 362 | Indie own-index attempt (TS) | "Independent search engine... crawling, indexing." Hobby-scale. |
| MarcellM01/TinySearch | 165 | Token-efficient web for local LLMs | Python, created 2026-05, active. |

## Key HN thread IDs (verified live 2026-07-25 via Algolia)

- `Search engines and SEO spam` (Paul Graham tweet) — 592pts, 2022. Canonical "search quality is declining" signal.
- `Almost all searches on my independent search engine are now from SEO spam bots` — 696pts, 2022, searchmysite.net. Indie-search spam problem.
- `Launch HN: Andi (YC W22) – anti-spam search engine` — 352pts, 2022. Direct precedent (anti-spam positioning).
- `Mojeek: own spider` — 264pts, 2020. Own-index existence proof.
- Multiple `Bing Search APIs will be retired on 11 August 2025` posts — the WhyNow anchor.
