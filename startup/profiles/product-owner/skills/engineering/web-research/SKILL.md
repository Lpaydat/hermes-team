---
name: web-research
description: >-
  Conduct systematic web research when standard search tools
  (Google, DuckDuckGo, Bing) block automated queries. Covers
  direct API access to academic databases, reader-proxy extraction
  of search-engine HTML, in-page JS extraction from authoritative
  pages (the browser fallback when search is fully blocked), and
  targeted content retrieval — the complete alternative-search
  toolkit for agent-based research.
---

# Web Research (Alternative Search Techniques)

Use this skill when you need to search the web for information
but standard web-search tools (browser-based Google/DuckDuckGo)
are blocked by CAPTCHA, bot detection, or rate limiting.

## The Core Problem

- Google Search returns CAPTCHA walls from most headless browser
  IP ranges. DuckDuckGo's JS interface shows the same.
- Traditional search-engine scraping does not work without
  residential proxies.
- You still need access to academic papers, industry blog posts,
  documentation, and news.

## Primary Toolkit

### 1. arXiv API (Direct XML Feed)

Use the arXiv API for academic paper searches. It is free, has no
CAPTCHA, and supports structured field queries.

```
curl -sL "https://export.arxiv.org/api/query?search_query=all:%22{term}%22+AND+all:%22{term2}%22&max_results=10&sortBy=relevance"
```

Key query fields: `ti:` (title), `au:` (author), `abs:` (abstract),
`all:` (full entry). Combine with AND / OR / NOT.

Parse the XML response or extract key fields:
```
curl -sL "..." | grep -E "<title>|<id>http|<summary>"
```

**Caveats:** Max 10 results per query for reliability. Rate limit is
approximately 1 request per 3 seconds. Use `&start=N` for pagination.

### 2. jina.ai Reader Proxy (for DuckDuckGo HTML)

When you need general web search (not just academic papers), use
DuckDuckGo's lightweight HTML frontend via the jina.ai reader proxy:

```
curl -sL "https://r.jina.ai/https://duckduckgo.com/html/?q={encoded+query}"
```

This bypasses the JS-based CAPTCHA because:
- The HTML frontend (`/html/`) has weaker bot detection than the JS
- The jina.ai reader acts as a fetch-and-extract layer
- The result is clean Markdown rather than raw HTML

Extract result links:
```
grep -oE 'uddg=(https?%3A%2F%2F[^&]+)' | sed 's/uddg=//' | python3 -c "import sys,urllib.parse; [print(urllib.parse.unquote(l.strip())) for l in sys.stdin]"
```

**Caveat:** jina.ai may have its own rate limits. Use responsibly.
The extracted HTML result set is the same as what a human on a
text-only browser would see.

### 3. Content Extraction (Full Blog/Article Reads)

Once you have URLs from search results, extract full article text:

```
curl -sL "https://r.jina.ai/https://{article-url}"
```

This produces clean Markdown with title, publish date, and body text.
Useful for reading blog posts, static/SSR documentation pages (e.g.
readthedocs, MkDocs, Sphinx, GitHub READMEs), and news articles.

**CRITICAL CAVEAT — client-side-rendered (CSR) docs frameworks defeat jina.ai.**
Sites built with Docusaurus (`docs.slack.dev`, many Vercel-hosted docs),
Nextra, Next.js docs, Gatsby, or VuePress fetch their content via JS
*after* the HTML shell loads. jina.ai returns HTTP 200 + clean-looking
Markdown, but the body is **only the navigation sidebar / header boilerplate**
— the actual article text is missing. Worse, this output is identical across
every page on the site, so you can mistake it for a thin/empty article when
really the extraction silently failed.

**Detection heuristic — a jina.ai fetch on a docs page is CSR-failed when:**
- The Markdown is much shorter than the page title promises, AND
- It's mostly a flat list of section/anchor links (the sidebar), AND
- Two different URLs on the same domain return near-identical content.
When you see this, do NOT retry jina.ai on the same URL. Skip straight to
`browser_navigate` + `browser_console` extraction (technique #5 below),
which runs the JS and renders the real content.

### 4. Direct API Access (Domain-Specific)

For high-trust primary sources, prefer direct API access:

| Source | API Endpoint | Notes |
|--------|-------------|-------|
| arXiv | `export.arxiv.org/api/query` | XML, structured field queries |
| GitHub | `api.github.com` | Search code, issues, repos |
| HN Algolia | `hn.algolia.com/api/v1/` | Hacker News search |
| Wikipedia | `en.wikipedia.org/w/api.php` | Structured content |
| Reddit | ~~`www.reddit.com/r/{sub}/.json`~~ | **BLOCKED** — see Reddit pitfall below. Use DuckDuckGo `site:reddit.com` via jina.ai instead. |

### 5. Direct Navigation + In-Page JS Extraction (browser fallback)

When **every search engine** is bot-blocking (Google, Bing, DuckDuckGo,
Ecosia, Startpage all CAPTCHA from headless IPs) but you know the
authoritative source URLs directly (encyclopedias, docs, standards
pages), use `browser_navigate` to load the HTML page and extract its
text via `browser_console`:

```
# Step 1: navigate directly to the known authoritative page
browser_navigate → "https://en.wikipedia.org/wiki/Software_verification_and_validation"

# Step 2: extract the readable text from the rendered page
browser_console → expression:
    document.querySelector('#mw-content-text').innerText.substring(0, 8000)
```

**Why this works when search engines don't:**
- Reference sites (Wikipedia, MDN, official docs) generally serve
  content to any client without aggressive bot detection — the
  CAPTCHA walls live on the search-engine front doors, not on the
  destination pages.
- `browser_navigate` already renders the page and returns a snapshot,
  but for long articles the snapshot is truncated. The `browser_console`
  JS extraction gives you the full `innerText` (up to the limit you
  request) in one call.

**When to use it:**
- You already know the canonical URL (e.g., `en.wikipedia.org/wiki/<Topic>`),
  or can construct it, or saw it referenced in an earlier successful fetch.
- Search engines are all blocked and jina.ai is rate-limited/slow.
- The content is on a static/SSR HTML page (most encyclopedias, docs).

**Combination pattern:** navigate to a portal/hub page (e.g., a
Wikipedia article), skim its section links in the snapshot, then
navigate to the most relevant linked sub-articles — each one loads
cleanly because they are content pages, not search pages.

**Caveat:** `browser_console` returns a string; if you request more
than ~10K chars it can be truncated by the tool layer. Page through
with `substring(N, N+8000)` offsets if you need a long article in full.

## Research Strategy Pattern

1. **Start with arXiv** — structured, reliable, covers papers/tech
2. **Start broad on arXiv** — use `all:` queries with OR between
   related terms to discover the vocabulary the field uses
3. **Follow with DuckDuckGo HTML via jina.ai** — for industry blog
   posts, practitioner content, and news
4. **If search engines are ALL blocked**, switch to **direct
   navigation** (#5 above): construct the canonical URL for the
   most authoritative source (Wikipedia, official docs, standards
   bodies) and extract text via in-page JS. Chain from one known
   page to the next via its links.
5. **Extract and read full content** of the most relevant hits
6. **Synthesize** findings, noting which terms/authors/sources are
   authoritative

## Pitfalls

- **Do not use `browser_navigate` for plain-text endpoints.** The
  browser stack is slow and overkill for XML/JSON/Markdown. Use curl.
- **jina.ai reader is not anonymous.** It fetches on your behalf.
  Do not use it for sensitive queries.
- **jina.ai silently fails on client-rendered (CSR) docs sites.**
  Docusaurus, Nextra, Next.js/Vercel docs, Gatsby, VuePress — these load
  article content via JS after the HTML shell. jina.ai returns HTTP 200
  with clean-looking Markdown that is **only the nav sidebar**, and the
  output is near-identical across every URL on the domain. This looks
  like a real (if thin) result, so it's easy to trust. Don't. If the
  content is suspiciously short / mostly anchor links / identical across
  pages, the page is CSR — skip directly to `browser_navigate` +
  `browser_console` extraction (#5). Confirmed against `docs.slack.dev`
  (Docusaurus) in 2026-07.
- **arXiv truncates summaries** at ~500 chars when served via API.
  Fetch individual paper pages for full abstracts.
- **DuckDuckGo HTML `uddg=` links are redirects.** The actual URL is
  URL-encoded in the `uddg=` parameter — decode it as shown above.
- **Search engines are a lost cause from headless-browser IPs — all
  of them, not just Google.** Bing, DuckDuckGo, Ecosia, Startpage,
  and Google all serve CAPTCHA/Cloudflare challenges to headless
  clients. Do not waste turns rotating through them expecting one to
  work; jump straight to direct navigation (#5) or jina.ai proxy (#2).
- **When `browser_console` JS extraction fails** with
  `Cannot read properties of null`, the selector doesn't exist on the
  current page — you are probably still on a blocked/error page, not
  the article you intended. Re-navigate to the real URL before retrying.
  Don't loop the same expression: it means the page, not the query,
  is wrong.
- **Guessed docs URLs that 404 → extract the live sidebar hrefs.** Docs
  sites rename/restructure sections constantly (e.g. Slack renamed
  "App Directory" → "Slack Marketplace" and moved all sub-pages).
  Guessing `/submission-process` or `/review-process` returns 404s and
  wastes turns. Instead, navigate to the section's overview/landing
  page (the one URL you DO know), then dump the rendered sidebar's real
  links in one call:
  ```
  browser_console → expression:
    (() => JSON.stringify(
      Array.from(document.querySelectorAll('a'))
        .map(a => ({text: a.innerText.trim(), href: a.href}))
        .filter(x => x.text)
    ))()
  ```
  The actual current URLs are in that list — navigate to the right one
  directly. This is faster and more reliable than guessing slugs, and
  it works on any Docusaurus/MkDocs/Sphinx site with a nav sidebar.
  (Wrap in an IIFE per the shared-JS-context pitfall above.)
- **`browser_console` reuses one shared JS context — wrap multi-step
  extraction in an IIFE.** Each `browser_console` call evaluates in the
  SAME page context as the previous call on that loaded page, so top-level
  `const`/`let` declarations persist across calls. A second expression
  like `const main = document...` throws
  `SyntaxError: Identifier 'main' has already been declared` and returns
  no data. Fix: wrap every extraction expression in an immediately-invoked
  function —
  `(() => { const m = document.querySelector('article'); return m ? m.innerText.substring(0, 6000) : 'NOT FOUND'; })()`
  — so declarations are scoped to the call and never collide. Use this
  IIFE form by default for all but the very first extraction on a freshly
  navigated page.
- **Parallelize batched queries.** arxiv and jina.ai both support
  concurrent requests — send independent queries in the same turn.
  Direct navigations to independent pages can also be batched.
- **Overly specific search terms understate the competitive landscape.**
  Searching `"git standup weekly summary engineering team"` returns 4
  results with 0-5 stars. Searching `"git standup"` surfaces the 7.8k-star
  tool. Start with BROAD terms (1-2 words), then narrow. Prior research
  rounds that claimed "17+ tools with 0-2 stars" were wrong because the
  queries were too specific. Same applies to GitHub API search and
  DuckDuckGo queries.
- **For competitive landscape work, mine competitor comparison pages.**
  Most SaaS tools list their own competitors on "Compare" / "X Alternative"
  pages. One such page gives you the full competitive set in one click —
  faster and more complete than searching for each competitor individually.
  See `references/competitive-landscape-research.md` for the full pattern.
- **Reddit `.json` endpoints are BLOCKED for programmatic access.**
  Both `www.reddit.com/*.json` and `old.reddit.com/*.json` return
  "You've been blocked by network security" pages (HTTP 403) regardless
  of User-Agent string. This includes search endpoints, post endpoints,
  and comment endpoints. Reddit tightened bot detection in 2024-2025.
  **Working alternative:** use DuckDuckGo to find Reddit threads, then
  read individual threads via jina.ai:
  ```
  # Step 1: find Reddit threads via DuckDuckGo
  curl -sL "https://r.jina.ai/https://duckduckgo.com/html/?q=site:reddit.com+{search+terms}"
  
  # Step 2: read a specific Reddit thread via jina.ai
  curl -sL "https://r.jina.ai/https://www.reddit.com/r/{sub}/comments/{id}/{slug}/"
  ```
  Note: jina.ai can read Reddit post content even though direct `.json`
  access is blocked — the reader proxy fetches the rendered page.
  You will get the post body and top comments in Markdown.

## Related Reference Files

This skill packages accumulated research output as support files.
Check these before starting a new research task in the same domain:

- **`references/ai-agent-verification-terminology.md`** — Terminology
  map (verifier/critic/reviewer/checker/evaluator), ∼20 academic papers
  with quotes, industry blog posts, researcher/founder quotes from
  Karpathy/Willison/Chase/Devin/SWE-agent/Shumer, and a framework
  terminology comparison table (LangGraph/AutoGen/CrewAI/Aider/
  OpenHands/Devin/SWE-agent). Full of concrete URLs and verbatim
  quotes you can cite directly.
- **`references/software-vv-and-agent-loops.md`** — The software/systems
  engineering V&V side of verification: formal IEEE/ISTQB/INCOSE
  definitions of verification vs validation vs review, Boehm's classic
  distinction, the V-model, shift-left verification (4 types), and
  continuous verification/testing — all mapped onto agent-loop concepts
  (verify = spec-conformance check, validate = outcome check, review =
  static pre-execution check, shift-left = validate the task before
  acting, continuous verification = eval-gated rollouts + monitoring).
  Companion to the AI-side terminology reference above.
- **`references/demand-validation-research.md`** — Pattern for
  validating product/venture ideas: a 4-channel search strategy (HN
  Algolia for stories+comments, DuckDuckGo for blog/forum discovery,
  GitHub API for competitive tool landscape, jina.ai for deep reads),
  an evidence quality framework, competitive density assessment
  method, and red flags to watch for in idea briefs. Use when
  researching "does this pain exist?" or "who already solves this?"
- **`references/competitive-landscape-research.md`** — Pattern for
  systematic competitive landscape cataloging: 5 discovery methods
  (GitHub topic pages, GitHub search, competitor comparison-page
  mining, SaaS pricing-page extraction, direct repo-page verification),
  a tier-based cataloging structure (CLI / SaaS / Enterprise / Native),
  and a differentiation assessment method with explicit verdicts.
  Includes when to use browser vs curl/jina.ai for each subtask.
  Use when researching "what existing tools solve or overlap this?"
- **`references/slack-api-doc-verification.md`** — Canonical
  `docs.slack.dev` URL structure (including the dotted `message.*` URL
  pitfall), the load-bearing scope-vs-subscription-type distinction,
  the bot-event vs workspace-event nuance, and a table of verified
  scope mappings (`reaction_added`→`reactions:read`,
  `message.channels`→`channels:history`, etc.). Load when verifying
  any Slack API claim (OAuth scopes, event payloads, method params).
- **`references/slack-app-distribution-verification.md`** — Verified
  facts on app *distribution & approval* (distinct from the API
  surface above): the 3 distribution states (undistributed / unlisted
  / Marketplace-listed), the "App Directory → Slack Marketplace" rename,
  external install via direct OAuth URL WITHOUT Marketplace approval,
  no workspace cap for unlisted apps, the ~10-week Marketplace review
  timeline (10 business days preliminary + up to 10 weeks functional),
  the ≥5-active-workspace submission prerequisite, and the
  admin-managed-workspace caveat. Load when verifying claims about
  "can external users install this?", "do we need App Directory
  approval?", MVP launch timing, or Add to Slack button mechanics.

To view a reference, call `skill_view(name='web-research', file_path='references/<filename>')`.

## When to Load This Skill (Even Unprompted)

If you are dispatched as a kanban worker and your task involves ANY
research (competitive landscape, demand validation, technology
evaluation, source-finding), **load this skill immediately** even if
it wasn't in the card's `skills` field. The curl/jina.ai patterns here
are significantly faster than browser navigation for many research
subtasks, and the reference files capture techniques that prevent
repeating prior research mistakes (e.g., overly specific search terms
understating the competitive landscape).
