# Team Integration Audit for Gateway-less Profiles

Methodology for verifying a gateway-less profile (card-spawned only, no
always-on gateway) is fully wired into the team workflow — both the
routing infrastructure AND the identity prompts of other profiles.

## When to run this audit

- After adding a new gateway-less profile (architect, qa, etc.)
- After a major workflow restructuring
- When diagnosing why a profile "never gets work in production"

## The audit script

```python
import os

root = os.path.expanduser("~/.hermes-teams/startup/profiles")
shared = os.path.expanduser("~/.hermes-teams/shared-skills")
profiles = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

target_profile = "architect"  # the profile being audited

print(f"AUDIT: Is '{target_profile}' wired into the team workflow?\n")

# 1. Wayfinder routing
print("1. WAYFINDER ROUTING")
wayfinder_paths = [
    os.path.join(root, "product-owner", "skills", "wayfinding-auto"),
    os.path.join(shared, "wayfinding-auto"),
]
for p in wayfinder_paths:
    if os.path.exists(p):
        for f in os.listdir(p):
            if f.endswith('.md'):
                with open(os.path.join(p, f)) as fh:
                    if target_profile in fh.read():
                        print(f"   ✅ {p}: routes to {target_profile}")

# 2. Identity prompts (SOUL.md)
print(f"\n2. IDENTITY PROMPTS (SOUL.md)")
for profile in sorted(profiles):
    soul = os.path.join(root, profile, "SOUL.md")
    if not os.path.isfile(soul):
        continue
    with open(soul) as f:
        content = f.read()
    if target_profile in content.lower():
        # Show the relevant lines
        for i, line in enumerate(content.split('\n'), 1):
            if target_profile in line.lower():
                print(f"   ✅ {profile}/SOUL.md L{i}: {line.strip()[:100]}")
    elif profile != target_profile:
        print(f"   ⚠️  {profile}/SOUL.md: NO mention of {target_profile}")

# 3. Consumer skills (verifier, tech-lead artifacts)
print(f"\n3. CONSUMER SKILLS")
target_artifacts = ["ADR", "conformance", "architecture"]
for profile in ["verifier", "tech-lead", "developer"]:
    skills_dir = os.path.join(root, profile, "skills")
    if not os.path.isdir(skills_dir):
        continue
    for dirpath, dirs, files in os.walk(skills_dir):
        for f in files:
            if f == 'SKILL.md':
                fp = os.path.join(dirpath, f)
                with open(fp) as fh:
                    content = fh.read()
                matches = [kw for kw in target_artifacts if kw.lower() in content.lower()]
                if matches:
                    rel = fp.replace(skills_dir, '...')
                    print(f"   ✅ {profile}/{rel}: {matches}")

# 4. Gate skill references workflow
print(f"\n4. GATE SKILL")
gate_path = os.path.join(root, target_profile, "skills")
gate_found = False
for dirpath, dirs, files in os.walk(gate_path):
    for f in files:
        if f == 'SKILL.md':
            fp = os.path.join(dirpath, f)
            with open(fp) as fh:
                content = fh.read()
            if any(kw in content.lower() for kw in ['to-tickets', 'to-spec', 'map']):
                rel = fp.replace(gate_path, '...')
                print(f"   ✅ {rel}: references workflow stages")
                gate_found = True
if not gate_found:
    print(f"   ⚠️  No gate skill references workflow stages")
```

## Interpreting results

| Integration point | ✅ = wired | ⚠️ = gap |
|---|---|---|
| Wayfinder routing | Profile receives work via routing layer | Won't receive routed work |
| Identity prompts | Other profiles proactively seek this profile | Only passive routing; no proactive contact |
| Consumer skills | Downstream profiles reference this profile's artifacts | Artifacts may go unread |
| Gate skill | Profile knows where it sits in the workflow | May not interact correctly with adjacent stages |

### The common gap pattern

The most common pattern when adding a gateway-less profile:
- **Wayfinder routing**: ✅ wired (tested in isolation)
- **Gate/ceremony skills**: ✅ wired (tested on test boards)
- **Other profiles' SOUL.md**: ⚠️ not updated

This means the profile is reachable via the routing layer but invisible
to other profiles' identity. The profile will be called when wayfinder
routes to it, but never when another profile proactively seeks its input.

### Fixing identity-prompt gaps

To complete the integration, update each sender profile's SOUL.md to
reference the new profile. For example, adding architect references to
product-owner's identity:

```diff
+ - **Route architecture questions to architect** via wayfinder:architecture
+   tickets. Do not invent technical answers — stay the asker.
```

This requires editing another profile's SOUL.md, which is outside the
scope of the profile being audited. File it as a follow-up task for each
profile that needs updating.
