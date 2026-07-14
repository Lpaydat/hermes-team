---
name: web-research
description: Investigate external platforms, APIs, services, and documentation using the browser toolset. Use when you need to determine API capabilities, pricing, rate limits, sign-up requirements, coverage, or feature availability from live web sources (developer portals, affiliate programs, docs sites, marketing pages). Covers techniques for JS-rendered SPA docs, headless browser limitations, and citing primary source URLs.
---

# Web Research via Browser Tools

Investigate a question about an external platform, API, or service against
**live primary sources** — the vendor's own developer portal, docs site,
affiliate/marketing pages, and API reference — not secondary write-ups.

## Core workflow

1. **Identify the canonical entry points.** Most platforms have 2–4 distinct
   surfaces that are easy to conflate. Map them BEFORE deep-diving:
   - **Developer portal** (API reference, SDKs, auth specs)
   - **Affiliate/partner program** (commission, data feeds, sign-up)
   - **Marketplace/seller portal** (seller-facing management APIs)
   - **Marketing homepage** (capabilities overview, pricing tiers)

   For Walmart, these turned out to be: `developer.walmart.com` (seller APIs),
   `www.walmart.io` (developer/affiliate APIs), and `affiliates.walmart.com`
   (the affiliate program). They are different platforms with different auth
   and different capabilities — do not assume one covers the others.

2. **Harvest all hrefs first.** Before reading page content, extract every
   link to discover the real structure:
   ```js
   Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.textContent.trim()})).filter(a => a.text || a.href)
   ```
   This reveals docs paths, sub-portals, and API category pages that
   marketing copy doesn't mention by name.

3. **Read the marketing/FAQ/onboarding pages for the overview.** These are
   usually server-rendered and load reliably. They summarize capabilities,
   pricing, sign-up steps, and link to the deeper docs. Cite both: the
   overview page you actually read AND the docs URL it points to.

4. **Confirm with the API reference.** Open the actual endpoint list to
   verify which operations exist. For seller/marketplace APIs, check
   whether operations are read (browse) or write (manage) — a "Price
   Management" API that only has PUT/POST is for *setting* prices, not
   *reading* them.

5. **Cite every claim with a URL.** Each finding in the output must trace
   to a specific page you actually loaded. If you could not render a page,
   say so explicitly — do not fabricate its contents.

6. **Read the Terms of Service for use-case restrictions.** When the research
   is about whether an API can serve a specific product (e.g. price
   comparison, aggregation, scraping), the ToS is often the deciding factor
   — more than the technical capabilities. See "Extracting text from long /
   truncated pages" below for how to pull specific clauses out of a long ToS,
   and "Pitfalls → Ignoring ToS use-case restrictions."

## Extracting text from long / truncated pages

`browser_snapshot(full=true)` truncates pages over ~8000 chars — it stops
mid-way through long legal terms, API reference pages, or full-page renders.
When you need to find specific clauses (price, rate limit, prohibition,
indemnity) inside a large document that has already rendered, use
`browser_console` to filter the full DOM text in-place instead of scrolling:

```js
const lines = document.body.innerText.split('\n');
lines.filter(l => /rate limit|prohibit|fee|pricing|per call|royalt/i.test(l))
     .join('\n---\n');
```

This returns every matching line as a single string, regardless of how long
the page is — `browser_snapshot` cannot see below the truncation point, but
`document.body.innerText` can. Patterns to keep handy:

- **Terms/restrictions**: `/prohibit|may not|restrict|forbid|not permit/i`
- **Pricing**: `/fee|pric|\$\d|per call|per month|tier|quota|rate limit/i`
- **Rate limits**: `/rate limit|requests per|calls per|throttl|quota|RPS|QPS/i`
- **Data fields**: `/price|inventory|stock|fulfil|availability|SKU/i`

Confirm any flagged clause by re-rendering that section or following its
section link — regex hits are leads, not settled citations. This technique
surfaced the Instacart Developer Platform ToS prohibition on cross-retailer
price comparison (clause k/l) that a truncated snapshot had hidden — the
single most important finding in the grocery-API research session.

## Handling JS-rendered SPA documentation

Many modern docs sites (Walmart I/O, Stripe, Instacart, etc.) are
client-side rendered SPAs that fail to render in headless mode. See
`references/researching-javascript-rendered-doc-sites.md` for full diagnosis
and workaround techniques, and `references/grocery-price-apis.md` for a
worked example mapping a whole API landscape (Instacart, Kroger, Chicory).

**Quick rules:**
- Empty snapshot + 40+ JS exceptions + `SSR disabled` in HTML = SPA that
  won't render headless. This is an environment limitation, NOT evidence
  the docs/API don't exist.
- Try `www.` prefix if the bare domain returns Forbidden.
- Static shell HTML still contains `<a>` tags — harvest hrefs even from
  unrendered pages.
- Fall back to marketing/FAQ/onboarding pages (usually server-rendered)
  for the capability overview.
- State unconfirmed items as "could not verify from primary docs in this
  session" — never fabricate specs, rate limits, or schemas.

## Output format

Structure findings as direct answers to each sub-question asked, with a
summary table where multiple platforms/options are compared. Each answer
block cites the source URL. Close with a "Limitations" section listing what
could not be confirmed and recommended next steps.

## Pitfalls

- **Conflating platforms.** A "Walmart API" could mean the Marketplace Seller
  API, the Affiliate API, or the Grocery/Pickup API — different products,
  different auth, different access requirements. Always disambiguate.
- **Assuming seller APIs serve buyers.** Marketplace developer portals
  (developer.walmart.com, developer.amazon.com) are for *sellers to manage
  their own listings* — they do not browse competitor prices. Do not cite
  them as a price-data source.
- **Treating headless render failure as "docs don't exist."** The page works
  for real users. Note the limitation, recommend a non-headless check, and
  do not draw negative conclusions.
- **Fabricating specs you couldn't read.** Rate limits, response fields,
  and coverage details that live behind a SPA you couldn't render must be
  marked unconfirmed, not guessed.
- **Ignoring ToS use-case restrictions.** An API that technically exposes
  pricing may still *prohibit* your intended use in its Terms. Instacart's
  Developer Platform Terms (clauses k & l) explicitly forbid "display priced
  items from multiple retailers on the same screen" and "move, copy, compare,
  or transfer items from one retailer basket to another" — so it cannot be
  used for price comparison even though it returns price data. Always report
  "can I legally use this for X?" separately from "does the API expose X?"
