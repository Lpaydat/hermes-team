# Research Second-Brain Vault Structure

Detailed reference for the folder layout, frontmatter templates, tagging taxonomy,
and naming conventions referenced in SKILL.md. Designed for a daily-scouting research
agent that processes papers, articles, videos, and news into an Obsidian vault.

## Folder structure

```
<vault>/
  00-Index/
    MOC-Agentic-AI.md          # Map of Content: hub note linking all agentic AI notes
    MOC-Generative-AI.md       # Map of Content: generative AI (code/image/video/TTS)
    Dashboard.md               # Auto-updated overview of recent notes, open threads
  01-Notes/
    Agent-Loop-Patterns.md     # Atomic: the concept of agent loops
    ReAct-Pattern.md           # Atomic: Reason+Act prompting
    Tool-Use-via-Function-Calling.md
  02-Sources/
    Source: LLM-Powered-Autonomous-Agents-2024.md
    Source: Claude-3.5-Benchmark-Analysis.md
    Source: Matt-Pocock-Skills-Video.md
  03-Daily/
    2026-07-01.md              # Today's raw feed: all scouted items, one-liner each
  04-Templates/
    template-source-note.md
    template-atomic-note.md
    template-daily-feed.md
  99-Attachments/
```

## Naming conventions

- **Atomic notes** (`01-Notes/`): `Concept-Name-In-Title-Case.md` (e.g. `Agent-Loop-Patterns.md`).
  No date prefix — the concept is timeless; the `date` field in frontmatter records creation.
- **Source notes** (`02-Sources/`): `Source: <Short-Title>.md` (e.g. `Source: ReAct-Yao-2022.md`).
  The `Source:` prefix makes them visually distinct in wikilinks and autocomplete.
- **Daily feeds** (`03-Daily/`): `YYYY-MM-DD.md` (e.g. `2026-07-01.md`). ISO date, zero-padded.
- **MOCs** (`00-Index/`): `MOC-<Topic>.md` (e.g. `MOC-Agentic-AI.md`).

## Frontmatter templates

### Atomic note (`01-Notes/`)

```yaml
---
title: Agent Loop Patterns
date: 2026-07-01
tags:
  - agents
  - architecture
  - loops
status: complete          # seed | stub | complete
aliases:
  - Agentic Loops
  - Agent Reasoning Loops
---
```

### Source note (`02-Sources/`)

```yaml
---
title: "Source: LLM-Powered Autonomous Agents (Weng, 2024)"
date: 2026-07-01
type: paper               # paper | article | video | news | blog | repo
author: Lilian Weng
source: https://lilianweng.github.io/posts/2023-06-23-agent/
tags:
  - agents
  - survey
status: complete          # seed | stub | complete
related:
  - "[[Agent-Loop-Patterns]]"
  - "[[ReAct-Pattern]]"
---
```

### Daily feed (`03-Daily/`)

```yaml
---
title: Daily Feed — 2026-07-01
date: 2026-07-01
type: daily
tags:
  - daily-feed
items_total: 18
items_deep: 3
---
```

## Tagging taxonomy

Use **lowercase-hyphenated** tags. Keep the taxonomy flat — don't nest with slashes
unless a facet genuinely needs sub-categories.

**Domain facets:**
`agents`, `llm`, `prompt-engineering`, `tool-use`, `function-calling`, `rag`,
`fine-tuning`, `alignment`, `benchmark`, `evaluation`, `multi-agent`,
`code-generation`, `image-generation`, `video-generation`, `tts`, `multimodal`

**Workflow facets:**
`daily-feed`, `moc`, `template`

**Status facets** (in frontmatter `status`, not as tags):
`seed` (just a link, no content), `stub` (2-3 sentences), `complete` (full note)

**Quality facets:**
`breakthrough` (for top-tier items), `notable`, `signal-only`

## MOC (Map of Content) pattern

A MOC is a living hub note. It doesn't contain knowledge itself — it organizes links
to atomic notes. Structure:

```markdown
---
title: MOC — Agentic AI
date: 2026-07-01
tags:
  - moc
  - agents
---

# Agentic AI — Map of Content

## Core Concepts
- [[Agent-Loop-Patterns]]
- [[ReAct-Pattern]]
- [[Tool-Use-via-Function-Calling]]

## Architectures & Frameworks
- [[(link to framework notes)]]

## Papers & Sources
- [[Source: LLM-Powered-Autonomous-Agents-2024]]
- [[Source: (other papers)]]

## Open Questions / Gaps
- What coordination patterns emerge in multi-agent systems at scale?
- (flagged during synthesis — research these next)
```

## Depth tiers (how much to write per item)

| Tier | Count/day | Depth | Note type |
|------|-----------|-------|-----------|
| Breakthrough | 1–3 | Full deep-dive: read source, extract concepts, 200–500 word atomic note + wikilinks | `01-Notes/` + `02-Sources/` |
| Notable | 5–10 | 2–3 paragraph summary, source link, key takeaway | `02-Sources/` (stub status) |
| Signal-only | 10–20 | One-liner in daily feed: title + link + tag | `03-Daily/` only |

This tiering prevents vault bloat. Most items are cataloged; only the top items get
full atomic notes. Items can be promoted from signal-only to a full note later when
they become relevant.
