---
name: codegraph
description: "CodeGraph MCP — semantic code intelligence for coding agents. Use when indexing a codebase for agent navigation, checking blast-radius of a change, finding untested code paths, detecting stale docs, or when a coding agent needs structured code understanding instead of grep. Mention 'codegraph', 'index the codebase', 'blast radius', 'test gaps', 'code graph'."
---

# CodeGraph

Semantic code graph for coding agents — functions, classes, imports, call chains exposed through MCP tools so agents get structured understanding instead of grepping. Parses 37 languages via tree-sitter.

## Per-project setup

Install: `npm install -g codegraph-ai`

Add to the project's MCP config (`.claude.json` for Claude Code):
```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph-server",
      "args": ["--mcp", "--workspace", "/absolute/path/to/project"]
    }
  }
}
```

Drop agent rules so coding agents prefer CodeGraph before falling back to grep: [codegraph-ai/codegraph-rules-for-agents](https://github.com/codegraph-ai/codegraph-rules-for-agents)

## One-shot mode (for validation in loops)

Index, run one tool, exit — no MCP handshake:

```bash
# Blast-radius of a PR (fast: no embeddings)
codegraph-server --graph-only --workspace /project \
  --run-tool codegraph_pr_context \
  --tool-args '{"baseBranch":"main","format":"markdown"}'

# Untested code paths
codegraph-server --graph-only --workspace /project --run-tool codegraph_find_untested

# Stale documentation
codegraph-server --graph-only --workspace /project --run-tool codegraph_find_stale_docs
```

`--graph-only` skips embeddings (10-50× faster). Use for CI and validation passes.

## Key tools by loop phase

| Tool | Phase | Purpose |
|------|-------|---------|
| `codegraph_pr_context` | Validate | Blast-radius: what does this change affect? |
| `codegraph_find_untested` | Validate | Which paths lack test coverage? |
| `codegraph_find_stale_docs` | Validate | Docs out of date? |
| `codegraph_find_duplicates` | Validate | Semantically similar code |
| `codegraph_get_callers` | Discover/Plan | What calls this? (impact analysis) |
| `codegraph_get_callees` | Discover/Plan | What does this call? (dependency tracing) |
| `codegraph_search_semantic` | Discover/Plan | Find code by meaning |

## Flags quick reference

| Flag | Default | When to change |
|------|---------|----------------|
| `--graph-only` | off | ON for validation/CI — 10-50× faster, no semantic search |
| `--embedding-model` | `bge-small` | `static` for ~100× faster indexing, no ONNX, ~90% of BGE quality |
| `--max-files` | 5000 | Raise for large monorepos |
| `--exclude` | — | Add `node_modules/`, `dist/`, `build/`, `.git/` |
