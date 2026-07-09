# Root-cause tracing: bundled-skills regression

## Symptom

After `hermes update` to 0.18.0, cloning from `base` re-seeded bundled
skills (dogfood, polymarket, etc.) into the new profile despite both base
and prior clones having `.no-bundled-skills` opt-out markers.

## How the root cause was found

### 1. Don't trust the marker — verify the sync path reads it

The `.no-bundled-skills` marker existed in base and advisor. The assumption
was "marker present → no seeding." Wrong. The key question is: **does the
code path that actually fires check THIS marker in THIS location?**

```bash
# What sync_skills() actually checks at runtime
cd ~/.hermes/hermes-agent && python3 -c "
import os
os.environ.pop('HERMES_HOME', None)  # simulate the global context
from hermes_constants import get_hermes_home
home = get_hermes_home()
print(f'HERMES_HOME: {home}')
print(f'marker exists: {(home / \".no-bundled-skills\").exists()}')
"
```

Result: `HERMES_HOME` resolves to `~/.hermes` (the platform default), and
there was **no marker there** — only inside `~/.hermes/profiles/*/`.

### 2. Trace the two sync paths separately

Hermes has **two independent** bundled-skill sync code paths, and they check
different markers:

| Path | Code | Called by | Marker checked |
|------|------|-----------|----------------|
| Global | `sync_skills()` in `tools/skills_sync.py:483` | `hermes update`, installer | `~/.hermes/.no-bundled-skills` |
| Per-profile | `seed_profile_skills()` in `hermes_cli/profiles.py:1163` | profile create, update loop | `<profile_dir>/.no-bundled-skills` |

The global path's marker check is at `skills_sync.py:496`:
```python
if (HERMES_HOME / NO_BUNDLED_SKILLS_MARKER).exists():
    return { "skipped_opt_out": True, ... }
```

`HERMES_HOME` is resolved at module load time (`skills_sync.py:39`):
```python
HERMES_HOME = get_hermes_home()  # → ~/.hermes when no env override
```

### 3. Trace the clone path

`hermes profile create --clone` (`profiles.py:1056-1079`):
1. Copies `_CLONE_CONFIG_FILES` = `["config.yaml", ".env", "SOUL.md"]` — **`.no-bundled-skills` is NOT in this list**
2. Copies `source_dir/skills/` via `shutil.copytree(..., dirs_exist_ok=True)` — this copies whatever the source has, including pollution
3. Does NOT call `seed_profile_skills()` for clones (main.py:10938: `if not (clone_config or clone_all)`)

So the clone inherits the source's (polluted) skills dir, gets no marker,
and the next `hermes update` loop seeds it fully.

### 4. Timestamp forensics confirmed the sequence

```bash
stat -c '%y' <profile>/.no-bundled-skills        # marker written 20:31
stat -c '%y' <profile>/skills/.bundled_manifest   # manifest written 20:07
```

Marker written 24 minutes after seeding happened — added manually after
noticing the pollution, not before.

## The fix (durable, not code)

1. Write `~/.hermes/.no-bundled-skills` — the global marker that was always missing.
2. Clean existing pollution via `HERMES_HOME=<dir> hermes skills opt-out --remove --yes`.
3. Run `scripts/fix-bundled-skills-opt-out.sh` after any update, clone, or migration.

A code patch to `profiles.py` (adding `.no-bundled-skills` to
`_CLONE_CONFIG_FILES`) would fix the clone path but gets clobbered by
`hermes update`. The marker is profile data — it survives updates.

## Generalizable technique

When "opt-out isn't working" for any Hermes feature:
1. Find the code path that performs the action you want suppressed.
2. Check what **path** it resolves the marker/opt-out file from at runtime
   (not what you assume — trace `get_hermes_home()` / `HERMES_HOME`).
3. Check whether that path is the same one where your marker lives.
4. Use timestamp forensics (`stat -c %y`) to reconstruct the event sequence.
