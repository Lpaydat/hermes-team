# Verification Script Template

Write this to `/tmp/verify-<slug>.py` before calling loop_engine. It parses locked decisions from context/ and checks the prototype + README against them.

```python
#!/usr/bin/env python3
"""Verify <slug> prototype against grill decisions in context/."""
import re, os, sys

context_dir = os.path.expanduser("~/projects/<slug>/context")
proto_dir = os.path.expanduser("~/projects/<slug>/prototype")
readme_path = os.path.expanduser("~/projects/<slug>/README.md")

# Parse locked decisions from context/
decisions = {}
for f in os.listdir(context_dir):
    if f == "_state.md": continue
    with open(os.path.join(context_dir, f)) as fh:
        for line in fh:
            m = re.match(r'Lock (D\d+):\s*(.+?)\s*=\s*(.+)', line)
            if m:
                decisions[m.group(1)] = (m.group(2).strip(), m.group(3).strip())

failures = []

# Check 1: Prototype exists
proto_files = os.listdir(proto_dir) if os.path.isdir(proto_dir) else []
if not proto_files:
    failures.append("No prototype files in prototype/")

# Check 2: README exists with required sections
required_sections = ["## What It Is", "## The Problem", "## Core Features",
                     "## How to Review", "## Grill Decisions", "## Riskiest Assumption",
                     "## How to Run", "## What Happens Next", "## Dossier"]
if os.path.exists(readme_path):
    readme = open(readme_path).read()
    for section in required_sections:
        if section not in readme:
            failures.append(f"README missing section: {section}")
else:
    failures.append("README.md does not exist")

# Check 3: Each decision is referenced in README
if os.path.exists(readme_path):
    readme_lower = readme.lower()
    for d_id, (title, value) in decisions.items():
        keywords = title.lower().split()[:2]
        if not all(kw in readme_lower for kw in keywords):
            failures.append(f"Decision {d_id} ({title}) not reflected in README")

# Report
print(f"Decisions checked: {len(decisions)}")
print(f"Checks passed: {3 - len([f for f in failures if 'Check' in f])}")
print(f"Failures: {len(failures)}")
for f in failures:
    print(f"  FAIL: {f}")

sys.exit(1 if failures else 0)
```
