#!/usr/bin/env python3
"""
Task Hygiene Scanner — scans a beads project for structural task problems.

Outputs a JSON report. Empty findings = silent (exit 0, no output).
Designed to run as a cron script (no_agent=True pattern).

Usage:
    scan_hygiene.py <project_dir> [--stale-days 14] [--kill-days 30]
"""
import sys
import os
import json
import subprocess
from datetime import datetime, timezone


def run_bd(project_dir, args):
    """Run a bd command in a project directory and return parsed JSON."""
    try:
        result = subprocess.run(
            ["bd"] + args,
            capture_output=True, text=True,
            cwd=project_dir,
            timeout=30
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout.strip(), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def parse_issues(project_dir):
    """Get all issues from bd as a list of dicts."""
    out, err = run_bd(project_dir, ["list", "--json"])
    if err:
        return [], err
    if not out:
        return [], None
    try:
        return json.loads(out), None
    except json.JSONDecodeError:
        return [], "failed to parse bd output"


def check_orphans(issues):
    """Find issues with no parent epic."""
    orphans = []
    for issue in issues:
        if issue.get("status") in ("closed", "done"):
            continue
        has_parent = bool(issue.get("parent"))
        is_epic = (
            "[epic]" in issue.get("title", "").lower()
            or issue.get("type") == "epic"
            or issue.get("issue_type") == "epic"
        )
        labels = issue.get("labels", [])
        is_standalone_allowed = any(
            l in labels for l in ("chore", "tech-debt", "infra", "docs")
        )
        if not has_parent and not is_epic and not is_standalone_allowed:
            orphans.append(issue)
    return orphans


def check_unlabeled(issues):
    """Find issues with no labels."""
    unlabeled = []
    for issue in issues:
        if issue.get("status") in ("closed", "done"):
            continue
        labels = issue.get("labels", [])
        if not labels:
            unlabeled.append(issue)
    return unlabeled


def check_stale(issues, stale_days=14, kill_days=30):
    """Find stale issues based on last modified time."""
    stale = []
    kill_candidates = []
    now = datetime.now(timezone.utc)

    for issue in issues:
        if issue.get("status") in ("closed", "done"):
            continue
        # Don't flag in_progress, blocked, or already-deferred (deferred = already parked)
        if issue.get("status") in ("in_progress", "blocked", "deferred"):
            continue

        updated = (
            issue.get("updated_at")
            or issue.get("updated")
            or issue.get("mtime")
            or issue.get("modified")
        )
        if not updated:
            continue

        try:
            # Handle various timestamp formats
            dt_str = updated.replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (now - dt).days
        except (ValueError, AttributeError):
            continue

        if age_days >= kill_days:
            kill_candidates.append({**issue, "_age_days": age_days})
        elif age_days >= stale_days:
            stale.append({**issue, "_age_days": age_days})

    return stale, kill_candidates


def check_duplicates(issues):
    """Detect potential duplicates by title word overlap."""
    open_issues = [i for i in issues if i.get("status") not in ("closed", "done")]
    suspects = []
    seen = set()

    for i, a in enumerate(open_issues):
        words_a = set(a.get("title", "").lower().split())
        if len(words_a) < 3:
            continue
        for b in open_issues[i + 1:]:
            pair_key = tuple(sorted([a.get("id", ""), b.get("id", "")]))
            if pair_key in seen:
                continue
            words_b = set(b.get("title", "").lower().split())
            if not words_b:
                continue
            overlap = len(words_a & words_b) / len(words_a | words_b)
            if overlap > 0.7:
                seen.add(pair_key)
                suspects.append({
                    "issue_a": {"id": a.get("id"), "title": a.get("title")},
                    "issue_b": {"id": b.get("id"), "title": b.get("title")},
                    "overlap": round(overlap, 2),
                })
    return suspects


def main():
    if len(sys.argv) < 2:
        print("Usage: scan_hygiene.py <project_dir> [--stale-days N] [--kill-days N]", file=sys.stderr)
        sys.exit(1)

    project_dir = os.path.abspath(sys.argv[1])
    stale_days = 14
    kill_days = 30

    # Parse args
    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--stale-days" and i + 1 < len(args):
            stale_days = int(args[i + 1])
        elif arg == "--kill-days" and i + 1 < len(args):
            kill_days = int(args[i + 1])

    # Check project exists
    if not os.path.isdir(project_dir):
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Check .beads exists
    if not os.path.isdir(os.path.join(project_dir, ".beads")):
        # No beads = no issues = silent exit
        sys.exit(0)

    # Parse issues
    issues, err = parse_issues(project_dir)
    if err:
        print(f"Error reading issues: {err}", file=sys.stderr)
        sys.exit(0)  # Don't fail loud — just skip this project

    open_issues = [i for i in issues if i.get("status") not in ("closed", "done")]
    if not open_issues:
        # No open issues = clean = silent
        sys.exit(0)

    # Run checks
    orphans = check_orphans(issues)
    unlabeled = check_unlabeled(issues)
    stale, kill_candidates = check_stale(issues, stale_days, kill_days)
    duplicates = check_duplicates(issues)

    # Build report
    report = {
        "project": os.path.basename(project_dir),
        "project_dir": project_dir,
        "scanned": len(open_issues),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "findings": {
            "orphans": len(orphans),
            "unlabeled": len(unlabeled),
            "stale": len(stale),
            "kill_candidates": len(kill_candidates),
            "duplicate_suspects": len(duplicates),
        },
        "details": {
            "orphans": [
                {"id": i.get("id"), "title": i.get("title", "")[:80]}
                for i in orphans
            ],
            "unlabeled": [
                {"id": i.get("id"), "title": i.get("title", "")[:80]}
                for i in unlabeled
            ],
            "stale": [
                {"id": i.get("id"), "age_days": i.get("_age_days", 0), "title": i.get("title", "")[:80]}
                for i in stale
            ],
            "kill_candidates": [
                {"id": i.get("id"), "age_days": i.get("_age_days", 0), "title": i.get("title", "")[:80]}
                for i in kill_candidates
            ],
            "duplicate_suspects": duplicates,
        },
    }

    # Silent if no findings
    total_findings = sum(report["findings"].values())
    if total_findings == 0:
        sys.exit(0)

    # Output report as JSON to stdout
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
