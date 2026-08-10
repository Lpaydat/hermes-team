# Engine Skill Validation at Load Time

## Problem

Cross-profile skill crashes (Pattern 22) happen when agents create cards with `skills=["X"]` assigned to a profile that doesn't have skill X. The card crashes on spawn with `Error: Unknown skill(s): X`, the circuit breaker trips at 2 failures, and the card sits blocked forever.

While the root fix is installing the skill on the target profile (Pattern 22), there was no EARLY WARNING system — the crash only surfaces at dispatch time, after the card has already been created and claimed by a worker.

## Solution

Added `_validate_skills()` to `TemplateStore.all()` in `store.py`. At engine startup (every template load), it checks every node's `skill` field against the profile's skill inventory. Mismatches log a WARNING immediately.

### What it checks

1. Profile exists under `~/.hermes-teams/startup/profiles/<profile>/`
2. Skill exists in EITHER:
   - `profiles/<profile>/skills/` (profile-local skills, recursive)
   - `~/.hermes-teams/shared-skills/` (mattpocock bundle and other shared skills, recursive)

The dual-path search is critical — skills like `to-tickets` and `codebase-design` live in `shared-skills/mattpocock/`, NOT under any profile's skills directory.

### What it does NOT check

Agent-created cards (via `kanban_create`). When an agent calls `kanban_create(skills=["live-testing"], assignee="debugger")`, the skill validation happens in hermes-agent code at dispatch time — our engine can't intercept it. The defense for that path is:
- The bug-handoff skill warns agents not to pass skills on finding cards
- Installing commonly-needed skills (live-testing, loops-engineering) on ALL profiles eliminates the crash even if the agent ignores the warning

### Implementation

Location: `startup/scripts/workflow_engine/store.py`, method `_validate_skills()`

```python
def _validate_skills(self, workflows: list[Workflow]) -> None:
    import os
    hermes_root = Path.home() / ".hermes-teams"
    profiles_root = hermes_root / "startup" / "profiles"
    shared_skills = hermes_root / "shared-skills"
    for wf in workflows:
        for node in wf.nodes:
            skill = (node.skill or "").strip()
            if not skill:
                continue
            profile_dir = profiles_root / node.profile
            found = False
            skills_dir = profile_dir / "skills"
            if skills_dir.exists():
                found = any(skill in dirs for _, dirs, _ in os.walk(skills_dir))
            if not found and shared_skills.exists():
                found = any(skill in dirs for _, dirs, _ in os.walk(shared_skills))
            if not found:
                log.warning("SKILL VALIDATION: %s/%s uses skill '%s' on profile '%s' — NOT FOUND",
                            wf.id, node.id, skill, node.profile)
```

### Verification

All 17 templates pass with zero warnings after:
- live-testing installed on debugger + verifier
- loop_engine + kanban_chains on all 15 profiles
- to-tickets and codebase-design resolved via shared-skills path

```bash
cd startup/scripts && python3 -c "
import logging; logging.basicConfig(level=logging.WARNING)
from workflow_engine.store import TemplateStore
store = TemplateStore('workflow_engine/templates')
templates = store.all()  # zero SKILL VALIDATION warnings
"
```

### Commit

`c1364ec` (2026-08-10) on branch `feat/dev-port-workflow`
