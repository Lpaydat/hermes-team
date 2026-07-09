# Source friction catalog

Concrete extraction methods that worked, per source type. Add entries as you
discover new patterns. This is the durable memory of "what actually gets the text
out of site X" — SKILL.md stays principle-level, this stays tactic-level.

## DuckDuckGo HTML — discovery (works reliably)

Endpoint returns parseable HTML result links without JS. The link titles come out
via `grep -oiE 'result__a"[^>]*>[^<]+'`. The real target URL is wrapped:
`duckduckgo.com/l/?uddg=<urlencoded-real-url>&rut=...` — decode the `uddg` param.

```
curl -sL --max-time 20 -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://html.duckduckgo.com/html/?q=<query>" \
  | grep -oiE 'result__a"[^>]*>[^<]+' | sed 's/result__a" href="[^"]*">//'
```

**Rate-limit behavior:** sequential curl calls without delay start returning empty
bodies after ~2–3 queries. Fix: `sleep 3–8` between queries, or interleave with
direct fetches. The browser-stack version of DDG sometimes serves a CAPTCHA/
checkbox anomaly page — the curl/HTML endpoint is more resilient.

`lite.duckduckgo.com/lite/` is an alternate endpoint, sometimes less aggressively
gated. Result links use `class="result-link"`.

## Blogspot / Blogger (e.g. testing.googleblog.com)

- **`curl` is blocked** — returns empty body or a redirect wall.
- **`browser_navigate` works** — the snapshot contains the full article text as
  `StaticText` nodes inside the post body. Read it from the snapshot directly;
  you rarely need `browser_snapshot(full=true)`.
- Headings come through as `heading [level=N]`; links as `link "text" [ref=...]`.
- Comments are included in the snapshot (may be truncated) — useful for finding
  corroborating discussion.

## Medium

- **Cloudflare challenge** in front of both `curl` and the browser stack. The
  page returns a JS-challenge HTML blob, not the article.
- Workaround: search DDG for the article title + a distinctive phrase, fetch a
  republished version (dev.to, a syndicated mirror, or a quote in another article),
  OR use an archive mirror (`archive.ph` / `web.archive.org` — fetch via Tier 0).
- Don't waste more than 2 attempts fighting the Cloudflare wall.

## GitHub — raw file fetch

- `raw.githubusercontent.com/<org>/<repo>/<branch>/<path>` via `curl` — returns
  the file content directly. Works great for READMEs, docs, configs.
- **`api.github.com` and raw both return 429 (Too Many Requests)** under repeated
  unauthenticated calls. Fix: space requests, or use the browser to view the
  rendered repo page (snapshot shows README content).
- For READMEs of popular repos, the rendered `github.com/<org>/<repo>` page in the
  browser shows the README text in the snapshot.

## Google Search

- **Aggressive CAPTCHA interstitial** for both `curl` and browser — `google.com/sorry/index`
  with an IP/time log. Not worth fighting.
- Use DuckDuckGo HTML instead for programmatic discovery.

## Bing

- Loads in the browser but the results often don't appear in the accessibility-tree
  snapshot (JS-rendered, lazy). Less reliable than DDG for programmatic extraction.
- Can work as a secondary if DDG is rate-limited and you can scroll/interact.

## Martin Fowler (martinfowler.com / bliki)

- **`curl` works cleanly** — plain HTML, no JS, no blocks. Strip tags with
  `sed -n 's/<[^>]*>//g; /./p'` and grep for your signal.
- A reliable secondary/primary source for software-engineering practice claims.

## Atlassian docs, MDN, Wikipedia

- Generally `curl`-friendly (plain or near-plain HTML). Strip tags and grep.
- MDN has good API/reference content; Atlassian has good process/practice overviews.

## General extraction one-liner pattern

```
curl -sL --max-time 20 -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" \
  -H "Accept: text/html" \
  "<url>" 2>/dev/null \
  | sed -n 's/<[^>]*>//g; /./p' | grep -iE "<signal keywords>" | head -40
```

The `sed` strips all tags and drops empty lines; the `grep -iE` pulls only lines
mentioning your signal keywords. Good for extracting just the relevant prose from
a large page without loading the whole thing into context.

## When to give up on a source

Budget ~3 escalation attempts (direct fetch → DDG-discover-then-fetch → browser).
If all three fail, label the fact at its achieved tier (usually "⚠️ widely-documented")
and move on. Do not spend the session on one CAPTCHA.
