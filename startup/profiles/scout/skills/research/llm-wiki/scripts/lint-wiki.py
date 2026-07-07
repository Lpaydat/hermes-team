#!/usr/bin/env python3
"""Wiki linter — works in both interactive and cron/headless sessions.

Usage:
    python3 scripts/lint-wiki.py /path/to/wiki

Checks:
    1. Orphan pages (no inbound wikilinks)
    2. Broken wikilinks (point to non-existent pages)
    3. Index completeness (pages missing from index.md)
    4. Pages over 200 lines
    5. Missing required frontmatter fields

Cron-safe: no execute_code needed, no heredocs, no pipes.
"""
import sys
import os
import re
from collections import defaultdict

def main():
    if len(sys.argv) < 2:
        print("Usage: lint-wiki.py <wiki-path>")
        sys.exit(1)
    
    wiki = sys.argv[1]
    if not os.path.isdir(wiki):
        print(f"Error: {wiki} is not a directory")
        sys.exit(1)
    
    # Collect all .md files
    wiki_dirs = ['wiki', 'entities', 'concepts', 'comparisons', 'queries']
    all_pages = {}  # slug -> filepath
    page_links = defaultdict(set)  # page -> set of outbound links
    inbound_links = defaultdict(set)  # page -> set of pages linking to it
    
    for d in wiki_dirs:
        dirpath = os.path.join(wiki, d)
        if not os.path.isdir(dirpath):
            continue
        for fname in os.listdir(dirpath):
            if fname.endswith('.md'):
                slug = fname[:-3]  # remove .md
                filepath = os.path.join(dirpath, fname)
                all_pages[slug] = filepath
    
    # Also check daily/ for signal items (don't lint, just skip)
    
    # Extract links from each page
    link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
    for slug, filepath in all_pages.items():
        with open(filepath, 'r') as f:
            content = f.read()
        links = link_pattern.findall(content)
        for link in links:
            # Handle [[link|alias]] format
            target = link.split('|')[0].strip()
            page_links[slug].add(target)
            inbound_links[target].add(slug)
    
    issues = []
    
    # 1. Orphan pages
    for slug in sorted(all_pages.keys()):
        if slug not in inbound_links or len(inbound_links[slug]) == 0:
            issues.append(('orphan', slug, all_pages[slug]))
    
    # 2. Broken wikilinks
    for slug, links in page_links.items():
        for target in links:
            if target not in all_pages:
                issues.append(('broken-link', f'{slug} -> [[{target}]]', ''))
    
    # 3. Index completeness
    index_path = os.path.join(wiki, 'index.md')
    index_content = ''
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            index_content = f.read()
    for slug in sorted(all_pages.keys()):
        if f'[[{slug}]]' not in index_content:
            issues.append(('missing-from-index', slug, all_pages[slug]))
    
    # 4. Pages over 200 lines
    for slug, filepath in all_pages.items():
        with open(filepath, 'r') as f:
            lines = f.readlines()
        if len(lines) > 200:
            issues.append(('over-200-lines', f'{slug} ({len(lines)} lines)', filepath))
    
    # 5. Missing frontmatter
    required_fields = ['title', 'created', 'updated', 'type', 'tags']
    for slug, filepath in all_pages.items():
        with open(filepath, 'r') as f:
            content = f.read()
        if not content.startswith('---'):
            issues.append(('missing-frontmatter', slug, filepath))
            continue
        # Extract frontmatter block
        parts = content.split('---', 2)
        if len(parts) < 3:
            issues.append(('malformed-frontmatter', slug, filepath))
            continue
        fm = parts[1]
        for field in required_fields:
            if field + ':' not in fm:
                issues.append(('missing-field', f'{slug}: missing "{field}"', filepath))
    
    # Report
    print(f"Wiki Lint Report: {wiki}")
    print(f"Total pages: {len(all_pages)}")
    print(f"Total issues: {len(issues)}")
    print()
    
    severity_order = ['broken-link', 'orphan', 'missing-frontmatter', 'missing-field', 
                      'malformed-frontmatter', 'missing-from-index', 'over-200-lines']
    for severity in severity_order:
        matching = [i for i in issues if i[0] == severity]
        if matching:
            print(f"## {severity.upper()} ({len(matching)})")
            for _, desc, path in matching:
                print(f"  - {desc}" + (f" ({path})" if path else ""))
            print()

if __name__ == '__main__':
    main()
