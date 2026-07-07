# Multi-Project Backlog Automation — The Cron Trio Pattern

Proven pattern for keeping backlogs clean across many projects without
manual triage. Three coordinated cron jobs, each with a distinct role.
All deliver to a gateway-connected platform (Telegram/Discord), never
local-only.

## The three jobs

### 1. Goal Bootstrapper (one-shot)

**Purpose:** Create `.driver/goal.md` for each project that lacks one.
Goals are the prerequisite for everything else — without a goal,
goal-traceability checks are meaningless.

**When to run:** Once, when setting up the hygiene system for the first
time, or when a new project is added.

**Schedule:** `2m` (one-shot, 2 minutes after creation).

**Deliver:** local is fine — the output is written to files, not
messaged. But if a gateway is connected, deliver there so the user sees
the goals were created.

**Skill:** `project-discovery`

**Key detail:** Must read AGENTS.md (richest source) → README →
docs/prd/ → bd list to synthesize goals. See the skill's auto-init
section for the full priority order.

### 2. Task Hygiene Watchdog (every 4h)

**Purpose:** Scan all active beads projects for structural problems.
Auto-take reversible actions (defer stale, tag traceable orphans).
Report irreversible decisions (kill-candidates) in batch.

**When to run:** Every 4 hours, recurring.

**Deliver:** MUST be a gateway platform (telegram/discord). Local-only
delivery means the user never sees the report.

**Skill:** `task-hygiene-validator`

**Script-first design:** The mechanical checks (orphan/stale/label/duplicate detection) run via `scripts/scan_hygiene.py` — a pure Python script
that needs no agent tokens. Only when it finds actionable results does
the agent loop spin up to auto-defer, auto-tag, and write the report.
This keeps token cost near zero for clean projects.

**Silent-when-clean rule:** If ALL projects are clean, produce NO
output. This is the watchdog pattern — only bark when there's something
to report.

### 3. Weekly Sprint Steward (weekly)

**Purpose:** Produce a health briefing: what closed, what's stuck, what
changed. Traffic-light (R/G/Y) per project. Proposes next priorities.

**When to run:** Weekly (e.g. Sunday 19:00 local).

**Deliver:** Gateway platform.

**Skill:** `project-discovery`

## Setup checklist

1. Confirm gateway is connected (`hermes gateway status`). If no
   gateway, set one up FIRST — local-only delivery defeats the purpose.
2. Run Goal Bootstrapper — wait for completion, verify `.driver/goal.md`
   exists in all target projects.
3. Create Hygiene Watchdog cron — set `deliver` to the right
   platform/channel.
4. Create Weekly Sprint Steward cron.
5. Verify Beadbox is installed (optional but recommended — gives the
   visual layer the crons maintain the data layer for).

## Multi-project discovery (NEVER hardcode)

All three cron jobs discover projects at runtime. Do NOT maintain a
project list in cron prompts, config files, or reference docs. Instead,
each cron prompt includes this discovery snippet:

```bash
find /home/<user> -maxdepth 4 -name ".beads" -type d 2>/dev/null | while read beads_dir; do
    project_dir=$(dirname "$beads_dir")
    remote=$(git -C "$project_dir" remote get-url origin 2>/dev/null)
    echo "$project_dir|$remote"
done
# Dedup by git remote (skip worktrees that share a DB)
```

This means:
- **Adding a project**: just run `bd init` in the new directory. Next cron run discovers it automatically.
- **Deleting a project**: close issues, remove `.beads/`. Next cron run stops finding it automatically.
- **NEVER update cron prompts when projects change** — the prompts are project-agnostic.

## Beadbox integration

Beadbox is a native desktop GUI that reads `.beads/` directly via
WebSocket. Any `bd update`, `bd tag`, or `bd create` the cron jobs
perform appears in Beadbox within ~2 seconds. This means the hygiene
system's auto-actions are visible to the user in real-time without
needing to read the report.

The report (delivered to Telegram/Discord) is the "why"; Beadbox is the
"what". Both serve different purposes — don't skip the report even if
Beadbox is installed, because the report explains the reasoning behind
deferrals and kill-candidates.

## Project deletion cascade

When a project is deleted, the deletion must cascade to all surfaces
that reference it — or the user will see stale references and lose trust
in the system. The full cascade (in order):

1. **Close all open beads issues** with reason "Project archived"
2. **Remove `.beads/`** directory
3. **Remove `.driver/`** directory
4. **Delete Discord channel** for the project (via API:
   `DELETE /channels/<id>`)
5. **Post a correction** in the hygiene-alerts channel noting the
   deletion (so old reports with the project don't confuse)
6. **Truncate/purge logs** that contain the project name (agent.log,
   errors.log, old cron output)

If the system is built correctly (dynamic discovery, no hardcoded
names), steps 1-4 are sufficient — no skill/cron/reference file edits
needed. But if any file DID hardcode the name, it must also be cleaned.

**Channel lifecycle rule:** Create a Discord channel when a project is
added, delete it when the project is deleted. Stale channels cause
confusion. The bot can create/delete channels programmatically via the
Discord API — no manual user action needed.

## bd command reference (tested)

- `bd label add <id> "<label>"` — adds one label per invocation. There
  is NO `bd tag` command. Use `bd label add` for all labeling.
- `bd update <id> --defer "+30d"` — defers an issue (hides from
  `bd ready`). Reversible.
- `bd update <id> --parent <epic-id>` — parents an orphan to an epic.
- `bd close <id> --reason "<text>"` — closes an issue. Never do this
  automatically; only the user approves kills.
- `bd list --json` — full issue inventory with all fields. Use
  `issue_type` (not `type`) for epic detection.
