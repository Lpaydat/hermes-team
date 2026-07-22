---
name: venture-dossier-research
description: Build full venture dossiers and idea research for a startup/venture idea pipeline. Use when the user asks to research an idea, build a dossier, score a venture, write up market validation, or fill an idea template. Covers the multi-source signal-mining, competitive pricing verification, and no-fabrication rigor the pipeline demands.
---

# Venture Dossier Research

Build evidence-backed venture dossiers for an idea pipeline. The pipeline lives at `~/vault/ventures/` with a known structure: `ideas/` (dossiers), `specs/` (deep dives), `templates/`, `signals/`, `idea-bank.md`, `portfolio.md`, `killed-ideas.md`.

## The core rule: no fabrication

Every quote, URL, price, and stat in a dossier must trace to a **live-verified source**. The user has been explicit about this: *"Do NOT fabricate quotes or URLs."* This is the one hard constraint that overrides speed.

- If you cannot verify a URL resolves (HTTP 200), do not cite it as primary evidence.
- If Reddit or another platform blocks your access, say so in the dossier and pivot to sources you CAN verify rather than inventing the blocked content.
- Mark anything you could not re-verify: *"could not re-verify specific thread URL this session"* is honest; a made-up URL is not.

## Workflow

1. **Read the inputs.** Before researching, read the template (`~/vault/ventures/templates/idea-dossier-template.md`), the existing spec/deep-dive (`~/vault/ventures/specs/<slug>.md`), the idea-bank entry, and at least one example dossier in `ideas/` to match the house style. Batch these reads.

2. **Mine for signals.** The dossier's evidence section is its backbone. Source real quotes from:
   - **HN Algolia API** (primary, most reliable): `https://hn.algolia.com/api/v1/search?query=<terms>&tags=<story|ask_hn|show_hn>&numericFilters=created_at_i><epoch>&hitsPerPage=20`. Then fetch full thread + comments via `https://hn.algolia.com/api/v1/items/<objectID>`.
   - **Reddit**: often blocks curl/RSS/browser (403/429). If blocked, pivot to HN and note the gap — don't fabricate Reddit content.
   - **Pricing pages**: fetch via browser (browser_navigate) then extract prices via `browser_console` with a DOM query (see Pitfalls).

3. **Verify competitor pricing live.** Every price in the Competitive Landscape must come from a pricing page fetched this session. Capture the tier names AND dollar amounts.

4. **Write all sections.** The template has 13 sections (Origin through Source References). Fill every one. Pain points need evidence quotes; the scoring must cite the evidence; features map back to pain points.

5. **Verify all URLs resolve — but check content, not just status codes.** Before completing, batch-curl every URL in the Source References table. **HTTP 200 ≠ accessible content.** Reddit specifically returns 200 with a tiny "Please wait for verification" challenge page (~8 KB), not a 403 — so a status-code-only check gives a false positive and you'll think a thread is live when it isn't. For Reddit URLs, additionally check the `<title>` (a real thread has the post title; a block page says "Please wait for verification") or the body size (a real thread is >50 KB; a block page is <10 KB). Confirmed 2026-07-23: `reddit.com/r/SaaS/comments/1v29zgb/` returned HTTP 200 but the body was a bot wall. HN, Wikipedia, and most competitor pricing pages return honest 200s. Flag any URL that fails the content check as "could not re-verify live this session."

## Research techniques

### HN Algolia — the reliable primary source

HN's Algolia API is free, stable, and returns structured JSON. It is the best source for founder-pain evidence.

```
# Search stories by keyword
curl -s "https://hn.algolia.com/api/v1/search?query=<url-encoded-terms>&tags=ask_hn&numericFilters=created_at_i%3E<epoch>&hitsPerPage=20" | jq -r '.hits[] | "\(.points)pts | \(.num_comments)c | \(.created_at) | \(.objectID) | \(.title)"'

# Fetch a full thread with comments
curl -s "https://hn.algolia.com/api/v1/items/<objectID>" | jq '{title, author, points, created_at, story_text}'
curl -s "https://hn.algolia.com/api/v1/items/<objectID>" | jq -r '.children[]? | select(.text != null) | "\(.author): \(.text)"'
```

**Pitfall**: Algolia's `numericFilters` uses URL-encoded operators: `%3E` for `>`, `%3C` for `<`, `,` for AND. Do NOT put `hitsPerPage` inside `numericFilters` — it's a top-level param. A query that returns empty often has malformed `numericFilters`.

**Pitfall**: High-engagement threads (497pts) sometimes return empty children on first fetch (Algolia throttles). Retry the same `/items/<id>` call — it usually works on the second attempt.

### Extracting prices from JS-rendered pricing pages

Many SaaS pricing pages (Taplio, SparkToro) render prices client-side, so the browser snapshot shows tier names but not dollar amounts. After `browser_navigate` to the pricing page, run:

```js
// browser_console expression — extracts all visible price text
JSON.stringify(Array.from(document.querySelectorAll('h2,h3,h4,span,div,p,b,strong')).map(el => el.textContent.trim()).filter(t => /\$\d/.test(t) && t.length < 80).filter((v,i,a) => a.indexOf(v) === i))
```

### Epoch for "last 2 years" filter

`numericFilters=created_at_i%3E<epoch>`. For mid-2024 onward, use `1719792000` (2024-07-01). Compute others as needed.

## Pitfalls

- **Reddit access is unreliable from curl/browser.** It returns 403/429 for JSON, RSS, and even headless browser. Do NOT spend more than 2 attempts. Pivot to HN Algolia (reliable) and note in the dossier that Reddit signals came from the spec but couldn't be re-verified live.
- **Reddit can fail *silently*: HTTP 200 with a bot-wall body.** Reddit returns status 200 with an ~8 KB "Please wait for verification" challenge page, not a 403 — so a `curl -w "%{http_code}"` check reports success on a blocked URL. Always also check the page `<title>` or body size for Reddit URLs (see workflow step 5). When the live thread is unreachable, fall back to the pipeline's own `signals/daily-scan.md` / `killgate-*.md` scan captures, which hold the verbatim quote + source ID from the original run — cite with the capture date and flag "could not re-fetch live this session" (this is how the AI-Interview-SaaS dossier, 2026-07-23, sourced its r/SaaS `1v29zgb` quote).
- **Don't put `hitsPerPage` inside `numericFilters`.** It's a separate top-level query param. Mixing them silently returns zero results.
- **URL-encode the operators in `numericFilters`.** `>` must be `%3E`, not the raw character, or Algolia ignores the filter.
- **Verify URLs with spacing.** Rapid batch-curling HN URLs triggers 429 rate-limiting. The URLs are valid — add `sleep 2` between checks or verify a sample with delays.
- **The "200 dead startups" signal** (or similar graveyard framing) is often concretely findable as a startup-graveyard product (e.g., loot-drop.io: "1,209 dead startups, $40B+ burned"). Search for these — they're stronger evidence than paraphrasing.

## House style (from existing dossiers)

- Tables use markdown pipe syntax with evidence quotes in italics with source IDs (e.g., *"...quote..."* — r/smallbusiness `1tyefvv`).
- Source References table is the final section, numbered, with URL + date accessed + platform.
- Scoring rationale cites evidence by source ID in parentheses.
- Competitive landscape includes a "Net gap" summary paragraph.
- Sections are separated by `---` horizontal rules.
- Where a stat couldn't be re-verified live, mark it explicitly (*"could not re-verify... this session"*).

## Reusable reference data

- [`references/verified-competitor-pricing.md`](references/verified-competitor-pricing.md) — live-verified pricing for SparkToro, Buffer, Hootsuite, Taplio, Hypefury, BuzzSumo (2026-07-23). Reusable for distribution/marketing/community-tool dossiers. Re-verify if citing months later.
- [`references/verified-competitor-pricing-ai-interview.md`](references/verified-competitor-pricing-ai-interview.md) — live-verified pricing for CodeSignal, CoderPad, HackerRank, Karat, Final Round AI + company funding facts (2026-07-23). Reusable for any AI-interview / engineering-assessment / hiring-tool dossier.
- [`references/hn-signal-library-distribution.md`](references/hn-signal-library-distribution.md) — verified HN thread IDs for founder-distribution pain (the "build/distribute inversion" cluster). Reusable across indie-builder/SaaS-founder idea dossiers.
