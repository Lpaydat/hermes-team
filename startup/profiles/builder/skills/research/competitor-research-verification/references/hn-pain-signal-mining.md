# HN Pain-Signal Mining (multi-query evidence extraction)

Reusable technique for extracting verbatim pain-point quotes from HN for a
venture dossier's §1 (Pain) / §2 (Evidence) sections. Produces quotes with
exact text + verifiable URL + date + engagement — the no-fabrication bar.

Verified 2026-07-25 building the AI Always-Adds-Code Fixer dossier: 12 queries
→ 213 unique stories → 15 threads fetched → 87 pain-keyword matches → 12
citable primary quotes (parent threads 13–1774 pts). Reddit was blocked this
session; pivoted fully to HN with strong results.

## When to use

- Any dossier needing verbatim user-pain quotes (devtools, infra, AI tools
  where the audience lives on HN, not Reddit).
- When Reddit RSS is blocked / silent and you need a primary-quote source.
- When you need *specific* behavioral pain (not just "code quality" generally,
  but "AI adds code instead of refactoring" specifically).

## The 5-stage pipeline

Write each stage as a standalone Python script using `urllib.request` (NOT
`curl | python3` — see parent SKILL.md security section). Run sequentially.

### Stage 1 — Broad multi-query story discovery

Run **8–12 different query phrasings** of the pain (synonyms, tool names,
behavioral verbs). Dedupe hits by `objectID`. This is critical: a single query
misses most of the signal. The AI-code-bloat run used these and got very
different hit counts:

```
"AI code bloat"        → 134 hits
"cursor code quality"  →  93 hits
"AI refactor code"     → 129 hits
"AI coding debt"       → 635 hits
"AI never refactors"   →  38 hits
"copilot spaghetti code" → 2 hits
```

The low-hit queries ("copilot spaghetti", "AI never refactors") returned the
*sharpest* threads even though they had few results. **Don't skip narrow
queries — they surface the most on-target stories.**

Rank the deduped set by `(points + num_comments)` descending; keep the top ~40
above an engagement floor (e.g. `points + comments >= 8`).

### Stage 2 — Targeted thread selection

Pick the 10–15 highest-engagement, most-on-topic stories to fetch as full
threads. Prioritize **Ask HN** threads (users describe pain unprompted) and
threads whose title names the exact behavior. Fetch each via
`GET /items/<objectID>`.

### Stage 3 — Pain-keyword tree-walk

Each `/items/` response is a nested comment tree. Walk it recursively and keep
comments whose text matches a **pain keyword regex** AND whose length is in a
citable range (~60–900 chars: not one-liners, not essays):

```python
import re
PAIN_RE = re.compile(
    r"\b(bloat|bloated|spaghett|duplicat|DRY|refactor|consolidat|append|"
    r"adds? code|added code|new code|never (?:refactor|delet|remov)|"
    r"copy[- ]?paste|dead code|cruft|mess\b|junk|trash|garbage|crap|"
    r"reinvent|wheel|tech debt|technical debt)\b", re.I)

def walk(node, depth=0):
    yield (depth, node)
    for c in (node.get("children") or []):
        yield from walk(c, depth + 1)

for depth, c in walk(thread):
    t = (c.get("text") or "").strip()
    if 60 <= len(t) <= 900 and PAIN_RE.search(t):
        matches.append({"id": c.get("id"), "author": c.get("author"),
                        "text": t, "url": f"https://news.ycombinator.com/item?id={c.get('id')}"})
```

Tailor the regex keywords to the *specific* pain thesis. For "always adds
code," the high-value terms were `append|adds code|never refactor|duplicat|DRY|
reinvent|dead code`.

### Stage 4 — Comment-level search for razor phrasing

After the tree-walk, run **comment-tagged searches** (`tags=comment`) with
sharp quoted phrases to catch the most quotable one-liners that broad story
search misses. These found the single best quote of the AI-code-bloat run:

```
GET /search?query="AI never refactors existing"&tags=comment
GET /search?query=prefer+adding+new+code&tags=comment
GET /search?query=AI+adds+code+never+deletes&tags=comment
```

Comment hits have `comment_text`, `story_id`, `story_title`. Fetch each hit's
full text via `/items/<objectID>` to verify before citing.

### Stage 5 — Resolve parent-story metadata + verify URLs

Standalone comments need their parent story's title/points/date for proper
sourcing. Each comment's `story_id` field points to it — fetch
`/items/<story_id>` to get title + engagement.

**Final verification (do NOT skip):** for every quote you cite, re-fetch its
`objectID` from the API and confirm the response `text` contains the exact
quote fragment you attributed. A 4-line ad-hoc script (sample 4–6 objectIDs,
substring-match the quote) catches any copy/paste/normalization error before
it ships. Every `news.ycombinator.com/item?id=<id>` URL is deterministic and
resolves to the exact item.

## HTML-entity normalization

HN comment `text` is HTML-encoded. Normalize for readable quoting:
`&#x27;`→`'`, `&gt;`→`>`, `&lt;`→`<`, `&quot;`→`"`, `&#x2F;`→`/`, `<p>`→space.
State in the dossier that only entities were normalized, wording preserved.

## Engagement-floor guidance

- A quote in a **high-engagement parent thread** (200+ pts) reads as
  broadly-representative pain. Lead with these.
- A razor-sharp quote in a low-engagement thread (10–50 pts) is still citable
  if the phrasing is uniquely on-point — just don't over-weight it.
- **OP text of an Ask HN / rant thread is often the strongest single signal**
  (the poster articulates the whole thesis). The 64-pt "AI coding is a
  nightmare" OP (48770319) stated the refactor-vs-append thesis verbatim —
  better than any individual comment.

## Output format (dossier-ready)

Build a table per the parent SKILL.md quality bar: `# | quote | URL | date |
engagement`. Keep verbatim quotes under ~120 words; longer → excerpt with `[...]`.
