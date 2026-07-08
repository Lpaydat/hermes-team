---
name: dev-env-setup
description: "Install, configure, and onboard the agent dev environment. Use on first run, new project setup, tool installation, profile configuration, or when the user says 'setup', 'install', 'onboard project', 'configure environment'."
metadata:
  hermes:
    tags: [setup, install, environment, ops, infrastructure]
    category: software-development
---

# dev-env-setup — first-time + per-project environment setup

## When to use

- First time setting up the agent team
- Adding a new project to the workflow
- Installing/upgrading a tool
- Fixing broken environment state

## Prerequisites check

Before any setup, verify the current state:

```bash
# Check what's already installed
echo "=== TOOLS ===" 
for tool in bd pi zz codegraph graphify; do
  which $tool 2>/dev/null && echo "  ✅ $tool" || echo "  ❌ $tool missing"
done

# Check profiles
echo "=== PROFILES ==="
hermes profile list 2>&1

# Check gateways
echo "=== GATEWAYS ==="
hermes gateway status 2>&1
```

## Global tools (install once)

### bd (beads issue tracker)
```bash
npm install -g @beads/bd
# Verify
bd --version
```

### pi (coding harness)
```bash
# Already installed via fnm if present
which pi || npm install -g @nousresearch/pi
pi --version
```

### CodeGraph (semantic code analysis)
```bash
npm install -g codegraph-ai
# Verify — the package provides the `codegraph` binary (NOT codegraph-server)
codegraph --help
# Subcommands: index, serve (MCP server), dashboard, query, watch
```

> **See `references/code-indexing-tools.md`** for the full verified landscape of both CodeGraph and Graphify — subcommands, pip/npm package names, and the per-profile skill-install gotcha.

### Graphify (knowledge graph indexer)
```bash
# 1. CLI (pip package is "graphifyy", binary is "graphify")
pip install graphifyy
graphify --version

# 2. Install the skill into Hermes (one-time)
graphify install --platform hermes
#    → copies SKILL.md + references/ to ~/.hermes/skills/graphify/
```

⚠️ **Per-profile gotcha:** `graphify install` targets the DEFAULT profile skills dir (`~/.hermes/skills/`). Other profiles (ops, tech-lead, etc.) have their own skills dir under `~/.hermes-teams/startup/profiles/<name>/skills/` and will NOT see the graphify skill. Symlink it into each profile that needs it:
```bash
ln -s ~/.hermes/skills/graphify ~/.hermes-teams/startup/profiles/<profile>/skills/graphify
```

**Done when**: `graphify --version` responds AND the skill is visible in every profile that needs it (verify with `skill_view(name='graphify')`).

## Per-project setup

For each new project the team will work on:

### 1. Initialize beads
```bash
cd <project_dir>
bd init
```

### 2. Create .driver/ steering files
```bash
mkdir -p .driver
# goal.md — vision, success criteria (PO writes this)
# progress.md — current state snapshot (updated each cycle)
# decisions.md — ADRs + open questions
# gaps.md — identified gaps, tech debt
```

### 3. Index codebase (for projects >50 files)
```bash
# CodeGraph index (for call graph / symbol analysis)
codegraph index <project_dir>
# Or start the MCP server for live queries:
# codegraph serve <project_dir> &

# Graphify index (for context compression) — run INSIDE the project dir
cd <project_dir>
# Full pipeline (generates graphify-out/ with graph.json + GRAPH_REPORT.md + interactive HTML):
graphify .
# Incremental update on changed files only:
graphify . --update
```

#### Graphify post-commit git hook (optional, per-project)
Auto-rebuilds the graph after every commit so `graphify-out/` stays current:
```bash
cd <project_dir>
graphify hook install    # install | uninstall | status
```
The hook runs AST extraction on changed files only, then rebuilds `graph.json` + `GRAPH_REPORT.md`. Doc/image changes are ignored — run `graphify . --update` manually for those.

### 4. Add to active-projects.json
```bash
# Update the tech-lead's active-projects.json
python3 -c "
import json
path = '/home/lpaydat/.hermes-teams/startup/active-projects.json'
with open(path) as f:
    data = json.load(f)
data['active_projects'].append({
    'path': '<project_dir>',
    'name': '<project_name>'
})
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"
```

### 5. Verify
```bash
cd <project_dir>
bd ready  # should show no ready issues yet
ls .driver/  # should have at least goal.md
```

**Done when**: project has beads, .driver/, and is in active-projects.json.

## Profile configuration

### Standard settings for all profiles
```yaml
model:
  default: glm-5.2
  provider: zai
  rate_limit_delay: 30
fallback_model: []
```

### Per-profile toolsets

`hermes-cli` is the default toolset — it bundles `_HERMES_CORE_TOOLS` (terminal, process, read/write/patch/search file ops, skills, memory, session_search, todo, clarify, execute_code, delegate_task, cronjob, browser, web, vision, TTS, etc.). Add `kanban` explicitly for any profile that coordinates via the board. You do NOT need to list terminal/file/skills/memory/session_search individually — `hermes-cli` already includes them all.

| Profile | Toolsets | Notes |
|---------|----------|-------|
| product-owner | `hermes-cli`, `kanban` | Front door + beads + PRD |
| tech-lead | `hermes-cli`, `kanban` | May restrict toolsets later (NO file ops, delegation, code_execution) |
| developer | `hermes-cli`, `kanban` | Wraps pi harness |
| verifier | `hermes-cli`, `kanban` | Wraps adversarial-review + delegate_task for fresh-eyes |
| ops | `hermes-cli`, `kanban` | Environment management |

> **Verification:** `hermes-cli` = `_HERMES_CORE_TOOLS` in `toolsets.py` (line ~430). The list includes terminal, process, all file tools, all skill tools, memory, session_search, todo, clarify, execute_code, delegate_task, cronjob, browser, web, vision, TTS, and HA tools. Confirmed by reading source on 2026-07-06.

## Profile configuration pitfalls (learned the hard way)

Hand-rolled profiles (created without the `transform` skill) commonly leave these gaps. Check each during setup or audit:

### `hermes config set` overwrites list values — use yaml.dump instead
`hermes config set <key> <value>` writes scalars fine but **overwrites lists entirely**. For list keys (`command_allowlist`, `skills.disabled`, `fallback_model`, `toolsets`), edit `config.yaml` directly via Python `yaml.dump`:

```python
import yaml
path = "<HERMES_HOME>/config.yaml"
with open(path) as f:
    config = yaml.safe_load(f)
config["command_allowlist"] = ["df *", "git status", ...]  # real list
with open(path, "w") as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
```

Setting a JSON string via `hermes config set command_allowlist '["df *"]'` stores it as a **quoted string** (`'[...]'`), not a YAML list. The approval system reads `config.get("command_allowlist", [])` — a string fails silently.

### command_allowlist takes glob patterns, not approval descriptions
Entries are shell commands with optional wildcards (`df *`, `git status`, `systemctl --user status *`). They are NOT the human-readable approval-prompt text ("delete in root path", "script execution via -e/-c flag"). Approval descriptions as allowlist entries match nothing — every flagged command still prompts.

### SOUL.md must have the full base template structure
A specialized SOUL.md is not just the specialty block. It must include (in order):
1. Opening line ("You are **<name>**, a specialized Hermes agent...")
2. `CONSTITUTION:BEGIN`/`END` block (FROZEN — copied verbatim from base)
3. `SPECIALTY:BEGIN`/`END` block (the role description)
4. `Team coordination` section (copied verbatim from base)

A hand-rolled SOUL with only the specialty block is missing the constitution — the agent loses its safety invariants.

### Markers that must exist per-profile
- `.bootstrap_complete` — prevents re-transforming. Should contain date + one-line specialty.
- `.no-bundled-skills` — prevents re-seeding on update. See `bundled-skills-opt-out` skill.

### Profile description is required for kanban routing
`hermes profile describe <name> --text "<one or two sentence role>"` — the kanban decomposer routes by description, not name. A profile without a description won't receive routed tasks correctly.

### Read-only permissions on cloned skill dirs
Some skill directories (e.g. mattpocock) ship with mode 555/444. `rm -rf` fails with Permission denied. Fix with `chmod -R u+w <dir>` before deleting.

> **For a comprehensive profile audit checklist**, see `references/profile-audit.md`.

## Document state

After every setup action, append to `~/dev-env-setup.md`:

```markdown
## [YYYY-MM-DD HH:MM] <action>
- What was installed/changed
- Verification result
```

**Done when**: state documented and verified.
