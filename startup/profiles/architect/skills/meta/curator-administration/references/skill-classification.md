# Skill Classification Audit

Script to classify every skill across all profiles into three categories:
shared (symlinked), bundled (independent copy in 2+ profiles), or
profile-specific (independent copy in 1 profile only).

## Python audit script

```python
import os

root = os.path.expanduser("~/.hermes-teams/startup/profiles")
# Always get profiles from `hermes profile list` — this list is for reference
profiles = [
    "advisor", "architect", "base", "developer", "product-owner",
    "researcher", "scout", "tech-lead", "venture-builder",
]

# Phase 1: walk every profile's skills, classify each category as
# symlink (shared) or real dir, collect independent skill names.

independent = {}       # profile -> [(category, skill_name)]
name_profiles = {}     # skill_name -> [profiles where it's independent]

for profile in profiles:
    skills_dir = os.path.join(root, profile, "skills")
    independent[profile] = []
    if not os.path.isdir(skills_dir):
        continue
    for cat in sorted(os.listdir(skills_dir)):
        cat_path = os.path.join(skills_dir, cat)
        if cat.startswith('.') or not os.path.isdir(cat_path) or os.path.islink(cat_path):
            continue  # skip .hub, non-dirs, and symlinked categories
        for skill in sorted(os.listdir(cat_path)):
            skill_path = os.path.join(cat_path, skill)
            if not os.path.isdir(skill_path) or os.path.islink(skill_path):
                continue
            independent[profile].append((cat, skill))
            name_profiles.setdefault(skill, []).append(profile)

# Phase 2: classify into bundled (2+ profiles) vs profile-specific (1).

bundled = {}       # skill_name -> [profiles]
profile_specific = {}  # skill_name -> profile

for name, plist in sorted(name_profiles.items()):
    if len(plist) == 1:
        profile_specific[name] = plist[0]
    else:
        bundled[name] = sorted(plist)

print(f"Bundled (copied to 2+ profiles): {len(bundled)} unique skills")
for name, plist in sorted(bundled.items()):
    print(f"  {name:40s} [{len(plist)}] → {', '.join(plist)}")

print(f"\nProfile-specific (1 profile only): {len(profile_specific)}")
for name, profile in sorted(profile_specific.items(), key=lambda x: (x[1], x[0])):
    print(f"  {profile:20s} → {name}")
```

## What each category means for operations

### Bundled skills → consolidation candidates
These are the same skill copied to multiple profiles. They drift apart
when patched independently. To consolidate: move one canonical copy to
`shared-skills/<name>/`, then replace each profile's real dir with a
symlink pointing there.

### Profile-specific skills → leave alone
These are unique to each profile (doctrine, tool integrations, agent-
created). They should NOT be symlinked — they're meant to diverge.

### Shared skills → no action needed
Already symlinked. Patching one propagates to all profiles. Pinning
still works per-profile independently.

## Detecting the shared (symlinked) set separately

```bash
for profile in $(hermes profile list | awk 'NR>1{print $1}'); do
  dir=~/.hermes/profiles/$profile/skills
  [ -d "$dir" ] || continue
  find "$dir" -maxdepth 1 -type l -exec basename {} \; 2>/dev/null \
    | while read cat; do
        echo "$profile/$cat → $(readlink -f "$dir/$cat")"
      done
done
```
