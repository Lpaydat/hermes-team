---
name: hermes-cron-admin
description: Inspect, audit, and repair Hermes cron jobs and config across the home trees. Use when asked to "scan cron jobs", "audit cron", "find references in cron", "check scheduled jobs", "fix cron config", or when debugging a cron job that isn't firing. Knows where job definitions actually live (per-profile cron/jobs.json), how to separate runtime state from definitions, and how to scan both home trees in one pass.
---

# Hermes Cron Administration

## The layout (read this first)

Hermes has **two parallel home trees** and job definitions do NOT live where you'd guess. Getting this wrong wastes a full exploration loop.

| Thing you want | Where it actually lives |
|---|---|
| **Job definitions** | `<home>/profiles/<profile>/cron/jobs.json` (per-profile, one file each) |
| Runtime state (locks, tickers) | `<home>/cron/` and `<home>/profiles/<profile>/cron/` — `.jobs.lock`, `.tick.lock`, `ticker_heartbeat`, `ticker_last_success` |
| Job run output logs | `<home>/profiles/<profile>/cron/output/<job-id>/<timestamp>.md` |
| Legacy / stale copies | `~/.hermes/profiles-backup/<profile>/cron/jobs.json` plus timestamped `jobs.json.<timestamp>` siblings |

The two home trees:
- `~/.hermes/` — the default-profile install
- `~/.hermes-teams/startup/` — the teams startup install (mirrors the same structure)

**Do not** search `~/.hermes/cron/` or `~/.hermes-teams/startup/cron/` for job definitions — those top-level cron dirs contain ONLY runtime state (locks + ticker files). The definitions are per-profile.

## When to load this skill

- "Scan cron jobs for X" / "audit cron" / "find references in cron"
- A cron job isn't firing or is firing the wrong thing
- You need to rename a skill and must find every cron job that loads it
- Debugging which profiles have which scheduled jobs

## Workflow: audit all cron jobs for a pattern

1. **Find every jobs.json across both trees** (this is the canonical file list — don't enumerate the cron/ dirs):
   ```bash
   find ~/.hermes ~/.hermes-teams -path '*/cron/jobs.json' -type f 2>/dev/null
   ```
2. **Search the definition files** (NOT the output logs, which are huge and historical):
   ```bash
   for f in $(find ~/.hermes ~/.hermes-teams -path '*/cron/jobs.json' -type f 2>/dev/null); do
       grep -nE 'pattern-one|pattern-two' "$f" | sed "s|^|$f:|"
   done
   ```
3. **Skill-name references** appear in two places inside each job object:
   - `"skills": ["skill-a", "skill-b"]` — the explicit skills array the job loads
   - free text inside `"prompt"` — prose like "load the X skill" that doesn't show up in the skills array
   - Grep for the bare skill name, not just the `skills:` key, or you'll miss prose references.
4. **Distinguish active vs stale**: `~/.hermes/profiles-backup/` holds old snapshots. Anything there is not live. The active set is `~/.hermes/profiles/*/cron/jobs.json` and `~/.hermes-teams/startup/profiles/*/cron/jobs.json`.
5. Report with `file:line: matching text` for every hit. State explicitly when a tree had no matches.

## Editing cron jobs

Cron jobs are also editable via `hermes cron` CLI commands, which write `jobs.json` atomically and update the discovery fingerprint. Prefer the CLI over hand-editing `jobs.json` when the change is structural (add/remove/rename a job or its skills array). Hand-edit only for in-prompt text changes.

See `references/cron-layout.md` for the full directory map and a copy-paste scan script.

## Pitfalls

- **Searching the wrong dir.** `~/.hermes/cron/` looks like it should hold jobs. It doesn't. Definitions are per-profile under `profiles/<profile>/cron/jobs.json`.
- **Forgetting the second home tree.** `~/.hermes-teams/startup/` mirrors `~/.hermes/`. An audit that only scans one tree misses half the profiles. Always scan both.
- **Treating `profiles-backup/` as live.** Those are stale snapshots (note the `jobs.json.<timestamp>` history siblings). They're useful for seeing what changed, not for editing.
- **Grepping only the `skills:` key.** Skill names embedded in prompt prose ("load the X skill and follow it") won't match `grep skills`. Match the bare skill name.
- **Searching output logs.** `cron/output/**/*.md` files are historical run transcripts and can be enormous. Exclude them from pattern searches unless you specifically want run history.
