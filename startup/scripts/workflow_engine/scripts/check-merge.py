#!/usr/bin/env python3
"""Check if code merged to master — replaces cron phase_qa_trigger signal 1.

Reads the last-seen SHA from state file, compares with current HEAD,
checks if any code files changed. Outputs JSON for the workflow engine.

Output: {"should_test": true/false, "commit_sha": "<sha>"}
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STATE_FILE = Path.home() / ".hermes-teams/startup/kanban/qa-merge-state.json"
CODE_EXTS = {
    ".py", ".js", ".ts", ".rs", ".go", ".java", ".rb", ".sh",
    ".sql", ".yaml", ".yml", ".toml",
}


def load_active_projects():
    """Get board → project_dir mapping from active-projects.json."""
    f = Path.home() / ".hermes-teams/startup/active-projects.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text())
    return {
        p["board"]: (p.get("path") or p.get("repo"))
        for p in data.get("active_projects", [])
        if p.get("board") and (p.get("path") or p.get("repo"))
    }


def get_head_sha(project_dir: str) -> str | None:
    """Get current HEAD SHA (12 chars) or None."""
    git_dir = Path(project_dir)
    if not (git_dir / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(git_dir), capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip()[:12]
    except Exception:
        return None


def get_changed_files(project_dir: str, old_sha: str, new_sha: str) -> list[str]:
    """List files changed between two SHAs."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", f"{old_sha}..{new_sha}"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
        return [f for f in r.stdout.strip().split("\n") if f]
    except Exception:
        return []


def has_code_files(files: list[str]) -> bool:
    """Check if any changed file has a code extension."""
    return any(
        any(f.endswith(ext) for ext in CODE_EXTS)
        for f in files if f
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True)
    args = parser.parse_args()

    # A/B test isolation: skip boards ending in '-a' (cron handles those)
    if args.board.endswith("-a"):
        print(json.dumps({"should_test": "false", "commit_sha": "", "reason": "A/B test: cron handles board A"}))
        return

    projects = load_active_projects()
    project_dir = projects.get(args.board)

    if not project_dir:
        print(json.dumps({"should_test": "false", "commit_sha": "", "reason": "no project for board"}))
        return

    current_sha = get_head_sha(project_dir)
    if not current_sha:
        print(json.dumps({"should_test": "false", "commit_sha": "", "reason": "no git repo"}))
        return

    # Load state
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    last_sha = state.get(args.board)

    # First run — seed state, don't trigger
    if last_sha is None:
        state[args.board] = current_sha
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
        print(json.dumps({"should_test": "false", "commit_sha": current_sha, "reason": "first run — seeded"}))
        return

    # No change
    if last_sha == current_sha:
        print(json.dumps({"should_test": "false", "commit_sha": current_sha, "reason": "no change"}))
        return

    # Check for code files
    changed = get_changed_files(project_dir, last_sha, current_sha)
    code_changed = has_code_files(changed)

    # Update state
    state[args.board] = current_sha
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

    if code_changed:
        print(json.dumps({"should_test": "true", "commit_sha": current_sha}))
    else:
        print(json.dumps({"should_test": "false", "commit_sha": current_sha, "reason": "docs/specs only"}))


if __name__ == "__main__":
    main()
