# Doc-extraction recipes

Concrete patterns for pulling verbatim text out of documentation sites, so you can quote/cite without bot-detection fights or browser-snapshot truncation. Organized by site; read the section relevant to your task.

---

## Cloudflare developers.cloudflare.com

### Markdown endpoint (highest leverage)

Most pages under `developers.cloudflare.com` expose their full rendered content as clean markdown at:

```
https://developers.cloudflare.com/<path>/index.md
```

For `https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/`:
```
curl -sL "https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/index.md" -o /tmp/cf_params.md
```

Returns YAML frontmatter + the full page as plain markdown — **no JS, no bot wall, no truncation.** Tables come through as pipe-tables, code as fenced blocks. This is dramatically more reliable than the browser snapshot (which hit a bot-detection warning and truncated at ~400 lines).

Fallback if `/index.md` 404s: try `/<path>/markdown/index.md`.

### The three pages you usually need together

Rate-limiting claims typically span three sibling pages — don't source a claim from only one:
- **Overview** (`/waf/rate-limiting-rules/`) → `#availability` anchor holds the **plan-tier table** (Free/Pro/Business/Enterprise columns × features rows). This is the ONLY place to settle "what plan tier supports Headers/Custom/JSON counting." The "Important remarks" section also documents counter-update lag.
- **Request rate calculation** (`/…/request-rate/`) → the verbatim **per-data-center** statement ("Counters are not shared across data centers, with the exception of data centers associated with the same geographical location").
- **Parameters** (`/…/parameters/`) → the characteristic list (`http.request.headers["<name>"]`, `cf.colo.id`, etc.) and the `cf.colo.id` "do not use in expressions" warning.

A common ADR error: claiming "header counting needs the Business plan" when the Availability table shows **Headers** is in the Enterprise-with-Advanced-Rate-Limiting column only. You will only catch this if you read the overview's Availability table specifically.

---

## AWS docs (docs.aws.amazon.com)

### "Download Markdown" link

AWS doc pages have a **"Download Markdown"** link near the page title (top of main content). Grab it directly — it's the authoritative source-text file, no HTML stripping needed.

### CloudWatch metric-definition pages

For latency/overhead claims, the canonical anchor is the metrics-and-dimensions page. Example for API Gateway:
```
https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-metrics-and-dimensions.html
```

Download to file, strip HTML, grep for the metric names. The two that define "managed hop overhead":
- **`IntegrationLatency`** — "The time between when API Gateway relays a request to the backend and when it receives a response from the backend." (Unit: ms) — your app's time.
- **`Latency`** — "The time between when API Gateway receives a request from a client and when it returns a response to the client. **The latency includes the integration latency and other API Gateway overhead.**" (Unit: ms) — total.

So overhead = `Latency − IntegrationLatency`, and AWS defines it as a real quantity but **publishes no ms number**. Claims like "20-50ms" are empirical (community benchmark), not AWS-documented. Report the metric-definition URL as the citable anchor; label the number empirical.

### Deep-link redirect wall (Cognito, and likely other restructured AWS subsites)

**⚠️ Deep/old AWS doc URLs now silently redirect to the guide root.** Navigating directly to a known deep Cognito URL like `docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-sdk-token-handling.html` does NOT land you on that page. Instead the server returns a tiny HTML stub with both a `<meta http-equiv="refresh" content="0;URL=what-is-amazon-cognito.html">` AND a `<script>self.location.replace(myDefaultPage)</script>` — you end up on "What is Amazon Cognito?" with no error surfaced. This affects:

- `browser_navigate` to the deep URL → the final `url` in the result shows the guide root, and the page title is the guide root's title. The redirect is silent from the tool's perspective.
- `curl -sL <deep-url>` → returns only the ~1.3KB redirect stub (no `Refresh:` header to follow; the real redirect is in the JS/HTML body). `wc -c` reveals ~1KB instead of the expected ~50KB article.

Old anchor-based URLs (`…/token-handling.html`, `…/revoking-all-user-tokens.html`) and app-idp-settings URLs all exhibited this in 2026-07. AWS periodically restructures doc trees and leaves these meta-refresh stubs behind.

**✅ The fix: navigate the expanding sidebar tree to the sub-page, then extract via `browser_console`.** The sidebar (in the `navigation "Side navigation"` region) is the source of truth for current URLs:

1. `browser_navigate` to the guide root (`…/developerguide/what-is-<service>.html`).
2. Click the top-level section button (e.g. "Amazon Cognito user pools") to expand it — ref IDs like `@e147`.
3. Click the nested section button (e.g. "User pool tokens") to expand the leaf list — `@e350`.
4. Click the leaf link (e.g. "Refresh tokens", "Revoking tokens") — `@e375`, `@e376`.
5. Extract content via `browser_console` (`document.querySelector('#main-col-body')?.innerText ?? document.body.innerText`) — Cognito renders server-side so the content is in the initial HTML, but the sidebar is the only reliable way to reach the right page.

The "Download Markdown" link (next section) still works once you've landed on the right page — the redirect wall only defeats direct deep-linking, not in-page extraction. If you have a markdown link, prefer it; if you only have a deep HTML URL, use the sidebar.

**Proven on (2026-07):** A refresh-token-rotation verification task. Six direct-deep-link attempts (browser + curl) all landed on the guide root. Expanding the sidebar (user pools → user pool tokens → refresh tokens) reached the correct page, and `#main-col-body` extraction returned the full ~3000-word rotation doc including the verbatim `origin_jti` / `jti` claims and the grace-period wording.

### AWS pricing pages — the image-table trap (use the Price List API instead)

**⚠️ The naive approach does NOT work.** `https://aws.amazon.com/<service>/pricing/` renders its pricing **tables as `<img>` tags** — there is no `$X.XX/million` text anywhere in the HTML to grep. Downloading and tag-stripping yields only the surrounding prose ("Pay only for the API calls you receive…"), never the actual per-tier numbers. The `browser_snapshot` shows `image` nodes where the tables should be, and `document.querySelectorAll('table')` returns `0`. **Do not waste a turn grepping a pricing page for numbers — they aren't there as text.**

**✅ The fix: the AWS Price List API (Bulk API).** AWS publishes the exact same pricing as machine-readable JSON, updated daily. This is the *authoritative* source (it feeds the AWS Pricing Calculator), and it carries tier descriptions as text strings — strictly better than the rendered image.

**Single-service index (all regions, ~700KB for API Gateway):**
```
https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<ServiceCode>/current/index.json
```
where `<ServiceCode>` is the AWS service code (e.g. `AmazonApiGateway`, `AmazonCloudFront`, `AmazonEC2`, `AmazonS3`). The `publicationDate` field in the JSON tells you how fresh it is.

**Per-region variant** (smaller, if bandwidth matters): append `/current/region_index.json` to get a map of region → version URL.

**Schema you need to navigate (key field names):**
- `products` — dict keyed by SKU. Each has `productFamily` (e.g. `"API Calls"`, `"Amazon API Gateway Cache"`), `attributes.regionCode` (`us-east-1`), `attributes.usagetype` (`USE1-ApiGatewayHttpRequest`), `attributes.operation` (`ApiGatewayHttpApi`), `attributes.description` (`HTTP API Requests`).
- `terms.OnDemand.<sku>.<termId>.priceDimensions.<pdId>` — dict of price tiers. Each has:
  - `pricePerUnit.USD` — the rate as a string like `"0.0000035000"` (per single unit).
  - `unit` — `"Requests"`, `"GB-Mo"`, `"hours"`, etc.
  - `description` — **human tier text as published**, e.g. `"$3.50/million requests - first 333 million requests/month"`. This is the verbatim source you quote in the scorecard.

**Proven parse recipe** — filter `products` by `regionCode == us-east-1` AND `usagetype` matching the service's request type, then for each match walk `terms.OnDemand` to pull every `priceDimension`. Multiple priceDimensions on one SKU = volume tiers. See `scripts/parse-aws-price-list.py` — it runs as-is for any service/region and prints SKU → tier descriptions → per-unit USD. Run it rather than hand-rolling each time.

**Cross-check the two sources:** the pricing-page prose (e.g. "one million API calls … for HTTP APIs") and the Price List API tier descriptions should agree. When they do, you can cite the Price List API (machine-readable, dated) as the authority and quote the `description` string verbatim. The pricing page itself is still useful for *narrative* claims ("pay only for calls you receive", "no data transfer charges for Private APIs") — just not for the numbers.

**Service codes** are discoverable via `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/offers.json` (lists every ServiceCode + current version URL). When in doubt, grep that file.

---

## nginx.org docs

Static HTML, no markdown endpoint, no bot wall. Simple two-step:
```
curl -sL "https://nginx.org/en/docs/http/ngx_http_proxy_module.html" -o /tmp/nginx_proxy.html
```
Then extract with a local Python script that reads the file from disk (NOT a `curl | python` pipe — see guard note below). For a specific directive, regex between the `<a name="<directive>"></a>` anchor and the next directive anchor:
```python
m = re.search(r'<a name="proxy_cache_valid"></a>.*?(?=<a name="proxy_connect_timeout")', html, re.DOTALL)
```
then strip tags. This is how to pull the verbatim *"If only caching time is specified … then only 200, 301, and 302 responses are cached."* and the `Set-Cookie` / `Cache-Control` override caveats from the same paragraph.

---

## PostgreSQL docs (postgresql.org)

### Static HTML, no bot wall, no markdown endpoint

Like nginx.org, `postgresql.org/docs/<version>/` serves static server-rendered HTML. Download-to-file then tag-strip works perfectly — no JS, no bot wall, no truncation. Versioned URLs are stable across minor versions:

```
curl -sL "https://www.postgresql.org/docs/16/sql-insert.html" -o /tmp/pg_insert.html
```

The same generic Python tag-strip from the nginx section works as-is (remove script/style, mark `<hN>` as `###`, unescape entities). Every page comes through clean.

### Slug naming — do NOT guess from prefixes (you will 404)

PostgreSQL doc slugs are kebab-case titles only, with **no section-number prefix and no consistent word stem**. This is the trap:

- ✅ `indexes-unique.html` (§11.6 Unique Indexes)
- ✅ `indexes-types.html` (§11.2 Index Types)
- ✅ `index-locking.html` (§64.4 Index Locking Considerations)  ← **note `index-` not `indexes-`**
- ✅ `index-unique-checks.html` (§64.5 Index Uniqueness Checks)

Guessing `indices-index-locking.html` (extrapolating from the `indexes-`/`indices-` stems seen elsewhere) returns a **"Page not found"** body — which still comes back HTTP 200, so check the *body*, not just the status code. The lesson: **slugs are title-derived, not taxonomy-derived.** When unsure of a slug, find it two reliable ways:

1. **From a cross-reference.** Docs cite each other by section ("the details are covered in Section 64.5"). Resolve the section number to a slug via the chapter's table-of-contents page: `https://www.postgresql.org/docs/16/<chapter-toc>.html` lists every sub-page with its real slug. Chapter ToCs live at e.g. `indexes.html` (Ch 11), `mvcc.html` (Ch 13), `indexam.html` (Ch 64, "Index Access Method Interface Definition" — not `indices.html`).
2. **From Prev/Next nav.** Every page's bottom nav names the adjacent section and links its slug. A downloaded page already contains the slugs of its neighbors, so one fetch gets you two more for free.

### Heavy nav chrome — content starts after the *second* title occurrence

Stripped output has ~90 lines of version-selector chrome (supported/dev/unsupported version lists) at the top of every page before the real content. The page title appears **twice** — once in the `<title>` area (line ~1) and again as the `<h1>` heading (line ~99). Real content starts at the **second** occurrence. When reading a 150-line stripped file, jump to the second `<title>` / `### N.M. Title #` line (e.g. `read_file offset=99`) and skip the chrome. Or grep for the section number (`### 64.5.`) to land directly on content.

### Error-code table (Appendix A) — SQLSTATE lookup

`errcodes-appendix.html` is the authoritative SQLSTATE → condition-name map. The table is clean text after stripping: each code sits on its own line above its condition name. To verify an error like `unique_violation`:

```
grep -n "23505\|unique_violation" errcodes.txt   # → 23505 / unique_violation under "Class 23 — Integrity Constraint Violation"
```

No other doc page carries these — always go to Appendix A for error-code claims.

---

## IETF RFCs and Internet-Drafts (rfc-editor.org, ietf.org) — plain text, no extraction gymnastics

IETF specifications are the canonical primary source for protocol/security questions, and they're uniquely easy to extract: every RFC is published as **clean plain text** (no HTML to strip, no JS, no bot wall, no truncation). This makes them the fastest source class to quote verbatim.

### RFC plain-text endpoint

```
curl -sS -L -o /tmp/rfc9700.txt https://www.rfc-editor.org/rfc/rfc9700.txt
```

The `.txt` is fixed-width plain text with form-feed page breaks (`\f`) and page headers/footers. `read_file`, `search_files` (ripgrep), and `grep` all work directly. Section numbers are stable anchors (`grep -n "4\.14\.  Refresh Token Protection"` lands you on the exact line). For quoting, the line-numbered `read_file` output (`LINE_NUM|CONTENT`) is ideal — you cite by RFC §number, not line number, but the line numbers let you navigate the full text. Companion formats if needed: `…/rfcNNNN.html`, `…/rfcNNNN.xml`. Prefer `.txt` for verbatim quoting.

### The draft→RFC verification pattern (check canonical status FIRST)

**⚠️ When the ask references a draft (`draft-ietf-…`), check whether it has become an RFC before fetching the draft.** Drafts are versioned (`-23`, `-24`, `-28`…) and the final version becomes an RFC with a different identifier. Citing `draft-ietf-oauth-security-topics-28` when `RFC 9700` exists is citing a superseded artifact — the RFC is the authoritative published version.

**How to check:** fetch the datatracker page and look for the canonical RFC number:
```
curl -sS -L https://datatracker.ietf.org/doc/draft-ietf-oauth-security-topics/ | grep -iE "rfc|canonical"
```
The `<link rel="canonical">` and `<meta property="og:title">` tags reveal the RFC number (e.g. `content="RFC 9700: …"`), the BCP number, and "Updates: RFC NNNN" relationships.

**When to still fetch the draft:** to confirm substantive equivalence (diff/grep the relevant section between the last draft and the published RFC) or to access changelog/appendix history. Drafts live at `https://www.ietf.org/archive/id/draft-ietf-<wg>-<name>-<rev>.txt`. A quick `grep -c "<term>" rfc.txt draft.txt` on key terms confirms they match.

**⚠️ Draft URL gotchas (2026-07):** The `www.ietf.org/archive/id/draft-ietf-<wg>-<name>-latest.txt` `-latest` suffix **404s** — the archive only serves explicit revisions (`-07`, `-13`, etc.), not `-latest`. And the **WG folder name can differ from the obvious guess**: the idempotency-key draft is `draft-ietf-**httpapi**-idempotency-key-header` (HTTPAPI WG), *not* `draft-ietf-httpbis-idempotency-key-header` (HTTPBIS WG) — guessing `httpbis` returns a 404 page. Both of these return a real IETF "404 - Not Found" HTML page (not an error status), so check the body, not just HTTP 200.

**✅ The reliable draft-discovery path:** use the datatracker API to find the draft name + latest revision, then fetch the explicit revision:
```
# Find drafts by title keyword
curl -sL "https://datatracker.ietf.org/api/v1/doc/document/?title__icontains=<keyword>&format=json"
# → returns draft names like "draft-ietf-httpapi-idempotency-key-header" with rev numbers

# Then fetch the explicit revision's text
curl -sL "https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt"
```
The datatracker HTML render (`https://datatracker.ietf.org/doc/html/draft-ietf-<wg>-<name>-<rev>`) is a reliable fallback when the archive `.txt` is elusive — it returns the full draft text server-rendered, strip the tags locally.

**Proven on (2026-07):** Fetching the idempotency-key standard for a refresh-token crash-recovery analysis. `draft-ietf-httpbis-idempotency-key-header` (wrong WG) and the `-latest.txt` suffix both 404'd. The datatracker API (`title__icontains=idempotency`) revealed `draft-ietf-httpapi-idempotency-key-header-07` (Oct 2025, HTTPAPI WG) as the correct document; the explicit `-07.txt` fetched cleanly.

**Proven on (2026-07):** "Research the OAuth 2.0 Security BCP (draft-ietf-oauth-security-topics, now RFC 9700)." Datatracker canonical URL confirmed RFC 9700 (BCP 240, Jan 2025, updates RFCs 6749/6750/6819). Fetched `rfc9700.txt` (2569 lines, clean) and `draft-…-28.txt` — §4.14 matched verbatim.

### Absence-as-evidence: grep the full text to prove a negative

A full-text `grep` across the complete RFC artifact is a legitimate and powerful evidence technique. Because you have the *entire* source (not a truncated browser snapshot), a zero-match result is a real finding, not a truncation artifact.

```
grep -n "7009\|Token Revocation\|RFC 7009" /tmp/rfc9700.txt   # → zero hits = the BCP doesn't cite RFC 7009
```

This surfaced a key finding: **RFC 9700 (the Security BCP) does not reference RFC 7009 (Token Revocation) anywhere** — neither normative nor informative references. That absence shaped the entire conclusion (the BCP's strategy is rotation + sender-constraining + short access-token lifetimes, not RFC 7009 revocation). The same grep on `draft-…-28.txt` confirmed it wasn't a post-RFC edit.

**Rule:** for "does spec X mention/cite Y" questions, download the full `.txt`, grep it, and report the match count (including zero). Strictly more reliable than skimming the table of contents or relying on memory of what a spec "covers."

### Quoting multiple related RFCs together

OAuth/security questions often require quoting the foundational RFC (6749), the BCP that updates it (9700), and companion specs (7009, 8705, 9449) in the same finding. Download all of them as `.txt` artifacts up front — they're small (~50–250KB each) and the cross-references between them (§numbers, [RFCxxxx] citations) are the connective tissue of the evidence. Cite each quote with its RFC §number and the `rfc-editor.org/rfc/rfcNNNN.txt` URL.

---

## JS-rendered docs sites (Mintlify / Auth0 / Docusaurus client-rendered) — use `browser_console` DOM extraction

Some docs sites are **client-rendered SPAs** — the HTML returned by `curl` is a multi-megabyte shell with the real content injected by JavaScript at runtime. Auth0 docs (`auth0.com/docs`, built on Mintlify) is the canonical example: `curl` returns ~5MB of HTML but the actual article text is absent; it's hydrated by JS. Mintlify also powers many other SaaS docs sites, so this pattern recurs.

**❌ The two approaches that DON'T work well here:**

1. **`curl -o file.html` + tag-strip** — returns the JS shell, not the content. You get nav chrome and script bundles, not the article. (For server-rendered sites like nginx.org/postgresql.org this works; for client-rendered SPAs it does not.)
2. **`browser_snapshot`** — loads the page correctly (JS runs), but the accessibility-tree snapshot is **truncated** at ~8000 chars / a few hundred lines and is dominated by nav/sidebar elements. On a content-rich page you get the left sidebar (every nav link, expanded tree) and "181 more lines truncated" — you never reach the article body.

**✅ The fix: `browser_console` with a DOM `.innerText` extraction.**

After `browser_navigate` to the page (which lets JS run), call `browser_console` with a JavaScript expression that grabs the content element's rendered text:

```javascript
// browser_console expression — tries article, then main, then body
document.querySelector('article')
  ? document.querySelector('article').innerText
  : document.querySelector('main')
    ? document.querySelector('main').innerText
    : document.body.innerText
```

This returns the **full, clean, JS-rendered text** in a single call:
- **No truncation** — `browser_console` returns the complete result string, unlike `browser_snapshot`.
- **JS-rendered** — the DOM has been hydrated, so dynamic content is present (curl can't see it).
- **Targeted** — `article`/`main` selectors skip the nav sidebar chrome that bloats `browser_snapshot`. Fall back to `body` if the site lacks semantic containers.

**When to use which selector:**
- `article` — most docs/blog sites wrap content in `<article>`. Try this first.
- `main` — fallback for sites using `<main>` without `<article>` (common in some Docusaurus configs).
- `[role='main']` or a site-specific content class — last resort if the above are empty. Inspect via `browser_console` with `document.querySelector('h1')?.closest('section,div,article')?.className` to find the content container class.

**Proven on:** Auth0 Refresh Token Rotation page (`auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation`). `curl` gave 4.9MB of JS shell (no content); `browser_snapshot` was truncated before reaching the article; `browser_console` with `document.querySelector('article').innerText` returned the full ~3500-word page including the "Automatic reuse detection" section, worked examples, and SDK list — all the quotable material in one call.

**Pattern for the rest of the flow:** once you have the clean text from `browser_console`, you don't need to re-fetch — copy the relevant verbatim quotes directly into your findings file with the page URL. The URL is the citation anchor; the `browser_console` extraction is just the reading mechanism.

---

## Restructured docs portals (Okta developer.okta.com, GitLab, Atlassian) — discover slugs by clicking, not guessing

**⚠️ Docs portals that mirror a product's own IA restructure frequently, and they 404 (not silently redirect).** Unlike the AWS meta-refresh wall (which sends you to the guide root with no error), these portals return a real HTTP **404 "Page not found"** page. Old deep URLs you recall or find in ADRs/old tickets are unreliable. Affected in 2026-07: `developer.okta.com` — the entire tree moved; `oauth-token/`, `implement-oauth/configure-refresh-token/`, `concepts/oauth-overview/`, `oauth-openid-connect/` all 404.

The trap: guessing the new slug by extrapolating from siblings (e.g. trying `concepts/token-lifecycles/` after seeing `concepts/oauth-openid/`) **mostly 404s too** — slugs are renamed, not just relocated, and there's no consistent stem. Burning turns guessing is worse than the AWS case because each guess is a full navigation round-trip.

**✅ The fix: load a known index page, click the actual nav link, read `location.href`.**

1. `browser_navigate` to a stable index/landing page you know exists (e.g. `developer.okta.com/docs/concepts/` — the concepts hub survived the restructure). The snapshot shows the left sidebar nav with every concept as a `link` ref.
2. `browser_click` the ref of the topic you need (e.g. `@e77` "Token lifecycles").
3. Immediately call `browser_console` with `location.href` — this returns the *current canonical URL* of the page you just landed on. That string is your citation anchor going forward.
4. Extract content via `browser_console` DOM extraction (`document.querySelector('main')?.innerText`). These portals render server-side, so `main` (not `article`) is usually the right selector, and the content is present in the initial load.

This is strictly faster than guessing-and-404ing, and it doubles as a citation-discovery step: you get the exact current URL from `location.href` to use in your scorecard.

**Proven on (2026-07):** An OAuth token-rotation verification task. Five guessed Okta slugs 404'd (`docs/api/oauth-token/`, `docs/concepts/oauth-overview/`, `docs/concepts/token-lifecycles/`, etc.). Clicking the "Token lifecycles" link (`@e77`) from `/docs/concepts/` revealed the real URL was `/docs/concepts/token-lifecycles/` (one guess was right, but only *after* confirming via click — guessing got 4/5 wrong). The `location.href` + `main.innerText` combo then extracted the verbatim "added to a blocklist or denylist" revocation quote in one call.

**When you have the current URL, prefer `browser_console` over re-navigating.** Once `location.href` gives you the slug, you don't need to revisit — the extracted text + the URL is everything you need to cite. Only re-navigate if you need a different sub-page.

---

## The `curl | interpreter` guard — and the fix

**Blocked pattern:**
```
curl -sL "https://…" | python3 -c "…"     # ❌ shell safety guard blocks this
```
The guard flags piping downloaded content into an interpreter as untrusted-code execution. You'll get `status: pending_approval` / `approval_pending: true` and exit_code -1.

**Correct pattern — download to file, then process the file:**
```
curl -sL "https://…" -o /tmp/page.md      # ✅ download only
# then in a separate step:
python3 -c "import re; html=open('/tmp/page.html').read(); …"
# or just:
read_file /tmp/page.md
```
This is guard-friendly AND leaves the artifact on disk so you can `read_file` it again or re-grep without re-downloading. Prefer `read_file` for markdown; use the local Python strip for HTML.

---

## Discovery: search engines are an unreliable discovery layer — go direct to authoritative URLs

**⚠️ Google and DuckDuckGo both throw bot-walls/CAPTCHAs at automated agents.** This is now the default, not a rare edge case:

- **Google** (`google.com/search?q=…`) returns a **302 redirect to `google.com/sorry/index`** — an "unusual traffic from your computer" CAPTCHA page. HTTP 200, but zero results. No error is surfaced; the snapshot just shows the interstitial.
- **DuckDuckGo** (`duckduckgo.com/?q=…` and `html.duckduckgo.com/html/?q=…`) returns a **"Select all squares containing a duck"** challenge page. The snapshot shows the CAPTCHA form, not results. DDG's lite/HTML endpoints that used to work for bots are now also gated.

You cannot solve these reliably headless. **Do not burn turns retrying search or trying alternate engines** — treat search-engine discovery as broken for this class of work and route around it.

**✅ The reliable discovery path — assemble a candidate-URL list from domain knowledge, then fetch directly:**

1. **List the authoritative sites** for the question by domain knowledge, not search:
   - Language/framework behavior → the official docs site (postgresql.org/docs, mongodb.com/docs, …). These are static HTML you can curl directly (see per-site sections above).
   - Independent correctness analysis → jepsen.io/analyses, aphyr.com/posts — known fixed URL patterns. Jepsen analyses live at `https://jepsen.io/analyses/<product>-<version>`; Aphyr's "Call Me Maybe" series at `https://aphyr.com/posts/<id>-call-me-maybe-<product>`.
   - Vendor engineering blogs → the canonical post URL if you can recall it (e.g. `uber.com/blog/<slug>`). Note these are often JS-heavy and bot-blocked even via curl — try `browser_navigate`; if it times out, note the URL is known-but-unreachable and don't cite content you couldn't fetch.
2. **Follow cross-references from a fetched page** instead of searching. Doc pages cite sibling sections ("see Section 64.5"); Jepsen reports link earlier analyses; official docs link their own sub-pages. One successful fetch gives you 2-5 more known-good URLs via the page's own links. For docs sites, the Prev/Next nav at the bottom names adjacent sections with real slugs (see "Slug naming" under PostgreSQL above).
3. **For "does a benchmark/case study exist?"** questions specifically: go to the primary docs + independent-audit sites first. Often the answer is "no direct benchmark exists, and none is needed — this is a correctness/failure-mode question, not a throughput one." That framing is itself the finding; don't manufacture a benchmark citation that doesn't exist.

**Proven on (2026-07):** A "find benchmarks comparing PG unique constraint vs MongoDB unique index under concurrent inserts" task. Google → `/sorry/index` wall; DuckDuckGo → duck-CAPTCHA. Pivoting to direct fetches of `postgresql.org/docs/current/index-unique-checks.html`, `mongodb.com/docs/manual/core/index-unique/`, `jepsen.io/analyses/mongodb-4.2.6`, `aphyr.com/posts/284-call-me-maybe-mongodb` (all HTTP 200) produced a stronger answer than search would have — primary-source quotes plus the documented failure modes from Jepsen/Aphyr.

**When you genuinely need search** (no candidate URLs come to mind, the topic is novel): try `browser_navigate` to the search engine — the browser stack sometimes passes where curl won't — but expect it to fail and have the direct-URL plan ready. Do not retry the same engine more than once.

---

## Generic strategy when a site has no markdown endpoint

1. `curl -sL -o /tmp/<name>.html` (download only — no pipe).
2. `read_file` it directly if it's small, or run a local Python tag-strip if large.
3. For "does the page mention X" questions, grep the saved file with `search_files` (ripgrep) — the full artifact, not a truncated browser snapshot.
4. Only fall back to the browser (`browser_navigate` + `browser_snapshot`) for sites that require JS to render content, or for interactive clicks. For docs sites that render server-side, the file artifact is strictly better.
