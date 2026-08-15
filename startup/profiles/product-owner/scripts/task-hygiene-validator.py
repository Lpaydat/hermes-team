#!/usr/bin/env python3
"""Wrapper — runs the task-hygiene scanner from the skill's scripts dir.

The cron scheduler only executes scripts inside HERMES_HOME/scripts/ (symlinks
out are blocked), so this wrapper execs the real scanner:
  skills/software-development/task-hygiene-validator/scripts/scan_hygiene.py

The cron job passes no arguments; with no args we iterate every project in
~/.hermes-teams/startup/active-projects.json (skipping dirs that don't exist).
Explicit args are forwarded untouched (manual runs, tests).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCANNER = (
    Path(__file__).resolve().parent.parent
    / "skills" / "software-development"
    / "task-hygiene-validator" / "scripts" / "scan_hygiene.py"
)
PROJECTS_FILE = Path.home() / ".hermes-teams" / "startup" / "active-projects.json"


def run(args):
    try:
        return subprocess.run(
            [sys.executable, str(SCANNER)] + args,
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        # ponytail: report cleanly instead of a traceback — cron records it as an error either way
        class _Timeout:
            returncode = 124
            stdout = ""
            stderr = f"scanner timed out after 120s: {args}"
        return _Timeout()


def main() -> int:
    if len(sys.argv) > 1:
        r = run(sys.argv[1:])
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        return r.returncode

    if not PROJECTS_FILE.exists():
        return 0
    try:
        projects = json.loads(PROJECTS_FILE.read_text()).get("active_projects", [])
    except (json.JSONDecodeError, OSError):
        return 0

    rc = 0
    for p in projects:
        path = p.get("path") or p.get("repo") or ""
        if not path or not Path(path).is_dir():
            continue
        r = run([path])
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            rc = r.returncode
            sys.stderr.write(r.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
