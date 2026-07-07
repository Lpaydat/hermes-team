---
name: research-scout
description: "Fast daily AI scout: fetch from tiered sources, dedup-check against SQLite, triage what's worth deep research, file kanban tasks for the researcher, deliver a Telegram digest. Use when running the daily scout cron, or when asked to scout, scan, or monitor AI topics."
version: 3.0.0
metadata:
  hermes:
    tags: [research, daily, scouting, triage, telegram, digest]
    category: research
    related_skills: [deep-research, arxiv, blogwatcher]
---

# Research Scout

Breadth-first daily scan of the AI frontier. You are **fast and shallow** — titles, abstracts, summaries. You do NOT read papers fully and you do NOT write Obsidian notes. You catalog candidates, file deep-research tasks, and deliver a digest.

**The researcher** (separate skill) does the slow, deep work of reading sources fully and writing curated wiki notes. You hand off to it via kanban tasks.

**Setup:** `export WIKI_PATH="$HOME/vault"`. Read `~/vault/meta/sources.md` for the source registry.

## Guard: same-day skip

The cron injects guard-script output before this skill loads.

- `STATUS:ALREADY_SCOUTED` → respond "Already scouted for [date]." and STOP.
- `STATUS:NEEDS_SCOUTING` → proceed.

**Done when:** guard confirms NEEDS_SCOUTING (or running manually).

---

## Phase 1 — Fetch

Poll every source tier from `~/vault/meta/sources.md`. Verified endpoints are in `references/operational-details.md` — load it before fetching. Fetch in parallel where independent.

**Done when:** every source tier (T1–T4) has been polled and you have a raw candidate list.

---

## Phase 2 — Dedup

For every item fetched:
```bash
python3 ~/.hermes/profiles/research/scripts/scout-db.py dedup-check "SOURCE_URL_OR_ID"
```
- `DUPLICATE` → check if there's genuinely new info. If yes → note it for the "updates spotted" digest section. If no → drop.
- `NEW` → passes to triage.

**Done when:** every fetched item is dedup-checked. Survivors are all NEW (or queued-as-update).

---

## Phase 3 — Triage

Sort survivors into four buckets. This is the core decision — **what is worth the researcher's time?**

| Bucket | Criteria | Action |
|--------|----------|--------|
| **deep-research** | ≥2 of: landscape-changing technique; T1 source; high community signal; core to agentic/generative AI | File a kanban task (see below) |
| **notable** | Significant release, interesting technique, or strong analysis — worth knowing but not a full deep-dive | Register in SQLite + include in digest |
| **signal** | Minor but worth tracking | Register in SQLite + one-liner in digest |
| **drop** | Noise, not AI-related, low quality | Drop silently |

**Done when:** every NEW item is assigned exactly one bucket.

### Filing a kanban task for deep-research items

For each deep-research candidate, create a kanban task:
```
kanban_create(
  title="Deep research: <concise topic>",
  assignee="research",
  body="Scout flagged this as deep-research-worthy on YYYY-MM-DD.\n\n"
       "Sources:\n- [Title](url)\n- [Related](url2)\n\n"
       "Why flagged: <1-2 sentences on significance>\n"
       "Suggested scope: <what the researcher should investigate>\n"
       "Load the `deep-research` skill for the full workflow.",
  parents=[]
)
```

**Done when:** every deep-research item has a kanban task filed.

---

## Phase 4 — Catalog in SQLite

Register all notable and signal items (deep-research items are tracked via the kanban task, but also register them):
```bash
# Notable
python3 scripts/scout-db.py register "SOURCE_URL" "Title" notable "" TIER

# Signal
python3 scripts/scout-db.py register "SOURCE_URL" "Title" signal "" TIER
```
Note: `wiki_note` is left empty — the scout doesn't create notes. If the researcher later processes this item, it fills in the note link.

**Done when:** every notable and signal item is registered. Deep-research items also registered with depth `deep-research`.

---

## Phase 5 — Deliver

Format the digest per `references/digest-format.md`, then send:
```bash
hermes send --to telegram "$(cat /tmp/daily-digest.txt)"
```
If `hermes send` fails, see `references/operational-details.md` → "Telegram Delivery".

The digest now includes a **🔬 Queued for deep research** section listing the kanban tasks filed.

**Done when:** digest sent (exit 0) OR failure logged.

---

## Phase 6 — Discover

Stay alert for new sources and emerging topics during the scan:
- **New high-signal source** → add to `~/vault/meta/sources.md`, register: `scout-db.py source-add "name" "url" "TIER"`, note in digest.
- **Source gone stale** → prune: `scout-db.py source-prune "name"`, remove from sources.md.
- **Emerging term** → register: `scout-db.py topic-touch "term" ""`, flag in digest.

**Done when:** any discoveries registered. No-op if nothing new — that's fine.

---

## Finalize

Write the completion marker:
```bash
date +%Y-%m-%d > ~/vault/meta/.last-scout
```

**Done when:** marker written.
