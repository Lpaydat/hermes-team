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

**Beyond links — extract structured body text when the snapshot drops it.** The accessibility snapshot sometimes collapses nested content to bare markers (e.g. list items render as `[level=1]` with no text, losing the actual `<li>` content). When the snapshot shows the structure but not the text you need, walk the DOM directly:

```js
// browser_console, expression= — extract headings + paragraphs + list items as text
const els = document.querySelectorAll('h2,h3,p,li');
[...els].map(el => el.tagName + ': ' + el.textContent.trim().substring(0,300)).join('\n')
```

Or scope it to a section: `document.querySelector('article')?.querySelectorAll('h2,h3,p,li')`. This recovers list-item text, table cells, and nested structure that the snapshot flattened — the general case of "the snapshot shows empty nodes where content should be."

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

**Disambiguating a stub: rendering failure vs. source-actually-empty.** When the raw markdown rescue (step 2 above) returns near-empty content, don't assume you found the wrong file — the page may genuinely be an unwritten placeholder in the source itself. Check for telltale signs: a `.md` file containing only a few bullet fragments (`page_size`, `chunk_size (?)`) or `<!-- TODO -->` comments is a real stub, meaning the docs haven't been written yet. This is itself a finding ("the official performance guide does not exist yet") — cite it directly rather than searching for the information elsewhere without noting the gap.

## 14. Researching one author's framework → harvest sibling links from the foundational article

When the research target is a *named expert's body of work* (their taxonomy, framework, or opus), the highest-leverage move is to find their **foundational article/post** and then batch-fetch everything it links to. A single well-chosen page is a link cluster that maps the whole framework:

- **Article series** — an author's "Part 1" almost always links to Parts 2…N at the bottom ("Read Part 2", "Read Part 3"). Fetch Part 1, parse its sibling links, and pull all N in one parallel turn.
- **Course lesson lists** — a DeepLearning.AI / Coursera course page lists every lesson title + duration, which doubles as the expert's own table of contents for the topic.
- **"Recommended reading" / bibliography sections** — the author's own paper citations are a curated, authoritative reading list (better than any search engine's ranking for "what are the key papers on X").
- **Author newsletter archives** — the `?s=<query>` or tag page on their blog lists their chronological take on a topic, often surfacing follow-ups that update the original framework.

Treat the foundational page as a **link mine, not just a source**: extract every sibling/related href in one `browser_console` or snapshot pass, dedupe, then fire the fetches in a single batched turn. This turned a 5-source Andrew Ng agentic-patterns dig into two rounds (one to locate Part 1, one to pull Parts 2–5 + two course pages + the talk) instead of ten serial searches. It works precisely because the author has already done the decomposition work and linked their own subtopics — you just follow the edges.

A close cousin: **the author's personal homepage** (`<name>.ai`, `<name>.github.io`, `<name>.com`) is often a hand-curated index of their entire body of work — talks, papers, blog posts, projects, all with direct links and dates. Fetch it with §8 curl+grep to harvest the full link list in one pass before deciding which sources to pull in depth. When researching a named person's framework, hit their homepage first — it's the link mine that §14 describes but at the top level, not just within one article.

## 15. YouTube talk/podcast metadata via curl + embedded JSON

Talks, keynotes, and podcast interviews are high-value primary sources for researching a person's views — they contain the author's own framing, chapter structure, slide links, and inline annotations that transcripts alone miss. The browser stack is overkill for extracting their metadata; `curl` + a small Python parse of the page's embedded JSON is faster and needs no API key.

**What you can extract from a YouTube watch page:**
- **Title** — `<title>...</title>` tag.
- **Full description** — including chapter timestamps, slide/PDF links, the author's own "thoughts" annotations, and links to related resources. YouTube stores this in a `shortDescription` JSON field embedded in the page HTML.
- **Chapter list** — the description text usually contains `00:00 Intro / 01:25 Next section / ...` which is the talk's own table of contents.

**Pattern:**
```sh
curl -sL "https://www.youtube.com/watch?v=VIDEO_ID" -A "Mozilla/5.0" | python3 -c "
import sys, re, json
html = sys.stdin.read()
# Title
title = re.search(r'<title>(.*?)</title>', html)
print('TITLE:', title.group(1) if title else 'N/A')
# Description (embedded as JSON, needs proper unescaping)
desc = re.search(r'\"shortDescription\":\"((?:[^\"\\\\]|\\\\.)*)\"', html)
if desc:
    text = json.loads('\"' + desc.group(1) + '\"')  # JSON-decode escapes
    print(text)
"
```

**Key details:**
- The `shortDescription` value is JSON-escaped inside the page. Use `json.loads('"' + raw + '"')` to correctly unescape `\n`, `\"`, etc. — don't do naive string replacement.
- The description often contains the author's slide PDF links (Google Drive), companion blog post links, and their own timestamped "thoughts" — these are primary sources in their own right. Harvest and fetch them.
- **Chapter timestamps in the description ARE the talk's structure** — use them to decide which sections are relevant before attempting a full transcript.

**Caption transcripts are harder.** The `youtube.com/api/timedtext` endpoint requires a signed `signature` parameter from the page, and bare requests return empty. If you need the full transcript, use the browser to load the page and extract the caption track URL from the `captionTracks` JSON, or fall back to third-party transcript services. In practice, the description + chapter list + any companion blog post usually give you enough to cite the talk's claims without the full transcript.

**Batch video IDs** — when researching one author, their homepage or a YouTube playlist page lists all their video IDs. Harvest them (§2 `browser_console` on a playlist, or curl the playlist page), then batch-curl each watch page's metadata in one turn.

## 16. GitHub raw files and API as primary source

When the primary source is code, a repo README, a config file, or an agent-instruction file (e.g. a `program.md` that defines an agentic loop), GitHub serves these as plain text — no browser needed.

**Raw file fetch** — `raw.githubusercontent.com` returns the file content directly:
```sh
curl -sL "https://raw.githubusercontent.com/<org>/<repo>/<branch>/<path>"
# Try master first, then main — branches vary
```
This is how you read READMEs, CLAUDE.md/AGENTS.md files, prompt templates, Makefiles, CI configs — anything committed. No rate limits for public repos, no auth needed.

**Browser variant — `browser_console` + `fetch()` when you're already in the browser.** When mid-browser-session (navigating doc pages, extracting DOM) and you need structured data from a repo's `package.json` or README, you don't need to switch to the terminal. Execute the fetch + parse inline in one `browser_console` call:
```js
// browser_console, expression= — extract specific fields from package.json
fetch('https://raw.githubusercontent.com/<org>/<repo>/master/package.json')
  .then(r => r.json())
  .then(d => JSON.stringify({name: d.name, version: d.version, license: d.license, engines: d.engines, description: d.description}))
```
This is faster than a tool switch when the browser is already loaded, and lets you select exactly which fields you need (version, license, engines, peerDependencies) in a single round-trip. The `raw.githubusercontent.com` URL works the same as `curl` — no CORS restrictions on GET for raw files. Use the terminal `curl` approach when starting fresh or batch-fetching many files; use the browser variant when the browser is already active and you need a quick structured lookup.

**Discover an author's repos by topic** — the GitHub API lists repos sorted by recency or stars:
```sh
curl -sL "https://api.github.com/users/<user>/repos?per_page=100&sort=updated" \
  | python3 -c "
import sys, json
repos = json.loads(sys.stdin.read())
for r in repos:
    name, desc, stars = r['name'], r.get('description','') or '', r['stargazers_count']
    print(f'{name} ({stars}★): {desc}')
"
```
Filter the output by keyword (e.g. `agent`, `llm`, `tool`) to find the repos relevant to your research question. Star counts signal which repos are the author's flagship work vs. experiments.

**Pinned repos on the profile page** — `curl` the user's GitHub profile or `api.github.com/users/<user>/repos?sort=stars&per_page=10` to find their most prominent work fast. The top-starred repos are usually the ones that define their public framework.

**When raw fetch 404s**, the default branch may be `main` not `master`, or the file may live in a subdirectory. Probe with the API: `api.github.com/repos/<org>/<repo>/contents/` lists the root directory; follow `path` into subdirs.

**Recursive git tree API — list the entire repo in one call.** The `contents/` endpoint lists one directory at a time, which is slow when you don't know where docs live. The **git tree API with `recursive=1`** returns the complete file tree in a single request:

```sh
# 1. Get the default branch (master vs main varies)
curl -sL "https://api.github.com/repos/<org>/<repo>" | python3 -c "
import json,sys; print(json.load(sys.stdin).get('default_branch','main'))"

# 2. List the entire repo tree recursively
curl -sL "https://api.github.com/repos/<org>/<repo>/git/trees/<branch>?recursive=1" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('tree', []):
    p = item['path']
    if p.endswith('.md') or p.endswith('.rst'):
        print(p)"

# 3. Batch-curl the discovered source files
for f in guide/src/templates/conditional.md guide/src/templates/include_exclude.md; do
  echo "=== $f ==="
  curl -sL "https://raw.githubusercontent.com/<org>/<repo>/<branch>/$f"
done
```

This is the **definitive rescue for broken doc sites**. When a rendered doc site (readthedocs.io, mdBook, MkDocs, Docusaurus) serves 404s or has a different URL structure than expected, don't keep guessing rendered URLs — go to the source. The pattern: doc site 404s → list repo tree → find source `.md`/`.rst` files → batch-curl raw → get authoritative content directly from the repo.

**Doc-framework source locations** (where to look in the tree):
- **mdBook** → `guide/src/*.md` or `src/*.md` (rendered at `book/<chapter>.html`)
- **Sphinx** → `docs/*.rst` or `docs/*.md` (rendered at readthedocs.io)
- **MkDocs / Material** → `docs/*.md`
- **Docusaurus** → `docs/*.mdx` or `docs/*.md`

The tree API returns up to 100,000 entries and handles truncated results with a `truncated: true` flag. For very large repos, filter by extension in the python step before printing. No auth needed for public repos (rate limit: 60 requests/hour unauthenticated, sufficient since one call lists everything).

**Repo metadata API — assess project health/maturity in one call.** The `/repos/` endpoint (not just `/contents/` or `/git/trees/`) returns stars, last-push date, archived flag, open-issue count, and license — the exact signals you need to judge whether a project is alive, abandoned, or production-ready. Essential for any "compare N tools/libraries" research task:

```sh
curl -sL "https://api.github.com/repos/<org>/<repo>" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('stars:', d.get('stargazers_count'))
print('open_issues:', d.get('open_issues_count'))
print('pushed:', d.get('pushed_at'))       # last push — key liveness signal
print('archived:', d.get('archived'))       # True = repo explicitly archived
print('created:', d.get('created_at'))      # age
print('license:', d.get('license',{}).get('spdx_id'))
print('desc:', d.get('description'))"
```

Batch these across all candidate repos in one turn (parallel curls). Compare the output side-by-side: a repo last pushed 2+ years ago with `archived: False` is effectively abandoned even without the archive flag (e.g. sqlite-vss: last push 2024-05, README says "not in active development"). The `pushed_at` date + README deprecation notice together are the decisive liveness signal.

**Search API — discover projects by topic (not by author).** When researching a class of tools ("SQLite vector extensions", "graph database extensions"), the search API finds repos by keyword, sorted by stars:

```sh
curl -sL "https://api.github.com/search/repositories?q=sqlite+graph+extension&sort=stars&per_page=10" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total:', d.get('total_count'))
for r in d.get('items',[])[:8]:
    print(f\"{r['full_name']} ({r['stargazers_count']}★): {(r.get('description','') or '')[:80]}\")"
```

This is distinct from `/users/<user>/repos` (which lists one author's repos). Use search when you don't know the author — it surfaces the ecosystem. Combine with the repo metadata API above: search to discover candidates, then `/repos/` each one for health signals.

**Package registry existence check — verify a user-named tool exists.** When a user names a package/tool you don't recognise, check the registry before assuming it's real:

```sh
# PyPI
curl -sL "https://pypi.org/pypi/<name>/json" | python3 -c "import json,sys; d=json.load(sys.stdin); print('found:', d.get('info',{}).get('name'))"
# npm
curl -sL "https://registry.npmjs.org/<name>" | python3 -c "import json,sys; d=json.load(sys.stdin); print('found:', d.get('name'))"
```

A 404 or "not found" from both GitHub search AND the package registries means the name is likely misremembered — say so explicitly and list the closest matches you did find, rather than guessing what they meant.

**Package-registry stats as SDK/tool maturity signals.** Beyond existence, the registries expose **download counts, version numbers, version counts, and update recency** — the exact signals you need when a user asks "how good/mature are the SDKs?" or "is tool X production-ready." Each registry has a JSON API you can curl + parse:

```sh
# crates.io (Rust) — needs a User-Agent header or it 403s
curl -sL -H "User-Agent: research-script" https://crates.io/api/v1/crates/<name> \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['crate']; \
    print('version:',d.get('max_stable_version')); print('total downloads:',d.get('downloads')); \
    print('recent downloads:',d.get('recent_downloads'))"

# npm (JS/TS) — dist-tags gives latest; versions dict length = release count
curl -sL https://registry.npmjs.org/<name> \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print('latest:',d['dist-tags']['latest']); print('versions:',len(d['versions']))"

# npm download counts (weekly/monthly) — separate endpoint
curl -sL https://api.npmjs.org/downloads/point/last-week/<name>   # → {"downloads":N,...}

# PyPI (Python) — latest version + summary
curl -sL https://pypi.org/pypi/<name>/json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('version:',d['info']['version'])"
```

Batch all three registries for one tool's SDKs in a single turn (they're independent reads). Side-by-side output — e.g. "Rust crate 3.2.4 / 1.23M downloads; JS npm 2.0.8 / 36.5K weekly; Python PyPI 2.0.0" — instantly shows which SDK is the **most mature/actively used** (usually the one written in the same language as the core tool) vs which is younger. Version-count disparity (50 npm versions vs 3 PyPI versions) signals release cadence and maintenance investment. This turned "how good are the SDKs?" from a vague impression into a quantitative comparison in one parallel turn. Distinct from the repo-metadata API above (which covers the GitHub repo, not the published package registries).

**Go module proxy — version + release date for Go packages.** Go has no crates.io/npm-style download-count registry, but `proxy.golang.org` exposes the latest version and its release timestamp in one call. This gives you currency/recency data (the Go equivalent of "is this package actively maintained") when comparing Go libraries:

```sh
# Go module proxy — latest version + release time (JSON)
curl -sL "https://proxy.golang.org/<module-path>/@latest"
# → {"Version":"v5.3.1","Time":"2026-07-05T18:51:45Z","Origin":{...}}
```

Batch across multiple Go packages in one for-loop (the proxy is not rate-limited like pypistats). The `Time` field is the key liveness signal — a module last published 3+ years ago is effectively unmaintained even if importable. Note: private/misnamed modules return a `not found` error (the proxy only serves modules that have been publicly fetched at least once); fall back to GitHub repo-metadata API (above) for those. Use this alongside the other three registries when the comparison spans Rust/Python/Go — the Go module proxy fills the gap where Go's ecosystem otherwise has no download-count signal.

**pypistats.org rate-limiting (HTTP 429).** The `pypistats.org/api/packages/<name>/recent` endpoint (for Python download counts) rate-limits aggressively — batch-querying 6+ packages in a tight loop returns `HTTP Error 429: Too Many Requests` partway through. The fix is a `sleep(1)` between calls:

```python
import urllib.request, json, time
for pkg in ['httpx', 'requests', 'aiohttp', 'uvicorn', 'hypercorn', 'granian']:
    req = urllib.request.Request(
        f"https://pypistats.org/api/packages/{pkg}/recent",
        headers={"User-Agent": "research-agent/1.0"})
    d = json.load(urllib.request.urlopen(req, timeout=10))
    print(f"{pkg}: {d['data']['last_week']}")
    time.sleep(1)  # avoid 429
```

The 429 is per-IP, not per-key (no key exists), and resets within seconds — so `sleep(1)` is sufficient, no exponential backoff needed. Hit in a 6-package Python ecosystem comparison. **For the version number** (which pypistats doesn't provide), use `pypi.org/pypi/<name>/json` instead — that endpoint does *not* rate-limit, so batch those freely in parallel without sleeps.

**GitHub API rate-limit fallback.** The GitHub REST API (api.github.com) has an unauthenticated rate limit of **60 req/hour** (shared across all calls in the session). It fails in **two distinct ways** depending on which limit you hit — detect both, and don't conclude "no data exists" when you're actually throttled:

1. **Primary rate limit exhausted (the 60 req/hour cap)** → HTTP **403** with an **explicit JSON error**: `{"message":"API rate limit exceeded for <ip>. (...)","documentation_url":"https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"}`. This is loud — if you parse the response as JSON, `d.get('message')` starts with "API rate limit exceeded". Easy to detect; check for it before treating the response as data. Notably, fields like `stargazers_count` come back as `None`/null rather than missing — the JSON shape is preserved but all values are empty.
2. **Search API secondary rate limit** → HTTP 200 with a **silently empty result set** (`items: []` or `total_count: 0`) and no error message. This is the dangerous case — you'll see `[]` where you expected releases/tags/search hits and have no signal it's throttling. Signals: a search/releases/tags call returns zero results for a repo you know has releases, or `/search/repositories` returns `total_count: 0` for a query that obviously matches.

Don't conclude "no releases exist" / "repo not found" in either case. Fall back to:
1. `raw.githubusercontent.com/<org>/<repo>/main/<file>` for README/LICENSE/changelog files (no rate limit, no auth) — try `main` then `master`, and try alternate org names (e.g. ArangoDB's JS driver lives at `arangojs/arangojs`, not `arangodb/arangojs`).
2. The repo's `/releases` or `/tags` **web page** via `browser_navigate` (the HTML renders even when the API is throttled).
3. The package-registry APIs above (crates.io/npm/PyPI list release history independently of GitHub).

The raw-file fallback is almost always sufficient — READMEs and LICENSEs are the highest-value sources anyway. **Batch-probe candidate raw URLs** (§9 inline one-liner) across branch/org variants when you're unsure of the exact path — a `200` confirms the repo exists and gives you the README in one fetch.

**Org-level SDK discovery when the API is rate-limited.** The `/orgs/<org>/repos` call above (for "does tool X have a language-Y SDK?") is itself subject to the 60 req/hour cap. When it's throttled, fall back to **raw-file probing** of likely SDK repo names instead of the listing API:
```sh
for spec in "arangodb/arangodb-java-driver:main" "arangodb/arangojs:main" \
            "arangodb/arangodb-python-driver:master" "arangodb/arangodb-go-driver:master"; do
  repo="${spec%%:*}"; branch="${spec##*:}"
  echo "$(curl -sL -o /dev/null -w '%{http_code}' \
    "https://raw.githubusercontent.com/$repo/$branch/README.md")  $repo ($branch)"
done
# 200  arangodb/arangodb-java-driver (main)
# 200  arangodb/arangojs (main)
# 404  arangodb/arangodb-python-driver (master)   ← wrong branch/org, try variants
```
A `200` confirms the SDK repo exists and fetches its README in one call; a `404` means the org/branch guess was wrong, not necessarily that the SDK doesn't exist — try the alternate org (vendor name vs community name), alternate branch (`master` vs `main`), and alternate naming (`-driver` vs `-sdk` vs bare language name). This turns "enumerate the org's repos then filter" into "probe the candidate names you already suspect" — often faster than the API even when unthrottled, since you skip the listing + filter step entirely.

**Org-level SDK ecosystem discovery — map a vendor's language/platform coverage in one call.** When a comparison question asks "does tool X support language Y / platform Z," the answer is usually "does the org have an SDK repo for it." List all repos under the org, then filter for SDK-shaped names:

```sh
curl -sL "https://api.github.com/orgs/<org>/repos?per_page=100" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for r in d:
    name = r['name']
    if 'sdk' in name.lower():
        print(f\"{name} ({r.get('language')}): {(r.get('description','') or '')[:60]}\")
"
```

This maps the full SDK breadth (TS, Python, Go, Rust, React-Native, Flutter, iOS, Android…) in a single call per org. Batch across all candidate orgs in one turn — it turns "which of these 7 auth tools has a Rust SDK" from 7 browser navigations into 7 parallel curls you eyeball in seconds. Distinct from the per-author `/users/<user>/repos` pattern above (one developer's repos): this scans a vendor's entire published ecosystem. For an individual maintainer's project rather than an org, the same call works with `/users/<user>/repos`.

**Search API returning 0 results as decisive negative evidence.** The SDK ecosystem discovery above answers "which SDKs *exist*." The complementary question — "does a vendor have a SDK for language X?" — can be answered directly with a scoped search that returns either hits or nothing:

```sh
curl -sL "https://api.github.com/search/repositories?q=org:supertokens+rust" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('total:', d.get('total_count',0))"
# total: 0  ← no Rust SDK exists in the org. Decisive.
```

A `total_count: 0` from `org:<vendor>+<language>` is strong evidence the SDK doesn't exist (distinct from the rate-limit false-zero covered earlier — `org:`-scoped queries rarely hit the secondary limit). This is how you confirm a *negative* claim ("SuperTokens has no Rust SDK") with a primary source rather than from memory. Pair it with the org-level listing above for belt-and-suspenders: listing shows what exists, scoped search confirms what doesn't.

**`package.json` peerDependencies as plugin/server coupling evidence.** When a question turns on whether a plugin or package requires a specific server/runtime (e.g. "does Better Auth's Expo plugin work standalone?"), the `peerDependencies` field in `package.json` is the authoritative answer — more precise than docs prose, because it's what the package manager actually enforces:

```sh
curl -sL "https://raw.githubusercontent.com/<org>/<repo>/main/packages/<plugin>/package.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('peerDependencies',{}), indent=2))"
# {
#   "better-auth": "workspace:^",   ← hard peer dep on the core TS server
#   "expo-secure-store": ">=7.0.0"
# }
```

A `peerDependencies` entry pointing at the core package (`"better-auth": "workspace:^"`, `"@auth/core": "^5"`, etc.) means the plugin cannot run without that core dependency installed — i.e. it requires the server, not standalone. Fetch `deps` (runtime) and `peerDependencies` (required-by-host) together; `devDependencies` is build-time only and not load-bearing. This turns a fuzzy docs claim into a machine-verifiable fact from source. Works for any monorepo: the `packages/<name>/package.json` path is the conventional location in pnpm/yarn workspaces.

**Mine build scripts and contributor docs for architecture, not just READMEs.** When the research question is about a project's *architecture, internals, or design decisions* (not just its API or how to use it), the README and official docs are marketing-shaped — they tell you *what* the project claims, not *how* it works. The authoritative primary sources for architecture live in files most researchers skip:

- **`Cargo.toml` / `package.json` / `go.mod`** — the dependency list IS the tech stack. `Cargo.toml` naming `graph = { path = "graph" }` + `redis-module` reveals a Redis module with a separate core crate; `redis-module` being a forked git dep (`git = "https://github.com/AviAvni/redismodule-rs"`) reveals a maintained fork, not upstream. Dependencies like `roaring` (Roaring bitmaps), `rquickjs` (embedded JS engine), `simsimd` (SIMD similarity) reveal capabilities the README doesn't mention.
- **Build scripts (`build.rs`, `Makefile`, `*.sh`)** — `graphblas.sh` revealed the exact GraphBLAS version (v10.3.1), the PreJIT kernel vendoring strategy, OpenMP static-linking approach, and optimization flags (`-O3 -fPIC -fno-stack-protector`). A `build.sh` or CMake invocation is the authoritative source for how the binary is actually assembled — more reliable than any architecture blog post.
- **`CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md`** — contributor-facing docs written for AI agents and maintainers describe the architecture in unvarnished, practical detail. `CLAUDE.md` gave the full query-processing pipeline (parser → binder → planner → optimizer → runtime), the concurrency model (MVCC reads, serialized writes), the storage model (adjacency matrices, versioned copy-on-write), and the success criteria ("p99 latency must match or beat C"). These files are gold mines precisely because they're written for someone who needs to *work on* the system, not evaluate it.
- **`Cargo.lock` / lockfiles** — pinned dependency versions reveal the exact upstream library versions in use (e.g. `graphblas.sh` pins `GRAPHBLAS_VERSION=v10.3.1`), which matters for compatibility/security research.

**The pattern:** when a user asks "how does X work internally" or "what's X's architecture," fetch these files via `raw.githubusercontent.com` in parallel with the README. The build scripts and contributor docs will surface the design decisions, performance strategies, and internal structure that marketing docs abstract away. Batch-fetch `Cargo.toml` + `build.rs` + `CLAUDE.md`/`CONTRIBUTING.md` + any `*.sh` in the repo root in one turn.

**CHANGELOG.md as a maintenance-liveness primary source.** When assessing whether a project is actively maintained (the "is it safe to choose for new projects" question), the repo's `CHANGELOG.md` is a richer signal than the repo-metadata API's `pushed_at` date. The changelog gives you release *cadence* (how often), *recency* (when was the last entry), and *substance* (security fixes vs cosmetic bumps) in one fetch:

```sh
curl -sL "https://raw.githubusercontent.com/<org>/<repo>/main/CHANGELOG.md" | head -80
# If 404, try master, or CHANGELOG (no extension), or CHANGES.md
```

What to extract: the most recent version header + date, the gap between releases, and the nature of changes (security fixes = active production support; only dependency bumps = maintenance mode; nothing for 12+ months = likely abandoned). The v25.4.0 CHANGELOG for Dgraph showed CVE fixes, Go version upgrades, and new features dated one week prior — instantly confirming active maintenance without needing the API or the releases page.

**GitHub Discussions as a community-health signal.** The `/discussions` tab (newer than Issues) is where maintainers post release announcements, acquisition notices, and roadmap items. Navigate there via browser and read the pinned posts + recent announcement-category threads. This is where you find acquisition/ownership-change announcements, EOL notices for cloud/managed offerings, and maintainer responsiveness signals. For Dgraph, the pinned discussion contained both the acquisition announcement ("See this press release for details on Dgraph's new owner") and a direct maintainer confirmation of the license consolidation — facts that were not in the README, the docs, or any blog post. Distinct from Issues (bug reports) and the releases page (changelog only); Discussions carry the *narrative* of the project's direction.

**License `NOASSERTION` fallback — fetch the raw file when the API gives up.** The repo metadata API's `license.spdx_id` returns `"NOASSERTION"` (or `"Other"`) for dual-licensed repos, custom-header licenses, and open-core projects with an `ee/` (enterprise) directory. This is common — SuperTokens and Authentik both return `NOASSERTION`. Don't conclude "license unknown"; fetch the raw license file and read its header:

```sh
# Try LICENSE.md first (common in dual-licensed/open-core repos), then LICENSE
for f in LICENSE.md LICENSE; do
  echo \"=== $f ===\"
  curl -sL \"https://raw.githubusercontent.com/<org>/<repo>/<branch>/$f\" | head -10
done
```

The first few lines reveal the actual license: an `"Apache License Version 2.0"` header plus a `"Portions of this software are licensed as follows"` preamble naming an `ee/LICENSE.md` = open-core Apache 2.0 (core OSS, enterprise features separately licensed). This preamble pattern is how you distinguish true-OSS from open-core without reading the whole file — and it's often the decisive fact when the user's question is "is it fully open source."

## 17. Evaluating repo size and structure empirically (discover → clone → count)

The search API (above) finds repos by topic. When the task has a **size constraint** — "find small repos", "under 500 LOC", "1-5 files" — you need two things the search API alone can't give you: size-qualified search and empirical LOC verification.

### Size-qualified search — find small repos by KB footprint

The GitHub Search API supports a `size:` qualifier (in KB) alongside `stars:` and `language:`. Use it to pre-filter before cloning:

```sh
curl -sL -H "User-Agent: research-script" \
  "https://api.github.com/search/repositories?q=markdown+parser+python+size:<100+stars:>5&sort=stars&order=desc&per_page=5" \
  | python3 -c "
import json, sys
for r in json.load(sys.stdin).get('items', []):
    print(f\"{r['full_name']:45s} | {str(r.get('language') or 'N/A'):12s} | {r['size']:5d}KB | ★{r['stargazers_count']:4d} | {(r.get('description','') or '')[:65]}\")"
```

**Key qualifier combos for repo discovery:**
- `size:<100` → roughly <500 LOC (KB includes docs, configs, assets; code is a fraction)
- `stars:>5` → filters out personal scratch repos while staying inclusive
- `language:python` → same-language constraint for combining repos

**Rate-limit reality for search.** The Search API has a stricter secondary rate limit (10 req/min, not the 60/hr core limit). You'll burn through 10 queries in one discovery pass. Strategy:
1. Check `api.github.com/rate_limit` → read `resources.search.remaining` and `resources.search.reset`
2. If `remaining` is 0, wait for `reset` (epoch) — typically 60 seconds, not an hour
3. Make each query count: use broad queries (`markdown+parser+python`) not hyper-specific ones, and batch 8-10 per minute window

**Description encoding gotcha.** Some repo descriptions contain control characters that break `json.loads()` with "Invalid control character at column N". When parsing search results in Python, use `json.loads(r["output"])` and catch the exception — the API call itself succeeded, you just need tolerant parsing. Or pipe through `python3 -c "import json,sys; ..."` which handles it more gracefully than embedded f-strings in shell.

### Shallow clone + LOC counting — verify actual code size

GitHub's `size` field (KB) is a rough proxy — it includes READMEs, images, test fixtures, configs. When the constraint is "under 500 LOC", verify empirically:

```sh
# Shallow clone (no history — fast, minimal bandwidth)
git clone --depth 1 https://github.com/<org>/<repo>.git /tmp/repo_eval/<name>

# Count Python files
find /tmp/repo_eval/<name> -name '*.py' -not -path '*/.git/*' | wc -l

# Total raw LOC (all .py files)
find /tmp/repo_eval/<name> -name '*.py' -not -path '*/.git/*' -exec wc -l {} + | tail -1

# SLOC (non-blank, non-comment) — the number that actually matters
grep -v '^\s*$' /tmp/repo_eval/<name>/<main>.py | grep -v '^\s*#' | wc -l
```

**Why SLOC matters:** a 99-line file (raw) can be 51 SLOC — almost half is blank lines, docstrings, and comments. When comparing repos for a "combine these" task, SLOC is the real measure of integration effort. A 50-SLOC repo is a few hours to integrate; a 500-SLOC one is a multi-day effort.

**File count check:** `find . -not -path '*/.git/*' -type f | wc -l` — a repo can have 3 `.py` files but 22 total files (docs, CI configs, sample data). For a "1-5 files" constraint, count code files specifically.

### The discover → clone → evaluate workflow

When evaluating candidate repos for combination/integration:

1. **Batch search** (one rate-limit window): fire 8-10 size-qualified searches across complementary categories
2. **Triage from search metadata**: filter by `size` (KB) and `stars` from the API response — don't clone everything
3. **Shallow clone the top 3-5 candidates**: `git clone --depth 1` in a batch
4. **Count LOC/SLOC + file count**: the empirical ground truth
5. **Read the core source**: `head -30 <main>.py` to confirm functionality and assess integration complexity
6. **Check dependencies**: `head` of the main file shows `import` statements — stdlib-only repos are trivial to combine; repos with heavy external deps need dependency reconciliation

This workflow turned a vague "find small complementary repos" task into a verified report with exact SLOC counts, file counts, and dependency assessments for each repo — all backed by actual cloned code, not API metadata estimates.

## 18. Academic papers (arXiv) → PDF + pdftotext, not the HTML mirror

arXiv is the dominant primary source for ML/CS/AI research. Its abstract pages (`arxiv.org/abs/<id>`) are clean and curl-friendly, but its full-text HTML mirror (`ar5iv.labs.arxiv.org`) is unreliable — it frequently renders as an empty stub page in headless browsers (zero headings, zero body text in the snapshot). Don't waste turns on ar5iv.

**The reliable three-step workflow:**

1. **Batch screen abstracts first.** When you have a list of candidate paper IDs (some of which will be wrong subjects — arXiv IDs are recycled across all categories), curl all the `/abs/` pages in one for-loop and extract title + abstract before committing to full-text downloads:

```sh
for id in 2405.15793 2404.05427 2310.06770; do
  echo "===== arxiv:$id ====="
  curl -sL --max-time 20 -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' "https://arxiv.org/abs/$id" \
    | sed 's/<[^>]*>/\n/g' | grep -iE '.' | sed '/^$/d' \
    | grep -iA8 'Title:' | head -10
done
```

This catches wrong-subject hits fast (you'll see "Ropes" or "Quantum teleportation" where you expected "Software engineering") before downloading megabytes of irrelevant PDFs.

2. **Download the PDF + extract text with `pdftotext`.** arXiv PDFs (`arxiv.org/pdf/<id>`) are always available and contain the full paper including figures-as-text:

```sh
curl -sL --max-time 40 -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36' -o paper.pdf "https://arxiv.org/pdf/<id>"
pdftotext paper.pdf paper.txt   # poppler-utils; usually pre-installed as /usr/bin/pdftotext
```

`pdftotext` preserves section structure well enough for `grep` to hit cleanly. Download multiple PDFs in one batched turn (parallel curls), then extract + grep in the next.

3. **Grep the extracted text for specific claims.** Once you have `.txt` files, use targeted grep patterns to find the architecture/method/quote you need without reading the full paper:

```sh
# Find where the paper describes its architecture/method
grep -niE 'workflow|architecture|loop|plan|phase|decompos' paper.txt | head -30
# Extract a window around a hit for context
sed -n '150,400p' paper.txt | grep -niE 'ACI|command|edit|loop' | head -30
```

**arXiv ID gotcha:** IDs are NOT subject-scoped — `2405.15793` (SWE-agent, SE) and `2405.11403` (MapCoder) coexist with `2405.07867` (phonon physics). Always verify the title in the abstract screen before assuming a guessed ID is the paper you want. When you have a title but not an ID, §12 (Wikipedia) or the author's homepage (§14) will give you the correct ID.

**Versioned URLs:** `arxiv.org/abs/<id>` shows the latest version; `arxiv.org/abs/<id>v1` pins a version. `arxiv.org/pdf/<id>` (no version) serves the latest. For reproducibility, cite the specific version you fetched.

**Related preprint servers** (Semantic Scholar, bioRxiv, SSRN) follow the same pattern: screen abstracts, then PDF + pdftotext.

## 19. SaaS vendor pricing pages → extract from `<table>` via browser_console, not sliders

Modern SaaS pricing pages (WorkOS, Stytch, Ory, Clerk, many others) render their pricing tables via JavaScript with **interactive sliders** ("estimate your cost — drag to N users"). The actual per-unit prices and tier boundaries are computed client-side and are **not present in the static HTML** that `curl` fetches. A `curl + grep` on the pricing URL returns the page chrome but not the numbers you need.

**Don't try to interact with the sliders** (clicking, dragging, reading the computed total). That's fragile and slow. Instead, **extract the structured data directly from the DOM** via `browser_console`:

```js
// browser_console, expression= — extract pricing table rows as text
(() => {
  const rows = document.querySelectorAll('table tr');
  const results = [];
  rows.forEach(row => {
    const cells = row.querySelectorAll('td, th');
    const text = [...cells].map(c => c.textContent.trim()).join(' | ');
    if (text && /MAU|user|connection|\$|free|included|additional|month|per/i.test(text)) {
      results.push(text.substring(0, 200));
    }
  });
  return results.join('\n');
})()
```

This pulls the full pricing matrix — tier names, base prices, included quotas, per-unit overage rates, feature checkmarks — in one shot, regardless of what the slider is set to. The regex filter keeps only the rows with pricing-relevant content; drop it if you want every row.

**When the pricing isn't in a `<table>`** (some pages use `<div>` grids), fall back to the §2 body-text extraction:

```js
// browser_console, expression= — extract all pricing-relevant text
(() => {
  const lines = document.body.innerText.split('\n').map(t => t.trim()).filter(t => t);
  return lines.filter(t => /\$|free|per |MAU|user|month|included|additional|tier|plan/i.test(t))
              .filter((t, i, arr) => arr[i-1] !== t)  // dedupe consecutive
              .slice(0, 50).join('\n');
})()
```

**Caveat — some vendors hide the exact overage rate behind the slider.** Stytch (as of 2026) shows "10,000 included" and "Additional monthly active users fee" in the table but not the dollar amount — that rate only appears when you drag the slider above the free tier. If the per-unit rate is the decisive claim and it's slider-gated, note it as "not disclosed in static page; requires interactive slider" in the findings rather than guessing. Most vendors (WorkOS, Ory, Clerk, SuperTokens) do publish the full rate table in the DOM.

**Batch workflow for comparing N vendors' pricing:**
1. `curl` all N pricing URLs in parallel (§8) — get HTTP status + confirm the page is live.
2. For each JS-rendered page, `browser_navigate` to it, then `browser_console` the table-extraction expression above.
3. Capture the extracted pricing rows into the findings file as you go (§5).
