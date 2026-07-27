---
name: competitor-research-verification
description: > 
  Live-verification techniques for researching competitors during venture
  dossier builds. Covers detecting competitor repositioning/pivots via
  browser, multi-source triangulation (GitHub landscape → HN funding →
  browser verification → pricing), and the pattern of cross-referencing
  known competitor claims against live evidence rather than citing stale
  comparison data.
tags:
  - research
  - competitor-analysis
  - market-research
  - due-diligence
---

# Competitor Research Verification

## When to use

- During the competitive-landscape section of any venture dossier
- After initial competitive scanning to verify each known competitor still
  exists in its stated category
- Before citing a competitor's pricing, funding, or product claims

## Core principle: verify every competitor live, every session

A competitor cited in a prior dossier, scan, or comparison table may have
pivoted, raised (or run out of) funding, changed pricing, or exited the
category entirely. The half-life of a startup competitor's positioning is
~6 months. Always verify before citing.

## Verification workflow

### Step 1: Cross-reference with HN Algolia for market presence

Search for the competitor name on HN to see their last significant signal
(funding announcement, launch, Show HN, or complaint):

```
curl -sL "https://hn.algolia.com/api/v1/search?query=COMPETITORNAME&tags=story&hitsPerPage=5"
```

Check: When was their last HN post? How many points did it get? If their
last appearance was 12+ months ago despite having significant VC funding
($9M+), a pivot or sunset is possible.

### Step 2: Browser homepage verification

After curl fails to return meaningful pricing/structure, use the browser
to check the homepage:

1. `browser_navigate("https://competitor.com")`
2. Read the accessibility tree snapshot — does the positioning match
   what you expect?
3. If skeptical, `browser_console(expression="document.body.innerText")`
   to see fully rendered content curl might have missed.

**Pivot signals:**
- Homepage describes a research lab, foundation, adjacent category, or
  completely different value proposition
- No pricing page exists (or redirects to a generic about page)
- No login / dashboard / "Get started" entry
- Messaging emphasizes research outputs (papers, blog posts) over product
- "About" section dominates over "Product" section

### Step 3: Pricing verification — JSON-LD first, regex second, browser last

Before citing a competitor's pricing, extract it live from their pricing page.
Pricing extraction has three tiers — **try them in this order**:

**Tier 1 — schema.org JSON-LD (check the raw HTML first).** Many SaaS pricing
pages embed complete, exact tier pricing as structured data in
`<script type="application/ld+json">` blocks (`@type: Offer` / `@type: Product`).
This gives exact tier name + price + currency + billing unit with zero regex
ambiguity, and it's in the *initial* HTML — no browser render needed. Always
grep the raw HTML for JSON-LD before anything else:
```python
import re, json
with open('page.html', encoding='utf-8', errors='ignore') as f: html = f.read()
for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
    try: data = json.loads(block)
    except json.JSONDecodeError: continue
    nodes = data if isinstance(data, list) else [data]
    for n in nodes:
        for g in (n.get('@graph') or [n]):
            for offer in (g.get('offers') if isinstance(g, dict) else None) or []:
                name = offer.get('name', g.get('name',''))
                price = offer.get('price')
                unit = (offer.get('priceSpecification') or {}).get('unitText','')
                print(f"{name}: ${price} {unit}".strip())
# Quick probe if the structured walk misses:
for m in re.finditer(r'"name"\s*:\s*"([^"]+)"[^}]*?"price"\s*:\s*"?(\d[\d,]*)"?', html):
    print(f"{m.group(1)}: {m.group(2)}")
```
Verified 2026-07-24 (onboarding-tools landscape): **Intercom** JSON-LD gave
`Essential $39 SEAT_PER_MONTH`, `Advanced $99`, `Expert $139`, `Fin $0.99/resolution`;
**Userflow** JSON-LD gave `Adoption Studio monthly $500 / annual $400` and
`Adoption Agent monthly $100 / annual $80` — complete billing-cycle structure
that regex on rendered text alone would have missed.

**Tier 2 — clean curl+regex.** When no JSON-LD offers exist, strip `<script>`
tags first (to avoid Next.js/React hydration false-positives — framework
serialization blobs contain dollar amounts that aren't real prices), then regex
the visible text for `[\\$€£]\\s?\\d[\\d,]*`. Captures server-rendered tiers.

**Tier 3 — browser_console on the rendered DOM.** Only when curl returns
JS-gated HTML (empty price spans, just a bundle manifest). After
`browser_navigate`, run `document.body.innerText` or an element-filter query
to extract client-rendered prices.

**Tier 4 — iTunes Search/Lookup API for mobile-app competitors.** When a
competitor's marketing site is 401/404/unreachable but it's an iOS app,
Apple's public API returns base price, seller, and description with no
bot-walling:
```
# Search by app name → get trackId, formattedPrice
curl -sL "https://itunes.apple.com/search?term=<url-encoded-name>&entity=software&limit=3"
# Lookup a known app id directly
curl -sL "https://itunes.apple.com/lookup?id=<trackId>&country=us"
# results[0].formattedPrice → "Free", "$9.99", etc.
```
This reliably gives the base app price ("Free" is common for freemium
trackers). It does NOT return in-app-purchase tier prices — for IAP fall back
to the App Store web page or mark "IAP price not verified live this session."
Confirmed 2026-07-25 (subscription-cancellation landscape): **Bobby**
(`id1059152023`) and **Subby** (`id6739703718`) both verified "Free" via
lookup when their own sites returned 401/unreachable.

**Detect sales-gating as a competitive signal.** When a pricing page has a
pricing URL but no dollar amounts anywhere (JSON-LD, regex, or DOM), the product
is **sales-gated** ("Book a demo" / "Request a quote"). This is itself a
meaningful competitive data point: a sales-gated tool has forfeited the
self-serve / SMB / solo-buyer segment by definition. Record it explicitly
("sales-gated, no public price") rather than marking "pricing not found."
Verified 2026-07-24: Pendo, Appcues, Stonly, Whatfix, and WalkMe are all
sales-gated with no public price; ChurnZero's `/pricing/` returns a 404.

**Tier 2.5 — entity-encoded JSON in `data-*` / inline `<script>` blobs.**
Some sites serialize their full tier table as a JSON object inside an inline
`<script>` tag or a `data-tippy-content`/`data-*` attribute, with quotes
HTML-entity-encoded (`&quot;` for `"`). A flat `\$` regex hits every dollar
amount on the page (className hashes, component IDs, unrelated examples) and
produces an unreadable wall; the structured blob gives you tier-name ↔ price ↔
unit in one pass. When a pricing page is large (>100KB) and dollar-regex
returns noise, search for the serialized structure instead:
```python
import re
t = open('p.html', encoding='utf-8', errors='ignore').read()
for m in re.finditer(r'&quot;name&quot;:&quot;([^&]+)&quot;,&quot;price&quot;:&quot;(\$[\d,]+)&quot;,&quot;(\w+)&quot;:&quot;([\d,]+)&quot;', t):
    print(m.group(1), m.group(2), m.group(3), m.group(4))
```
The exact key order varies by site (probe with a looser regex first), but the
`&quot;name&quot;...&quot;price&quot;...` adjacency is the stable anchor.
Confirmed 2026-07-25 on **serpapi.com/pricing**: this recovered all 50+ tiers
(Starter $25/1k → Cloud 54M $424,200/mo) where dollar-regex alone returned a
span of 50+ unattributed amounts. This is distinct from Tier-1 JSON-LD
(`application/ld+json`, real quotes, schema.org shapes) — it's vendor-specific
serialization that happens to be parseable.

**Tier 3.5 — pricing behind auth / JS-hash route.** A growing number of SaaS
sites put pricing behind a login wall or load it via a JS hash route that the
public snapshot doesn't contain. `curl` returns nothing useful and
`browser_navigate` lands on a login redirect. **Do not burn a browser login
flow on a research fetch.** Instead: capture whatever IS public (funding,
traction logos, partner names, endpoint names) and **explicitly flag the
per-unit price as "pricing behind auth — not verified live this session."**
The no-fabrication rule is satisfied by saying so, not by producing a number.
Confirmed 2026-07-25: **Tavily** (`tavily.com/#pricing` loads the price table
via JS hash; `app.tavily.com/pricing` requires login) — captured "$25M Series
A, 2M+ developers, joining Nebius, partners IBM/Databricks/JetBrains" from the
public homepage and marked the $/1k rate unverified. This is different from
sales-gating (Tier-2/3 found a pricing URL with no numbers) — here there's a
pricing *page*, but it's gated behind identity.

### Step 3b — Extract revenue / user-count from self-disclosed-metrics pages

Private companies won't publish financials, but a surprising number expose a
**self-disclosed live-metrics / "live stats" page** that reports paying users,
queries-per-day, or member counts in real time. This is a first-class primary
source — stronger than any third-party estimate — and is often missed because
the data lives on a path like `/stats`, `/live`, `/about`, or a footer link, not
the pricing page. **Check for one before citing a triangulated estimate.**

Workflow:
1. After loading the homepage/pricing in the browser, **scan the footer and
   company nav for "Live Stats", "Stats", "Transparency", or "About" links.**
2. Navigate to it and read the accessibility snapshot — the counts are usually
   rendered as plain StaticText (e.g. `StaticText "73,426 Members"`), no
   extraction tricks needed.
3. If a time-series chart is present, **read the most-recent AND oldest
   visible data points** to compute a growth rate (members gained per month).
   The chart labels are often in the snapshot as
   `graphics-symbol "Jul 11: 73,016"`.
4. **Triangulate revenue only if no financials are disclosed:** (verified
   member count × blended ARPU from the pricing tiers). Label it explicitly as
   an estimate ("≈$8.7M ARR triangulated from 73K members × ~$10 blended ARPU").

Verified 2026-07-25 (search-engine landscape): **Kagi** (`kagi.com/stats`)
publishes 73,426 members, 1,021,200 queries/day, and a 14-day member-growth
chart — enough to triangulate ~$8.7M ARR with no third-party source. This page
is the single most authoritative source on Kagi's business that exists, and it
sits behind a "Live Stats" footer link that is easy to overlook.

### Step 3c — Detect consumer → B2B-API pivot via pricing-page structure

A consumer SaaS that has **abandoned consumer pricing entirely** and now only
sells a developer API has executed a **consumer → B2B pivot**. This is a
stronger competitive signal than a pivot *within* consumer: the company
concluded the consumer model didn't pay and switched to where WTP is proven.
Detect it structurally — no archive.org or press release needed:

- The `/pricing` page lists **API tiers priced per-1k-calls / per-request**
  (e.g. "$5.00 /1k calls", "$12.00 /1k calls") and **no per-seat or monthly
  consumer plan** anywhere on the page.
- The page leads with **developer/API framing** ("Web Search API", "Research
  API", "SOC 2 certified", "MCP Server", "SDK") rather than consumer benefits.
- A "free credit" line ("$100 free credit to get started") instead of a free
  tier / trial for end-users.

Record it as **"pivoted entirely to B2B API — consumer abandoned"** and cite
the pricing-page structure as the evidence. Then frame it in the dossier as
the market's own verdict on consumer viability: if a funded player ($20M+
seed) walked away from consumers, the consumer model is structurally hard.
This is the direct counterpart to the "vacated segment" pattern in
`references/magical-healthcare-pivot-example.md`, but at the *business-model*
level rather than the *vertical* level.

Verified 2026-07-25: **You.com** (`you.com/pricing`) — originally a consumer AI
search engine for developers (HN 29165601, $20M+ seed) — now shows API-only
pricing (Web Search $5/1k, Contents $1/1k, Research $12/1k, Finance $110/1k)
with zero consumer plans. The pivot is the evidence; cite it as the market
validating that search-tech monetization works best selling to AI-agent
builders, not consumers.

### Step 4: GitHub repo check (for OSS competitors)

If the competitor has an OSS project or SDK:

```
curl -sL -A "Mozilla/5.0" "https://api.github.com/repos/ORG/REPO"
```

Check for: stale commits (>6 months without push), archived repo, or a
README that describes a different product than expected.

### Step 5: Multi-source triangulation

Combine findings from Steps 1-4 into a verdict:

| Source | If healthy | If pivoted |
|--------|-----------|------------|
| HN Algolia | Recent launch/funding (last 6 mo) | No HN presence in 12+ mo |
| Browser homepage | Clear product + pricing | Research lab / switched category |
| GitHub activity | Active pushes in last 60 days | Archived or dormant (>6 mo) |

### Detecting ACQUIRED / DEFUNCT competitors (distinct from a pivot)

A named competitor is frequently **acquired or dead** by research time —
different from a pivot (the entity still exists, just aimed elsewhere). This
is itself dossier evidence: a category where standalone players keep getting
absorbed (or die) is structurally fragile, and the surviving product is
often degraded into the acquirer's bundle. Three live signals distinguish
this from a pivot, and each is a citable finding rather than a "not found":

- **`curl` returns `HTTP:000 SIZE:0`** — the domain doesn't resolve or
  connect at all. The product is almost certainly dead (not JS-gated, not
  pivoted — gone). Confirmed 2026-07-25: `trim.is` and `subbyapp.com` both
  `HTTP:000`; both products defunct. Don't cite a price; mark "appears
  defunct — could not verify live."
- **Tribute / wind-down homepage** with a "2016–2025" date range and
  "Acquired by X" language is a shutdown notice, not a live product.
  Confirmed 2026-07-25: **Cushion** (`cushion.ai`) shows "2016–2025,
  AI-Powered Consumer Finance, Acquired by LendingClub" — the homepage IS
  your evidence the competitor exited.
- **Redirect-to-acquirer on the pricing or root URL.** `curl -L` and check
  `url_effective`; if it lands on a different company, the original was
  absorbed. Confirmed 2026-07-25: `vendr.com/pricing` → `vertice.one/pricing`
  = Vendr acquired into Vertice. The acquirer's pricing/marketing replaces
  the target's; cite the surviving entity.

**Confirm the deal via HN.** Search `<competitor> acquired` on HN Algolia —
the acquisition thread's linked press (Reuters/HousingWire/TechCrunch) gives
you a citable deal price and date (e.g. Truebill → Rocket Companies, $1.275B
cash, Dec 2021; HN 29626570). This turns "competitor gone" into "competitor
gone, $1.275B exit" — a market-size signal, not just a footnote.

**Pattern worth recording:** when *multiple* standalone competitors in a
category are all acquired or dead (2026-07 subscription-cancellation:
Truebill→Rocket, Cushion→LendingClub, Trim dead), the standalone model is
structurally hard. Note this in the dossier's net-gap as both a risk and a
wedge — the acquirers typically degrade the acquired tool, leaving room for
a focused independent entrant.

## Example: Martian detection (2026-07-24)

- **Known as:** Martian (withmartian.com) — model router startup, $9M raised
- **HN check:** Last HN post was low-engagement from May 2024 (2pts, 0c)
- **Browser check:** No model router product found; homepage described
  "Thesean AI" — an interpretability research lab studying "model minds"
- **GitHub:** No active router-related repos
- **Verdict:** Pivoted out of router category. This detection meaningfully
  thinned the competitive landscape for the AI Cost Optimization dossier,
  contributing to a score uplift from 17→19/25.

## Reusable reference data

- [`references/onboarding-adoption-tools-pricing.md`](references/onboarding-adoption-tools-pricing.md) — live-verified pricing for 20+ customer-onboarding / digital-adoption / in-app-guidance tools across enterprise, mid-market, indie, and founder-workaround tiers, with extraction method per tool (2026-07-24). Reusable for any onboarding, adoption, DAP, or PLG dossier. Includes the verified price-ladder / solo-founder gap analysis.
- [`references/verified-pricing-ipaas-smb-sync.md`](references/verified-pricing-ipaas-smb-sync.md) — live-verified pricing for iPaaS (Zapier, n8n, Make-blocked, Workato, Tray), SMB CRMs (Keap $249/mo, HubSpot, Pipedrive-blocked), and AI-native automation (Bardeen, Magical-pivoted) for the SMB data-sync / zero-config-automation category (2026-07-24). Includes Cloudflare-blocked-site handling and the whitespace price-band analysis.
- [`references/martian-thesean-pivot-example.md`](references/martian-thesean-pivot-example.md) — worked example of detecting a competitor pivot (Martian → Thesean AI).
- [`references/magical-healthcare-pivot-example.md`](references/magical-healthcare-pivot-example.md) — worked example of detecting a competitor pivoting OUT of a target segment (Magical: SMB autofill → healthcare AI operations, 2026-07-24). Includes the "vacated segment" competitive-intel pattern: a pivot away from your segment is a first-class signal, but requires distinguishing under-served (bullish) from unviable (bearish).
- [`references/verified-pricing-subscription-cancellation.md`](references/verified-pricing-subscription-cancellation.md) — live-verified pricing/status for 13 consumer + SMB subscription-cancellation/SaaS-spend tools (Rocket Money, Truebill-defunct, Cushion-defunct, Trim-dead, Bobby, Subby, Capital One Eno, Vendr→Vertice, Tropic, Cledara, Spendesk, Tally, Papercups) + FTC Click-to-Cancel rule finalized-then-struck-down timeline + the "standalone players keep getting absorbed" structural fragility pattern (2026-07-25). Reusable for any consumer-fintech / bill-negotiation / SMB SaaS-spend dossier.
- [`references/verified-pricing-devtools.md`](references/verified-pricing-devtools.md) — live-verified pricing for AI-coding/code-quality/code-review dev tools (CodeRabbit, SonarQube, Cursor, Sourcery, Qodo) + the "$12–$48/seat/mo settled band" pricing heuristic + extraction recipe for SSR Next.js pricing pages + the PLG free-tier/rate-limit gating pattern (2026-07-25). Reusable for any devtools / AI-coding-assistant / code-quality / developer-platform dossier.
- [`references/verified-pricing-search-api.md`](references/verified-pricing-search-api.md) — live-verified pricing for the "search API for AI agents" segment (Serper $0.30–$1/1k, Exa $7/1k, SerpAPI $25–$3750/mo, Brave $3–$5/1k, Mojeek £2–3 CPM, You.com credit model) + the Layer-1-owns-index vs Layer-2-wrapper framing + the Bing-API-retired-Aug-2025 WhyNow signal + the crowded 2025-26 entrant wave (Tavily $25M Series A, Crustdata, Seltz, Quercle, Souko, ArguSeek, LLMLayer). Reusable for any search / web-access / RAG / AI-agent-infrastructure dossier. (2026-07-25)
- [`references/hn-pain-signal-mining.md`](references/hn-pain-signal-mining.md) — Reusable 5-stage technique for extracting verbatim pain-point quotes from HN for a dossier's §1/§2 (multi-query story discovery → targeted thread fetch → pain-keyword tree-walk → comment-level razor-phrase search → parent-metadata resolve + URL verification). Produces quotes with exact text + verifiable URL + date + engagement. The go-to method when Reddit is blocked or the audience lives on HN.
- [`references/ai-code-bloat-pain-quotes.md`](references/ai-code-bloat-pain-quotes.md) — 12 verified verbatim HN quotes (Apr 2025–Jul 2026, parent threads 13–1774 pts) on the "AI always adds code / refactor-vs-append / code bloat" problem, with corroborating threads and root-cause synthesis. Reusable demand-side evidence for any AI-coding-tools dossier. Re-verify URLs before citing.
- [`references/verified-landscape-search-engines.md`](references/verified-landscape-search-engines.md) — live-verified data for 16 alternative / SEO-spam-free search engines across 5 monetization tiers (Kagi, Brave, DDG, SearXNG, Marginalia, Mwmbl, You.com, Perplexity, Neeva-defunct, Mojeek, Gibiru, TinySearch, Arlong-unverified) + the "consumer subscription works at boutique scale only" pattern (Kagi ~$8.7M ARR vs Neeva $77M → dead) + the consumer→B2B-API pivot exemplar (You.com). Reusable for any search-engine / answer-engine / web-index / meta-search dossier. (2026-07-25)
- [`references/duckduckgo-html-search.md`](references/duckduckgo-html-search.md) — DuckDuckGo HTML endpoint (`html.duckduckgo.com/html/`) parse script, redirect-URL extraction, silent rate-limiting behavior. Corrects the pinned `venture-research` skill's "all search engines blocked" claim. (2026-07-25)
- [`references/web-source-access.md`](references/web-source-access.md) — consolidated try-in-order source-access map for headless research: search engines (Brave + DDG-HTML, neither permanently reliable — try both), the Reddit escalation ladder (`.json` → `.rss` → `old.reddit.com` HTML → pipeline `signals/`), and reliable official-stats sources (Apple Newsroom, Google Security Blog, FTC). The single reference to consult first when a source returns blocked/empty. (2026-07-25)
- [`references/app-store-research-tooling.md`](references/app-store-research-tooling.md) — Apple iTunes Search/Lookup API (official, no auth, field reference, rate limit) + google-play-scraper (Python/Node, the only way to search Google Play — no official search API exists) + impersonation-detection techniques (RapidFuzz name matching, imagehash icon similarity) + market-sizing data (app counts, GitHub repo counts, TAM derivation). (2026-07-25)
- [`references/app-store-brand-protection-landscape.md`](references/app-store-brand-protection-landscape.md) — live-verified competitor table for 11 brand-protection / anti-counterfeiting players (ZeroFox, Tracer, MarkMonitor-repositioned, Mimecast-BED-404, Bolster-blocked, PhishLabs/Fortra-blocked, CSC, Appdome-wrong-category, Brand24, Mention-repositioned, Validecs-defunct) + the ClipGrab entry incident (HN 48830439) + the indie-dev whitespace analysis (no service targets indie/OSS; sub-$50/mo self-serve band unoccupied; process-not-detection is the moat). Reusable for any brand-protection / app-impersonation / fake-app / takedown dossier. (2026-07-25)

## Copycat-feasibility / market-crowding signal (for copycat-venture dossiers)

When an idea is a **copycat of a known reference product**, triangulate
whether the wedge is defensible using three numbers — often more decisive than
the feature analysis alone:

1. **Reference product's GitHub stats** (stars/forks/open-issues) via the
   single-repo endpoint (`api.github.com/repos/OWNER/REPO`). Low absolute
   traction (single-digit stars, zero forks) means either (a) the idea is too
   early, or (b) the category is crowded and the reference is being
   out-competed.
2. **The reference's Show HN / Launch thread** (points + comments) via HN
   Algolia (`/items/<id>` on the story). A Show HN that got 1 point is itself a
   signal — poor distribution or insufficient differentiation.
3. **Competing-tool count**: run the HN Algolia search across the category's
   keyword cluster and *count how many Show HN launches for comparable tools*
   appeared in the last ~6 months. **5+ comparable OSS tools launching in a
   window = a saturated field** where a new entrant's *differentiation*, not the
   technology, is the existential question.

**Reading the triangulation:** if (1) is low AND (2) is low AND (3) is high,
the evidence points to "crowded category, reference flopping, no clear unowned
wedge" — record this in the dossier's risks as the riskiest assumption, not as
a feature gap to fill. This is a *go/no-go* signal, not a roadmap input.

Example (agent-security repo-intake scanning, 2026-07): the reference product
(agent-zero-trust) had 4 GitHub stars / 0 forks; its Show HN got 1 point; and
an HN Algolia sweep found 10+ comparable OSS tools (Aguara, Driftcop, MCP
Security Suite, mcp-scan, Golf Scanner, Aidevshield, ClawCare, ContextGuard,
SkillScan, Beelzebub) launched in the prior ~6 months. The dossier concluded
the defensible venture is a *curated advisory database* (the "GHSA for agent
instruction surfaces"), not another scanner — because the scanner is a weekend
build and the field is saturated. See
[`references/agent-security-landscape.md`](references/agent-security-landscape.md).

**Where to capture the finding:** record the landscape + verified thread IDs +
GitHub stats in `references/<domain>-landscape.md` so a future dossier reuses
the sweep instead of re-running it.

## Wrong-category competitor detection (distinct from pivot / defunct)

A competitor on your list may be **real, active, well-funded, and still not a
competitor** — because it operates in a *different category* than the thesis
assumes. This is a distinct signal from a pivot (the company changed direction)
or a defunct player (the company died). Here nothing changed about the company;
your assumption about what they do was wrong, often inherited from a stale
comparison table or a similar-sounding name. Three reasons a healthy company is
misclassified as a competitor:

1. **Wrong category entirely.** The company solves a different problem that
   *sounds adjacent* and gets lumped in by list-makers. Always read the
   top-level product nav + hero copy, not just the company name. If the product
   described ≠ your thesis, reclassify as "adjacent / wrong category."
2. **Same noun, different verb.** "App protection" can mean *detecting fakes of
   your brand* (your thesis) OR *hardening your own app against tampering* (a
   different product). The overlap is in the marketing vocabulary, not the
   buyer or the workflow. The product-nav scan disambiguates.
3. **Enterprise bundle line-item mistaken for a product.** A capability appears
   inside a behemoth's security suite but isn't sold standalone and isn't the
   focus. This is encroachment (see that section), not a same-category rival.

Record *why* (one sentence: the actual category) so the dossier can cite the
misclassification as a landscape-thinning signal rather than a live rival.
Misclassification is itself evidence: when a naive list over-counts rivals
because names sound similar, the true category is narrower — and the fact that
no one does exactly your thesis is the gap.

Verified 2026-07-25 (app-impersonation landscape): **Appdome** was on the
named-competitor list but is a *mobile app security-hardening platform*
(builds anti-fraud/anti-bot defenses INTO your own apps) — it does NOT detect
fake apps impersonating your brand. Healthy, active, well-funded, wrong
category. **Mimecast Brand Exploit Defense** — the parent repositioned to
"Human Risk Management / Email Security" (BED's product page 404s); no longer a
standalone brand-protection product. The reclassifications thinned the field
and confirmed the indie-dev whitespace.

## Secondary citations must be independently verified

A common fabrication trap: a source (README, blog, vendor comparison) *cites*
prior-art URLs/incidents ("Mozilla warns of…", "Microsoft case study on…").
Treat these as **leads, not evidence.** A secondhand citation is not the same
as a live-verified source. Before putting it in a dossier's evidence table:
- Fetch the cited URL yourself (curl/browser) and confirm it says what the
  intermediary claims; **or**
- Flag it explicitly: *"cited in [intermediary]; not independently verified
  this session."* Never pass a secondhand citation through as if you'd checked
  the primary source. The no-fabrication rule covers *representing unverified
  material as verified*, not just inventing quotes.

This matters most when an idea's prior-art section is built from one README's
link list — copying those links into a dossier without checking them inherits
any rot or misattribution in the README. Confirmed 2026-07-25: the
agent-zero-trust README cites Microsoft + Cloud Security Alliance blog posts as
prior art; the session flagged both "needs-verification" rather than citing
them as live-confirmed.

## Encroachment detection — checking whether the window is already closing

Pricing verification tells you what a competitor *charges*. For WHY-NOW /
Competition scoring you also need to know whether an incumbent has *already
started building into the thesis*. A common failure mode is treating a
competitor's pricing as the full signal while missing that incumbents have
already encroached. Run this encroachment check on the nearest 2–3
incumbents (adjacent-category vendors, not same-category rivals):

1. **Product navigation scan.** Navigate to each incumbent's homepage /
   pricing page and read the *top-level product nav* (not just the pricing
   table). A new top-nav item marked "New", or a recently shipped product
   line, is the strongest encroachment signal — it means the incumbent has
   already committed engineering + marketing to the space.
2. **Pricing-tier feature-list scan.** Read the *feature bullets* under each
   pricing tier, not just the dollar amounts. Encroachment often appears as
   a single feature line inside a higher tier (e.g., "Scan AI models",
   "AI-generated code protection") before it becomes a standalone product.
3. **Three-level classification.** State, per incumbent, whether the current
   offering (a) does not cover the thesis, (b) partially covers it as a
   feature, or (c) has shipped a dedicated product for it. This is more
   useful than a flat "competitor exists" note for scoring Competition / WhyNow.

**Distinguishing encroachment from normal competitive overlap:** encroachment
is *directional* — an incumbent in an *adjacent* category adding your thesis
as a feature/product. Normal competition is multiple vendors *already in*
your category. If the nearest competitors are adjacent (not same-category),
encroachment risk is high and the window is short.

**Example (Pre-Flight Repo Security Scan, 2026-07-25):** The nearest two
incumbents both encroached. Snyk has "Evo Agent Security" as a top-nav
product (marked New) — level (c), dedicated product shipped. Socket.dev
Business tier ($50/dev/mo) lists "Scan GitHub Actions and AI models" as a
feature line — level (b), partial coverage. This encroachment finding, *not*
the pricing table, confirmed the window was closing and validated the prior
kill; the pricing data alone looked like a normal competitive landscape.
Full pricing + encroachment table in
[`references/agent-security-landscape.md`](references/agent-security-landscape.md).

### Pricing-model structural misalignment (a fourth encroachment lens)

Beyond product-nav / feature-list / dedicated-product, check whether an
incumbent's **pricing unit** is aligned or *misaligned* with your thesis. If
the incumbent's revenue metric is the thing your product *reduces*, the
incumbent is structurally disincentivized from building your feature
themselves — which is both (a) a wedge they won't easily close and (b) a
positioning argument ("they profit from the problem we solve"). Record it in
the dossier's net-gap as a **structural advantage**, not just a feature gap
— it is harder to copy than a feature, because copying it means cannibalizing
their own per-unit revenue.

**Example (AI code-quality landscape, 2026-07-25):** Two incumbents charge
**by lines-of-code processed** — DeepSource ($8–15 per 10K LOC on top of
$24/dev/mo) and Bito ($5 per 1K LOC overage above 5K/seat/mo). A venture
whose thesis is *reducing* code (refactor-don't-append enforcement,
deduplication, code-bloat removal) is structurally misaligned with their
revenue: every line the tool removes is revenue the incumbent loses. This
makes DeepSource/Bito poor candidates to build the code-reduction feature
themselves — an opening for a focused entrant pricing per-seat (not per-LOC).
Full landscape in
[`references/ai-code-quality-linting-landscape.md`](references/ai-code-quality-linting-landscape.md).

## HN engagement as an adoption proxy

When official user/download numbers for a dev tool aren't available (private
vendor, pre-disclosure), **top-thread point + comment counts on HN are a
reliable relative-adoption proxy**. Compare across tools, not in absolute
terms:

- A tool whose launch thread crosses **~1,000+ points and ~500+ comments**
  has reached mass developer awareness.
- Multiple threads above that threshold over 6–12 months signals *sustained*
  adoption, not a launch spike.
- Use this when: (a) the vendor is private and doesn't disclose users
  (Cursor/Anysphere pre-ARR-leak), (b) you need a triangulation signal for
  ICP sizing, or (c) the tool is too new for third-party market reports.

**Example (Claude Code adoption, 2026-07-25):** No public user count exists,
but the launch thread (HN 43163011, 2,127 pts / 963 comments) and a later
steganography thread (HN 48734373, 2,445 pts / 750 comments) — plus ~15
threads over 1,000 pts across 2025–2026 — establish that Claude Code has
among the highest sustained HN engagement of any dev tool in the period.
Cite the thread IDs + counts as the evidence; don't assert a user number.

## Bottom-up market sizing (TAM / SAM / SOM)

When a dossier needs a defensible market-size number, build it **bottom-up from
adoption × price** — do NOT cite a paywalled market-research figure (those
sources block headless access anyway and are usually stale). This pairs
naturally with the HN-engagement / GitHub-traction proxies above: the adoption
side comes from a named, citable figure (Copilot 20M+ paid users; Cursor
~$100M+ ARR), and the price side comes from the verified competitor pricing
tables. The model:

1. **TAM** = (total addressable users of the *underlying* tool/category) ×
   (blended annual price/seat). Anchor the user count to a named, citable
   figure. Derive seats from revenue when user counts are private:
   `~$100M ARR ÷ $240/yr ≈ 400k+ paying seats`. Cite each source.
2. **SAM** = the slice of TAM matching your ICP (company size, region,
   buyer-has-budget). Express as a % of TAM with a one-line justification
   (e.g., "~15–20% of AI-tool users sit in 50–500-dev orgs that already buy
   dev-quality tooling").
3. **SOM** = 3-year reachable revenue at a credible capture rate. **1–2% of
   SAM via PLG + outbound is a standard Series-A-scale claim.** Compare to a
   real comp's trajectory ("CodeRabbit reached 7-figure ARR in ~2 years on a
   similar wedge") so the SOM isn't a naked number.

**Example (AI Always-Adds-Code Fixer, 2026-07-25):** TAM ~$6B (25M AI-coding
users × $240/yr) → SAM ~$1B (4M pro devs in 50–500-dev target orgs) → SOM
$10–20M ARR (1–2% of SAM). Every multiplier stated with its basis; no naked
dollar figures.

**Pricing anchor for devtools / AI-coding dossiers:** the market has settled
on **$12–$48/seat/month** for AI-adjacent code-quality / review SaaS (verified
2026-07-25: CodeRabbit $24/$48, SonarQube $20–$34, Cursor $20/$40, Sourcery
$12/$24, Qodo ~$15–19). New ventures should price in the $15–$30 (Pro) /
$30–$50 (Team/Ent) band, per-seat/month annual, with a free tier gated by OSS
repo type or rate limit (PLG table-stakes). See
[`references/verified-pricing-devtools.md`](references/verified-pricing-devtools.md)
for the full table and extraction recipe.

## Finding the right URL when direct guesses 404 — try Brave then DDG

When you don't know a vendor's or article's exact URL (Apple restructures
newsroom paths frequently; regulatory press releases live deep in agency
sites; incident reports are on news domains you haven't memorized), use an
**HTML search endpoint** as the discovery interface — Google and Bing both
return captcha pages, but **two** HTML endpoints have each worked in
*different* sessions, so **try both, in order, until one returns parseable
HTML**: Brave Search (`search.brave.com/search`) then DuckDuckGo HTML
(`html.duckduckgo.com/html/`).

**Don't hardcode one as "the working fallback."** This skill previously
treated DDG-HTML as the one reliable engine, but on 2026-07-25 (App Store
Impersonation research) DDG returned empty for every query while **Brave
Search** delivered — recovering exact Apple Newsroom fraud-stats URLs, the
correct BleepingComputer article slug, and Reddit thread paths. Neither
session's verdict is permanent; the divergence is real, so the order-of-attack
matters, not a fixed claim.

```bash
# Option A — Brave Search (try first)
curl -sL "https://search.brave.com/search?q=<url-encoded-query>&source=web" \
  -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36" -o brave.html
# Option B — DuckDuckGo HTML (try second)
curl -s -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://html.duckduckgo.com/html/?q=<url-encoded-query>" -o ddg.html
```

Both return server-rendered HTML parseable with curl + regex. DDG result
URLs are redirect links — extract with `re.search(r'uddg=([^&]+)', url)` +
`urllib.parse.unquote()`. Both can **rate-limit silently** (0-byte pages,
not errors) — add `sleep 3` between calls and retry once before concluding
a query is empty.

See [`references/web-source-access.md`](references/web-source-access.md)
for the consolidated, try-in-order source-access map (engines + Reddit
escalation ladder), and [`references/duckduckgo-html-search.md`](references/duckduckgo-html-search.md)
for the DDG-specific parse script.

**Note:** This contradicts the pinned `venture-research` skill's claim that
"all search engines (Google, Bing, DuckDuckGo, Brave) block headless." That
skill should be updated to reflect both DDG-HTML and Brave work, once unpinned.

## App store / mobile-app competitor research

For mobile-app ventures (impersonation monitoring, clone detection, app
ecosystem sizing, mobile competitor pricing), the two stores have a critical
**asymmetry**: **Apple has a legitimate public search API; Google Play does
NOT and must be scraped.** Both are reliable from headless:

- **Apple iTunes Search/Lookup API** — no auth, ~20 calls/min, returns
  name/developer/bundleId/icon/price/genres. `attribute=softwareDeveloper`
  for developer-specific search; `lookup?id=<artistId>&entity=software`
  returns a developer's full app catalog.
- **google-play-scraper** (Python: `JoMingyu/google-play-scraper` 998★;
  Node.js: `facundoolano/google-play-scraper` 2920★) — returns title,
  appId, developer, installs bucket, score, genre. No official search API
  exists (Google Play Developer API is publishing-only).

For impersonation-detection ventures specifically: RapidFuzz (fuzzy name
matching) cleanly separates impersonators (70.6 score) from competitors
(36.8); imagehash (perceptual hashing) detects near-identical icons via
Hamming distance. See
[`references/app-store-research-tooling.md`](references/app-store-research-tooling.md)
for full API reference, verified field lists, scraper usage, detection
techniques, and market-sizing data points (app counts, GitHub repo
counts, TAM derivation).

## Pitfalls

- Do NOT cite a competitor as an active market participant based on a
  stale comparison table or prior dossier. Always verify live.
- A short HTML body from curl does NOT mean the site is JS-rendered — it
  could mean there's nothing there anymore. Use the browser to distinguish.
- HN silence is not definitive proof of a pivot — some successful companies
  stop posting to HN. But combined with a homepage that no longer matches
  the expected category, it's strong evidence.
- If a competitor's homepage has a product tour + pricing + login but the
  messaging is stale/unchanged, they're likely still operating even if
  their HN presence is quiet.
- Funded competitors ($5M+) are more likely to pivot than shut down — they
  have the runway to try a new direction. Track their homepage, not just
  their Crunchbase profile.
- **Cloudflare can block BOTH curl and headless browser on the same site.**
  When a pricing page returns 403 to curl AND a "Just a moment..." /
  "Sorry, you have been blocked" title to `browser_navigate`, stop
  retrying — the site is behind an enterprise WAF that defeats both paths.
  Cite pricing as "publicly documented, could not verify live this session"
  rather than inventing a number. Confirmed 2026-07-24: **Make.com**
  (`make.com/en/pricing`) and **Pipedrive** (`pipedrive.com/en/pricing`)
  both Cloudflare-blocked curl AND browser; G2 and GetApp also 403. Do NOT
  treat these as "JS-rendered, escalate to browser" — the browser is
  blocked too. Retry in a future session (blocking is environment- and
  time-dependent), but don't burn the current session on it.
- **A pivot OUT of your target segment is a first-class competitive signal,
  not just an absence of competition.** When a named competitor has left
  the segment you're targeting (e.g. Magical: SMB autofill → healthcare),
  the segment is under-served — frame it as a "vacated segment"
  opportunity in the net-gap summary. BUT distinguish *under-served*
  (bullish: the incumbent's cost structure couldn't serve SMB, leaving room
  for a cheaper entrant) from *unviable* (bearish: the segment structurally
  doesn't support a business). A pivot out is evidence the economics are
  hard; engage that risk honestly. See
  `references/magical-healthcare-pivot-example.md`.
- **Reddit verbatim-quote access — escalate `.json` → `.rss` → `old.reddit.com` HTML, don't give up.** Reddit pain/complaint threads are often the best evidence source but its access surface is flaky and *session-dependent*. The main `reddit.com/.../json` and `.rss` endpoints frequently return HTTP 403 ("blocked by network security") or silent 0-byte pages. When they do, **`old.reddit.com/r/SUB/comments/ID/SLUG/` (plain HTML, desktop UA) still works** and returns the full submission body + comments (parse successive `<div class="md">` blocks; HTML-unescape + strip tags). Verified 2026-07-25 (App Store Impersonation research): `reddit.com/.../json` returned the identical 403 block page for *every* thread, but `old.reddit.com` HTML recovered the full OP + top comments for r/androiddev `1kbeyr7`, r/apple `usd6b2`, and r/iOSProgramming `1lpfale`. Do NOT conclude "Reddit is blocked" from a `.json` failure alone. See [`references/web-source-access.md`](references/web-source-access.md) for the full ladder.
