# Skill Consolidation Recipe

Step-by-step recipe for converting bundled skill copies (same skill in
2+ profiles) into shared symlinks under `shared-skills/bundled/`.

## Prerequisites

1. Run the classification audit (see `skill-classification.md`) to get
   the full list of bundled skills with their profiles.
2. Run a divergence check — not all copies are identical.
3. Commit-and-push current state first (recovery point).

## Phase 1: Divergence check

For each bundled skill, md5 the SKILL.md across all profiles to find
variants:

```python
import os, hashlib
from collections import defaultdict

root = os.path.expanduser("~/.hermes-teams/startup/profiles")
profiles = ["advisor","architect","base","developer","product-owner",
            "researcher","scout","tech-lead","venture-builder"]

# Key: (category, skill_name) -> {md5: [profiles]}
for cat, skill in bundled_skills:
    variants = defaultdict(list)
    for profile in profiles:
        path = os.path.join(root, profile, "skills", cat, skill, "SKILL.md")
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                md5 = hashlib.md5(f.read()).hexdigest()
            variants[md5].append(profile)
    if len(variants) > 1:
        print(f"DIVERGENT: {cat}/{skill}")
        for md5, plist in variants.items():
            label = "MAJORITY" if len(plist) == max(len(p) for p in variants.values()) else "MINORITY"
            print(f"  [{label}] {md5}  {plist}")
```

## Phase 2: Choose canonical version

For each bundled skill, pick ONE canonical copy to move to
`shared-skills/bundled/`:

- **Majority wins**: if 5+ profiles have identical content and 1-2
  differ, use the majority version. The minority variant was likely a
  local edit or stale version.
- **Newest version wins**: if versions differ (check `version:` in
  YAML frontmatter), use the highest. E.g. `transform` had v2.0.0 on
  most profiles but v2.3.0 on base — base wins.
- **50/50 split**: examine the diff. If one variant has profile-specific
  content (hardcoded paths like `~/.hermes/profiles/scout/scripts/`),
  **skip the skill entirely** — it can't be safely shared as one copy.

## Phase 3: Profile-specific path exception check

Before sharing a skill, check whether any copy contains hardcoded
profile-specific paths that would break on other profiles:

```bash
# Check for profile-specific paths in any copy
grep -r "\.hermes/profiles/" ~/.hermes-teams/startup/profiles/*/skills/<cat>/<skill>/
```

If found, **skip that skill** — leave it as independent copies. The
profile-specific paths make a single shared version impossible without
templating.

Known skills with this problem:
- `research/research-scout` — has `~/.hermes/profiles/scout/scripts/scout-db.py`

## Phase 4: Execute consolidation

```python
import os, shutil

root = os.path.expanduser("~/.hermes-teams/startup/profiles")
bundled_root = os.path.expanduser("~/.hermes-teams/shared-skills/bundled")
os.makedirs(bundled_root, exist_ok=True)

# (category, skill, canonical_profile) — from Phase 2
bundled_skills = [
    ("coordination", "team-delegation", "base"),
    ("meta", "transform", "base"),
    # ... etc
]

for cat, skill, canonical_profile in bundled_skills:
    canonical_path = os.path.join(root, canonical_profile, "skills", cat, skill)
    dst_path = os.path.join(bundled_root, skill)

    # 1. Copy canonical to bundled/
    if not os.path.isdir(dst_path):
        shutil.copytree(canonical_path, dst_path)
        # Ensure writable (canonical may be read-only)
        for dirpath, dirnames, filenames in os.walk(dst_path):
            os.chmod(dirpath, 0o755)
            for f in filenames:
                os.chmod(os.path.join(dirpath, f), 0o644)

    # 2. Replace each profile's copy with a symlink
    for profile in profiles:
        profile_skill_path = os.path.join(root, profile, "skills", cat, skill)
        if not os.path.exists(profile_skill_path) and not os.path.islink(profile_skill_path):
            continue  # profile doesn't have this skill
        if os.path.islink(profile_skill_path):
            if "bundled" in os.readlink(profile_skill_path):
                continue  # already correct
            os.unlink(profile_skill_path)
        elif os.path.isdir(profile_skill_path):
            shutil.rmtree(profile_skill_path)
        # Create relative symlink
        rel = os.path.relpath(dst_path, os.path.dirname(profile_skill_path))
        os.symlink(rel, profile_skill_path)
```

### Pitfall: read-only shared-skill packages

Installed skill packages (e.g. `shared-skills/mattpocock/`) are often
**read-only** (dirs=555, files=444). If you need to modify or remove
files inside them:

```bash
# Fix permissions on the subtree before rm/mv
chmod -R u+w ~/.hermes-teams/shared-skills/mattpocock/find-skills
rm -rf ~/.hermes-teams/shared-skills/mattpocock/find-skills
# Restore parent dir to read-only if needed
chmod 555 ~/.hermes-teams/shared-skills/mattpocock
```

Python's `shutil.move` will fail with PermissionError on read-only dirs.
Always `chmod -R u+w` first, or use terminal `rm -rf` with a preceding
`chmod`.

### Pitfall: misfiled skills in shared packages

Skills from one package can end up inside another package's shared dir
(e.g. `find-skills` — a Hermes bundled skill — was inside
`shared-skills/mattpocock/`). When consolidating, detect misfiles by
comparing against upstream, then move the misfiled skill to the correct
location (`shared-skills/bundled/`) before symlinking.

## Phase 5: Dead symlink cleanup

After consolidation, check for pre-existing broken symlinks:

```python
for profile in profiles:
    skills_dir = os.path.join(root, profile, "skills")
    for dirpath, dirnames, filenames in os.walk(skills_dir):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) and not os.path.exists(os.path.realpath(full)):
                print(f"BROKEN: {full} → {os.readlink(full)}")
```

Remove dead symlinks — they point to source directories that were never
populated or were removed. Common cause: profile setup created symlinks
to `.agents/skills/<name>/` but those source skills were never installed.

## Phase 6: Verify

```python
broken = 0
ok = 0
for profile in profiles:
    skills_dir = os.path.join(root, profile, "skills")
    for dirpath, dirnames, filenames in os.walk(skills_dir):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                if os.path.exists(os.path.realpath(full)):
                    ok += 1
                else:
                    broken += 1
                    print(f"BROKEN: {full}")
print(f"OK: {ok}, Broken: {broken}")
```

All symlinks must resolve before committing.

## Phase 7: Commit and push

```bash
git add -A
git commit -m "refactor: consolidate bundled skills into shared-skills/bundled/ via symlinks"
git push origin main
```

The diff will show large deletions (duplicated content removed) and
symlink additions (mode 120000).
