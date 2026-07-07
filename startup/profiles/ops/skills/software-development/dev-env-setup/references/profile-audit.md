# Profile audit checklist

Run this when reviewing a profile for completeness — either one you just set up, or one handed off from another session/agent. Each item lists the check and the failure mode.

## 1. Config validity

```bash
python3 -c "import yaml; yaml.safe_load(open('<HERMES_HOME>/config.yaml')); print('valid')"
```

**Fail mode:** hand-edited YAML has tabs, bad indentation, or a string where a list is expected.

## 2. command_allowlist is a real list of glob patterns

```python
import yaml
c = yaml.safe_load(open("config.yaml"))
al = c.get("command_allowlist", [])
assert isinstance(al, list), f"got {type(al).__name__} — likely a quoted string"
for entry in al:
    assert "*" in entry or len(entry.split()) > 1, f"'{entry}' looks like an approval description, not a command pattern"
```

**Fail mode:** entries are approval-prompt descriptions ("delete in root path", "script execution via -e/-c flag") copied from the TUI. These match nothing; every flagged command still prompts.

## 3. approvals.mode is explicitly set

```python
mode = c.get("approvals", {}).get("mode")
assert mode is not None, "approvals.mode not set — inherits manual (every flagged command prompts)"
```

**Fail mode:** profile was hand-rolled without setting this. The ops/infra role that runs `npm install`, `systemctl`, `pip install` constantly will hit an approval prompt on each one.

## 4. SOUL.md has all structural blocks

```bash
grep -c 'CONSTITUTION:BEGIN' SOUL.md  # must be 1
grep -c 'CONSTITUTION:END' SOUL.md    # must be 1
grep -c 'SPECIALTY:BEGIN' SOUL.md     # must be 1
grep -c 'SPECIALTY:END' SOUL.md       # must be 1
grep -c 'Team coordination' SOUL.md   # must be 1
```

**Fail mode:** hand-rolled SOUL only has the specialty block. Missing constitution = no frozen safety invariants. Missing team-coordination = agent doesn't know how to use the kanban board.

## 5. Markers exist

```bash
test -f .bootstrap_complete && echo "ok" || echo "MISSING — profile will re-transform"
test -f .no-bundled-skills && echo "ok" || echo "MISSING — bundled skills will re-seed on update"
```

## 6. Description is set

```bash
hermes profile describe <name>  # should print a one-two sentence role, not empty
```

**Fail mode:** no description → kanban decomposer can't route tasks to this profile.

## 7. Skills are triaged (not bloated)

```python
import yaml, os
c = yaml.safe_load(open("config.yaml"))
disabled = set(c.get("skills", {}).get("disabled", []))
on_disk = []
for root, dirs, files in os.walk("skills"):
    if "SKILL.md" in files:
        # parse name from frontmatter...
        on_disk.append(name)
enabled = [s for s in on_disk if s not in disabled]
print(f"Enabled: {len(enabled)}")
# A specialized profile should have ~10-20 enabled skills, not 80+.
# >50 enabled = the profile wasn't triaged; it's carrying base's full kit.
```

**Fail mode:** profile inherited all of base's skills and nobody pruned. Context window pollution on every turn.

## 8. Cron job healthcheck script uses correct tool names

Check the cron script's tool list against what's actually installed. Stale scripts reference tools that were renamed or don't exist (e.g. `codegraph-server` instead of `codegraph`).

## 9. No orphaned disabled entries

Every entry in `skills.disabled` should correspond to a skill still on disk. Orphans accumulate when skills are deleted but the disabled list isn't pruned.

```python
disabled = set(c.get("skills", {}).get("disabled", []))
orphans = disabled - set(on_disk)
# orphans should be empty
```
