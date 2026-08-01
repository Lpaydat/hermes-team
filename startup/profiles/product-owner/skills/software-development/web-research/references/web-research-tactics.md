# Web Research Tactics (browser-tool mechanics)

The skill lays out the principles — follow every claim back to a primary source. This file covers the **mechanics** of doing that with the browser tools — the moves that turn "research" from slow scrolling into a fast, traceable pass.

## 1. Truncated browser snapshots → read the cache file

`browser_navigate` / `browser_snapshot` truncate large pages at ~15k chars and print:

```
[... N more lines truncated — full snapshot: read_file path="/abs/path/browser-snapshot-<hash>.txt" offset=K limit=200]
```

**Do not** re-navigate or re-snapshot to see the rest. `read_file` that cache path with `offset` to page through the remainder. Cheaper, and you keep your place. Watch for a `next_offset` / `hint` in the `read_file` output to continue.

## 2. Navigate dense doc pages with `browser_console`, not eyes

Large documentation pages (book TOCs, API reference indexes) bury the link you want. Instead of scrolling, run a JS expression to surface the relevant anchors:

```js
// browser_console, expression=
[...document.querySelectorAll('a')]
  .filter(a => /continuous integration|CI at|presubmit/i.test(a.href + a.textContent))
  .map(a => a.href + ' :: ' + a.textContent.trim())
  .join('\n')
```

You get an exact list of `href`s + labels; jump straight to the right one with `browser_navigate`. This beats visual scanning on any page with hundreds of links.

## 3. Paywalled / bot-blocked primary source → find the official mirror

Canonical primary sources are often paywalled or behind bot detection:
- ACM Digital Library (`dl.acm.org`) → Cloudflare "Just a moment..." challenge.
- O'Reilly online library → "Access Denied".

**Don't give up on the source, and don't cite a secondary blog as a substitute.** The authors almost always host the same content on an official, open mirror:
- **Papers** → the org's research publications site (e.g. `research.google/pubs/...` reproduces the abstract + bibtex for Potvin & Levenberg's CACM 2016 monorepo paper).
- **Books** → the publisher/imprint's open HTML edition (e.g. `abseil.io/resources/swe-book/html/...` is the free CC-licensed *Software Engineering at Google*).
- **Conf talks** → the speaker's/company's own blog or the conference's slide PDF.

Verify the mirror is first-party (same authors/org) before citing it as the primary source. This is rung 2 of the skill's fallback ladder.

## 4. Moved / 404 doc URLs → relocate, don't abandon

Official docs move (GitHub reorganised its `pull-requests/.../managing-a-merge-queue` path multiple times across 2023-2025). On a 404:
1. Don't conclude "the feature doesn't exist."
2. Try the obvious relocated path — drop or shift one path segment (e.g. `pull-requests/...` → `repositories/configuring-branches-and-merges-in-your-repository/...`).
3. If that fails, the search box on the docs-site root usually resolves it.

A moved doc is still the authoritative primary source — just at a new URL.

## 5. Capture quotes as you go, not at the end

When you hit a decisive paragraph, capture the verbatim quote + source URL into a scratch buffer immediately. Re-reading the whole page later to find "that one quote" wastes a full second pass, and the browser cache file may age out. The quote is the unit that makes the findings defensible — don't lose it.

## 6. Check bot-detection signals before trusting page content

`browser_navigate` returns a `stealth_warning` / `bot_detection_warning` field when a site may be serving a challenge page instead of content. If you see one, verify the page's actual text content (via the snapshot or `browser_console` on `document.title` / `document.body.innerText`) before treating it as the source — you may be staring at a "Just a moment..." interstitial, not the article.

## 7. Search engines are bot-blocked → go direct to known URLs (don't fight the CAPTCHA)

All three major search engines aggressively CAPTCHA or content-strip automated access — often simultaneously, so trying the next engine is not a reliable fallback:
- **Google** → returns `/sorry/index` (CAPTCHA interstitial).
- **DuckDuckGo** → `lite.duckduckgo.com` / `html.duckduckgo.com` returns empty result bodies or a checkbox challenge page. The JS homepage (`duckduckgo.com`) renders only the landing shell.
- **Bing** → returns 200 but strips result snippets to near-nothing after tag stripping.

**Don't waste turns cycling through search engines hoping one works.** The winning move is to **bypass search entirely and fetch authoritative URLs directly.** You usually know (or can reason about) which domains are authoritative for the question — go straight there:
- A book's author/publisher mirror site (e.g. `lamb.github.io/a-philosophy-of-software-design/...`).
- The vendor's own site / blog (`theleanstartup.com/principles`, `thoughtworks.com/radar`, `allthingsdistributed.com`).
- `en.wikipedia.org/wiki/<Topic>` — see §8.
- `web.archive.org/web/<year>/<original-url>` (Wayback Machine) for moved/deleted first-party docs.

The research question itself usually names the candidate sources (§1 of SKILL.md: "name the primary sources before you fetch"). When search is down, that named-source list *is* your search — just fetch each directly.

## 8. curl + grep beats the browser for extracting specific facts from known URLs

When you already know the URL and just need to confirm a specific claim (an attribution, a quoted phrase, a version number), `curl` in the terminal is faster and more reliable than the browser stack. The browser tools shine for *interactive* pages (clicking, filling forms, dynamic content); for plain text extraction they are overkill. Pattern:

```sh
curl -sL "<url>" -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  | sed 's/<[^>]*>/\n/g' | grep -iE 'pattern1|pattern2' | head
```

Key details:
- `-A "<browser UA>"` — many sites 403 a bare curl/Python UA. A desktop browser User-Agent usually passes.
- `sed 's/<[^>]*>/\n/g'` (or `tr -s ' '`) flattens HTML to one-token-per-line / space-normalised text so `grep` hits cleanly.
- `grep -iE '...'` — extract only the lines matching your target claim; `head` keeps output readable.
- `--max-time 20` on flaky/slow hosts to avoid hanging the turn.

Run several of these in parallel (independent reads → batch in one turn) when verifying multiple distinct sources. Reserve `browser_navigate` for pages that need JS to render or require clicking/scrolling.

## 9. Batch-probe candidate URLs before committing to a full fetch (probe-urls.sh)

When you have many candidate URLs at once — a restructured doc section (8+ likely-dead URLs), a list of possible mirrors, or several books' candidate excerpt pages — probe them all for HTTP status *before* fetching content. This saves 10+ wasted full-page fetches per dead cluster. The skill ships `scripts/probe-urls.sh`:

```sh
bash "$(skill_dir)/scripts/probe-urls.sh" \
  "https://url1" "https://url2" "https://url3"
# → "200  https://url1"
# → "404  https://url2"
```

Or inline a one-liner when you don't need the script:

```sh
for url in url1 url2 url3; do
  echo "$(curl -sL --max-time 12 -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' "$url")  $url"
done
```

Act on the status: `200` → fetch content (§8 curl+grep or browser for JS); `404` → path-shift (§4) or Wayback; `403` → mirror (§3) or browser tools; `000` → DNS gone, check Wayback. **Batch the probe calls in one turn** — they're independent reads.

## 10. Whole-site restructure → escalate, don't keep trying single paths

§4 covers a *single* moved URL. Sometimes an **entire doc section** 404s simultaneously (vendor reorganised their docs tree). Signals: you've hit 3+ consecutive 404s on different paths of the *same* domain/root. At that point stop guessing path segments and escalate:

1. **Probe the docs-site root** (§9) — confirms whether the whole site or just a section moved.
2. **Wayback Machine** the original URL: `web.archive.org/web/<year>/<original-url>` — the most reliable rescue for restructured/deleted first-party docs. Gives you the content as it was, often with the original's link structure intact.
3. **Browser navigate to the docs root** and use the on-site search (§2) — the vendor usually kept the content, just rerouted it.
4. **Fall back to the next-rung source** (authoritative secondary, clearly labelled) and note the gap in the findings — don't keep burning turns on a dead tree.

## 11. Copyrighted books with no free full text → cite the book, corroborate with open sources

Not every load-bearing primary has a free legal full text. Copyrighted books (Ousterhout's *A Philosophy of Software Design*; Hunt & Thomas's *The Pragmatic Programmer*; Bryar & Carr's *Working Backwards*) have **neither** an official open mirror (rung 2) nor a free edition. The fallback ladder (SKILL.md) assumes a fetchable rung-1; for books that assumption breaks. Handle these explicitly:

1. **State the source and its authority** — name the book, author, chapter, year, and why it's the canonical source for the claim. This anchors credibility even without a verbatim quote.
2. **Paraphrase from established knowledge of the book** *when you're confident*, and mark it clearly ("content from established knowledge of this canonical book"). **Do not present a reconstructed sentence as a verbatim quote** — fabricating a quote is worse than citing without one.
3. **Find a corroborating open source** — the author's course page (e.g. Ousterhout's Stanford CS190), a conference talk by the author, the publisher's official book page, or Wikipedia citing the book. These confirm the practice exists and the attribution is correct.
4. **Note the access gap in the findings' Sources section** — "content not directly fetchable online (no free legal full text); conclusions rest on established knowledge + the fetched corroborating open source." Transparency about access limits is itself part of a defensible findings file.

## 12. Wikipedia as a primary-source locator (not a primary source itself)

When the canonical primary source is a paywalled book/paper or a moved first-party doc, the Wikipedia article on the topic is the fastest way to **locate and verify** the attribution — it names the authors, titles, and years, and its citations point at the primaries. Use it to:
- Confirm *who* coined/named a practice and *where* (book title, chapter, paper, year) before quoting.
- Find the exact title of a paper to then fetch directly (or via a mirror / Wayback).
- Corroporate a framing ("iterative and incremental approach") with a citable source (e.g. an Ars Technica article cited in the references).

Cite the primary it points to, not Wikipedia itself — but lean on Wikipedia's reference list as a search-substitute when search engines are blocked (§7).

## 13. JS-redirected SPA doc sites → curl returns a stub, not content

Some modern doc sites (LangGraph `docs.langchain.com`, Next.js/Vite SPAs, Docusaurus with client-side routing) return only a `<title>Redirecting...</title>` stub to `curl` — the real content is rendered by JavaScript after the page loads. `curl -L` follows HTTP 3xx redirects but **cannot follow JS-based `window.location` / client-router redirects**. Signals: curl output is a few bytes of "Redirecting..." or an empty `<div id="root">` shell, even though `curl -o /dev/null -w "%{http_code}"` returns 200.

**Don't keep trying curl path variants — the content exists, it's just JS-rendered.** Switch tools:

1. **Use `browser_navigate`** — the browser executes JS and renders the real page. It also follows client-side redirects to the final URL. Check `url` in the response to see where it actually landed.
2. **If the browser also lands on a redirect loop or wrong page**, try the **raw markdown source** from the repo: many doc sites (Docusaurus, MkDocs, Sphinx) store `.md`/`.mdx` source files on GitHub. Try `raw.githubusercontent.com/<org>/<repo>/main/docs/<path>.md` — probe a few path variants with §9.
3. **If the site has a `/llms.txt` or `/llms-full.txt` endpoint** (increasingly common — CrewAI docs expose this), curl THAT instead of the HTML. It returns the doc content as plain text designed for LLM consumption.

This is distinct from §4 (404 / moved URL) and §10 (whole-site restructure): the URL is correct and returns 200, but the content is behind a JS render wall.
