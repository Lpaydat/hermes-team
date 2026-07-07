# Code indexing tools — verified facts (2026-07-06)

Researched while resolving the `codegraph-server` confusion. Concise ground truth for future ops runs.

## CodeGraph (`codegraph-ai` on npm)

- **npm package**: `codegraph-ai` (v0.1.5+)
- **Bins provided**: `codegraph` and `codegraph-ai` — both point to `dist/cli.js`.
- **There is NO `codegraph-server` binary.** The skill was written against an early name; it is wrong. The MCP server is a subcommand of `codegraph`.
- **Subcommands**:
  - `codegraph index [dir]` — index a project (default: cwd)
  - `codegraph serve [dir]` — start MCP server on stdio
  - `codegraph dashboard [dir]` — web dashboard on :3000
  - `codegraph query <name>` — query a symbol from the index
  - `codegraph watch [dir]` — re-index on file changes

## Graphify (`graphifyy` on pip)

- **pip package**: `graphifyy` (note double-y) — binary is `graphify`.
- **Version**: 0.9.7 as of this writing.
- **Skill install**: `graphify install --platform hermes` copies `SKILL.md` + `references/` into `~/.hermes/skills/graphify/`. Supports: claude, codex, hermes, pi, cursor, gemini, and many more.
- **Per-profile gotcha**: install targets the DEFAULT profile only. Other profiles need a symlink (see SKILL.md "Per-profile gotcha").
- **Core pipeline**: `graphify .` inside a project dir → generates `graphify-out/` with `graph.json`, `GRAPH_REPORT.md`, and interactive HTML.
- **Incremental**: `graphify . --update` re-extracts only new/changed files.
- **Git hook** (per-project): `graphify hook install` → post-commit hook auto-rebuilds graph.json on code changes (doc/image changes ignored).
- **Query tools** (after a graph exists):
  - `graphify path "A" "B"` — shortest path between two nodes
  - `graphify explain "X"` — plain-language explanation of a node + neighbors
  - `graphify diagnose multigraph` — report same-endpoint edge collapse risk
  - `graphify merge-graphs <g1> <g2>` — merge graphs across repos

## Index output location

Both tools write their output **in the project dir** (`graphify-out/`, `.codegraph/`), NOT in `/tmp`. Do not hedge about `/tmp` space when planning an indexing run unless you've verified the tool actually uses `/tmp` for intermediates — neither tool has been confirmed to do so.

## Index survival across `hermes update`

`hermes update` runs `git stash` → `git pull` → `git stash pop`. It **never** runs `git clean`, so untracked files (including index dirs) survive every update. Verified in `hermes_cli/config.py` — the comment explicitly states this is intentional ("Stash-and-drop (not `reset --hard` + `git clean -fd`) so ignored paths — node_modules, venv, build outputs — are never touched").

**Keep index dirs from polluting git status** by adding them to `.git/info/exclude` (local-only, doesn't touch the tracked `.gitignore`, so it won't show as a local change or risk a pull conflict):

```bash
cd <project_dir>
cat >> .git/info/exclude <<'EOF'

# Code graph indexes (local only, not tracked)
graphify-out/
.codegraph/
codegraph-out/
EOF
```
