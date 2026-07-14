# Hermes Cron Layout Map

Captured from a live two-tree install (Hermes + teams-startup). Use this to
navigate quickly without re-discovering the layout each session.

## The two home trees

| Tree | Purpose |
|---|---|
| `~/.hermes/` | default-profile install |
| `~/.hermes-teams/startup/` | teams startup install (mirrors the same structure) |

Both trees have identical internal layout. Scan both or you miss half the profiles.

## File map

```
<home>/
├── cron/                              # RUNTIME STATE ONLY — no job definitions
│   ├── .jobs.lock
│   ├── .tick.lock
│   ├── ticker_heartbeat
│   └── ticker_last_success
├── profiles/
│   └── <profile>/
│       └── cron/
│           ├── jobs.json              # ← THE JOB DEFINITIONS (edit / audit this)
│           ├── jobs.json.<timestamp>  # history snapshots (stale, ignore unless diffing)
│           ├── .discovery-fingerprint # runtime, ignore
│           ├── .jobs.lock / .tick.lock / ticker_*   # runtime state, ignore
│           └── output/
│               └── <job-id>/
│                   └── <YYYY-MM-DD_HH-MM-SS>.md     # per-run transcripts (historical, large)
└── profiles-backup/                   # STALE SNAPSHOTS — not live
    └── <profile>/cron/jobs.json
```

## Observed profiles (your install may differ)

Both trees together held jobs.json for: `product-owner`, `scout`, `tech-lead`,
`venture-builder`, `vault-keeper`, `ops` (teams tree only). Several profiles
also carry non-empty `"skills":` arrays.

## Copy-paste scan script

Audits every job definition across both trees for a set of patterns. Excludes
output logs (historical, large) and prints `file:line: match`.

```bash
PATTERNS='to-spec|to-tickets|to-prd|to-issues|mattpocock-hub'   # ← edit this (old names kept for finding stale refs)
for f in $(find ~/.hermes ~/.hermes-teams \
           -path '*/cron/jobs.json' -type f 2>/dev/null); do
  grep -nE "$PATTERNS" "$f" 2>/dev/null | sed "s|^|$f:|"
done
```

To also catch skill names referenced only in prompt prose (not in a `"skills":`
array), repeat the grep against the full file — that already covers it, since
`grep` is not limited to the skills key.

## Confirming what's live

- Active set: `~/.hermes/profiles/*/cron/jobs.json` and
  `~/.hermes-teams/startup/profiles/*/cron/jobs.json`.
- `~/.hermes/profiles-backup/*/cron/jobs.json` = stale. Useful for "what
  changed", not for editing.
- `jobs.json.<timestamp>` siblings = per-save history. Newest one without a
  suffix is current.
