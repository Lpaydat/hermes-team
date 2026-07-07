# SQLite Analytics Layer

Why and how the research scout uses SQLite alongside the markdown wiki.

## Architecture decision: hybrid, not either/or

The vault uses **markdown for human-readable content** (wiki notes, index, log, sources)
and **SQLite for machine-facing indexes** (dedup registry, source quality, topic tracking).

This preserves Obsidian browsability while getting O(1) dedup lookups and SQL analytics.

| Component | Format | Why |
|-----------|--------|-----|
| Wiki notes | markdown | The whole point — Obsidian, graph view, human editing |
| Index (`index.md`) | markdown | Human-browsable catalog with `[[wiki-links]]` |
| Log (`log.md`) | markdown | Append-only timeline, human-readable |
| Sources (`sources.md`) | markdown | Human-editable registry |
| **Dedup registry** | **SQLite** | Thousands of rows, O(1) hash lookup, never human-read |
| **Source analytics** | **SQLite** | Quality scores, trending, pruning decisions |
| **Topic tracking** | **SQLite** | Mention counts, trending detection |

## Schema

Three tables in `~/vault/meta/scout.db` (WAL mode = crash-safe):

### `processed` — dedup registry
- `url_hash` (SHA256[:16] of normalized identifier) — UNIQUE index
- `url`, `arxiv_id` — original identifiers
- `title`, `depth_tier`, `wiki_note` — what was created
- `first_seen`, `last_updated`, `update_count` — lifecycle tracking

### `sources` — quality tracking
- `name` (UNIQUE), `url`, `tier`
- `items_produced`, `deep_dives_produced`
- `quality_score` = deep_dives / max(1, items) — computed on every touch
- `pruned` flag for removed sources

### `topics` — concept tracking
- `topic` (UNIQUE)
- `mention_count`, `first_seen`, `last_seen`
- `related_notes` — comma-separated `[[wiki-links]]`

## Identifier normalization (critical for dedup)
The `make_hash()` function normalizes before hashing:
- arXiv: `arxiv.org/abs/2607.01234` and `arxiv.org/pdf/2607.01234v2` → same hash
  (strips version suffix, resolves /abs/ vs /pdf/)
- All URLs: lowercased, trailing slash removed
- This means the same paper appearing on arXiv (Mon), HN (Tue), Reddit (Wed)
  gets ONE wiki note, not three — as long as the agent uses the original URL for dedup-check

## Key analytics queries

### Source quality ranking
`source-stats` — ranks active sources by quality_score DESC.
Decision rule: prune sources with `quality_score < 0.1` after 2+ weeks of tracking.

### Topic trending
`topic-trending 7` — topics mentioned in last 7 days, sorted by mention_count.
High mention_count + recent last_seen = active interest = worth a wiki page.

### Stale note detection
`stale-notes 30` — deep-dive/notable notes not updated in 30+ days.
Candidates for: re-visiting, updating with new sources, or archiving.

## Evolution path
If the vault grows beyond ~10k items, consider:
- Adding full-text search index on `processed.title`
- Adding a `tags` table for structured tag queries (vs grep on markdown frontmatter)
- Migrating topic tracking to use embedding similarity for "related topics" discovery
