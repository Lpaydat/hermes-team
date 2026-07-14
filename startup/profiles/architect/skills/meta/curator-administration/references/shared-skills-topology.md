# Shared Skills Topology Audit

The Hermes skill library uses a hybrid topology: some skill packages are
**shared via symlinks** (single source of truth), while others are
**independent per-profile copies**. This file documents how to determine
which is which and what the implications are.

## Directory layout

`~/.hermes/` and `~/.hermes-teams/startup/` are the **same tree** (one is
symlinked/mounted to the other). Profile data lives at:

```
~/.hermes-teams/startup/profiles/<profile>/skills/<category>/<skill-name>/
```

Shared skill packages live in two locations:

```
~/.hermes-teams/shared-skills/        ← mattpocock, ponytail-hub, caveman, wayfinding-auto
~/.hermes-teams/.agents/skills/       ← advisor's business skills, beads
```

## Detecting symlinks vs copies

### Category-level (quick check)

```bash
# List symlinked categories for a profile
find ~/.hermes/profiles/<profile>/skills/ -maxdepth 1 -type l \
  -exec basename {} \;
```

### All profiles at once

```bash
for profile in $(hermes profile list | awk 'NR>1{print $1}'); do
  dir=~/.hermes/profiles/$profile/skills
  [ -d "$dir" ] || continue
  symlinks=$(find "$dir" -maxdepth 1 -type l -exec basename {} \; 2>/dev/null)
  if [ -n "$symlinks" ]; then
    echo "$profile: $symlinks"
  else
    echo "$profile: (no symlinks)"
  fi
done
```

### Resolving where a symlink points

```bash
readlink -f ~/.hermes/profiles/<profile>/skills/mattpocock
# → /home/lpaydat/.hermes-teams/shared-skills/mattpocock
```

### Verifying content is identical across profiles

```bash
# Same md5 = shared source (same physical file via symlink)
for profile in base developer tech-lead; do
  md5sum ~/.hermes/profiles/$profile/skills/mattpocock/codebase-design/SKILL.md
done
```

## Counting: shared vs independent

A proper count must detect category-level symlinks and classify ALL skills
under them as shared. Skills under real (non-symlink) categories are
independent copies unless individually symlinked.

```bash
shared=0; independent=0
for profile in advisor architect base developer product-owner \
               researcher scout tech-lead venture-builder; do
  skills_dir=~/.hermes-teams/startup/profiles/$profile/skills
  while IFS= read -r cat_name; do
    cat_path="$skills_dir/$cat_name"
    [ -d "$cat_path" ] || continue
    if [ -L "$cat_path" ]; then
      # Category is symlinked → all skills under it are shared
      shared=$((shared + $(find "$cat_path" -mindepth 1 -maxdepth 1 -type d | wc -l)))
    else
      independent=$((independent + $(find "$cat_path" -mindepth 1 -maxdepth 1 -type d | wc -l)))
    fi
  done < <(ls -1 "$skills_dir" 2>/dev/null | grep -v '^\.hub$')
done
echo "Shared: $shared"
echo "Independent: $independent"
```

## Implications

### For pinning
Pinning works per-profile regardless of topology. Curator state
(`.curator_state`) is tracked in each profile independently. Pinning a
symlinked skill on one profile does NOT pin it on others — you still need
to pin it on each profile.

### For patching (IMPORTANT)
- **Symlinked skill**: `patch` on ANY profile → change appears on ALL
  profiles that share the symlink. One edit, global propagation.
- **Independent copy**: `patch` only affects that one profile. To update
  the same skill across profiles, you must patch each copy individually.

### For the curator
The curator operates per-profile. Consolidation/demotion decisions are
made independently per profile. A skill that's stale on one profile but
active on another will be handled differently by each profile's curator.

## Known shared packages

As of the last audit (2026-07-11, post-consolidation):

| Package | Source | Profiles |
|---------|--------|----------|
| `mattpocock` (38 skills) | `shared-skills/mattpocock/` | all 9 profiles |
| `ponytail` (1 skill, 6 sub-skills) | `shared-skills/ponytail-hub/` | 8 profiles (not architect) |
| `caveman` | `shared-skills/caveman/` | architect, developer, tech-lead |
| `wayfinding-auto` | `shared-skills/wayfinding-auto/` | product-owner, tech-lead |
| `bundled` (21 skills) | `shared-skills/bundled/` | varies per skill (2–8 profiles each) |

### `shared-skills/bundled/` contents (post-consolidation)

Each skill below lives once in `shared-skills/bundled/<name>/` and is
symlinked from each profile that previously had an independent copy:

| Skill | Profiles | Canonical source |
|-------|----------|-----------------|
| `claude-code`, `codex`, `opencode` | 7 each | base |
| `team-delegation`, `find-skills`, `transform` | 8 each | base (transform: v2.3.0 newest) |
| `obsidian` | 6 | base |
| `hermes-agent-skill-authoring` | 6 | base |
| `arxiv`, `blogwatcher`, `xurl` | 3 each | researcher |
| `9arm-skills`, `codegraph` | 2 each | product-owner |
| `bundled-skills-opt-out` | 3 | developer |
| `messaging-delivery`, `youtube-content` | 2 each | researcher |
| `deep-research`, `llm-wiki` | 2 each | researcher |
| `evaluation`, `inference`, `models` | 2 each | advisor |

**Not consolidated** (left as independent copies due to profile-specific paths):
- `research-scout` — has `~/.hermes/profiles/scout/scripts/scout-db.py` hardcoded

**Removed from advisor** (dead symlinks, source never existed):
- `competitive-analysis`, `fundraising`, `lean-startup`, `startup-financial-modeling`, `startup-ideation`, `startup-metrics-framework`

This list should be re-verified with the detection commands above if the
shared-skills directory changes.

## Cross-profile references to deprecated skills

When cleaning up deprecated skills from ONE profile, these are known
references in OTHER profiles that keep the skill active in the shared dir:

| Deprecated skill | Referenced by | File | Context |
|-----------------|---------------|------|---------|
| `ubiquitous-language` | tech-lead | `SOUL.md` line 25 | Identity prompt: "produce a domain glossary (`ubiquitous-language`)" |
| `ubiquitous-language` | tech-lead | `loops-engineering/SKILL.md` line 47 | Workflow: "Artifacts: glossary (`ubiquitous-language`)" |
| `request-refactor-plan` | tech-lead | `loops-engineering/SKILL.md` line 169 | Workflow: "file a tech-debt issue (`request-refactor-plan`)" |

These references mean the skills CANNOT be removed from the shared
`mattpocock/` dir or disabled on tech-lead without first updating the
referencing prompts. The architect profile disabled them locally only;
they remain enabled on tech-lead, advisor, product-owner, and ops.
