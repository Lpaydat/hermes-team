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
        """Load a workflow template by ID."""
        if workflow_id in self._cache:
            return self._cache[workflow_id]

        path = self.dir / f"{workflow_id}.json"
        if not path.exists():
            log.warning("Template not found: %s", path)
            return None

        try:
            data = json.loads(path.read_text())
            wf = Workflow.from_dict(data)
            self._cache[workflow_id] = wf
            return wf
        except (json.JSONDecodeError, KeyError) as e:
            log.error("Failed to load template %s: %s", path, e)
            return None

    def list_ids(self) -> list[str]:
        """List all available workflow IDs."""
        if not self.dir.exists():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def all(self) -> list[Workflow]:
        """Load all templates."""
        return [wf for wid in self.list_ids() if (wf := self.load(wid))]
