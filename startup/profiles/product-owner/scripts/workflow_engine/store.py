"""Store for workflow templates — loads JSON files from disk."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import logging

from .model import Workflow

log = logging.getLogger(__name__)


class TemplateStore:
    """Loads workflow templates from a directory.

    Templates are JSON files: <templates_dir>/<workflow_id>.json
    """

    def __init__(self, templates_dir: str | Path):
        self.dir = Path(templates_dir)
        self._cache: dict[str, Workflow] = {}

    def load(self, workflow_id: str) -> Workflow | None:
        """Load a workflow template by ID.

        Returns None for any malformed, unreadable, or invalid template.
        Never raises — all errors are caught and logged.
        """
        if workflow_id in self._cache:
            return self._cache[workflow_id]

        path = self.dir / f"{workflow_id}.json"
        if not path.exists():
            log.warning("Template not found: %s", path)
            return None

        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            data = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            log.error("Failed to read/parse template %s: %s", path, e)
            return None

        if not isinstance(data, dict):
            log.error("Template %s: root is %s, expected dict", path, type(data).__name__)
            return None

        try:
            wf = Workflow.from_dict(data)
        except (KeyError, TypeError, ValueError) as e:
            log.error("Failed to load template %s: %s", path, e)
            return None

        self._cache[workflow_id] = wf
        return wf

    def list_ids(self) -> list[str]:
        """List all available workflow IDs."""
        if not self.dir.exists():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def all(self) -> list[Workflow]:
        """Load all valid templates. Invalid ones are skipped (logged on first load)."""
        results = []
        for wid in self.list_ids():
            wf = self.load(wid)
            if wf is not None:
                results.append(wf)
        return results
