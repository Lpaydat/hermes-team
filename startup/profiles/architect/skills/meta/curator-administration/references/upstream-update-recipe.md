# Upstream Skill Update Recipe

How to update installed shared-skill packages (mattpocock, ponytail,
caveman, etc.) to their latest upstream versions — **without running
the official installers**.

## Why not run the installer?

Both Matt Pocock and Ponytail ship install scripts that target:

- `~/.claude/skills/`
- `~/.agents/skills/`
- `~/.hermes/skills/` (Hermes adapter)

In a shared-symlink topology (`~/.hermes-teams/shared-skills/`), running
the installer would:
1. Put copies in the wrong location (not the shared dir).
2. Bypass the symlink structure entirely.
3. Not reach any profile — profiles point at `shared-skills/`, not at
   `~/.hermes/skills/`.

**Always update in-place** inside `shared-skills/<package>/`.

## Determine the update method

Shared-skill packages live in `~/.hermes-teams/shared-skills/`. There
are two shapes:

### Shape A: Git clone (e.g. ponytail)

The package directory is itself a git repo with an upstream remote:

```bash
cd ~/.hermes-teams/shared-skills/ponytail
git remote -v
# origin  git@github.com:DietrichGebert/ponytail.git
```

**Update method:** `git pull`

```bash
cd ~/.hermes-teams/shared-skills/ponytail

# Read-only files (555/444) — need write for the pull
chmod -R u+w .

git pull origin main

# Restore read-only after pull
chmod -R a-w .
chmod u+w .git  # keep .git manageable for future pulls
```

### Shape B: Static copy in the team repo (e.g. mattpocock)

The package directory is tracked inside `~/.hermes-teams/` (hermes-team
repo), NOT a separate clone. It has no upstream remote:

```bash
cd ~/.hermes-teams/shared-skills/mattpocock
git remote -v
# origin  git@github.com:Lpaydat/hermes-team.git  (← the team repo, not upstream!)
```

**Update method:** fetch individual stale skills from the upstream repo
via `gh api`.

## Identifying stale skills (Shape B)

### Step 1: Get the upstream skill list

```bash
# List categories
gh api repos/mattpocock/skills/contents/skills --jq '.[].name'

# List skills per category
for cat in engineering productivity in-progress misc personal deprecated; do
  echo "=== $cat ==="
  gh api repos/mattpocock/skills/contents/skills/$cat --jq '.[].name'
done

# Cross-check: plugin.json has the officially promoted skills
gh api repos/mattpocock/skills/contents/.claude-plugin/plugin.json \
  --jq '.content' | base64 -d
```

### Step 2: Compare content (md5 each SKILL.md)

```python
import os, subprocess, base64, hashlib

mattpocock_dir = os.path.expanduser("~/.hermes-teams/shared-skills/mattpocock")

# Build upstream category map from the API (or hardcode from step 1)
upstream_categories = {
    "engineering": ["ask-matt", "code-review", ...],
    "productivity": ["grill-me", "grilling", ...],
    # ...
}

for skill_dir in sorted(os.listdir(mattpocock_dir)):
    local_path = os.path.join(mattpocock_dir, skill_dir, "SKILL.md")
    if not os.path.isfile(local_path):
        continue
    with open(local_path, 'rb') as f:
        local_md5 = hashlib.md5(f.read()).hexdigest()

    cat = [c for c, sk in upstream_categories.items() if skill_dir in sk][0]
    result = subprocess.run(
        ["gh", "api", f"repos/mattpocock/skills/contents/skills/{cat}/{skill_dir}/SKILL.md",
         "--jq", ".content"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        continue
    upstream_md5 = hashlib.md5(base64.b64decode(result.stdout.strip())).hexdigest()

    if local_md5 == upstream_md5:
        print(f"  ✅ {skill_dir}")
    else:
        print(f"  ⚠️  {skill_dir} — STALE (local={local_md5[:8]} upstream={upstream_md5[:8]})")
```

### Step 3: Fetch and overwrite stale skills

```python
import os, subprocess, base64

mattpocock_dir = os.path.expanduser("~/.hermes-teams/shared-skills/mattpocock")

for skill, cat in stale_skills:
    skill_dir = os.path.join(mattpocock_dir, skill)

    # Read-only files — need write permission
    subprocess.run(["chmod", "-R", "u+w", skill_dir], check=True)

    # Fetch upstream SKILL.md
    result = subprocess.run(
        ["gh", "api", f"repos/mattpocock/skills/contents/skills/{cat}/{skill}/SKILL.md",
         "--jq", ".content"],
        capture_output=True, text=True, timeout=30
    )
    upstream_content = base64.b64decode(result.stdout.strip())

    with open(os.path.join(skill_dir, "SKILL.md"), 'wb') as f:
        f.write(upstream_content)

    # Restore read-only
    subprocess.run(["chmod", "-R", "a-w", skill_dir], check=True)
    subprocess.run(["chmod", "u+w", skill_dir], check=True)
```

Check for files in the upstream skill that are missing locally (new
references, scripts, etc.) — fetch and write those too.

**Preserve local custom additions.** If a skill has local-only files not
in upstream (e.g. `issue-tracker-beads.md` in `setup-matt-pocock-skills/`),
keep them — they're Hermes-specific extensions.

### Step 4: Verify

Re-run the md5 comparison from Step 2. All skills should now match.

## Gitignore implications

`shared-skills/mattpocock/` and `shared-skills/ponytail/` are typically
**gitignored** in the hermes-team repo (they're treated as external repos
that live on disk). This means:

- ✅ Updates are live on disk immediately — all profiles see them via
  symlinks.
- ⚠️ Updates **won't sync to other machines** via `git push` — each
  machine needs its own `git pull` / manual sync for these dirs.
- If multi-machine sync of shared-skill packages is needed, remove the
  gitignore rules and track them in git.

## Missing skills

If upstream has a skill not installed locally (e.g.
`setup-ts-deep-modules` in mattpocock's `in-progress/` category), decide
whether to install it. Drafts and in-progress skills can usually be
skipped — promoted skills (in `engineering/` or `productivity/`) should
be fetched and added.
