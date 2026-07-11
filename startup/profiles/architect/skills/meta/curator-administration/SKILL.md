---
name: curator-administration
description: >-
  Bulk curator operations across all Hermes profiles — pinning, unpinning,
  status checks, dry-runs, skill classification, upstream auditing, and
  symlink consolidation. Use when the user says "pin all skills", "pin
  every skill across profiles", "check curator on all profiles", "unpin
  everything", wants to protect/manage skills at scale, asks about shared
  vs copied skills, wants to audit installed skills against upstream, or
  wants to consolidate duplicate skill copies into shared symlinks.
  Trigger words: pin all, unpin all, curator status everywhere, protect
  skills, skill inventory, consolidate skills, shared skills, symlink
  skills.
---

# Curator Administration

Manage Hermes curator state (pin/unpin/status/dry-run) at scale across
all registered profiles — not just your own.

## Key mechanics

### Cross-profile pinning

`hermes curator pin <skill>` has **no `--profile` flag**, but the global
`-p` flag works:

```bash
hermes -p <profile> curator pin <skill>
hermes -p <profile> curator status
hermes -p <profile> curator unpin <skill>
```

This is the only way to pin skills on a profile other than your active one.

### Enumerating profiles

```bash
hermes profile list
```

This is the **authoritative** list of registered profiles. Do NOT infer
the profile list from `ls ~/.hermes/profiles/` — see Pitfalls below.

### Enumerating skills per profile

Skills live at `~/.hermes/profiles/<profile>/skills/<category>/<skill-name>/`.
Real skills are at **depth 2** (category/skill-name). Exclude `.hub/`
directories (index-cache, quarantine — internal caches, not skills).

```bash
find ~/.hermes/profiles/<profile>/skills/ -mindepth 2 -maxdepth 2 -type d \
  | grep -v '/.hub/' \
  | sed 's|.*/skills/||' \
  | sort
```

The skill name is the **leaf** directory (e.g. `codebase-design`), not
the category prefix.

### Batch pinning

For large-scale operations (50+ skills × 10+ profiles), use a script
rather than hand-typing each command. See
`references/batch-pinning-recipe.md` for a copy-paste-ready pattern.

## Verification

After pinning, check each profile's curator status:

```bash
hermes -p <profile> curator status
```

The output shows pinned skill count under `pinned (N):` for agent-created
skills. Note: installed (non-agent-created) skills don't appear in the
curator status output, but they ARE pinned — the pin applies regardless.

### Git side-effects of bulk operations

Bulk pinning modifies files inside each profile's `skills/` directory:
`.usage.json`, `.curator_state`, and `.hub/` (audit log, lock files,
taps). If the profile directory lives inside a git repo (e.g.
`~/.hermes-teams/`), these appear as untracked or modified files in
`git status`. This is expected — commit them alongside the operation
so the pinning state is reproducible across machines.

For the commit-and-push workflow (when the user asks to persist the
changes), check auth first and stop if unavailable:
1. Test SSH: `ssh -T git@github.com` (works even when `gh auth` token
   is invalid — they are independent auth paths).
2. Check the remote: `git remote -v` — the repo may have unusual
   branch tracking (e.g. `main` pulls from `origin/config` but pushes
   to `origin/main`). Verify ahead/behind counts before pushing.
3. `git add -A && git commit && git push origin <branch>`.

## Pitfalls

### Ghost profiles
Directories may exist under `~/.hermes/profiles/` for profiles that are
**not registered** (leftover from renames, deletions, or manual creation).
`hermes -p <ghost> curator pin` will error: "Profile does not exist."
Always use `hermes profile list` as the source of truth, not `ls`.

### Profiles with no skills
Registered profiles may have no `skills/` directory (e.g. freshly created
profiles). There's nothing to pin — skip them silently.

### Agent-created vs installed skills
`curator status` shows counts for **agent-created** skills only. Installed
skills (via `hermes skills install` or bundled) won't appear in the count,
but pinning them still works and still protects them. Don't assume a
profile with "no agent-created skills" has no skills to pin.

### Already-pinned skills
Re-pinning an already-pinned skill is idempotent — no error, no duplicate.
Safe to re-run batch operations.

### gh CLI auth vs SSH auth are independent
`gh auth status` may show an invalid/expired token while SSH (`git@github.com`)
works perfectly. Git push/pull over SSH does not depend on the `gh` token.
If the user asks to commit-and-push and `gh` is broken, don't stop — test
SSH first (`ssh -T git@github.com`). Only flag the broken `gh` token as a
separate issue for the user to fix if they need `gh` CLI commands (PRs,
issues, API calls) that SSH can't cover.

## Shared vs independent skills (blast radius)

Not all skills in a profile are independent copies. The skill library uses a
**hybrid topology** — understand which is which before bulk operations:

### Symlinked (shared) skills
Some category-level directories are symlinks to a single source:

| Symlink | Source |
|---------|--------|
| `mattpocock/` | `~/.hermes-teams/shared-skills/mattpocock/` |
| `ponytail/` | `~/.hermes-teams/shared-skills/ponytail-hub/` |
| `caveman/` | `~/.hermes-teams/shared-skills/caveman/` |
| `wayfinding-auto/` | `~/.hermes-teams/shared-skills/wayfinding-auto/` |
| individual bundled skills (e.g. `meta/transform`, `coordination/team-delegation`) | `~/.hermes-teams/shared-skills/bundled/<name>/` |

Note: advisor previously had symlinks to `.agents/skills/` for business
skills (competitive-analysis, fundraising, etc.) but those were **dead
symlinks** (source never existed) and were removed during consolidation.

**Patching a symlinked skill on one profile changes it for ALL profiles instantly**
— they share the same files on disk. Pinning still works per-profile (curator
state is tracked separately in each profile's `.curator_state`), but content
edits propagate everywhere.

### Independent copies
Skills that are real directories (not symlinks) under `skills/<category>/` are
per-profile copies. Editing them only affects that one profile. These include
profile-specific doctrine (`architecture-gate`, `developer-loop`), bundled skills
(`team-delegation`, `find-skills`, `transform`), and agent-created skills.

### How to check
```bash
# List symlinked categories for a profile
find ~/.hermes/profiles/<profile>/skills/ -maxdepth 1 -type l -exec basename {} \;
```

See `references/shared-skills-topology.md` for the full audit methodology and
the disk-layout relationship between `~/.hermes/` and `~/.hermes-teams/startup/`.

## Classifying skills: taxonomy

Skills on disk fall into three categories that cross-cut each other:

1. **Shared (symlinked)** — category-level symlink to `shared-skills/`
   or `.agents/skills/`. Patching one profile propagates to all.
   Identifiable with `find <skills_dir> -maxdepth 1 -type l`.

2. **Bundled (independent copies)** — real dirs copied to **2+ profiles**
   at install time (e.g. `claude-code` on 7 profiles, `team-delegation`
   on 8). These drift apart over time. Candidates for symlink
   consolidation.

3. **Profile-specific** — real dir in **only one** profile. Includes:
   - **Doctrine**: installed as part of the profile's identity
     (`architecture-gate`, `developer-loop`, `startup-advisory`)
   - **Tool integrations**: unique to one profile's workflow
     (`airtable`, `github-*` on venture-builder)
   - **Agent-created**: written by an agent during runtime, tracked in
     `.curator_state` (`team-observability`, `intercom`)

To classify: iterate every profile's skills, resolve symlinks, then
count how many profiles each real-dir skill appears in. Skills in 1
profile = profile-specific; in 2+ = bundled. See
`references/skill-classification.md` for the audit script.

## Auditing installed skills against upstream

When verifying installed skills match their source repo (e.g.
`github.com/mattpocock/skills`):

1. List upstream skills via GitHub API:
   ```bash
   gh api repos/<owner>/<repo>/contents/skills --jq '.[].name'
   # Then drill into each category dir
   gh api repos/<owner>/<repo>/contents/skills/<category> --jq '.[].name'
   ```
2. For plugin-provided packages, check `plugin.json` for the official
   (promoted) skill list:
   ```bash
   gh api repos/<owner>/<repo>/contents/.claude-plugin/plugin.json \
     --jq '.content' | base64 -d
   ```
3. Compare the upstream set against installed skills at
   `shared-skills/<package>/`.
4. Flag: missing (in repo, not installed), extra (installed, not in
   repo — likely a misfiled skill from another package).

### Misfile detection

Skills that don't belong to a package can end up inside its shared dir
(e.g. `find-skills` — a Hermes bundled skill — was found inside
`shared-skills/mattpocock/` despite not existing in the upstream repo).
Detect by comparing installed contents against upstream; investigate
any extras.

## Consolidating independent copies into shared symlinks

When the user wants to eliminate copy drift by moving bundled skills to
shared symlinks under `shared-skills/bundled/`:

1. **Divergence check** — md5 each copy across profiles; pick a canonical version (majority wins, or newest version if versions differ).
2. **Profile-specific path check** — grep for `~/.hermes/profiles/` in each copy; skip any skill with hardcoded profile paths (it can't be safely shared).
3. **Execute** — copy canonical to `shared-skills/bundled/<skill>/`, replace each profile's real dir with a relative symlink.
4. **Dead symlink cleanup** — scan for and remove pre-existing broken symlinks (e.g. advisor's `.agents/skills/` pointers whose source was never populated).
5. **Verify** — all symlinks must resolve before committing.

**Read-only packages**: installed skill packages (mattpocock, ponytail) are often read-only (555/444). `chmod -R u+w` before any rm/mv operation inside them — Python's `shutil.move` will fail with PermissionError otherwise.

**Misfiled skills**: detect by comparing against upstream; move to the correct location (`shared-skills/bundled/`) before symlinking.

This is a destructive operation (removing real dirs). Always commit-and-push the current state first so git history can recover.

See `references/consolidation-recipe.md` for the full 7-phase execution recipe with copy-paste Python scripts.

## When to use this skill

- **Pin all skills everywhere**: user wants maximum protection before a
  major change, migration, or extended idle period.
- **Pin specific profiles**: user wants to protect a teammate's workflow
  skills.
- **Skill inventory**: user asks "what skills does profile X have?"
- **Pre-migration audit**: check curator state before restructuring.
- **Upstream comparison**: verify installed skills match their source
  repo, detect misfiles or missing skills.
- **Consolidation planning**: convert independent copies to shared
  symlinks.

## Related

- `references/batch-pinning-recipe.md` — copy-paste-ready batch pin script
  with ghost-profile filtering and per-profile results.
- `references/shared-skills-topology.md` — how to audit which skills are
  symlinked (shared) vs independent copies, and the blast-radius
  implications for pinning vs patching.
- `references/skill-classification.md` — Python script to classify all
  skills into shared/bundled/profile-specific, and the consolidation
  decision for each category.
- `references/consolidation-recipe.md` — full 7-phase execution recipe
  for converting bundled copies to shared symlinks: divergence check,
  canonical selection, read-only permission handling, dead symlink
  cleanup, and verification.
