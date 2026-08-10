# Config File Storage Design — full spec

Originally produced for the paved-road Python stack (python3 + pytest + ruff).

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

## Example: manifest.json

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

## Example: pyproject.toml (composite template)

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

## Example: ruff.toml (standalone variant)

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

## Example: conftest.py

```python
"""Shared pytest fixtures — copied to tests/conftest.py."""
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Root directory of the project."""
    return Path(__file__).parent.parent
```

## Example: _shared/.gitignore

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

## Example: _shared/Makefile

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

## Resolver script: setup_configs.py

```python
#!/usr/bin/env python3
"""Resolve tech_stack → copy the right config files into a project directory.

Reads manifest.json, matches the tech_stack string to a stack key, copies
the declared files, and performs ${} substitution on flagged files.
"""
import argparse
import json
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
