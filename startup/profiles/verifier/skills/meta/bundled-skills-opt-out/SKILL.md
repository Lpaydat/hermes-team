---
name: bundled-skills-opt-out
description: Prevents the recurring regression where Hermes re-seeds bundled skills (dogfood, polymarket, etc.) into profiles despite opt-out markers. Use when bundled skills reappear after an update, clone, or profile import, or when setting up a fresh machine.
disable-model-invocation: true
---

# Bundled-skills opt-out regression fix

## The bug

Hermes has **two** bundled-skill sync paths:

1. **Global** — `sync_skills()` in `tools/skills_sync.py`, called by `hermes update` and the installer. Checks `~/.hermes/.no-bundled-skills`.
2. **Per-profile** — `seed_profile_skills()` in `hermes_cli/profiles.py`, called during profile creation and the update all-profile loop. Checks `<profile_dir>/.no-bundled-skills`.

The regression: the global `~/.hermes/` dir typically has **no marker** (only named profiles under `~/.hermes/profiles/` get one via `hermes skills opt-out`). So `sync_skills()` re-seeds the full bundled catalog into `~/.hermes/skills/` on every update. Then `--clone` from default copies that polluted skills dir into a new profile *before* any per-profile marker can protect it.

## The fix

Run the restoration script (lives at `~/.hermes/profiles/base/scripts/fix-bundled-skills-opt-out.sh`):

```bash
bash ~/.hermes/profiles/base/scripts/fix-bundled-skills-opt-out.sh
```

This script:
1. Writes the global marker at `~/.hermes/.no-bundled-skills` (the critical missing piece)
2. Ensures every named profile has its per-profile marker
3. Cleans manifest-tracked bundled skills from the global dir and each profile
4. Verifies the result

**Idempotent** — safe to re-run. User-installed and hub skills are never touched (the official `hermes skills opt-out --remove --yes` only removes manifest-tracked + unmodified skills).

## Prevention at create time (added 2026-07-03)

Three layers keep clones clean going forward:

1. **Always pass `--no-skills` when cloning** an opted-out profile:
   `hermes profile create <name> --clone-from <src> --no-skills`
   The clone still copies the source's curated skills/ dir; `--no-skills` writes
   the marker at create time so the post-create seeding no-ops. This is the
   upstream-supported path and needs no patches.
2. **Local patch in `hermes_cli/profiles.py`** (create_profile, clone branch):
   the clone now inherits the source profile's `.no-bundled-skills` marker
   automatically. NOTE: `hermes update` pulls upstream code and may drop this
   patch — re-verify after every update (`grep -n 'LOCAL PATCH' ~/.hermes/hermes-agent/hermes_cli/profiles.py`),
   and prefer layer 1 regardless.
3. **Post-create check**: `ls <profile>/skills/` — if `apple/` or `creative/`
   appeared, seeding fired; run this skill's fix script, then remove pristine
   manifest-tracked skills (compare on-disk `_dir_hash` against
   `skills/.bundled_manifest` origin hashes — the CLI's `opt-out --remove` can
   miss profile-scoped manifests, see #18594-adjacent HERMES_HOME caching).

## When to run

- After `hermes update` if bundled skills reappear
- After cloning a profile from default
- After importing a profile on a new machine
- As part of initial setup on a fresh install

## Portability

The script is profile data (not code), so it:
- **Survives `hermes update`** — update pulls upstream code but doesn't touch profile dirs
- **Travels with `hermes profile export`** — the script lives under `scripts/` which is included in exports
- **Works on any machine** — resolves `HERMES_HOME` dynamically, falls back to `~/.hermes`

## Manual commands (if the script isn't available)

```bash
# Write the global marker (the key fix)
echo "opted out" > ~/.hermes/.no-bundled-skills

# Clean a specific profile
HERMES_HOME=~/.hermes/profiles/<name> hermes skills opt-out --remove --yes

# Clean the global dir
HERMES_HOME=~/.hermes hermes skills opt-out --remove --yes
```

## Why the code fix isn't enough

A code edit to `profiles.py` (adding `.no-bundled-skills` to `_CLONE_CONFIG_FILES`) would fix the clone path but gets **clobbered by `hermes update`**. The marker-based fix is durable because it lives in profile data, not code.
