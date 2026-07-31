#!/usr/bin/env python3
"""Parse idea-bank.md, output top ideas as JSON for the workflow engine foreach node.

Replaces the awk/sed parsing in queue-builds.sh.
Outputs: {"ideas": [{"slug": "...", "name": "...", "score": N}, ...], "count": N}

Usage:
    python3 parse-idea-bank.py [--board hermes-hq] [--max 10] [--slugs slug1,slug2]
"""
import argparse
import json
import re
import sys
import subprocess
from pathlib import Path

IDEA_BANK = Path.home() / "vault/ventures/idea-bank.md"


def parse_idea_bank(max_items=10):
    """Parse idea-bank.md markdown tables into a list of idea dicts."""
    if not IDEA_BANK.exists():
        return []

    raw = IDEA_BANK.read_text()
    ideas = []

    for line in raw.split("\n"):
        # Match table rows: | N | score | origin | name | [dossier](ideas/slug.md) | status |
        m = re.match(r"\|*\s*(\d+)\s*\|\s*(\d+)/25\s*\|\s*(\w)\s*\|\s*(.+?)\s*\|\s*\[dossier\]\(ideas/(.+?)\.md\)\s*\|\s*(\w+)\s*\|", line)
        if not m:
            continue

        num, score, origin, name, slug, status = m.groups()
        score = int(score)

        # Skip ideas already built/grilling/building
        if status in ("BUILT_AWAITING_REVIEW", "IN_GRILL", "building"):
            continue

        ideas.append({
            "slug": slug,
            "name": name.strip(),
            "score": score,
            "origin": origin,
            "status": status,
        })

    # Sort by score descending
    ideas.sort(key=lambda x: x["score"], reverse=True)

    # Take top N
    return ideas[:max_items]


def dedup_against_board(ideas, board="hermes-hq"):
    """Remove ideas that already have kanban cards on the board."""
    try:
        result = subprocess.run(
            ["hermes", "kanban", "--board", board, "list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ideas  # fail-open: no dedup if list fails

        tasks = json.loads(result.stdout)
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks", [])

        existing_slugs = set()
        existing_names = set()
        for t in tasks:
            title = (t.get("title") or "").lower()
            body = (t.get("body") or "").lower()
            combined = title + " " + body
            # Check for slug in combined text
            for idea in ideas:
                if idea["slug"].lower() in combined:
                    existing_slugs.add(idea["slug"])
                if idea["name"].lower() in title:
                    existing_names.add(idea["name"])

    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
        return ideas  # fail-open

    return [i for i in ideas if i["slug"] not in existing_slugs and i["name"] not in existing_names]


def main():
    parser = argparse.ArgumentParser(description="Parse idea-bank.md for workflow engine")
    parser.add_argument("--board", default="hermes-hq", help="Kanban board for dedup")
    parser.add_argument("--max", type=int, default=10, help="Max ideas to output")
    parser.add_argument("--slugs", default="", help="Comma-separated specific slugs (overrides parsing)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip board dedup check")
    args = parser.parse_args()

    if args.slugs:
        # Targeted mode: use specific slugs
        ideas = []
        for slug in args.slugs.split(","):
            slug = slug.strip()
            if not slug:
                continue
            name = slug.replace("-", " ").title()
            # Try to get real name from dossier
            dossier = Path.home() / f"vault/ventures/ideas/{slug}.md"
            if dossier.exists():
                for line in dossier.read_text().split("\n")[:10]:
                    if line.startswith("# "):
                        name = line[2:].split("—")[0].split("|")[0].strip()
                        break
            ideas.append({"slug": slug, "name": name, "score": 0, "origin": "D", "status": "unbuilt"})
    else:
        ideas = parse_idea_bank(args.max)

    if not args.no_dedup and ideas:
        ideas = dedup_against_board(ideas, args.board)

    output = {"ideas": ideas, "count": len(ideas)}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
