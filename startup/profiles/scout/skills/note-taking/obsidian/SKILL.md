---
name: obsidian
description: Read, search, create, and edit notes in the Obsidian vault.
platforms: [linux, macos, windows]
---

# Obsidian Vault

Use this skill for filesystem-first Obsidian vault work: reading notes, listing notes, searching note files, creating notes, appending content, and adding wikilinks.

## Vault path

Use a known or resolved vault path before calling file tools.

The documented vault-path convention is the `OBSIDIAN_VAULT_PATH` environment variable, for example from `${HERMES_HOME:-~/.hermes}/.env`. If it is unset, use `~/Documents/Obsidian Vault`.

File tools do not expand shell variables. Do not pass paths containing `$OBSIDIAN_VAULT_PATH` to `read_file`, `write_file`, `patch`, or `search_files`; resolve the vault path first and pass a concrete absolute path. Vault paths may contain spaces, which is another reason to prefer file tools over shell commands.

If the vault path is unknown, `terminal` is acceptable for resolving `OBSIDIAN_VAULT_PATH` or checking whether the fallback path exists. Once the path is known, switch back to file tools.

## Read a note

Use `read_file` with the resolved absolute path to the note. Prefer this over `cat` because it provides line numbers and pagination.

## List notes

Use `search_files` with `target: "files"` and the resolved vault path. Prefer this over `find` or `ls`.

- To list all markdown notes, use `pattern: "*.md"` under the vault path.
- To list a subfolder, search under that subfolder's absolute path.

## Search

Use `search_files` for both filename and content searches. Prefer this over `grep`, `find`, or `ls`.

- For filenames, use `search_files` with `target: "files"` and a filename `pattern`.
- For note contents, use `search_files` with `target: "content"`, the content regex as `pattern`, and `file_glob: "*.md"` when you want to restrict matches to markdown notes.

## Create a note

Use `write_file` with the resolved absolute path and the full markdown content. Prefer this over shell heredocs or `echo` because it avoids shell quoting issues and returns structured results.

## Append to a note

Prefer a native file-tool workflow when it is not awkward:

- Read the target note with `read_file`.
- Use `patch` for an anchored append when there is stable context, such as adding a section after an existing heading or appending before a known trailing block.
- Use `write_file` when rewriting the whole note is clearer than constructing a fragile patch.

For an anchored append with `patch`, replace the anchor with the anchor plus the new content.

For a simple append with no stable context, `terminal` is acceptable if it is the clearest safe option.

## Targeted edits

Use `patch` for focused note changes when the current content gives you stable context. Prefer this over shell text rewriting.

## Vault organization

When creating or structuring a vault, use a Zettelkasten-inspired approach that scales to thousands of notes without becoming unnavigable.

### Folder structure (research/second-brain vault)

```
<vault>/
  00-Index/          # Entry points: MOCs, dashboard, daily feed
  01-Notes/          # Atomic permanent notes (the core knowledge)
  02-Sources/        # Source-anchored notes (one per paper/article/video)
  03-Daily/          # Daily scouting feeds (raw signal log)
  04-Templates/      # Reusable note templates
  99-Attachments/    # Images, PDFs, exports
```

See `references/vault-structure-research.md` for the full template with example frontmatter, tagging taxonomy, and naming conventions.

### Principles

- **Atomic notes**: one idea per note. A note should be short enough to title in one phrase.
- **Source traceability**: every claim links back to a source note in `02-Sources/` via `[[Source: Title]]`.
- **Link over file**: prefer wikilinks over nested folders. Notes discover each other through links, not by living in the same directory.
- **MOCs (Maps of Content)** in `00-Index/` are curated hub notes that link to related atomic notes on a theme. They evolve as the vault grows.
- **Tags for facets, folders for workflow**: tags capture cross-cutting facets (e.g. `#agents`, `#benchmark`); folders capture workflow stage.

### Frontmatter

Every note gets YAML frontmatter with at least: `title`, `date` (ISO), `tags` (list), `source` (URL or citation, for source-derived notes), `status` (seed/stub/complete). See the reference file for exact templates.

## LLM Wiki operational model (Karpathy pattern)

When the vault is run as a daily-scouting research second brain, it follows the
**LLM Wiki** methodology — a three-layer architecture (raw sources → wiki → schema)
with ingest/query/lint operations. The wiki is a persistent, compounding artifact:
knowledge is compiled once and kept current, not re-derived from scratch per query.

**Daily ingest cycle:** source note → depth-tier decision → atomic concept notes (if
breakworthy) → update MOC → append to `log.md`. One breakthrough source may touch
10–15 pages — that compounding is the whole point. **Ad-hoc queries** synthesize
across existing notes and file the answer back as a new note. **Periodic lint**
catches contradictions, orphans, missing pages, and stale claims.

See `references/llm-wiki-operations.md` for the full operational model (layers,
ingest/query/lint workflows, index.md vs log.md conventions, Obsidian integration).

## Wikilinks

Obsidian links notes with `[[Note Name]]` syntax. When creating notes, use these to link related content. Link generously — a note with more incoming links is more discoverable. Use `[[Source: Title]]` prefix convention for source notes so they're visually distinct from atomic concept notes.
