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

## 17. Academic papers (arXiv) → PDF + pdftotext, not the HTML mirror

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
