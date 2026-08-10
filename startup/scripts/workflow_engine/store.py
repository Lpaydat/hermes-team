"""Store for workflow templates — loads JSON files from disk."""
from __future__ import annotations
from pathlib import Path
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
        self._cache_mtime: dict[str, float] = {}

    def load(self, workflow_id: str) -> Workflow | None:
        """Load a workflow template by ID.

        Returns None for any malformed, unreadable, or invalid template.
        Never raises — all errors are caught and logged.
        """
        if workflow_id in self._cache:
            # Check if the file has been modified since caching
            path = self.dir / f"{workflow_id}.json"
            if path.exists():
                mtime = path.stat().st_mtime
                cached_mtime = self._cache_mtime.get(workflow_id, 0)
                if mtime > cached_mtime:
                    del self._cache[workflow_id]  # stale — force reload
                else:
                    return self._cache[workflow_id]
            else:
                return self._cache[workflow_id]  # cached, file gone (ok)

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
        except RecursionError:
            # CPython's json decoder recurses for nested containers and hits the
            # interpreter recursion limit (~1000 frames) on pathologically deep
            # nesting (e.g. 5000-deep {"k": {...}}). This is a malformed/hostile
            # template, not a valid workflow; honour the "never raises" contract
            # by treating it as unreadable.
            log.error("Template %s exceeds Python recursion limit; rejected", path)
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
        self._cache_mtime[workflow_id] = path.stat().st_mtime
        return wf

    def list_ids(self) -> list[str]:
        """List all available workflow IDs."""
        if not self.dir.exists():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def all(self) -> list[Workflow]:
        """Load all valid templates. Invalid ones are skipped (logged on first load).

        Also validates that every node's ``skill`` exists on its ``profile`` —
        mismatches are logged as warnings (the template still loads, but the
        operator gets an early signal to install the skill or fix the template).
        """
        results = []
        for wid in self.list_ids():
            wf = self.load(wid)
            if wf is not None:
                results.append(wf)
        self._validate_skills(results)
        return results

    def _validate_skills(self, workflows: list[Workflow]) -> None:
        """Warn when a node's skill doesn't exist on its profile.

        Checks both ``profiles/<profile>/skills/`` and ``shared-skills/`` for a
        matching skill directory (supports nested categories like
        ``mattpocock/to-tickets``).
        """
        import os
        hermes_root = Path.home() / ".hermes-teams"
        profiles_root = hermes_root / "startup" / "profiles"
        shared_skills = hermes_root / "shared-skills"
        for wf in workflows:
            for node in wf.nodes:
                skill = (node.skill or "").strip()
                if not skill:
                    continue
                profile_dir = profiles_root / node.profile
                if not profile_dir.exists():
                    log.warning(
                        "SKILL VALIDATION: %s/%s references profile '%s' which does not exist",
                        wf.id, node.id, node.profile,
                    )
                    continue
                found = False
                # Check profile-local skills
                skills_dir = profile_dir / "skills"
                if skills_dir.exists():
                    found = any(
                        skill in dirs
                        for _, dirs, _ in os.walk(skills_dir)
                    )
                # Check shared skills (mattpocock bundle, etc.)
                if not found and shared_skills.exists():
                    found = any(
                        skill in dirs
                        for _, dirs, _ in os.walk(shared_skills)
                    )
                if not found:
                    log.warning(
                        "SKILL VALIDATION: %s/%s uses skill '%s' on profile '%s' — skill NOT FOUND",
                        wf.id, node.id, skill, node.profile,
                    )
