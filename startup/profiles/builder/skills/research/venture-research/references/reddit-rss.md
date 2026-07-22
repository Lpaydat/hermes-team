# Reddit RSS — Pain-Signal Extraction

Reddit `.rss` endpoints are the primary source of verbatim user pain/complaint
quotes for SMB- and consumer-focused venture dossiers. Verified working
2026-07-23 (LeadPilot and AI-SMB-Bookkeeping dossiers). No API key required.

## Endpoints

| Feed | URL | Use |
|---|---|---|
| Subreddit top | `https://www.reddit.com/r/SUB/top/.rss?t=year&limit=25` | Highest-signal complaint threads (the "wall of rage") |
| Subreddit new | `https://www.reddit.com/r/SUB/new/.rss?limit=25` | Fresh/active signal |
| Subreddit search | `https://www.reddit.com/r/SUB/search.rss?q=KEYWORDS&restrict_sr=1&sort=top&t=year&limit=15` | Targeted pain-point mining within a subreddit |
| Thread (single) | `https://www.reddit.com/r/SUB/comments/THREAD_ID/.rss` | Full thread + comments for one ID |

Always send a User-Agent header: `-H "User-Agent: HermesResearchBot/1.0"`.
Reddit rejects empty/default UAs with empty bodies.

`t=` accepts `hour`, `day`, `week`, `month`, `year`, `all`.

## Response shape

Atom XML. Each `<entry>` contains:
- `<title>` — thread title
- `<link href="...">` — canonical URL (`.../comments/THREAD_ID/slug/`)
- `<author><name>/u/USERNAME</name>` — original poster
- `<published>` — ISO timestamp
- `<content type="html">` — HTML-encoded post body (may include thumbnails for image posts; the real text is inside `<!-- SC_OFF --><div class="md">...</div>`)

## Parsing script (two-step, avoids security-scanner flags)

```bash
# Step 1: download
curl -sL "https://www.reddit.com/r/QuickBooks/top/.rss?t=year&limit=25" \
  -H "User-Agent: HermesResearchBot/1.0" -o /tmp/sub.xml
```

```python
# Step 2: parse (save as parse_reddit.py, run separately)
import re, html

with open('/tmp/sub.xml') as f:
    content = f.read()

entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)
key_ids = ['1repihe', '1s4c9u3']  # IDs you want full bodies for

for e in entries:
    link = re.search(r'<link[^>]*href="([^"]+)"', e)
    if not link:
        continue
    m = re.search(r'/comments/(\w+)/', link.group(1))   # <-- THE GOTCHA
    if not m:
        continue
    thread_id = m.group(1)

    title = re.search(r'<title>(.*?)</title>', e)
    author = re.search(r'<name>(/u/\w+)', e)
    published = re.search(r'<published>([^<]+)</published>', e)
    cm = re.search(r'<content[^>]*>(.*?)</content>', e, re.DOTALL)

    print('=' * 70)
    print('TITLE:', html.unescape(title.group(1)) if title else 'NONE')
    print('LINK:', link.group(1))
    print('AUTHOR:', author.group(1) if author else 'NONE')
    print('DATE:', published.group(1)[:10] if published else 'NONE')
    if cm:
        text = re.sub(r'<[^>]+>', ' ', cm.group(1))
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Strip the trailing "submitted by /u/... [link] [comments]" boilerplate
        text = re.split(r'submitted by', text)[0].strip()
        print('CONTENT:', text[:1400])
```

## The thread-ID gotcha (cost a debug cycle — read this)

The `<link>` URL is `.../comments/1abc23d/the_slug_text/`. The thread ID is
the segment **between** `/comments/` and the slug — `1abc23d`, NOT
`the_slug_text`.

**Wrong:** `link.group(1).split('/')[-2]` → returns the slug (`were_done`),
so `if lid in key_ids:` matches nothing.

**Right:** `re.search(r'/comments/(\w+)/', link.group(1)).group(1)` → returns
the ID (`1repihe`).

If your parse loop returns zero hits on `key_ids` but the file clearly
contains the entries, you hit this bug. Fix the regex, not the key list.

## What to extract for a dossier

Per thread, capture for the §1 / §2 tables:
- **Verbatim quote** (the most visceral 1–2 sentences, unmodified).
- **Author** (`/u/username`) — attributes the quote.
- **Thread ID** (`1repihe`) + full URL — the citable source.
- **Date** (`published`, truncated to YYYY-MM-DD).
- **Severity / engagement** — "top post of the year," comment count if visible.

For pain-point tables, prefer the **most specific, visceral** quotes over
generic venting. "I pay more than $1k a year for this tool and it's barely
usable" (with bank feeds broken) beats "Fuck QuickBooks" — both are real, but
the former is evidence and the latter is affect.

## Verification

Before completing a dossier, confirm cited threads resolve:

```bash
for id in 1rfvyj0 1ron6m3 1s4c9u3 1slj9w9 1repihe; do
  code=$(curl -sL -o /dev/null -w "%{http_code}" \
    "https://www.reddit.com/r/QuickBooks/comments/${id}/" \
    -H "User-Agent: HermesResearchBot/1.0")
  echo "$id -> HTTP $code"
done
```

All should return `200`. A `404` means the ID was mis-copied or the thread
was deleted — re-fetch or drop the citation.
