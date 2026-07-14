# Web-source discovery when search engines are blocked

Companion to `doc-extraction-recipes.md` (which covers *extracting* content once you have a URL).
This file covers *finding* the URL in the first place when the usual search path is unavailable.

## The reality: general search engines are unreliable from automated IPs

Tested 2026-07. Do NOT open a research session by querying a search engine — you will burn turns:

- **Google** → returns a `google.com/sorry/index` CAPTCHA/abuse page (IP flagged: "unusual traffic"). No results.
- **DuckDuckGo** (`html.duckduckgo.com/html/`) → returns HTTP **202** with a JS challenge page, zero organic links in the body.
- **Bing** → renders, but **geo-redirects** non-local IPs to unrelated localized results (e.g. an English query about "Stripe architecture" returned Chinese `zhihu.com`/`baidu.com` pages about HTTP proxies). Results are useless, not just empty.

`site:` operators make this worse, not better — they tip off the bot filter faster.

## Discovery ladder (use in this order)

### 1. Go direct to the known source domain, skip search entirely

If you know which company/site you need (Stripe, Salesforce, GitHub, Notion…), `browser_navigate` straight to its engineering/blog index. Most engineering blogs have a stable index URL even when individual post slugs move:
- `stripe.com/blog/engineering`, `linear.app/blog`, `shopify.engineering/`, `github.blog/engineering/`, `notion.so/blog`.

### 2. Engineering blog indexes are JS-rendered — render then extract, don't curl

`curl` on these indexes (Stripe, Linear/Now, Shopify, Notion) returns a multi-MB JS shell with **zero article links** in the raw HTML. `read_file`/grep on it finds nothing. You must:

1. `browser_navigate` to the blog index (lets JS hydrate), then
2. `browser_console` with a DOM extraction to pull the real hrefs:
   ```js
   JSON.stringify([...document.querySelectorAll('a')]
     .map(a => a.getAttribute('href'))
     .filter(h => h && h.includes('/blog/') && h !== '/blog/engineering')
     .filter((v,i,arr) => arr.indexOf(v) === i))
   ```
   This returns the hydrated link list that curl/`read_file` cannot see — same technique as extracting article *text* from JS-rendered pages (see `doc-extraction-recipes.md` § "JS-rendered docs sites"), applied to the index instead of an article.

Many Stripe/blog-engineering posts also expose a clean `.md` variant (`/blog/<slug>.md`) or a "View as Markdown" link — prefer it over DOM scraping for article *bodies*.

### 3. When a recalled URL 404s, do NOT guess the new slug — use Web Archive

Old engineering-blog deep links are frequently dead because slugs are *renamed*, not relocated. Guessing `…/scaling-linear` → `…/scaling-our-product` mostly 404s and wastes turns (this is the same restructured-portal pitfall as Okta/Atlassian/GitLab docs, just for blog posts).

Use the **Web Archive** instead:
- Availability check (rate-limited, ~429 if hammered): `https://archive.org/wayback/available?url=<url>` → JSON `{archived_snapshots:{closest:{available,timestamp,url}}}`. Space requests out; do not loop rapidly.
- Snapshot fetch: `https://web.archive.org/web/<YEAR>/<original-url>` (e.g. `…/web/2023/https://developer.salesforce.com/page/Multi_Tenant_Architecture`). Returns the archived full HTML — strip tags locally with a download-to-file-then-process script (never `curl | python3`).
- **Caveat:** not every recalled URL was archived, and some year-prefixed snapshots themselves 404. If the first year fails, try an adjacent year; if all fail, treat the source as unavailable and flag it.

The Web Archive is also the reliable path for vendor docs pages that now 403 (e.g. `developer.salesforce.com/page/…` returns 403 to direct curl but the archived copy is open).

### 4. Rendered search as a last resort

If you genuinely don't know the source domain, `browser_navigate` to a search engine *in the browser* (JS-rendered) rather than `curl`-ing it — the browser session sometimes passes the bot filter where curl doesn't. Still expect CAPTCHAs; treat a search-engine hit as lucky, not a plan.

## Anti-patterns (don't do these)

- Opening with `curl`/`browser_navigate` to `google.com/search?q=…` — CAPTCHA wall, turn wasted.
- Guessing renamed slugs by extrapolation ("probably `…/scaling-our-product`") — 404s, turns wasted.
- Rapidly looping the Web Archive availability API across many URLs — 429 throttled.
- `curl | python3` to parse HTML — shell guard blocks it. Download to `/tmp/x.html`, then read/parse the file.
- Claiming "no primary source exists" after only trying search engines + guessed URLs. Work the ladder above before concluding a source is unavailable; flag thin/missing evidence honestly.

## Pattern: research a roster of named companies

For "how do companies X, Y, Z do <thing>, cite engineering blog posts" tasks:
1. One stable index per company (step 1) → extract article links (step 2) → fetch the 1-2 most relevant per company → extract body via `.md` or `browser_console` `.innerText`.
2. Dead/moved posts → Web Archive (step 3).
3. Some companies publish *nothing* on a given internals topic (e.g. Stripe publishes their Ledger and DocDB architecture but not an explicit "tenancy model" page; Linear removed older scaling posts). Report what the available primary sources *imply* and flag where the evidence is thin — do not fabricate a model that fits.
