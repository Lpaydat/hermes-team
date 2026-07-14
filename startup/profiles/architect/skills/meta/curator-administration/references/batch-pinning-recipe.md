# Batch Pinning Recipe

Copy-paste-ready pattern for pinning all skills across all registered
profiles. Handles ghost profiles, profiles with no skills, and idempotent
re-pinning.

## Step 1: Get registered profiles

```bash
hermes profile list
```

Parse the profile names from the table output. This is the authoritative
list — do NOT use `ls ~/.hermes/profiles/`.

## Step 2: Enumerate skills per profile

```bash
find ~/.hermes/profiles/<profile>/skills/ -mindepth 2 -maxdepth 2 -type d \
  | grep -v '/.hub/' \
  | sed 's|.*/skills/||' \
  | sort
```

- `-mindepth 2 -maxdepth 2` gets `category/skill-name` level only
- `grep -v '/.hub/'` excludes index-cache and quarantine
- Leaf directory name (after last `/`) is the skill name for `curator pin`

## Step 3: Batch pin

Using execute_code (Python) for reliability and result tracking:

```python
import os, subprocess, json

profiles = [
    "advisor", "architect", "base", "developer", "product-owner",
    "researcher", "scout", "tech-lead", "venture-builder"
    # Add/remove based on `hermes profile list` output
]

profiles_root = os.path.expanduser("~/.hermes/profiles")
pinned = 0
already = 0
failed = 0
errors = []

for profile in profiles:
    skills_dir = os.path.join(profiles_root, profile, "skills")
    if not os.path.isdir(skills_dir):
        print(f"✓ {profile}: no skills dir, skipping")
        continue

    # Collect skill names at depth 2, excluding .hub
    skill_names = set()
    for root, dirs, files in os.walk(skills_dir):
        rel = os.path.relpath(root, skills_dir)
        depth = rel.count(os.sep) if rel != "." else 0
        if depth == 1:
            parts = rel.split(os.sep)
            if parts[0] == ".hub":
                continue
            skill_names.add(parts[1])

    for skill in sorted(skill_names):
        cmd = ["hermes", "-p", profile, "curator", "pin", skill]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = result.stdout.strip() + result.stderr.strip()
        if result.returncode == 0:
            if "already pinned" in out.lower():
                already += 1
            else:
                pinned += 1
        else:
            failed += 1
            errors.append(f"{profile}/{skill}: {out}")

    print(f"✓ {profile}: {len(skill_names)} skills processed")

print(f"\nNewly pinned: {pinned}")
print(f"Already pinned: {already}")
print(f"Failed: {failed}")
if errors:
    for e in errors:
        print(f"  ✗ {e}")
```

## Step 4: Verify

```bash
hermes -p <profile> curator status
```

Check for `pinned (N):` in the output. Remember: installed (non-agent-created)
skills won't appear in the count but ARE pinned.

## Common failure: ghost profiles

If you see:
```
Error: Profile '<name>' does not exist.
```

That directory is a leftover — the profile was renamed, deleted, or never
properly created. Remove it from your profile list and skip. Do NOT try to
`hermes profile create` it unless the user asks for it back.
