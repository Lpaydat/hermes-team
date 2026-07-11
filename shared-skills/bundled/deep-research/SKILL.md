---
name: deep-research
description: "Thorough depth-first research workflow: read sources fully, synthesize comprehensive Obsidian wiki notes, cross-reference existing knowledge, update index. Use when doing deep research on a topic, processing a kanban deep-research task, or expanding the wiki with curated content."
version: 1.0.0
metadata:
  hermes:
    tags: [research, deep, synthesis, obsidian, wiki, knowledge]
    category: research
    related_skills: [research-scout, llm-wiki, arxiv, obsidian, youtube-content]
---

# Deep Research

Depth-first knowledge synthesis. You are **slow and thorough** — read sources fully, extract deep understanding, write curated wiki notes that compound over time. You are the **only thing that writes to Obsidian**.

The scout (separate skill) does the fast breadth-first scan and files kanban tasks. You pick those up and do the deep work.

**Setup:** `export WIKI_PATH="$HOME/vault"`. Read `~/vault/meta/AGENTS.md` for the vault schema.

---

## Phase 1 — Orient

Read the kanban task body (or user request) to understand:
- What topic/sources to investigate
- Why it was flagged (significance)
- Suggested scope

Check the vault's existing coverage:
```bash
# What do we already know about this topic?
grep -ril "KEYWORD" ~/vault/wiki/

# Has a related note already been registered?
python3 ~/.hermes/profiles/research/scripts/scout-db.py dedup-check "SOURCE_URL"
```

**Done when:** you understand the research scope and know what existing notes relate to it. You know whether this is a new topic or an expansion of existing knowledge.

---

## Phase 2 — Read sources fully

For each source listed in the task (and any related sources you discover):
- Papers: read via arxiv API (abstract + full PDF sections relevant to scope)
- Articles: `web_extract` the full text
- Videos: fetch transcript via youtube-content skill
- If paywalled or inaccessible: note it honestly and work with what's available

**Done when:** you've read every listed source (and discovered related ones) fully enough to write a comprehensive synthesis. No source left unread without a logged reason.

---

## Phase 3 — Synthesize

Write curated wiki note(s) in `~/vault/wiki/`. This is where the Karpathy LLM Wiki pattern lives — the note is a **synthesis**, not a summary.

### Writing the note

Create `~/vault/wiki/kebab-case-title.md` from the vault template:
- Full YAML frontmatter (see AGENTS.md)
- 200–500 words minimum for a single-source note; longer for multi-source synthesis
- Structure: summary → key findings → technical details → implications → connections
- `[[wiki-links]]` to every related existing note — this is what makes the graph work

### Synthesis rules
- **Connect, don't just summarize.** If the paper introduces "agent loops" and the vault already has `[[agent-frameworks]]`, link them and explain the relationship.
- **Flag contradictions.** If this source contradicts something in an existing note, say so explicitly and update both notes.
- **Note gaps.** If reading this source reveals an unanswered question, mark it: `> 🔍 **Gap:** ...` — these become future research tasks.

### Multi-source synthesis
If the task covers multiple sources on the same topic, write ONE synthesis note that integrates all of them — not separate notes per source. The synthesis is more valuable than the parts.

**Done when:** the note exists, reads as a synthesis (not a summary), and has `[[links]]` to every related existing note.

---

## Phase 4 — Cross-reference

Update the existing wiki to account for the new knowledge:

1. **Backlinks:** scan existing notes for mentions of this note's concepts; add `[[links]]` back to the new note.
2. **Index:** update `~/vault/meta/index.md` — add the new page under the right category with a one-line summary.
3. **Topics:** register/update topics in SQLite:
```bash
python3 scripts/scout-db.py topic-touch "concept-name" "[[note-name]]"   # repeat per concept
```

**Done when:** the new note has inbound links from related notes, the index lists it, and all key concepts are tracked as topics.

---

## Phase 5 — Register

Register the completed note in SQLite:
```bash
# If the scout already registered it (depth=deep-research), update it with the note link + bump:
python3 scripts/scout-db.py update "SOURCE_URL"
python3 scripts/scout-db.py set-note "SOURCE_URL" "[[note-name]]"

# If it's brand new (user-requested, not from scout):
python3 scripts/scout-db.py register "SOURCE_URL" "Title" deep-dive "[[note-name]]" TIER
```

**Done when:** the SQLite record reflects the new note (wiki_note field filled).

---

## Phase 6 — Log

Append to `~/vault/meta/log.md`:
```
## [YYYY-MM-DD HH:MM] research | Deep Research: <topic>
- Sources read: N
- Notes created: N (titles)
- Notes updated: N (titles)
- New cross-references: N
- Gaps identified: (observations or none)
```

**Done when:** log entry appended.

---

## Complete the kanban task

If this was triggered by a kanban task, mark it complete:
```
kanban_complete(
  task_id=<from context>,
  summary="Researched <topic>: wrote [[note-name]] with N cross-references. Key finding: <one sentence>.",
  metadata={"sources_read": N, "notes_created": [...], "notes_updated": [...]}
)
```
If the research revealed follow-up work, create child tasks rather than scope-creeping.

**Done when:** kanban task marked complete with a useful summary.
