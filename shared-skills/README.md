# Shared Skills

Centralized skill repositories shared across all Hermes profiles via symlinks.
**One source of truth — update once, all profiles get it.**

## Structure

```
shared-skills/
├── mattpocock/          ← git clone of github.com/mattpocock/skills
│   └── skills/
│       ├── engineering/     (to-prd, to-issues, tdd, implement, etc.)
│       ├── productivity/    (grilling, grill-me, handoff, etc.)
│       ├── misc/            (git-guardrails, setup-pre-commit, etc.)
│       ├── personal/        (edit-article, obsidian-vault)
│       ├── in-progress/     (drafts — wizard, loop-me, etc.)
│       └── deprecated/      (design-an-interface, qa, etc.)
├── mattpocock-hub/      ← Hermes-compatible symlink structure
│   ├── engineering -> ../mattpocock/skills/engineering
│   ├── productivity -> ../mattpocock/skills/productivity
│   └── ...
├── ponytail/            ← git clone of github.com/DietrichGebert/ponytail
│   └── skills/
│       ├── ponytail/
│       ├── ponytail-audit/
│       └── ...
└── ponytail-hub/        ← Hermes-compatible symlink structure
    └── ponytail -> ../ponytail/skills
```

## How profiles connect

Each profile has two symlinks:
```
profiles/<name>/skills/mattpocock -> ../../../../shared-skills/mattpocock-hub
profiles/<name>/skills/ponytail   -> ../../../../shared-skills/ponytail-hub
```

## Updating

```bash
cd ~/.hermes-teams/shared-skills/mattpocock && git pull
cd ~/.hermes-teams/shared-skills/ponytail && git pull
# All profiles immediately see the update — no per-profile work needed
```

## Read-only protection

All files in `shared-skills/` are **read-only** (`chmod a-w`). Hermes' skill
curator cannot modify them. If a profile needs to customize a skill:

1. Copy the skill to the profile's own skills directory:
   ```bash
   cp -r ~/.hermes-teams/shared-skills/mattpocock/skills/engineering/to-prd \
     ~/.hermes-teams/startup/profiles/<profile>/skills/custom/to-prd
   ```
2. Remove the symlink for that category (or the specific skill)
3. The profile-local copy can evolve freely via Hermes' curator

## Upstream changes tracked

### Mattpocock v1.0.0+ (2026-07-05)
- `diagnose` → `diagnosing-bugs` (renamed)
- `write-a-skill` → `writing-great-skills` (renamed)
- `caveman`, `zoom-out` → REMOVED
- `design-an-interface`, `qa`, `request-refactor-plan`, `ubiquitous-language` → deprecated
- NEW: `code-review`, `research` (engineering)
- NEW: `domain-modeling` (absorbs `decision-mapping` + `ubiquitous-language`)
- NEW: `codebase-design` (shared vocabulary extracted from `improve-codebase-architecture`)

### Ponytail (2026-07-05)
- 6 skills: ponytail, ponytail-audit, ponytail-debt, ponytail-gain, ponytail-help, ponytail-review
