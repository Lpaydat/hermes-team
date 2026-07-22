---
name: skill-pinning
description: "Lock high-value skills from Curator auto-archival."
disable-model-invocation: true
---

# Skill pinning

## Commands

```bash
hermes curator pin <skill_name>          # pin in current profile
hermes -p <profile> curator pin <skill_name>   # pin in a specific profile
hermes curator unpin <skill_name>
hermes curator status                     # see pinned + thresholds + inventory
hermes curator restore <skill_name>       # recover an archived skill
hermes curator list-archived
```

## Pin across all profiles

```bash
for p in advisor architect base builder debugger designer developer ops product-owner qa researcher scout tech-lead venture-builder verifier; do
    hermes -p $p curator pin <skill_name>
done
```

## When to pin

Pin hand-authored skills you rely on — custom workflows, complex logic that would be costly to recreate. Leave experimental skills unpinned; let the Curator manage them.
