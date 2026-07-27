# Web Source Access — which engines and endpoints work from headless

> **Framing rule:** which web sources block headless access is *environment-
> and time-dependent*, not a permanent property of the source. Treat the
> status below as a starting order-of-attack, not a permanent map. When a
> source returns empty/blocked, retry once after a pause before concluding
> it's down — silent rate-limiting (0-byte responses, not errors) is common.

## Search-engine discovery (when you don't know the exact URL)

Two HTML search endpoints have each worked in *different* sessions; neither
is permanently reliable. **Try both, in order, until one returns parseable
HTML.** Do not assume either is permanently blocked or permanently working
based on a single session.

### Option A — Brave Search

```
curl -sL "https://search.brave.com/search?q=YOUR+QUERY&source=web" \
  -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36" \
  -o brave.html
```

Result URLs appear both as `href` attributes and as `url:"..."` fields in a
JSON-ish data block inside the HTML:
```python
import re
t = open('brave.html').read()
items = re.findall(r'title:"([^"]{20,200})"[^}]*?url:"(https?://[^"]+)"', t)
for ti, u in dict.fromkeys(items): print('-', ti[:100], '\n  ', u)
links = re.findall(r'(https://(?:www\.)?[^ "<>]+)', t)  # broader fallback
```

**Worked this session (2026-07-25):** recovered exact Apple Newsroom
fraud-stats URLs, the correct BleepingComputer article slug, and relevant
Reddit thread paths — all of which Google/Bing/DDG failed on. When DDG
returned empty (below), Brave was the one that delivered.

### Option B — DuckDuckGo HTML endpoint

```
curl -s -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://html.duckduckgo.com/html/?q=YOUR+QUERY" -o ddg.html
```

Result URLs are DDG redirect links — extract the real URL:
`re.search(r'uddg=([^&]+)', url)` then `urllib.parse.unquote()`.
**Rate-limited silently:** bursts return 0-byte pages, not errors —
add `sleep 3` between calls. If a query returns nothing, suspect
rate-limiting and retry after a pause.

**Returned empty this session (2026-07-25)** even after UA/retry, where
Brave succeeded on the same queries. In prior sessions (2026-07-25
subscription-cancellation research) it worked. The divergence is real —
don't trust a single session's verdict on either engine.

### Blocked — don't use as a discovery interface

Google, Bing, and the main reddit.com JSON/RSS endpoints return captcha /
"blocked by network security" pages. Use Brave or DDG-HTML above instead.

## Reddit — escalation ladder for verbatim quotes

Reddit is the richest source of verbatim user pain quotes, but its access
surface is flaky. Try these in order:

1. **`reddit.com/r/SUB/comments/ID/SLUG.json`** — structured JSON, ideal.
   Blocked this session (HTTP 403 "blocked by network security" for *every*
   thread, identical body) but works in other sessions.
2. **`reddit.com/r/SUB/.../.rss`** — Atom XML. Reliable in some sessions,
   silent 0-byte in others.
3. **`old.reddit.com/r/SUB/comments/ID/SLUG/`** — **plain HTML, works when
   `.json` and `.rss` are blocked.** Fetch with a desktop UA. This is the
   fallback that rescued this session's Reddit evidence:
   ```bash
   curl -sL "https://old.reddit.com/r/SUB/comments/ID/SLUG/" \
     -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36" \
     -o thread.html
   ```
   Parse: the submission title is in `<p class="title">...<a>...</a>`; the
   OP body and comments are in successive `<div class="md">...</div>` blocks
   (block 0 = sidebar boilerplate on listing pages; the OP is usually block
   1, comments after). HTML-unescape and strip tags. Verified 2026-07-25:
   full submission body + top comments recovered for r/androiddev `1kbeyr7`,
   r/apple `usd6b2`, r/iOSProgramming `1lpfale` when `.json` was fully blocked.
4. **Pipeline `signals/daily-scan.md` / `killgate-*.md` captures** — the
   pipeline's own scan outputs hold the verbatim quote + source ID from the
   original capture run. A legitimate primary source; cite with the capture
   date and flag "could not re-fetch live thread this session."

**Silent-fail check:** Reddit can return HTTP 200 with a bot-wall body
(~8 KB "Please wait for verification"), not a 403. A `curl -w "%{http_code}"`
reports success on a blocked URL. Always also check the `<title>` (a real
thread has the post title; a block page says "Please wait for verification")
or the body size (real thread >50 KB; block page <10 KB).

**Faster batch detection when you fetched multiple .json endpoints: md5
them.** Bot-walls are byte-identical across all queries, so:

    md5sum reddit-*.json
    # Real data : every file has a DIFFERENT hash.
    # Bot-wall  : every file has the SAME hash (e.g. 87dd5b9fca5f325c707a6d176b810c32).

This is conclusive in one command and catches a wall you would otherwise miss
until you parse. Confirmed 2026-07-25 (SEO-search dossier): four unrelated
Reddit .json searches (technology/google+search+spam, arlong+search+engine,
SideProject/search+engine, kagi/worth+price) all returned the identical
189908-byte bot-wall body with the same md5.

**The .json vs .rss asymmetry — the key retry move.** .json being bot-walled
does NOT mean .rss is. In the same session where every .json search was walled
(identical 189908-byte body), the .rss variant of the SAME queries succeeded
(31 KB of real Atom entries). So when .json is walled, switch to the .rss
endpoint for that query immediately rather than retrying .json with different
UAs — the two endpoints have different bot-detection postures, and .rss is
frequently the one that is open. Only if .rss ALSO returns 0 bytes should you
fall down the ladder to old.reddit.com HTML or the pipeline signal captures.

## HN — always reliable, two-step

HN Algolia (`hn.algolia.com/api/v1/...`) never blocks and returns structured
JSON. Use the search endpoint for discovery and `/items/<id>` for full
threads/comments. See `references/hn-pain-signal-mining.md` for the quote-
extraction method, and the pinned `venture-research` skill's
`references/hn-algolia-api.md` for the API reference.

Always use the **two-step download-then-parse** pattern (the security scanner
flags `curl | python3` as HIGH risk):
```bash
curl -sL "https://hn.algolia.com/api/v1/search?query=X&tags=story" -o r.json
python3 -c "import json; [print(h['title']) for h in json.load(open('r.json'))['hits']]"
```

## Official platform stats pages (reliable via curl)

When a dossier needs authoritative volume figures, the platform's own
press/blog pages are server-rendered and curl-accessible (unlike market-
research firms, which are paywalled/Cloudflare-blocked):
- **Apple Newsroom** — annual fraud-prevention reports (dollar figures,
  app-submission rejection counts). Paths restructure frequently; discover
  the live URL via Brave/DDG rather than guessing.
- **Google Security Blog** (`blog.google/security/...`) — annual Google Play
  safety stats (apps prevented, accounts banned, AI-assisted review %).
- **Government agencies** (FTC, FBI IC3) — press releases; URL discovery
  via search, then curl the resolved URL.
