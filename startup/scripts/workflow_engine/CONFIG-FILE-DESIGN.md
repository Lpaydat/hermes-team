# Config File Storage Design — alongside tech-preferences.json

## Context

The paved road (python3 + pytest + sqlite/JSON) needs real config files —
`ruff.toml`, `pyproject.toml` with `[tool.ruff]` + `[tool.pytest]`, `.gitignore`,
etc. These are not JSON; they must be stored as real files the setup node copies
into a new project. This document specifies where they live, how they're
organized, and how the setup node finds the right ones.

## Design decisions (answers to the five questions)

### 1. Where do template files live?

**Alongside the workflow engine templates**, in a sibling `configs/` directory:

```
startup/scripts/workflow_engine/
├── templates/          ← existing workflow templates (.json)
└── configs/            ← NEW: real config files for project scaffolding
    ├── manifest.json   ← the index (the "tech-preferences.json" concept)
    ├── _shared/        ← cross-language files (.gitignore, Makefile)
    └── python/         ← language-specific configs
```

**Rationale:** The setup node is a `command`-type node in a workflow template.
It needs to reference config files by absolute path. Putting them next to the
templates keeps them version-controlled with the engine and discoverable by the
node. No new top-level directory, no magic path resolution.

### 2. How are language-specific configs organized?

**One directory per language/runtime**, mirroring the paved-road stack:

```
configs/
├── _shared/             # language-agnostic files copied to EVERY project
│   ├── .gitignore
│   └── Makefile
├── python/              # paved road: python3 + pytest
│   ├── ruff.toml        # standalone ruff config
│   ├── pyproject.toml   # composite: [project] + [tool.ruff] + [tool.pytest]
│   └── conftest.py      # pytest fixtures
├── node/                # future: if a project deviates to Node
│   ├── .eslintrc.json
│   └── tsconfig.json
└── go/                  # future
    └── .golangci.yml
```

The manifest declares which directory to use based on `tech_stack`.

### 3. How are composite configs handled?

`pyproject.toml` is the hard case: it carries `[project]` metadata AND `[tool.ruff]`
AND `[tool.pytest.ini_options]` in one file. Two options:

**Option A — full template file (RECOMMENDED).** Store a complete
`pyproject.toml` as one file with `${}` placeholders for the two project-specific
values (name, version). The setup node substitutes and copies. No fragment
assembly, no merging logic, no TOML parser in the shell.

**Option B — TOML fragment assembly.** Store `[tool.ruff]` and `[tool.pytest]` as
separate fragment files, then concatenate into a generated pyproject.toml.
Rejected: requires TOML-aware merging (sections can't be blindly appended if
`[project]` already exists), adds a build step, and the fragments are only ever
used together on the paved road.

**Decision: Option A.** The paved road has one Python project shape. A single
`pyproject.toml` template with two `${}` variables is simpler, auditable, and
diffable. If a project deviates from the paved road (T2+ deviation per
architect), the developer edits the copied file — the template is a starting
point, not a constraint.

If a project needs BOTH a standalone `ruff.toml` AND a `pyproject.toml` (ruff
auto-discovers `ruff.toml` and ignores `[tool.ruff]`), the manifest lists both —
but the `pyproject.toml` template should omit `[tool.ruff]` in that case. The
manifest handles this via a `config_set` concept (see manifest design below).

### 4. Should files use template syntax or be static?

**Static by default, `${}` placeholders only where unavoidable.**

- `ruff.toml`, `conftest.py`, `.gitignore`, `Makefile` → **100% static**. Copy as-is.
- `pyproject.toml` → **two placeholders**: `${PROJECT_NAME}` and `${PROJECT_VERSION}`.
  These are the only values that vary per project and can't be defaulted.

**Why minimal templating:** Every `${}` is a substitution the setup node must
perform. Shell `sed` is fragile; a Python one-liner is better but still a moving
part. The fewer placeholders, the fewer failure modes. Config files like
`ruff.toml` have no project-specific values — they encode team-wide linting rules
that are identical across every paved-road project.

**Templating mechanism:** The setup `command` node uses `envsubst` or a simple
`sed` for the two `pyproject.toml` variables. No template engine dependency.

### 5. How does the setup node find the right files?

**Via the manifest (`manifest.json`).** The setup node receives `tech_stack`
from the architect's output metadata, looks it up in the manifest, and copies
the declared file set.

The manifest maps a stack key to:
- A language directory (e.g., `python/`)
- A list of files to copy with optional target rename
- Which files need `${}` substitution

```
configs/manifest.json:
{
  "version": 1,
  "stacks": {
    "python-paved": {
      "description": "Python3 + pytest + ruff (paved road default)",
      "language_dir": "python",
      "files": [
        {"source": "_shared/.gitignore", "target": ".gitignore"},
        {"source": "_shared/Makefile", "target": "Makefile"},
        {"source": "python/pyproject.toml", "target": "pyproject.toml", "substitute": true},
        {"source": "python/conftest.py", "target": "tests/conftest.py"}
      ]
    },
    "python-ruff-standalone": {
      "description": "Python3 + pytest + standalone ruff.toml (no [tool.ruff] in pyproject)",
      "language_dir": "python",
      "files": [
        {"source": "_shared/.gitignore", "target": ".gitignore"},
        {"source": "_shared/Makefile", "target": "Makefile"},
        {"source": "python/pyproject-minimal.toml", "target": "pyproject.toml", "substitute": true},
        {"source": "python/ruff.toml", "target": "ruff.toml"},
        {"source": "python/conftest.py", "target": "tests/conftest.py"}
      ]
    }
  }
}
```

The architect stamps `tech_stack: "python3 + pytest + sqlite"` in the spec
metadata. The setup node's workflow template maps that string to a manifest
stack key (or the manifest uses a `match` field with keywords). On the paved
road this mapping is trivial: `python` in tech_stack → `python-paved` set.

---

## Complete directory layout with example files

```
startup/scripts/workflow_engine/configs/
├── manifest.json
├── _shared/
│   ├── .gitignore
│   └── Makefile
└── python/
    ├── pyproject.toml              # composite: [project] + [tool.ruff] + [tool.pytest]
    ├── pyproject-minimal.toml      # [project] only (for ruff-standalone variant)
    ├── ruff.toml                   # standalone ruff config (alternative to [tool.ruff])
    └── conftest.py                 # pytest fixtures
```

### Example: `configs/manifest.json`

```json
{
  "version": 1,
  "stacks": {
    "python-paved": {
      "description": "Python3 + pytest + ruff (paved road default)",
      "language_dir": "python",
      "match_keywords": ["python", "pytest"],
      "files": [
        {"source": "_shared/.gitignore", "target": ".gitignore"},
        {"source": "_shared/Makefile", "target": "Makefile"},
        {"source": "python/pyproject.toml", "target": "pyproject.toml", "substitute": true},
        {"source": "python/conftest.py", "target": "tests/conftest.py"}
      ]
    },
    "python-ruff-standalone": {
      "description": "Python3 + pytest + standalone ruff.toml",
      "language_dir": "python",
      "match_keywords": ["python", "ruff-standalone"],
      "files": [
        {"source": "_shared/.gitignore", "target": ".gitignore"},
        {"source": "_shared/Makefile", "target": "Makefile"},
        {"source": "python/pyproject-minimal.toml", "target": "pyproject.toml", "substitute": true},
        {"source": "python/ruff.toml", "target": "ruff.toml"},
        {"source": "python/conftest.py", "target": "tests/conftest.py"}
      ]
    }
  }
}
```

### Example: `configs/python/pyproject.toml` (composite template)

```toml
[project]
name = "${PROJECT_NAME}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = "-v --tb=short"
```

### Example: `configs/python/ruff.toml` (standalone variant)

```toml
# Standalone ruff config — use when pyproject.toml must stay minimal.
# ruff auto-discovers ruff.toml and ignores [tool.ruff] in pyproject.toml.
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[format]
quote-style = "double"
```

### Example: `configs/python/conftest.py`

```python
"""Shared pytest fixtures — copied to tests/conftest.py."""
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Root directory of the project."""
    return Path(__file__).parent.parent
```

### Example: `configs/_shared/.gitignore`

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.venv/
venv/
.env
```

### Example: `configs/_shared/Makefile`

```makefile
.PHONY: test lint format check

test:
	pytest -v

lint:
	ruff check src tests

format:
	ruff format src tests

check: lint test
```

---

## Setup node design (workflow template integration)

The setup node is a `command`-type node that runs a small Python script to read
the manifest, resolve the stack, and copy files. It receives `PROJECT_NAME`,
`PROJECT_SLUG`, and `tech_stack` from the architect node's output.

### Example setup node (in a workflow template JSON)

```json
{
  "id": "setup_configs",
  "profile": "",
  "skill": "",
  "body_template": "",
  "type": "command",
  "command": "python3 ~/.hermes-teams/startup/scripts/workflow_engine/configs/setup_configs.py --project-dir ~/projects/${trigger.slug} --project-name '${trigger.title}' --tech-stack '${nodes.architect.output.tech_stack}'",
  "depends_on": ["architect"]
}
```

### `configs/setup_configs.py` (the resolver script)

```python
#!/usr/bin/env python3
"""Resolve tech_stack → copy the right config files into a project directory.

Reads manifest.json, matches the tech_stack string to a stack key, copies
the declared files, and performs ${} substitution on flagged files.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

CONFIGS_DIR = Path(__file__).parent
MANIFEST_PATH = CONFIGS_DIR / "manifest.json"


def resolve_stack(tech_stack: str, manifest: dict) -> str:
    """Match tech_stack string to a manifest stack key via keywords."""
    stack_lower = tech_stack.lower()
    for key, stack in manifest["stacks"].items():
        keywords = stack.get("match_keywords", [])
        if all(kw.lower() in stack_lower for kw in keywords):
            return key
    # Default to paved road for Python
    if "python" in stack_lower:
        return "python-paved"
    raise ValueError(f"No config stack matches tech_stack: {tech_stack}")


def substitute(content: str, project_name: str) -> str:
    """Replace ${PROJECT_NAME} placeholder."""
    return content.replace("${PROJECT_NAME}", project_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--tech-stack", required=True)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    stack_key = resolve_stack(args.tech_stack, manifest)
    stack = manifest["stacks"][stack_key]

    project_dir = Path(args.project_dir).expanduser()
    project_dir.mkdir(parents=True, exist_ok=True)

    for file_entry in stack["files"]:
        src = CONFIGS_DIR / file_entry["source"]
        dst = project_dir / file_entry["target"]
        dst.parent.mkdir(parents=True, exist_ok=True)

        if file_entry.get("substitute"):
            dst.write_text(substitute(src.read_text(), args.project_name))
        else:
            shutil.copy2(src, dst)
        print(f"  copied: {file_entry['source']} → {file_entry['target']}")

    print(f"\nConfig setup complete: stack={stack_key}, {len(stack['files'])} files")


if __name__ == "__main__":
    main()
```

---

## Pipeline integration

Per the established pipeline ordering (`idea → features → constraints → tech
stack → architecture → scaffold → plan → dev`), the setup node runs AFTER the
architect gate and BEFORE ticket decomposition:

```
[spec] → [architect] → [setup_configs] → [decompose] → [ticket-NN...]
                          ↑
                  copies configs/ files into ~/projects/<slug>/
```

The architect's output (`tech_stack`, `spec_file`) feeds directly into the setup
node's command via `${nodes.architect.output.tech_stack}`.

## Summary of design choices

| Question | Decision |
|---|---|
| Where templates live | `configs/` sibling to `templates/` in the workflow engine dir |
| Language organization | One subdir per language (`python/`, `node/`, `go/`) + `_shared/` |
| Composite configs | Full template file with `${}` for project name/version (Option A) |
| Template vs static | Static by default; `${PROJECT_NAME}` only in `pyproject.toml` |
| Setup node file discovery | `manifest.json` maps `tech_stack` string → file list to copy |
