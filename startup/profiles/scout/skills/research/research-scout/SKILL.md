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
**Script path:** `~/.hermes/profiles/scout/scripts/scout-db.py` — this is the canonical location. Don't use a relative path; CWD during cron runs may not be the scripts directory.

### ⚠️ Pitfall: `scout-db.py register` parameter bug
The `register` command has a bug (as of Jul 2026): when passing 6 arguments (`register <url> <title> <depth> <wiki_note> <source_tier>`), `source_tier` incorrectly reads from `sys.argv[5]` (same as `wiki_note`) instead of `sys.argv[6]`.

**Workaround:** Pass source_tier IN the wiki_note position (5 args total), which is safe because the scout never sets wiki notes:
```bash
# CORRECT (5 args) — wiki_note gets the tier value (unused), source_tier also gets it
python3 ~/.hermes/profiles/scout/scripts/scout-db.py register "URL" "Title" notable T1

# WRONG (6 args) — source_tier value silently dropped
python3 ~/.hermes/profiles/scout/scripts/scout-db.py register "URL" "Title" notable "" T1
```
This only affects the scout. The researcher may need the 6-arg form when writing wiki_note paths — in that case, wiki_note (arg 5) works but source_tier (arg 6) is lost. To set both correctly, use the 5-arg form when source_tier matters, or patch the script.

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
python3 ~/.hermes/profiles/scout/scripts/scout-db.py dedup-check "SOURCE_URL_OR_ID"
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
  assignee="researcher",
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
# Notable (5 args: source_tier fills wiki_note position — see register parameter bug above)
python3 ~/.hermes/profiles/scout/scripts/scout-db.py register "SOURCE_URL" "Title" notable T1

# Signal
python3 ~/.hermes/profiles/scout/scripts/scout-db.py register "SOURCE_URL" "Title" signal T1
```
Note: `wiki_note` is left empty — the scout doesn't create notes. If the researcher later processes this item, it fills in the note link.
**Bulk registration:** For 10+ items, write a Python script that calls `subprocess.run([script, "register", url, title, depth, tier])` in a loop rather than calling `scout-db.py` per-item from the shell. See `references/operational-details.md` → "Bulk dedup & registration" for the pattern.

**Done when:** every notable and signal item is registered. Deep-research items also registered with depth `deep-research`.

---

## Phase 5 — Deliver

Format the digest per `references/digest-format.md`, then send:
```bash
hermes send --to telegram "$(cat /tmp/daily-digest.txt)"
```
If `hermes send` fails, see `references/operational-details.md` → "Telegram Delivery".

The digest includes a **🔬 Queued for deep research** section listing the kanban tasks filed.

### ⚠️ Pitfall: double-delivery
The cron job has `deliver=telegram` set, which sends your **final response text** to Telegram.
If you also call `hermes send` to send the digest, the user gets TWO messages: the digest
(from `hermes send`) and your response text (from cron delivery). To avoid this:
- **Primary path:** use `hermes send` for the formatted digest, and keep your response text
  minimal — just `"Done: digest sent, N tasks filed."` The cron delivers this short confirmation.
- **Alternative:** skip `hermes send` entirely, return the full digest as your response text,
  and let `deliver=telegram` handle delivery. Simpler but requires gateway credentials visible
  to the cron's profile — if credentials are cross-profile, `hermes send` with token extraction
  is more reliable.

**Done when:** digest sent via one path (not both), exit 0, OR failure logged.

---

## Phase 6 — Discover

Stay alert for new sources and emerging topics during the scan:
- **New high-signal source** → add to `~/vault/meta/sources.md`, register: `scout-db.py source-add "name" "url" "TIER"`, note in digest.
- **Source gone stale** → prune: `scout-db.py source-prune "name"`, remove from sources.md.
- **Emerging term** → register: `scout-db.py topic-touch "term" "note"`, flag in digest.
- **Order dependency:** `source-add` must be called BEFORE `source-touch`. If you call `source-touch` for a source that hasn't been added yet, it fails with "Source not found". Always add first, then touch.

After the scan, call `source-touch` for every source that produced items today (even sources already in the DB) to keep analytics current:
```bash
python3 ~/.hermes/profiles/scout/scripts/scout-db.py source-touch "arXiv" 7 2
#                                       source name      items  deep_dives
```
Run a batch from a Python script when touching many sources (see `references/operational-details.md` → "Bulk dedup & registration" for the subprocess pattern).

**Done when:** any discoveries registered. No-op if nothing new — that's fine.

---

## Finalize

Write the completion marker:
```bash
date +%Y-%m-%d > ~/vault/meta/.last-scout
```

**Done when:** marker written.
