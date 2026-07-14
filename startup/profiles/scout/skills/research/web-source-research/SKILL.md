---
name: web-source-research
description: "Investigate a factual question against high-trust primary web sources (official docs, developer portals, API references) and capture findings as a cited Markdown report. Use when the user asks to research, evaluate, or compare an external API/service/product from its official documentation, or wants primary-source facts gathered with citations. Distinct from research-scout (daily AI-frontier cron) — this is on-demand deep research against web docs."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [research, web, documentation, api-evaluation, primary-sources, citations]
    related_skills: [research-scout]
---

# Web Source Research

Investigate a specific question against **primary web sources** — the official site, developer portal, or API reference that *owns* the facts — and deliver a cited Markdown report. Default to the browser for JS-rendered sites; use `curl`/`web_extract` only for plain-text endpoints (`.md`, `.txt`, `.json`, `.xml`, raw API responses).

## When to Use

- User asks to research, evaluate, or compare an external product/API/service from its official docs.
- User wants a list of facts (pricing, rate limits, coverage, auth requirements) with citations.
- User wants to know whether a service is suitable for a specific use case (fit analysis).
- User says "research X," "look up," "find out," "what does the documentation say about."

**Don't use for:**
- Broad web search / market overviews with no authoritative source → use a search tool.
- Reading a single file or repo you already have → use `read_file` / terminal.
- Daily AI-frontier scanning pipeline → that's `research-scout`.

## Process

### 1. Frame the question as a checklist of sub-questions
Break "research the Kroger API" into atomic, answerable sub-questions: *Does it return pricing? What's the coverage? Cost? Rate limits? Account requirements?* Each sub-question maps to a section in the report and gives you a completion criterion per fact.

**Done when:** you have a written list of sub-questions before opening a browser.

### 2. Go to the primary source, not a write-up of it
Find the **official documentation root** (e.g. `developer.<company>.com`, `<company>.com/docs`, `docs.<company>.com`). Navigate the site's own sidebar nav to reach canonical pages. Treat blog posts, Stack Overflow, and third-party tutorials as leads only — follow every material claim back to the primary doc that owns it.

**Done when:** every fact you plan to cite comes from a URL on the official domain.

### 3. Extract content reliably on JS-rendered SPA docs
Modern doc portals (developer.kroger.com, developer.stripe.com, etc.) are SPAs: the accessibility-tree snapshot **truncates at ~8000 chars** and hides accordion/FAQ content. Use `browser_console` with DOM expressions to get the real text. See `references/extracting-js-rendered-docs.md` for the exact technique — the core moves are:

- Read the full `<article>` / `<main>` body: `document.querySelector('article').innerText.substring(0, 8000)`.
- Expand accordions via `browser_click` on their snapshot refs, then read all open panels with `document.querySelectorAll('button[aria-expanded="true"]')`.
- On SPA deep-link redirects to the index, click through the sidebar nav instead of navigating directly.

**Done when:** you have the full rendered prose of each target page, not just headings and nav.

### 4. Record the exact URL for each fact as you go
Keep a running note: fact → page URL. The report's value is traceability. If a fact came from an expanded accordion, cite the page it sits on (not a fragment). Note the access date for docs that may change.

**Done when:** every claim in your draft has a source URL recorded.

### 5. Capture restrictions and caveats as first-class findings
Terms-of-use, acceptable-use, and rate-limit policies often determine whether an API is *actually usable* for a given purpose — sometimes they're a hard blocker even when the technical capability exists. Surfacing "the API can do X but the terms forbid Y" is often the most valuable finding. Read Acceptable Use / Terms / FAQ pages explicitly.

**Done when:** you have checked the terms/acceptable-use/FAQ pages, not just the feature pages.

### 6. Write a structured Markdown report
Structure: TL;DR (1-2 sentences with the bottom-line answer), then one section per sub-question with the answer + citation, then a bottom-line/fit-summary table, then a "Key Documentation URLs" index. Write to the repo working directory with a descriptive filename.

**Done when:** report saved as `.md`, every claim cited, and the TL;DR states the actionable conclusion (including any blocker).

## Tool Choice — browser vs. curl

- **Browser** (`browser_navigate` + `browser_snapshot`/`browser_console`): JS-rendered docs, anything behind auth or a click, pages where you need to expand accordions or follow sidebar nav.
- **`curl`** (via terminal) or **`web_extract`**: plain-text endpoints — URLs ending in `.md`, `.txt`, `.json`, `.yaml`, `.csv`, `.xml`, `raw.githubusercontent.com`, or any documented REST endpoint that returns JSON. Do not spin up the browser stack for a JSON API response; it's slower and overkill.

## Output Convention

Write the report to the current working directory (or where the repo keeps such notes). Filename: `<topic>-research.md` or match an existing convention. Include a citation table at the end mapping each doc page to its URL.

## Common Pitfalls

1. **Citing a secondary source as if primary.** A dev.to blog summarizing an API is not the source. Follow links to the official doc and cite that.

2. **Stopping at feature pages and missing the terms.** The Acceptable Use / FAQ pages often contain the blocker (e.g. "no cross-retailer price comparison"). Always read them before concluding "this API is suitable."

3. **Trusting the truncated snapshot as the full page.** If you see `[... N more lines truncated]` or only nav + headings, the real content is elsewhere in the DOM. Use the `browser_console` extraction technique in `references/extracting-js-rendered-docs.md`.

4. **Navigating to SPA deep links that redirect to index.** SPAs don't hydrate deep routes on cold load. Land on the index, then click sidebar nav links to the target page.

5. **Reporting "not found" from a single failed path.** Doc sites reorganize; a 404 or redirect doesn't mean the info doesn't exist. Try the sidebar nav, the site search, and sibling pages before concluding absence.

## Verification Checklist

- [ ] Every factual claim in the report has a citation to an official-source URL.
- [ ] Terms / acceptable-use / FAQ pages were explicitly read, not just feature pages.
- [ ] Report includes a TL;DR stating the actionable bottom line (including any blocker).
- [ ] Report saved as `.md` in the working directory with a descriptive filename.
- [ ] A "Key Documentation URLs" table indexes every cited page.

## Reference Files

- `references/extracting-js-rendered-docs.md` — DOM-extraction technique for JS-rendered SPA docs: reading full article bodies, expanding accordions/FAQs, and working around SPA client-side routing. Load when the snapshot is truncated or content is hidden.
