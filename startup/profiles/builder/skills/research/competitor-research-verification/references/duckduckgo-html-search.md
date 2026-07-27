# DuckDuckGo HTML Endpoint — the working search-engine fallback

## TL;DR

When HN Algolia / Reddit RSS / GitHub API don't cover a query (e.g. finding
news articles, incident reports, vendor pages, regulatory actions),
**DuckDuckGo's HTML-only endpoint works reliably from headless** — unlike
Google and Bing, which both return captcha pages. This contradicts the
pinned `venture-research` skill's "❌ all search engines blocked" claim;
that skill should be updated when unpinned.

## The endpoint

```
https://html.duckduckgo.com/html/?q=<url-encoded-query>
```

Use a desktop browser User-Agent. Returns server-rendered HTML (not JS), so
`curl` + regex parsing works — no browser needed.

## Working pattern

```bash
curl -s -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://html.duckduckgo.com/html/?q=app+store+impersonation+scam+2024+2025" \
  -o ddg.html
```

```python
import re, urllib.parse
html = open('ddg.html').read()
# Result links are class="result__a"; URLs are DDG redirect links
results = re.findall(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    html, re.DOTALL
)
for url, title in results:
    clean = re.sub(r'<[^>]+>', '', title).strip()      # strip HTML from title
    m = re.search(r'uddg=([^&]+)', url)                 # extract real URL
    real_url = urllib.parse.unquote(m.group(1)) if m else url
    print(f"{clean}\n  {real_url}")
```

## Key behaviors (confirmed 2026-07-25)

1. **Result URLs are DDG redirect links**, not direct URLs. They look like:
   `//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath&rut=...`
   Extract the real URL with `re.search(r'uddg=([^&]+)', url)` then
   `urllib.parse.unquote()` it. If you skip this step you get an unreadable
   DDG redirect string instead of the actual destination.

2. **Rate-limited without error.** Rapid back-to-back calls return an **empty
   page (0 bytes), not an error code** — the curl still exits 0 and the file
   parses as an empty result list. There is no throttle message. Add
   `sleep 3` (3–5 seconds) between consecutive calls. If a query returns
   nothing, first suspect rate-limiting and retry after a pause before
   assuming the query is bad.

3. **Titles contain HTML entities / nested tags** — always strip tags with
   `re.sub(r'<[^>]+>', '', title)` before using.

4. **Bing as a fallback to DDG was tested and does NOT work** from headless
   (returns empty / bot-detect). Stick with the DDG HTML endpoint.

## When to use it

- Finding news articles / press releases about an incident or trend
  (e.g. "app store impersonation scam 2025")
- Locating the correct URL for a vendor page whose structure changed
  (e.g. when direct guesses 404 — use DDG to discover the live URL)
- Regulatory / government actions (FTC, EU) that won't surface on HN
- Any query where HN Algolia (tech-focused) has no coverage

## When NOT to use it

- Reddit pain signals → use Reddit RSS (`references/reddit-rss.md` in
  `venture-research`)
- Tech-market / competitor signals → use HN Algolia first
- Repo / category-formation signals → use GitHub API
- Academic / enabling-shift signals → use arXiv API

## Limitations

- No guaranteed result count (can't say "X results found")
- Results are relevance-ranked, not exhaustive — a missing result doesn't
  mean the page doesn't exist
- Subject to the same silent-empty-page rate-limiting as above
- Not a substitute for direct source verification — always curl/fetch the
  real destination URL DDG points you to and verify content before citing
