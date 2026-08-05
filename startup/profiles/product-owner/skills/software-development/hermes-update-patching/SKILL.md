---
name: hermes-update-patching
description: "Re-apply local patches after `hermes update`. Three patch categories: (1) de-brand system prompts — CRITICAL for z.ai/GLM plans, NOT cosmetic; (2) developer review-required fix — complete when verifier exists; (3) delegate tool kanban blocking — subagents must not control parent lifecycle. Load when running `hermes update`, when prompts break after update, when GLM/z.ai models fail, or when asked to 'update hermes' / 're-apply patches' / 'fix prompts after update'."
---

# Hermes Update + Local Patch Re-application

`hermes update` pulls upstream main, overwriting local patches. Three patches
must be re-applied after every update. The de-branding patch is CRITICAL —
without it, z.ai/GLM models fail because system prompts contain "Hermes Agent"
branding that confuses the model.

## Pre-update: save patches

```bash
cd ~/.hermes-teams/startup/hermes-agent
git diff origin/main...local/prompts-exp > local-patches.diff
git log --oneline origin/main..local/prompts-exp > local-patches-commits.txt
```

## Run update

```bash
hermes update
```

If permission errors on `plugins/skill_enforcer/`:
```bash
chmod -R u+w plugins/skill_enforcer/
```

If npm/Node.js fails (engine version mismatch) — not blocking. Python deps and
code update fine. Web UI may not work until Node version is fixed separately.

## Post-update: re-apply patches

### Step 1: De-brand ALL LLM-facing files (CRITICAL)

**The rule the user corrected twice:**

1. **De-branding is NOT cosmetic.** System prompts with "Hermes Agent" / "Nous
   Research" / "Hermes itself" cause model failures on some providers (z.ai
   yearly plan). These prompts are the most critical part of the system.

2. **Only change lines containing Hermes/Nous references.** Leave ALL other
   content untouched — do not shorten, rephrase, or restructure prompts that
   don't carry branding.

3. **Scan ALL LLM-facing files, not just the two main ones.** There are 8+
   files that build system prompts sent to the LLM.

**Scan for branding references:**

```python
from pathlib import Path
import re

repo = Path.home() / ".hermes-teams/startup/hermes-agent"
files = [
    "agent/prompt_builder.py",
    "agent/system_prompt.py",
    "hermes_cli/default_soul.py",
    "hermes_cli/kanban_decompose.py",
    "hermes_cli/kanban_specify.py",
    "hermes_cli/profile_describer.py",
    "plugins/memory/hindsight/__init__.py",
    "mcp_serve.py",
]

branding = re.compile(r'(Hermes Agent|Nous Research|by Nous|Hermes itself|Hermes desktop|Hermes terminal|Hermes WebUI|Active Hermes)')

for f in files:
    for i, line in enumerate((repo / f).read_text().split("\n"), 1):
        if branding.search(line):
            print(f"  {f}:L{i}: {line.strip()[:100]}")
```

For each hit, remove the branding word only. Examples:
- `"You are Hermes Agent, an intelligent..."` → `"You are an AI assistant..."`
- `"You run on Hermes Agent (by Nous Research)..."` → `"You run on this AI agent platform (by Nous Research)..."`
- `"Active Hermes profile: default"` → `"Active profile: default"`
- `"Hermes Agent messaging bridge"` → `"Messaging bridge"`
- `"conversation between Hermes Agent and the User"` → `"conversation between the agent and the User"`

**Do NOT change:**
- Code comments (lines starting with `#`) — not LLM-facing
- Legacy template detection strings (`_LEGACY_TEMPLATE_SOULS` in default_soul.py) — must match old installs
- `hermes_cli/doctor.py` — SOUL reset tool, must match legacy templates
- CLI banners, HTTP headers, bot names, version strings — infrastructure, not LLM-facing

**LLM-facing files reference table:**

| File | What it builds | De-brand? |
|------|---------------|-----------|
| agent/prompt_builder.py | Identity, help, platform hints, remote backend, kanban protocol | YES |
| agent/system_prompt.py | Active profile hint, workspace info | YES |
| hermes_cli/default_soul.py | DEFAULT_SOUL_MD identity (seeded SOUL.md) | YES (identity only, not legacy templates) |
| hermes_cli/kanban_decompose.py | Decomposer system prompt | YES |
| hermes_cli/kanban_specify.py | Triage specifier system prompt | YES |
| hermes_cli/profile_describer.py | Profile describer system prompt | YES |
| plugins/memory/hindsight/__init__.py | retain_context label (3 places) | YES |
| mcp_serve.py | MCP server instructions | YES |
| cli.py, banner.py, skin_engine.py | CLI banners, version display | NO |
| tests/ | Test assertions | Update expectations to match |

### Step 2: Developer review-required fix

In `agent/prompt_builder.py`, the Kanban task execution protocol tells
developers to block for ALL code changes. Change it so developers complete
when a downstream verifier exists:

```python
# BEFORE (upstream):
"Exception: if your output is a code change that needs human review "
"before counting as merged/done (most coding tasks), drop the "
"structured metadata ... then end with "
"`kanban_block(reason=\"review-required: ...\")` so a "
"reviewer can approve+unblock or request changes."

# AFTER (patched):
"If your output is a code change, drop the structured metadata "
"(changed_files / tests_run / diff_path) into a `kanban_comment` first, "
"then `kanban_complete`. A downstream verifier card (child of yours) "
"will review the work — do NOT block for human review. "
"Only use `kanban_block(reason=\"review-required: ...\")` when "
"there is NO downstream verifier and a human must review before merge."
```

### Step 3: Delegate tool kanban blocking

In `tools/delegate_tool.py`, add kanban lifecycle tools to the blocklist:

```python
DELEGATE_BLOCKED_TOOLS = frozenset(
    [
        "delegate_task",
        "clarify",
        "memory",
        "send_message",
        "cronjob",
        # Kanban lifecycle tools — subagents must not control parent state
        "kanban_complete",
        "kanban_block",
        "kanban_create",
        "kanban_unblock",
        "kanban_link",
        "kanban_heartbeat",
    ]
)
```

### Step 4: Fix test expectations

Tests assert on branded strings. Find and update them:

```bash
grep -rn "Hermes Agent\|Active Hermes" tests/ | grep assert
```

Update each assertion to match the de-branded text.

### Step 5: Restart all gateways

```bash
for svc in $(systemctl --user list-units --all "hermes-gateway-*" --no-legend | awk '{print $1}'); do
    systemctl --user restart "$svc"
done
```

### Step 6: Verify

```bash
# Run prompt-related tests
cd ~/.hermes-teams/startup/hermes-agent
python3 -m pytest tests/agent/test_system_prompt.py tests/agent/test_prompt_builder.py tests/tools/test_cross_profile_guard.py -q

# Verify no branding in LLM-facing files
python3 -c "
from pathlib import Path; import re
repo = Path.home() / '.hermes-teams/startup/hermes-agent'
files = ['agent/prompt_builder.py', 'agent/system_prompt.py', 'hermes_cli/default_soul.py',
         'hermes_cli/kanban_decompose.py', 'hermes_cli/kanban_specify.py',
         'hermes_cli/profile_describer.py', 'plugins/memory/hindsight/__init__.py', 'mcp_serve.py']
branding = re.compile(r'(Hermes Agent|Hermes itself|Hermes desktop|Hermes terminal|Hermes WebUI|Active Hermes)')
found = [f'{f}:L{i}' for f in files for i, line in enumerate((repo / f).read_text().split(chr(10)), 1) if branding.search(line)]
print('CLEAN' if not found else f'STILL BRANDED: {found}')
"
```

### Step 7: Checkpoint + push to private repo

Private repo: `https://github.com/Lpaydat/hermes-agent-our` (remote: `ours`)

```bash
# First-time setup only:
gh repo create hermes-agent-our --private  # DON'T use --source=.
git remote add ours https://github.com/Lpaydat/hermes-agent-our.git

# Every update:
VER=$(hermes --version 2>&1 | grep -oP 'v[\d.]+' | head -1)
git branch "our/${VER}-debranded"
git push ours "our/${VER}-debranded" main
```

## Pitfalls

- **"These prompts are cosmetic"** — WRONG. De-branding is critical for z.ai
  plan compatibility. System prompts are the most critical part of the system.
  Never dismiss prompt changes as cosmetic.
- **Only fixing prompt_builder.py + system_prompt.py** — WRONG. There are 8+
  LLM-facing files. Scan ALL of them. The user corrected this explicitly:
  "that is what you should do in the first place."
- **Shortening prompts while de-branding** — WRONG. Only change lines with
  Hermes/Nous references. Leave everything else as upstream wrote it. The user
  corrected this: "only those with `hermes` or `nous labs` needs to be fix."
- **Forgetting to restart gateways** — patches in source don't take effect
  until the gateway restarts and rebuilds its cached toolset + prompt.
- **Stale gateway after plugin add** — same restart requirement applies when
  adding plugins (loop_engine, etc.) to a running profile.
- **Typo in branch name silently fails push** — `git push ours our/v0.20.0-debranked`
  (typo: "debranked" not "debranded") fails with "src refspec does not match any"
  because the branch doesn't exist. Always verify with `git branch | grep our/`
  before pushing.
- **Mixing de-branding with prompt shortening in one commit** — the user caught
  this: I rewrote prompt CONTENT (shortening, restructuring) alongside removing
  branding words, then committed it all as "de-branding." The user said "revert
  the earlier changes that not related to de-branding back too." Fix: `git reset
  --hard <upstream-sha>`, then re-apply ONLY the branding removals via targeted
  patches. Keep the commit clean — branding removal only, nothing else.
- **Test glob matters for verification** — `test_prompt*.py` matches two files
  (test_prompt_builder.py + test_prompt_caching.py = 98 tests). Running only
  `test_prompt_builder.py` gives 79 tests. The count difference (19) is exactly
  the caching tests — not lost tests, just a narrower glob. Always run the full
  `test_prompt*.py` glob for complete verification.
