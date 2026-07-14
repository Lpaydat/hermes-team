# Grocery Price Comparison APIs — Landscape Map

Worked example of an API-landscape research session (US grocery, solo-dev
pricing tier). Captures citable facts for reuse in future venture /
market-research tasks. Each fact traces to a primary source URL loaded
during the session.

## Quick verdict

| Provider | Price data? | Solo-dev access | Rate limit | Legal for cross-retailer comparison? |
|----------|-----------|----------------|------------|--------------------------------------|
| **Kroger Products API** | ✅ (regular + promo) | ✅ Free, self-service | 10K calls/day | ✅ Yes (single-retailer coverage) |
| **UPCitemdb** | ✅ (multi-merchant offers + historical high/low) | ✅ FREE tier, no signup | 100 req/day (FREE); 20K lookup/day (DEV) | ✅ Yes (aggregator; offer links affiliate-redirected on FREE) |
| **Instacart Developer Platform** | ✅ (pricing available) | Self-service key | Unpublished | ❌ ToS clauses k/l forbid it |
| **Instacart Connect** | Retailer-side only | Enterprise partnership | N/A | N/A (retailer fulfillment, not price data) |
| **USDA FoodData Central** | ❌ Nutrition only, no retail prices | ✅ Free, public domain (CC0) | 1,000 req/hour per IP | N/A (not a price source) |
| **Chicory** | No | Enterprise ad-tech sales | N/A | N/A (ad platform, not a price API) |
| **Basketful** | Unknown | Enterprise | Unknown | Unknown |
| **RapidAPI marketplace grocery APIs** | Varies | Self-service | Per-API tier | Varies (check each provider's ToS) |

**Bottom line for solo-dev price comparison:** Kroger Products API is the
only confirmed free, self-service option that exposes **store-level
real-time pricing** AND has no anti-comparison ToS clause. Coverage is
limited to the Kroger Co. banner family (~2,700 stores, 35 states).
**UPCitemdb** is the best free complement for *multi-retailer* price
data — it aggregates merchant offers (not store-level) and includes
historical price tracking, but it is a general product database, not
grocery-specific. Instacart exposes pricing but its ToS bans the core use case.

---

## Kroger Developer API (Products API) ✅ recommended

- **Docs**: https://developer.kroger.com/ — Products API section
- **Coverage**: Entire Kroger product catalog (~2,700 stores under Kroger Co.:
  Kroger, Fred Meyer, Ralphs, King Soopers, Harris Teeter, etc.)
- **Pricing**: **FREE** public API — "APIs for Everyone." No published paid tiers.
- **Access**: Self-service — register app, receive client ID + secret, begin
  requests immediately. **Low friction.**
- **Rate limits (full Public API table)** — confirmed via FAQ page
  (https://developer.kroger.com/support/faq):
  | Public API | Rate Limit |
  |------------|-----------|
  | Products API | 10,000 calls/day |
  | Cart API | 5,000 calls/day |
  | Locations API | 1,600 calls/day per endpoint |
  | Identity API | 5,000 calls/day |
  HTTP 429 when exceeded.
- **Pricing data exposed**: `price` (regular + promo), `nationalPrice`
  (regular + promo national). Requires `filter.locationId` query parameter.
- **Operations**: `GET /products` (search by term or ID), `GET /products/{id}`
  (product details).
- **Version observed**: 1.3.0 (as of 2026-07)
- **Support**: APISupport@kroger.com
- **No ToS clause prohibiting price comparison** — suitable for aggregation.

---

## UPCitemdb ✅ free, multi-retailer offers (not grocery-specific)

- **Docs**: https://www.upcitemdb.com/wp/docs/main/development/
- **Coverage**: ~714 million+ UPCs in the database. Returns merchant offers
  across many online stores (not grocery-specific; covers all product
  categories). Currency support: USD, CAD, EUR, GBP, SEK.
- **Pricing tiers** — confirmed via Plan Comparison + Rate Limits pages:
  | Plan | Daily limit | Burst | Sustainable | Connections | Signup | Cost |
  |------|------------|-------|-------------|-------------|--------|------|
  | **FREE** | 100 combined (max 20 search) | 6 lookups/min; 2 search/30s | 1 req/10s | 1 | **None** | $0 |
  | **DEV** | 20K lookup + 2K search | 15 lookups/30s; 5 search/30s | 1 lookup/2s; 1 search/6s | up to 2 | Required | Monthly subscription (credit card) |
  | **PRO** | 150K lookup + 20K search | 12 lookups/sec; 2 search/sec | 6 lookups/sec; 1 search/sec | up to 6 | Required | Monthly subscription |
  Exact monthly $ amounts for DEV/PRO are **not published** on a public
  pricing page; only visible after signing in. Overages billed per-hit.
  Sources: https://www.upcitemdb.com/wp/docs/main/development/plan/ and
  .../api-rate-limits/
- **Data exposed** (ItemsResponse schema):
  - `title`, `brand`, `description`, `category` (Google taxonomy), `images`
  - `ean` / `upc` / `gtin` identifiers
  - **`offers[]`** — array of merchant offers, each with: `merchant`, `domain`,
    `title`, `currency`, and **price**. On FREE plan, offer links redirect
    through upcitemdb.com (affiliate); on paid plans they are direct merchant links.
  - **`lowest_recorded_price`** / **`highest_recorded_price`** — historical
    price tracking since the item was first tracked. Not available for books.
- **Batch**: up to 2 UPCs/request (FREE), up to 10 (paid).
- **Grocery relevance**: Covers grocery UPCs, but as part of a general product
  database — prices are aggregated online-merchant offers, **not** real-time
  in-store shelf prices. Best used for broad price discovery / historical
  trends, not live local comparison.
- **Solo-dev friendly**: Yes — FREE tier requires **no signup at all**.
- **Sources**: Plan Comparison (https://www.upcitemdb.com/wp/docs/main/development/plan/),
  API Rate Limits (https://www.upcitemdb.com/wp/docs/main/development/api-rate-limits/),
  Responses (https://www.upcitemdb.com/wp/docs/main/development/responses/).

---

## USDA FoodData Central ❌ nutrition only, no retail prices

- **Docs**: https://fdc.nal.usda.gov/api-guide
- **What it is**: REST API for food composition / nutrient data (Foundation
  Foods, SR Legacy, Branded Foods, FNDDS).
- **Pricing**: **Free**, data in the **public domain (CC0)**.
- **Rate limit**: 1,000 requests/hour per IP address (X-RateLimit headers
  returned on every response; HTTP 429 on exceed; key blocked 1 hour).
- **Access**: Free `data.gov` API key; anyone can sign up.
- **Why not useful for prices**: Returns nutrition data only — **no retail
  prices, no store availability, no merchant offers.** Useful as a *nutrition
  complement* alongside a price API (e.g. Kroger + USDA), not as a price source.

---

## Instacart Developer Platform API ⚠️ exposes pricing, ToS bans comparison

- **Docs**: https://docs.instacart.com/developer_platform_api
- **Purpose**: Built for app developers — recipe/meal-planning apps, shopping
  lists, e-commerce integrations that route users into Instacart Marketplace.
  Explicitly states it is for "app developers," distinct from Connect APIs
  which are for "retailer partners."
- **API suites**: Shopping APIs (product discovery, cart creation, recipe
  pages, product search); Retailer APIs (nearby stores, availability,
  service areas). Marketing copy mentions "real-time inventory and pricing."
- **Access**: Self-service via Instacart Developer Dashboard — create API
  key with scopes (read-only / read-write / admin), choose Development or
  Production environment.
- **Pricing tiers**: Not publicly published. Terms state the platform "may
  change or discontinue availability… requirements of fees for previously
  free features."
- **Rate limits**: Not published in public docs. FAQ references
  "Why was my API key access limited?" — throttling exists but is opaque.

### ❌ CRITICAL — ToS prohibits cross-retailer price comparison
Terms of Service (last updated 2024-07-03), Restrictions section, explicitly
prohibit:
- **(k)** "display priced items from multiple retailers on the same screen
  within any Application"
- **(l)** "move, copy, compare, or transfer items from one retailer basket
  to another retailer basket within an Application"

➡ The API **cannot legally be used for cross-retailer price comparison**.
It is designed for affiliate/commerce flows into Instacart checkout.

> Surfacing technique: these clauses were hidden below the truncation point
> of `browser_snapshot(full=true)`. They were found by running
> `browser_console` with `document.body.innerText` filtered by
> `/prohibit|restrict|forbid|compare/i` against the rendered ToS page.

---

## Instacart Connect APIs (separate product) — enterprise only

- **Docs**: https://docs.instacart.com/connect
- Built for **retailer partners** to add Instacart fulfillment (scheduling,
  full-service shopping, delivery, pickup, tracking) to the retailer's own
  branded e-commerce site.
- The docs page explicitly states: "Instacart Connect APIs are built for
  retailer partners. If you are an app developer who wants to generate a
  link to a shoppable recipe or list on Instacart Marketplace, see
  Instacart Developer Platform API."
- Access requires a retailer partnership with Instacart ("Contact us").
- Not a price-data source; not accessible to solo developers.

---

## Chicory ❌ not a price API

- **Site**: https://chicory.co/
- **What it is**: Contextual **advertising platform** for CPG & grocery
  brands. Listed as a Kroger Developer API client.
- Enterprise B2B ad tech — "Request a meeting" / enterprise sales.
- **No public developer API, no published pricing tiers.** Not a price-data
  source despite the grocery adjacency.

---

## Basketful ⚠️ enterprise, unconfirmed

- Listed as a Kroger Developer API client (client logos on developer.kroger.com).
- Appears to be enterprise grocery / recipe-to-cart technology.
- No evidence of a public developer API or solo-dev pricing.

---

## Other sources investigated — confirmed unavailable / unreachable

- **Datafiniti** (datafiniti.net): Known product-data API with pricing
  datasets, but **all domains unreachable** from the research environment
  (TLS connection reset on datafiniti.net, api.datafiniti.net,
  docs.datafiniti.net). Could not confirm pricing or coverage from primary
  sources. Retry from a non-blocked network.
- **Trolley.co.uk**: UK supermarket price-comparison site
  (Tesco, Asda, Sainsbury's, Morrisons, etc.). **No public API** —
  confirmed by fetching the homepage (no API or developer documentation).
  UK-focused; not applicable to the US market.
- **Mushroom API / Supermarket API**: Could not confirm as active,
  accessible APIs. No primary sources found; search engines were
  unavailable during the session (Google blocked, DuckDuckGo CAPTCHA).

---

## RapidAPI marketplace grocery APIs ⚠️ research incomplete

- RapidAPI hosts third-party grocery APIs (e.g. "Grocery Products API",
  various Kroger/Instacart wrappers) under per-API pricing tiers.
- Specific provider pages returned 404 or "user not found" errors.
- **Open item**: requires an authenticated RapidAPI session or manual
  browser inspection to enumerate live grocery APIs and their tiers.
- **Caution**: RapidAPI marketplace wrappers around Kroger/Instacart inherit
  the upstream ToS restrictions — verify the underlying data source and its
  terms before relying on a wrapper for price comparison.

---

## Research limitations from the session

- DuckDuckGo (lite + html) served a CAPTCHA blocking automated search.
- Google search results pages returned a "Why did this happen?" block page.
- Datafiniti domains returned TLS connection resets (likely geo/infra block).
- UPCitemdb DEV/PRO exact monthly $ amounts are not on any public page —
  only visible behind the developer portal login.
- Instacart Developer Platform pricing tiers and rate limits are not in the
  public docs — would require contacting an "Instacart representative."
