# Vault Migration & Cross-Profile Path Audit

## The correction

User (founder) corrected repeatedly: `~/vault/` is the Obsidian vault — second brain / knowledge base ONLY. Never put prototypes, project code, journals, traces, or build artifacts there.

The builder had been dumping prototypes to `~/vault/ventures/prototypes/` for months. The tech-lead's SOUL.md had `~/vault/journal/<project>/` and `~/vault/traces/`. Both wrong.

## What stays in vault (correct)

- `~/vault/ventures/signals/` — raw scan data
- `~/vault/ventures/ideas/<slug>.md` — dossiers
- `~/vault/ventures/idea-bank.md` — ranked index
- `~/vault/ventures/portfolio.md` — status tracker
- `~/vault/ventures/templates/` — dossier/verification templates
- `~/vault/ventures/user-ideas.md` — Door D intake
- `~/vault/ventures/PIPELINE-ARCHITECTURE.md` — architecture spec
- `~/vault/wiki/` — researcher's curated knowledge (READ ONLY)
- `~/vault/meta/scout.db` — scout findings database

## What moves to ~/projects/ (correct)

- Prototypes: `~/projects/<slug>/prototype/`
- Journals: `~/projects/<slug>/journal/`
- Traces: `~/projects/<slug>/traces/`
- Context (on promotion): `~/projects/<slug>/.context/`
- Production code: `~/projects/<slug>/src/`
- STATUS.md, README.md: `~/projects/<slug>/`

## Cross-profile audit technique

When a wrong path is found in ONE profile, scan ALL profiles immediately. The same SOUL.md / skill templates get copied across profiles, so the same error exists everywhere.

```bash
# Scan all profiles for a specific wrong pattern
grep -rn 'vault/journal\|vault/traces\|vault/prototypes' \
    ~/.hermes-teams/startup/profiles/*/SOUL.md \
    ~/.hermes-teams/startup/profiles/*/skills/ \
    ~/.hermes-teams/shared-skills/ \
    2>/dev/null | grep -v '.bak'
```

In this session:
- **Builder**: SOUL.md, self-grill, grill-rpc-ops, pipeline-context.md, queue-builds.sh, PIPELINE-ARCHITECTURE.md, portfolio.md — all had wrong references
- **Tech-lead**: SOUL.md, loops-engineering SKILL.md, harness-commands.md, kanban-native-loops.md, loop-theory.md — all had wrong references
- **Total**: 8+ files across 2 profiles needed patching

## sed backreference pitfall

When doing `sed -i 's|pattern|~/projects/\1/prototype/|g'` on path strings, the `\1` backreference in GNU sed does NOT work correctly when the replacement contains backslashes or special characters. It produced literal `\x01` control characters in the file.

**Fix:** Use Python instead of sed for any path replacement involving backreferences:

```python
import re
with open(path) as f:
    content = f.read()
content = re.sub(r'~/vault/ventures/prototypes/([^/]+)/', r'~/projects/\1/prototype/', content)
with open(path, 'w') as f:
    f.write(content)
```

Or better: read the file, match by context (project name in the same line), and replace the specific string.
