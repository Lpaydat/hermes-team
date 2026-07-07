---
name: task-hygiene-validator
description: "Validate beads issues for structural quality — orphan tasks, missing labels, stale items, goal-traceability. Use when running the hygiene watchdog cron, when asked to 'clean up the backlog', 'audit tasks', 'find orphan issues', 'check task quality', or 'triage issues'. Mention 'hygiene', 'orphan', 'stale', 'backlog cleanup', 'task quality'."
---

# Task Hygiene Validator

Scan a beads project's issues for structural problems and take automated action on stale items. Designed to run unattended via cron — silent when everything is clean, actionable report when it's not.

## Prerequisites

- Project must have `.driver/goal.md` (if not, run `project-discovery` skill first to auto-init)
- `bd` must be available and the project must have a `.beads/` directory

## Scanner script

A Python script at `scripts/scan_hygiene.py` performs the mechanical checks (Steps 0-2) without needing an agent loop. It outputs JSON findings to stdout, or exits silently if clean. Use it for the quick-scan path in cron jobs — only spin up the agent when the script finds something actionable.

```bash
python3 scripts/scan_hygiene.py <project_dir> [--stale-days 14] [--kill-days 30]
```

## Related references

- `references/beads-json-schema.md` — field reference for `bd list --json` output (field names, types, pitfalls like `issue_type` vs `type`)
- `references/cron-trio-pattern.md` — the proven 3-cron setup for multi-project backlog automation (goal bootstrapper + hygiene watchdog + weekly steward), including setup checklist and delivery rules
- `references/kanban-board-architecture.md` — why single-board dispatch is correct (dispatcher watches one board), concurrency enforcement, and the three-control duplicate prevention pattern
- `references/team-architecture.md` — the approved multi-domain org design: shared services (product-owner, scout, researcher) + parallel specialists (tech-lead, future commerce/content leads) + single-board routing

## Step 0: Quick exit

```bash
bd list --json 2>/dev/null | python3 -c "import sys,json; issues=json.load(sys.stdin); open_issues=[i for i in issues if i['status'] not in ('closed','done')]; print(len(open_issues))"
```

If 0 open issues → exit silently. Nothing to validate.

## Step 1: Load goal context

Read `.driver/goal.md` — extract the vision, success criteria, and in-scope areas. You need this to judge whether tasks serve the goal.

**Done when**: you can state the project's goal in one sentence.

## Step 2: Run hygiene checks

Pull all open issues and run these checks. Record findings.

```bash
bd list --json 2>/dev/null
```

### Check 1: Orphan detection (no parent epic)
For each issue, check if it has a `parent` field or belongs to an epic hierarchy.

- Issues with **no parent and not an epic themselves** → `orphan` finding
- Epic detection: beads uses the `issue_type` field (value `"epic"`), NOT a `type` field. Also check for `[epic]` in the title as a fallback convention.
- Exception: issues explicitly labeled as `chore`, `tech-debt`, `infra`, or `docs` are allowed to be standalone
- See `references/beads-json-schema.md` for the full field reference

### Check 2: Missing labels
Issues with zero labels → `unlabeled` finding. Every issue should have at minimum:
- A **type** label: `bug`, `feature`, `chore`, `tech-debt`, `infra`, `docs`
- A **priority** label or field: P0-P3

### Check 3: Goal traceability
For each orphan or unlabeled issue, read its title + description. Can you trace it to a goal area?

- **Yes, traceable** → auto-assign to the right epic (if one exists) or tag with the goal area
- **No, not traceable** → flag as `kill-candidate` (doesn't serve the goal)

### Check 4: Stale detection
For each open issue, check last-modified timestamp:

```bash
bd list --json 2>/dev/null | python3 -c "
import sys,json
from datetime import datetime, timezone
issues = json.load(sys.stdin)
now = datetime.now(timezone.utc)
for i in issues:
    if i['status'] in ('closed','done'): continue
    updated = i.get('updated_at') or i.get('updated') or i.get('mtime')
    if not updated: continue
    # Parse ISO timestamp
    dt = datetime.fromisoformat(updated.replace('Z','+00:00'))
    age_days = (now - dt).days
    if age_days >= 14:
        print(f\"{i['id']}\t{age_days}d\t{i.get('title','')[:60]}\")
"
```

Classify:
- **14-29 days untouched** → `stale` — auto-defer (see Step 3)
- **30+ days untouched** → `kill-candidate` — add to batch report for user approval

### Check 5: Duplicate detection
Check for issues with very similar titles (>80% word overlap). Flag as `duplicate-suspect`.

## Step 3: Take automated action

### Auto-defer stale items (14-29 days)
For each stale issue:
```bash
bd update <id> --defer "+30d"  # Hide from bd ready for 30 days
```
Record: `{id} deferred (stale: Nd untouched)`.

Do NOT defer issues that are:
- `in_progress` (someone is working on them)
- `blocked` (waiting on a dependency)
- Recently commented (activity within 7 days)

### Auto-tag orphans where traceable
For orphan issues that ARE traceable to a goal area:
```bash
bd label add <id> "<label>"   # Can add multiple labels one at a time
```
If a matching epic exists:
```bash
bd update <id> --parent <epic-id>
```

**Note:** The `bd label add` command adds one label per invocation. There is no `bd tag` command — use `bd label add` for labeling.

## Step 4: Build the report

Only produce output if there are findings. Format:

```markdown
## Task Hygiene Report — <Project> (<date>)

**Scanned**: N open issues
**Auto-actions taken**: X deferred, Y auto-tagged
**Needs your decision**: Z items

### Auto-deferred (stale, reversible)
| ID | Age | Title | Action |
|----|-----|-------|--------|
| tau-xxx | 18d | ... | deferred 30d |

### Kill-candidates (30d+ untouched, no goal trace)
| ID | Age | Title | Why |
|----|-----|-------|-----|
| tau-yyy | 45d | ... | Not traceable to goal |

### Orphans (no epic, review needed)
| ID | Title | Suggested epic |
|----|-------|----------------|
| tau-zzz | ... | tau-5v05 (TUI) |

### Unlabeled
| ID | Title | Suggested labels |
|----|-------|-----------------|
```

**If no findings**: produce NO output (silent). This is the watchdog pattern — only bark when there's something to report.

## Step 5: Update steering state

Update `.driver/gaps.md` with the hygiene findings:
```markdown
## Task Hygiene (as of <date>)
- N orphan issues (no parent epic)
- N unlabeled issues
- N stale issues (auto-deferred)
- N kill-candidates (awaiting user decision)
```

## User preference: autonomy over manual triage

This user does NOT want to handle tasks one-by-one. The entire hygiene system exists because the user said: *"I don't want to manually handle them one by one. I need workflow or loops that run automatically for me at the proper time with proper conditions."*

**Autonomy policy (user-approved):**
- ✅ **Auto-defer** stale items (14+ days untouched, not in_progress/blocked) — reversible, safe, no approval needed
- ✅ **Auto-tag** orphan issues when traceable to a goal area — reversible
- ⚠️ **Report only** kill-candidates (30+ days, no goal trace) — batch them in the report for one-click approval, never one-by-one
- ❌ **Never close issues automatically** — defer is reversible, close is not

This means: when in doubt about whether to take action or ask, take the reversible action and report it. Don't interrupt the user for safe operations.

## Cron delivery: gateway required for user-visible output

Hygiene watchdog cron jobs MUST have `deliver` set to a gateway-connected platform (e.g. `deliver='telegram'` or `deliver='discord'`), NOT `deliver='local'`. Local delivery only saves output to the reports directory — the user never sees it unless they open the files. If no gateway is connected, surface this gap before creating the cron job.

## Pitfalls

- **`bd` must be on PATH for cron jobs** — `bd` is typically installed at `~/go/bin/bd` (Go binary). Cron jobs and agent subprocesses may not inherit the full shell PATH. When setting up the hygiene watchdog cron, ensure the prompt instructs the agent to prepend `~/go/bin` to PATH before calling `bd`, or the script's `run_bd()` will fail silently with "bd not found". Test with `which bd` in the cron's working directory before relying on it.
- **Don't close issues automatically** — defer is reversible, close is not. Only the user approves kills.
- **Don't defer in_progress or blocked issues** — someone may be waiting on them.
- **Don't run this on projects without `.driver/goal.md`** — without a goal, goal-traceability is meaningless. Run `project-discovery` first.
- **Check for recent comments before deferring** — `bd show <id>` includes comment timestamps. An issue with recent discussion is NOT stale even if the issue record wasn't modified.
- **Worktrees/clones share beads DB** — detect at runtime by checking `git remote -v`. If two directories share the same remote URL, only scan the primary copy.
- **Never hardcode project names in skill files** — skills must be project-agnostic. Projects are discovered at runtime by scanning for `.beads/` directories (see `project-discovery` skill for the `find` snippet). NEVER maintain a project list in cron prompts — use dynamic discovery.
- **NEVER declare what the user's "active projects" are** — the user decides by which directories have `.beads/`. If you find yourself writing "the 3 active projects are..." or "active projects: X, Y, Z", STOP. You are hardcoding. The filesystem is the source of truth, not your interpretation. The user has been frustrated by this exact pattern: agent declares a project list → projects change → stale list causes confusion. Dynamic discovery only.
- **Cross-profile scope** — when the user says "clean all X" or "scan every profile", they mean ALL profiles under `~/.hermes/profiles/*/`, not just the current one. A common failure: clean only the current profile and get caught later. Always scan every profile's skills/config/memories. Session dumps (`request_dump_*.json`) are immutable API logs — skip them.
- **Platform-agnostic delivery** — cron `deliver` should route to whatever gateway the user has configured (Discord, Telegram). Never hardcode a platform in the skill or report format.
- **Beads writes propagate to Beadbox** — if Beadbox is running, any `bd update` or `bd tag` this skill performs will appear in the Beadbox UI within ~2 seconds. This is desirable (user sees the cleanup happen live) but means the skill should NOT make noisy intermediate writes — write the final state, not exploratory changes.
