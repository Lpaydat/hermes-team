# Cross-Profile Skill Crash + REFACTOR.md Path + Orphaned QA Findings (2026-08-10)

Three issues found during the e2e-final test. ALL NOW FIXED.

## Issue 1: Cross-Profile Skill Crash — FIXED

**Card t_9d6bf6c4** — assignee=developer, skills=`["loops-engineering"]`

```
Error: Unknown skill(s): loops-engineering
Error: Unknown skill(s): loops-engineering
Error: Unknown skill(s): loops-engineering
... (14 times)
```

Circuit breaker trips at 2 consecutive crashes (max-retries=2). Card blocked.
Manual unblock → crashes again. Repeat.

**Root cause:** `loops-engineering` exists ONLY on tech-lead. Developer has
`developer-loop`, NOT `loops-engineering`. Verifier has neither. Cards were
created by agents (loop_engine, QA route-bug) that inherited the skill name
from the tech-lead's loop_engine call.

**FIXED — loop_engine + kanban_chains symlinked to ALL 15 profiles (commit
`c0f3d7a`):** Both plugins now symlinked into every profile:

```bash
for p in startup/profiles/*/; do
  name=$(basename "$p")
  [ -e "$p/plugins/loop_engine" ] || ln -s ../../../plugins/loop_engine "$p/plugins/loop_engine"
  [ -e "$p/plugins/kanban_chains" ] || ln -s ../../../plugins/kanban_chains "$p/plugins/kanban_chains"
done
```

Verified: all 15 profiles have both plugins. The e2e-final livetest (hashcheck,
107 cards) ran with zero cross-profile skill crashes after this fix.

**General rule:** When an agent creates a card assigned to a DIFFERENT profile,
the `skills` field must only contain skills that exist on the TARGET profile.
Installing loop_engine on all profiles eliminates this class of crash entirely.

## Issue 2: REFACTOR.md Written to Scratch Workspace — FIXED

**Evidence:**
- refactor-review metadata: `refactor_file: /home/user/project/REFACTOR.md`
- Actual file on disk: DOES NOT EXIST
- The verifier wrote to scratch workspace, which was cleaned up

**FIXED — explicit repo path in template (commit `c0f3d7a`):** Body now says:
"Write the validated list to `${trigger.card_body}/REFACTOR.md` (the actual
repo directory, NOT your workspace)." Template interpolation resolves to the
absolute repo path at runtime.

## Issue 3: Orphaned QA Finding Cards — FIXED

**Evidence:** At pipeline completion, 2 cards remained in `todo` — spawned by
QA route-bug as finding follow-ups. The parent milestone-gate completed before
they were picked up.

**FIXED — route-bug now uses kanban_chains + bug-handoff skill (commits
`c0f3d7a` + `d43d93e`):** route-bug calls `kanban_chains` with one chain per
finding. kanban_chains handles parent-child linking, dependency blocking, and
auto-promotion automatically. The route-bug node CANNOT complete until all
finding cards are done.

The body was simplified from 1200 chars of manual kanban_create/block
instructions to 300 chars referencing the bug-handoff skill and kanban_chains
tool. See Pattern 23c (Don't Re-Explain Automation) for the design principle.
