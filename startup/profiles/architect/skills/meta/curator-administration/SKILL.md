---
name: curator-administration
description: >-
  Bulk curator operations across all Hermes profiles — pinning, unpinning,
  status checks, and dry-runs. Use when the user says "pin all skills",
  "pin every skill across profiles", "check curator on all profiles",
  "unpin everything", or wants to protect/manage skills at scale rather
  than one at a time. Also use when you need to enumerate what skills
  exist on a profile you don't control (cross-profile visibility).
  Trigger words: pin all, unpin all, curator status everywhere,
  protect skills, skill inventory.
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

## When to use this skill

- **Pin all skills everywhere**: user wants maximum protection before a
  major change, migration, or extended idle period.
- **Pin specific profiles**: user wants to protect a teammate's workflow
  skills.
- **Skill inventory**: user asks "what skills does profile X have?"
- **Pre-migration audit**: check curator state before restructuring.

## Related

- `references/batch-pinning-recipe.md` — copy-paste-ready batch pin script
  with ghost-profile filtering and per-profile results.
