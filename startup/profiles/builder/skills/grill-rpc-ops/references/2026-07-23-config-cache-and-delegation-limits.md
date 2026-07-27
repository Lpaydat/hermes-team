# Config Caching + Delegation Iteration Limits

## Problem: delegation.max_iterations changes don't apply mid-session

Config changes to `delegation.max_iterations` (or any config.yaml key) are written to disk immediately, but the **running engine process caches config values at startup**. Changes only take effect on the next engine restart.

### What happened (2026-07-23)

1. Default `delegation.max_iterations` was 50
2. Subagent building a dossier hit "Iteration budget exhausted (50/50)" mid-task
3. Raised to 200 via `patch` on config.yaml — verified on disk (PASS)
4. Raised again to 999 — verified on disk (PASS)
5. But the running engine was still using the original value of 50
6. New subagents launched in the same session ALSO hit 50/50

### Root cause

The Hermes engine loads config.yaml once at process startup. Subsequent writes to the file are not re-read by the live process. This affects ALL config keys, not just delegation settings.

### Fix / workaround

- **For new sessions:** No action needed — config is read fresh on startup.
- **For the current session:** Accept the current limit and design subagent tasks to fit within it. For research-heavy tasks (like dossiers), the subagent may hit the limit before writing the output file. The content is recoverable from the delegation summary:
  ```bash
  cat ~/.hermes-teams/startup/profiles/builder/cache/delegation/subagent-summary-*.txt
  ```
  Extract the dossier content (starts at `# <Idea Name> (Dossier)`) and write it locally.
- **To apply new config:** Restart the engine / start a fresh `hermes` session.

### Recommended default

`delegation.max_iterations: 999` — dossiers require 40-80 tool calls (web search + curl + file writes). 50 is too low (hits iteration budget mid-dossier). 200 works for simple dossiers but leaves no margin for the independent verification subagent. 999 gives comfortable headroom. Current production value is 999 (set 2026-07-23).

Root cause: `IterationBudget` class in `agent/iteration_budget.py` — code default is 50, configurable via `delegation.max_iterations` in config.yaml.

## How to check the effective limit

```python
# From config on disk (may differ from running engine):
import yaml, os
with open(os.path.expanduser("~/.hermes-teams/startup/config.yaml")) as f:
    print(yaml.safe_load(f)["delegation"]["max_iterations"])
```

If subagents are hitting iteration limits unexpectedly, this value on disk may be higher than what the engine actually enforces (cached from startup).
