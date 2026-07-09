---
name: web-research
description: "Use when gathering facts from the web — company practices, engineering blog posts, API docs, how-to answers — especially when search engines or target sites throw CAPTCHAs, rate-limits, or paywalls. Drives a triangulation protocol: try the direct path, escalate through fallbacks, then label sourcing tiers honestly. Load before concluding a fact is 'unverifiable' or a site is 'blocked'."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [research, web, scraping, search, friction, fact-gathering]
    related_skills: []
---

# Web research under friction

You need facts from the web. The direct path — search → click → read — frequently
breaks: Google serves a CAPTCHA interstitial, a blog blocks `curl`, Medium puts a
Cloudflare challenge in front of the article, DuckDuckGo rate-limits your Nth
query, GitHub raw returns 429. None of this means the fact is unreachable. It
means you haven't found the path that works yet.

**Triangulation** is the discipline: reach the same fact through several
independent paths until one yields, and label how confident you are in what each
path gave you. Never conclude "unverifiable" after a single failed attempt.

## The protocol

Work these tiers **in order**. Each has a **completion criterion** — advance only
when the current tier fails to yield a usable answer.

### Tier 0 — Direct fetch (cheapest)

For a known canonical URL, `curl` it first. Many docs (martinfowler.com, raw
markdown, API reference pages, plain HTML blogs) yield to a simple request.

- Use a realistic `User-Agent` (`Mozilla/5.0 (X11; Linux x86_64) ...`).
- Pipe through `sed`/`grep` to strip HTML and extract the signal, not the whole page.
- Prefer raw endpoints (`raw.githubusercontent.com`, `.md`/`.txt`/`.json` URLs) over
  rendered HTML — they have no JS and rarely block.

**Done when:** you have the text you need, OR the fetch returned a
CAPTCHA/challenge/429/403/empty body. A challenge page is not a "no" — it's a signal
to move to Tier 1.

### Tier 1 — Discovery via DuckDuckGo HTML, then direct fetch

When you don't have the URL, or the direct fetch failed, discover via search. The
reliable programmatic search surface is **DuckDuckGo's HTML endpoint** — it
returns parseable result links without JS:

```
curl -sL -A "Mozilla/5.0 ..." "https://html.duckduckgo.com/html/?q=<query>" \
  | grep -oiE 'result__a"[^>]*>[^<]+'
```

Extract the result titles + the real target URLs (they're wrapped in
`duckduckgo.com/l/?uddg=<encoded>` — URL-decode the `uddg` param). Then **Tier-0
fetch** each promising target.

- **Space requests** — DDG rate-limits sequential curl calls. `sleep 3–8` between
  queries. One query, then a direct fetch, then another query works better than a
  tight loop of queries.
- Google and Bing search pages serve CAPTCHAs to curl and to the browser stack
  far more aggressively than DDG. Prefer DDG for programmatic discovery.

**Done when:** a target URL is found and Tier-0 fetched successfully, OR DDG also
returns an anomaly page (blank, checkbox-only, no `result__a` links). Then Tier 2.

### Tier 2 — Browser stack for JS-rendered primary sources

Some primary sources only render through JS (Blogger/Blogspot, Medium, sites with
client-side hydration). Fetch these with `browser_navigate` — the snapshot returns
the rendered accessibility tree including article body text, links, and headings.

- The snapshot often contains the **full article text** as `StaticText` nodes —
  read it directly; you rarely need `browser_snapshot(full=true)` afterward.
- If the page shows a consent/CAPTCHA wall in the browser too, move on — don't
  fight it.

**Done when:** the article content appears in the snapshot, OR the browser also
hits a wall. Then Tier 3.

### Tier 3 — Secondary aggregation + domain expertise

When every primary-source path is blocked, fall back to:

- **Aggregator/secondary sources** — Atlassian docs, Martin Fowler's bliki, InfoQ,
  dev.to, GeeksforGeeks summaries. Fetch via Tier 0/1/2.
- **Established domain knowledge** — for widely-documented industry practice (the
  kind cited in textbooks and thousands of articles), your trained knowledge is a
  legitimate source **when labeled as such**.

**Done when:** you have a confident answer, even if partially from secondary or
domain sources.

## Honest sourcing tiers (always label)

Every fact you report gets a tier tag so the reader knows how hard it was verified:

- **✅ Primary** — fetched the original source (official blog, docs, repo README)
  and read the actual text.
- **✅ Verified via search** — found via DDG/search and confirmed through
  multiple references, even if the single canonical page was unreachable.
- **⚠️ Widely-documented** — could not re-fetch a primary page this session
  (CAPTCHA/rate-limit), but the fact is among the most established in the field
  and corroborated by many secondary sources. State this plainly.

The tier is part of the deliverable, not an apology. A "⚠️ widely-documented"
fact is usually fine to act on; the tag just lets the reader re-verify if stakes rise.

## When to stop and label

Do not burn the whole session fighting one CAPTCHA. Budget ~3 escalation attempts
per source (direct → DDG-discover-then-fetch → browser). If all three fail, label
the fact at its achieved tier and move on. A report with honest tier labels beats
a report that silently overstates or silently omits.

## Friction catalog

For the specific extraction method that works per source type (Blogspot, Medium,
GitHub raw, Google search, Wikipedia, MDN, etc.), load
`references/source-friction-catalog.md`. Add entries there as you discover new
patterns — it's the durable memory of what worked.

## Pitfalls

- **Treating a challenge page as a final answer.** A CAPTCHA on Google does not
  mean "this fact is unverifiable." It means "use a different path." Advance tiers.
- **Tight curl loops against DDG.** Sequential queries without delay trigger
  rate-limiting that looks like "search is broken." Space them.
- **Silent overstatement.** Citing a fact as if primary when you only saw a
  secondary summary. Tag the tier honestly.
- **Fighting a single source past 3 attempts.** Diminishing returns — label and
  move on. Triangulate via a different source, not a 4th attempt at the same one.
