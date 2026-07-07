#!/usr/bin/env python3
"""
Parse all fetched source files for the daily scout.
Expected inputs (downloaded by curl in Phase 1):
  /tmp/arxiv_raw.xml     — arXiv Atom XML (cs.AI+CL+LG)
  /tmp/hn_all.json       — Hacker News Algolia JSON
  /tmp/sw_feed.xml       — Simon Willison Atom feed
  /tmp/reddit_ll.xml     — Reddit r/LocalLLaMA RSS (Atom format)

Usage:
  python3 scripts/parse-sources.py [--days N]

Output: prints all candidate items grouped by source.
"""
import json
import xml.etree.ElementTree as ET
import re
import sys
import os
from datetime import datetime, timedelta

# Default: look back 2 days (arXiv submission lag)
DAYS_BACK = 2

if '--days' in sys.argv:
    idx = sys.argv.index('--days')
    DAYS_BACK = int(sys.argv[idx + 1])

today = datetime.now().strftime('%Y-%m-%d')
cutoff = (datetime.now() - timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')

NS = {
    'a': 'http://www.w3.org/2005/Atom',
    'arxiv': 'http://arxiv.org/schemas/atom',
}

AI_KEYWORDS = [
    'ai', 'llm', 'gpt', 'agent', 'model', 'openai', 'anthropic', 'gemini',
    'claude', 'diffusion', 'transformer', 'neural', 'ml', 'machine learning',
    'deep learning', 'copilot', 'chatbot', 'rag', 'fine-tun', 'inference',
    'gpu', 'cuda', 'pytorch', 'tensorflow', 'hugging', 'mistral', 'llama',
    'deepseek', 'qwen', 'grok', 'reasoning', 'chain of thought', 'embedding',
    'vector', 'langchain', 'generative', 'stable diffusion', 'midjourney',
    'sora', 'voice', 'speech', 'ocr', 'vision', 'multimodal', 'open source',
]


def parse_arxiv():
    path = '/tmp/arxiv_raw.xml'
    if not os.path.exists(path):
        print("  [SKIP] arxiv_raw.xml not found")
        return
    tree = ET.parse(path)
    root = tree.getroot()
    entries = root.findall('a:entry', NS)
    for entry in entries:
        title = re.sub(r'\s+', ' ', entry.find('a:title', NS).text.strip())
        arxiv_id = entry.find('a:id', NS).text.strip().split('/abs/')[-1]
        published = entry.find('a:published', NS).text[:10]
        if published < cutoff:
            continue
        authors_els = entry.findall('a:author', NS)
        authors = ', '.join(a.find('a:name', NS).text for a in authors_els[:3])
        if len(authors_els) > 3:
            authors += f" +{len(authors_els) - 3} more"
        summary = re.sub(r'\s+', ' ', entry.find('a:summary', NS).text.strip())[:300]
        cats = ', '.join(c.get('term') for c in entry.findall('a:category', NS))
        print(f"[{arxiv_id}] {title}")
        print(f"  Published: {published} | Cats: {cats}")
        print(f"  Authors: {authors}")
        print(f"  Abstract: {summary}...")
        print(f"  URL: https://arxiv.org/abs/{arxiv_id}")
        print()


def parse_hn():
    path = '/tmp/hn_all.json'
    if not os.path.exists(path):
        print("  [SKIP] hn_all.json not found")
        return
    with open(path) as f:
        data = json.load(f)
    hits = data.get('hits', [])
    print(f"Total frontpage hits: {len(hits)}\n")
    for hit in hits:
        title = hit.get('title', '')
        title_lower = title.lower()
        points = hit.get('points', 0)
        url = hit.get('url', '') or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        if any(kw in title_lower for kw in AI_KEYWORDS) and points >= 50:
            print(f"[{points} pts] {title}")
            print(f"  URL: {url}")
            print()


def parse_simon_willison():
    path = '/tmp/sw_feed.xml'
    if not os.path.exists(path):
        print("  [SKIP] sw_feed.xml not found")
        return
    tree = ET.parse(path)
    root = tree.getroot()
    entries = root.findall('a:entry', NS)
    for entry in entries[:20]:
        title = entry.find('a:title', NS).text.strip()
        link_el = entry.find('a:link', NS)
        link = link_el.get('href') if link_el is not None else ''
        published = entry.find('a:published', NS).text[:10]
        if published < cutoff:
            continue
        summary_el = entry.find('a:summary', NS)
        summary = ''
        if summary_el is not None and summary_el.text:
            summary = re.sub(r'<[^>]+>', '', summary_el.text)
            summary = re.sub(r'\s+', ' ', summary).strip()[:150]
        print(f"[{published}] {title}")
        print(f"  URL: {link}")
        if summary:
            print(f"  Summary: {summary}...")
        print()


def parse_reddit_rss():
    feeds = {
        'r/LocalLLaMA': '/tmp/reddit_ll.xml',
    }
    for name, path in feeds.items():
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"  [SKIP] {name}: file not found or empty")
            continue
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            entries = root.findall('a:entry', NS)
            for entry in entries[:10]:
                title = entry.find('a:title', NS).text.strip()
                link = entry.find('a:id', NS).text.strip()
                published = entry.find('a:updated', NS)
                pub_date = published.text[:10] if published is not None and published.text else ''
                content_el = entry.find('a:content', NS)
                content = ''
                if content_el is not None and content_el.text:
                    content = re.sub(r'<[^>]+>', '', content_el.text).strip()[:200]
                print(f"[{pub_date}] {title}")
                print(f"  URL: {link}")
                if content:
                    print(f"  Content: {content[:150]}...")
                print()
        except ET.ParseError as e:
            print(f"  [ERROR] {name}: XML parse failed: {e}")


if __name__ == '__main__':
    print(f"Cutoff date: {cutoff} (looking back {DAYS_BACK} days)")
    print()

    print("=" * 60)
    print("ARXIV (cs.AI + cs.CL + cs.LG)")
    print("=" * 60)
    parse_arxiv()

    print("\n" + "=" * 60)
    print("HACKER NEWS (frontpage, AI-filtered)")
    print("=" * 60)
    parse_hn()

    print("\n" + "=" * 60)
    print("SIMON WILLISON")
    print("=" * 60)
    parse_simon_willison()

    print("\n" + "=" * 60)
    print("REDDIT")
    print("=" * 60)
    parse_reddit_rss()
