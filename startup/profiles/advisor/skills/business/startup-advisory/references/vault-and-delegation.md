# Vault Structure & Delegation Workflow

The shared Obsidian vault at `~/vault` is the team's compounding knowledge artifact. The advisor writes business/strategy notes alongside the researcher (AI/tech wiki) and tech-lead (dev journals). This keeps advisory knowledge persistent across model switches.

## Vault layout

```
~/vault/
├── raw/              # Immutable source documents (clipped articles, PDFs)
│   └── assets/       # Images and attachments
├── wiki/             # Curated knowledge notes (researcher-owned for AI/tech)
├── journal/          # Dev journey logs (tech-lead-owned)
├── templates/        # Obsidian note templates
└── meta/             # Index, log, source registry, SQLite DB
    ├── index.md      # Content-oriented catalog of all wiki pages
    ├── log.md        # Chronological append-only activity log
    ├── sources.md    # Human-editable source registry
    └── scout.db      # SQLite: dedup registry, source analytics
```

## Where the advisor writes

Create a `~/vault/advisory/` directory for business/strategy notes. Do NOT write into `wiki/` (researcher-owned) or `journal/` (tech-lead-owned). Follow the same conventions: frontmatter, wiki-links, index maintenance.

### Suggested structure

```
~/vault/advisory/
├── frameworks/       # Reusable analytical frameworks (market sizing, unit economics, etc.)
├── market-analysis/  # Deep dives on specific markets, segments, competitors
├── playbooks/        # Step-by-step guides (how to raise a seed round, how to run customer discovery)
├── teardowns/        # Company/competitor teardowns
└── index.md          # Advisor's own index of notes
```

### Note conventions (match existing vault patterns)

```yaml
---
title: "Human Readable Title"
type: "framework|market-analysis|playbook|teardown"
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [business, startup, <subtopic>]
source:
  - url: "..."
    title: "..."
    author: ""
    date: "YYYY-MM-DD"
depth: "deep-dive"
related: ["[[other-note]]"]
---
```

- Use `[[note-name]]` wiki-links to connect to researcher's wiki notes and across advisory notes
- Every note should have at least 1 outbound link
- When using the writing pipeline: `writing-fragments` (mine raw research) → `writing-beats` (structure into narrative) → `writing-shape` (polish into final article). Then write the result into the vault.

## Delegation workflow (advisor → scout/researcher)

When you need deep research that goes beyond a quick web search:

1. **Identify the gap.** What specific question needs answering? (e.g., "What are the unit economics of the top 5 PLG companies in dev tools?")
2. **File a kanban task.** Use the `handoff` skill to write a clean, self-contained brief:
   - Title: specific research question
   - Body: context, what's needed, format expected, links to relevant vault notes
   - Assignee: `scout` (fast triage/source discovery) or `researcher` (deep synthesis into wiki notes)
   - Parents: link to the advisory task that triggered it, if applicable
3. **Don't block on it.** Give the founder your best analysis with current knowledge, flag the gap, and tell them you've dispatched deeper research that will land in the vault.
4. **Consume the output.** When the researcher completes the task, the wiki note lands in `~/vault/wiki/`. Read it, incorporate into your advice, and cross-link from your advisory notes.

### What to delegate vs do yourself

| Delegate to scout/researcher | Do yourself |
|---|---|
| Deep competitive teardowns (multi-source) | Quick competitive positioning check |
| Market sizing with primary data | Framework-based market sizing estimation |
| Trend analysis across many sources | Single-source fact check |
| Building a curated knowledge base note | Applying a framework to a founder's situation |
| Tracking funding rounds/M&A activity | Interpreting what a funding round means strategically |

## Team profiles (discover at runtime, don't hardcode)

- `scout` — fast source discovery, triage, SQLite cataloging, Telegram digests
- `researcher` — deep research synthesis, wiki note authoring, the only one who writes to `~/vault/wiki/`
- `tech-lead` — development work, dev journal authoring in `~/vault/journal/`

Always verify current profiles with `hermes profile list` and `hermes kanban assignees` — rosters change.
