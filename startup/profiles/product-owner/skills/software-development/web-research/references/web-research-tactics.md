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
