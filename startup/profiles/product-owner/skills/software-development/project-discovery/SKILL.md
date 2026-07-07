---
name: project-discovery
description: "Scan a project for work signals and gaps. Use when running the discovery cron, when asked to audit a project, when looking for what to build next, when the user says 'what should we work on', 'audit this project', 'scan for issues', 'what's missing', or 'propose next sprint'. Mention 'discovery', 'audit', 'project health', 'gaps'."
---

# Project Discovery

Scan a project to find what's missing, broken, or misaligned with the goal. Run this on each active project during the discovery cron cycle.

## Step 0: Early exit check (cheap, before any token-heavy work)

For each project, do this FIRST:

1. Does `.driver/` exist? If NO → see **Auto-init** below, then proceed to full scan.
2. If YES → run these zero-cost checks:
   - `git log --oneline --since="4 hours ago" | wc -l` — any new commits?
   - `bd list --json | python3 -c "import sys,json; old=open('.driver/progress.md').read(); now=json.load(sys.stdin); print('yes' if len([t for t in now if t['status'] not in ('closed','done')]) else 'no')"` — new issues since last scan?
3. If NO commits AND no new issues → **skip**. No output. Done.

This early exit costs ~0 tokens. Most runs hit it → silent.

### Auto-init (first run, `.driver/` doesn't exist)

If `.driver/` is missing, create it automatically — no interview needed. Read from the project directly, **in priority order of richness**:

1. **Read `AGENTS.md`** — **RICHESHEST source**. Often contains project purpose, conventions, architecture rules, product context, safety rules, and integration notes. Some projects have 30k+ chars of product context here that isn't in the README. Read this BEFORE the README.
2. **Read `README.md`** — what the project says about itself, badges/tech stack, user-facing description.
3. **Read `CONTEXT.md`** — domain glossary (if exists).
4. **Scan existing docs**: `docs/prd/` (or `docs/prd-*.md`), `docs/adr/` — design decisions, planned features, architecture decisions. These carry the design intent that goals should trace to.
5. **Scan beads**: `bd list --json` — all existing issues. Closed = done, open = pending. Epics (`issue_type: "epic"`) reveal the project's major work areas.
6. **Check `git remote -v`** — detect shared databases (worktrees/clones of the same repo share beads). Don't auto-init `.driver/` in duplicates; only the primary copy.

Then synthesize a proposed goal.md:

```markdown
# <Project> — Goal

**Vision** — extracted from AGENTS.md / README

**Success criteria** — implicit from PRDs or inferred from issues

**In scope** — from existing work items and ADRs

**Out of scope** — if mentioned anywhere; leave blank if unknown

> *(Auto-generated from project analysis on <date>. Adjust as needed.)*
```

Write this to `.driver/goal.md`. Also create:
- `.driver/progress.md` — what's done (closed beads), in progress (open beads), next (ready beads)
- `.driver/decisions.md` — existing ADRs summarized
- `.driver/gaps.md` — empty (first run)

**Done when**: `.driver/` exists with all 4 files. Then proceed to full scan.

## Step 1: Read steering state

Read `.driver/goal.md`, `.driver/progress.md`, `.driver/decisions.md`, `.driver/gaps.md`.

**Done when**: you can state the project's goal, current progress, and known gaps in 3 sentences.

## Step 2: Scan for signals

Run these checks. Record findings to `$TMP_DIR/findings.json`.

- **Failing tests**: run the project's test command. Count failures.
- **TODO/FIXME density**: `grep -rn "TODO\|FIXME\|HACK\|XXX" src/ --include="*.*" | wc -l`. Flag if >20 per 1k lines.
- **Stale PRs/branches**: `gh pr list --state open` + `git branch --merged | grep -v main`. Flag PRs open >7 days.
- **Tech debt**: if `ponytail-audit` is available, run it. Record top 5 findings.
- **Docs staleness**: if CodeGraph is configured, run `codegraph_find_stale_docs`. Otherwise, check if README/AGENTS.md last modified before recent code changes.
- **Git velocity**: `git log --oneline --since="7 days ago" | wc -l`. Compare to previous week.

**Done when**: every signal checked, findings recorded.

## Step 3: Cross-reference design vs implementation

- Read recent git log: `git log --oneline -20`
- Read tech-lead journal: `~/vault/journal/<project>/` (latest entry)
- Compare against PRD (`docs/prd-*.md`) and ADRs (`docs/adr/`)

Check: Is the implementation following the design? Has it evolved past the design (update docs)? Has it diverged (flag to user)?

**Done when**: you can state whether implementation aligns with design, with evidence.

## Step 4: Check beads for duplicates

Before filing any new issue:
```bash
bd list --json  # All issues, all statuses
```
Build a set of existing issue titles/IDs. Never file a duplicate.

**Done when**: you have the complete existing issue inventory.

## Step 5: File issues + update state

For each finding that warrants action:
- **Concrete problem** (failing test, bug, missing feature from goal) → `bd create` with type, priority, and description
- **Decision needed** → add to `.driver/decisions.md` under "Open Questions" + create a kanban task on `hermes-hq` board with `[general]` tag and `--assignee default` (surfaces to user)
- **Tech debt** → `bd create -t chore` with ponytail/improve-codebase-architecture finding

When creating kanban tasks for specialist routing:
```bash
kanban_create(title="[<project-tag>] <short description>", assignee="<specialist-profile>")
```
**Tagging convention:** Every kanban task title MUST start with a project tag in brackets:
- `[pir]` — traces to pir's beads DB
- `[pi-subagents]` — traces to pi-subagents' beads DB
- `[general]` — cross-project, infrastructure, or no specific project

**Never create an untagged task.** If you can't determine the project, use `[general]`.

Then **rewrite** `.driver/progress.md` and `.driver/gaps.md` as snapshots:
- `progress.md`: what's done (closed beads), what's in progress (open beads), what's next (ready beads)
- `gaps.md`: top 5 gaps between current state and goal, ranked by impact

**Done when**: all findings filed or triaged, steering state updated, no duplicates created.

## Related skill: task-hygiene-validator

After initial discovery, ongoing task quality is enforced by `task-hygiene-validator` (auto-defers stale issues, flags orphans and kill-candidates). Run discovery first to establish `.driver/goal.md`, then the hygiene validator can check goal-traceability.

## Related references

- `references/visual-and-notification-routing.md` — how to set up Beadbox (native GUI for beads) and configure multi-profile gateway routing (Telegram vs Discord, channel-based routing, the "company in Discord" pattern)

## User preference: automation over manual triage

This user does NOT want to handle tasks one-by-one. Whenever proposing a solution for backlog management, task validation, or triage:

- **Prefer automated loops (cron jobs) over manual processes.** Build self-running systems that act at proper intervals with proper conditions.
- **Auto-take reversible actions** (defer stale items, auto-tag traceable orphans) — don't ask for approval on safe operations.
- **Batch irreversible decisions** (closing issues, killing tasks) for one-click approval, never one-by-one.
- **Only notify the user when a decision is needed.** Silent when clean.

## Active projects list (CRITICAL — the gate that prevents scanning wrong projects)

Discovery must **only scan projects listed in `active-projects.json`**. This file
is the explicit gatekeeper — if the list is empty, discovery does NOT run.

```json
{
  "active_projects": [
    {"path": "/home/user/workspace/my-app", "name": "my-app"}
  ],
  "paused_projects": [],
  "note": "Manual override. The discovery guard script reads this file — empty list = no scan."
}
```

Location: `~/.hermes/profiles/<profile>/config/active-projects.json`

The discovery guard script (`scripts/discovery-guard.sh`) reads this file BEFORE
waking the agent. If `active_projects` is empty → `{"wakeAgent": false}` → zero
tokens, zero scan. This is by design.

**Why this exists**: during workflow testing (Jul 2026), the guard script used
`find ~ -name .beads` to scan ALL projects dynamically. It found a real project
(`taskboard`) and autonomously created a kanban card for unpushed security fixes —
polluting the test board with real project work. The user was confused why an
agent was touching their real project without permission.

**The rule**: never use `find` to discover projects. Always read from the
active-projects list. The list is the user's explicit consent to scan.

### Cross-profile scope

When the user says "make everything X" or "clean all Y", they mean
**every profile**, not just the one you're running under. When the scope
is "all profiles", scan ALL of:

- `~/.hermes/profiles/*/skills/`
- `~/.hermes/profiles/*/config/`
- `~/.hermes/profiles/*/memories/`
- `~/.hermes/skills/` (shared/global)
- `~/.hermes/cron/`
- `~/.hermes/memories/`

Do NOT clean only the current profile and assume the others are fine.
**Session dump files** (`request_dump_*.json`) are immutable API logs
and can be skipped — they don't influence future behavior.

### When a project is deleted

1. Close all open issues with a clear reason
2. Remove from `active-projects.json`
3. Remove the `.beads/` directory
4. Remove the `.driver/` directory
5. Delete any Discord channel for the project

### When a project is added

Add it to `active-projects.json`. The next discovery cron tick will pick it up.
The goal bootstrapper will auto-init `.driver/`.

## Output

Deliver to user via the configured gateway (Telegram or Discord):
- Project health summary (green/yellow/red per signal)
- New issues filed (if any)
- Open decisions needing user input (if any)
- Proposed next priorities (ranked, for approval)
- Auto-init note (if this was a first run: "I created a proposed goal for project X from project analysis — review and adjust.")
