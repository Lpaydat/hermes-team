# LLM Wiki Operational Model (Karpathy Pattern)

Reference for the three-layer architecture and daily operations when running an
Obsidian vault as a persistent, compounding knowledge base — not a RAG store that
rediscovers knowledge from scratch on every query.

Based on [Andrej Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Three layers

1. **Raw sources** — the immutable source-of-truth. Articles, papers, transcripts,
   data. The agent reads from these but never modifies them. In the vault, these
   live as `02-Sources/` notes that link out to the original URL/citation.

2. **The wiki** — LLM-generated, interlinked markdown. Atomic concept notes
   (`01-Notes/`), source summaries (`02-Sources/`), MOCs (`00-Index/`). The agent
   owns this layer entirely: creates, updates, cross-references, keeps consistent.

3. **The schema** — the conventions document (this skill + its references). Tells
   the agent how the wiki is structured and what workflows to follow. Co-evolved
   over time as the domain and preferences sharpen.

## Core operations

### Ingest (daily scouting)

When a new source arrives:
1. Read/extract the source content.
2. Write a source note in `02-Sources/` with frontmatter (type, author, URL, tags).
3. Determine depth tier (breakthrough → full atomic notes; notable → stub; signal → daily feed one-liner only).
4. If breakthrough/notable: create or update atomic concept notes in `01-Notes/` — extract key ideas, add `[[wikilinks]]` to related notes.
5. Update the relevant MOC(s) in `00-Index/` to link the new notes.
6. Append an entry to `log.md` (see below).

A single breakthrough source might touch 10–15 wiki pages. That is the point —
the knowledge compounds.

### Query (ad-hoc analysis)

When the user asks a question:
1. Read `00-Index/` MOCs to find relevant notes.
2. Drill into the linked atomic + source notes.
3. Synthesize an answer with citations (`[[Source: Title]]`).
4. **File the answer back** — if the analysis is valuable, write it as a new note
   or append to an existing one. Explorations should compound, not vanish into chat.

### Lint (periodic health check)

Run occasionally to keep the wiki navigable:
- Contradictions between pages (newer source supersedes older claim).
- Stale claims that need updating.
- Orphan pages with no inbound links.
- Important concepts mentioned but lacking their own page.
- Missing cross-references (two notes that should link but don't).
- Data gaps that could be filled with a targeted source search.

## index.md vs log.md

These two special files keep the wiki navigable at scale:

**`index.md`** (content-oriented) — catalog of every page, grouped by category,
each with a one-line summary. Updated on every ingest. The agent reads this first
when answering queries to find relevant pages. Works well to ~hundreds of pages.

**`log.md`** (chronological) — append-only record of operations. Each entry uses
a consistent prefix for parseability:

```
## [2026-07-01] ingest | Source: ReAct-Yao-2022
## [2026-07-01] lint  | Fixed 3 broken wikilinks, promoted 2 stubs
## [2026-07-01] query | Synthesized agent-loop comparison → [[Agent-Loop-Comparison]]
```

`grep "^## \[" log.md | tail -5` gives the last 5 operations.

## Why this beats RAG for a personal knowledge base

The tedious part of maintaining a knowledge base is not reading or thinking —
it's the bookkeeping: updating cross-references, keeping summaries current,
flagging contradictions. Humans abandon wikis because maintenance burden grows
faster than value. The agent does the bookkeeping at near-zero cost, so the wiki
stays maintained and compounds with every source ingested.

## Connection to Obsidian

Obsidian is the IDE for this wiki:
- **Graph view** shows the shape — hubs, orphans, clusters.
- **Dataview** (plugin) runs queries over frontmatter for dynamic tables/lists.
- **Web Clipper** (browser extension) converts articles to markdown for fast sourcing.
- **Attachments** — set a fixed folder (`99-Attachments/`) and download images
  locally so they don't break when source URLs rot.
