#!/usr/bin/env python3
"""
Scout DB — helper for dedup, analytics, and topic tracking.

Usage:
  python3 scout-db.py dedup-check <url_or_id>          # Check if item already processed
  python3 scout-db.py register <url_or_id> <title> <depth> <wiki_note> [source_tier]
  python3 scout-db.py update <url_or_id>               # Bump update_count + last_updated
  python3 scout-db.py source-add <name> <url> <tier>
  python3 scout-db.py source-touch <name> [items] [deep_dives]
  python3 scout-db.py source-prune <name>              # Mark source as pruned (sets quality_score=0)
  python3 scout-db.py source-stats                     # Show source quality rankings
  python3 scout-db.py topic-touch <topic> [note]       # Track a topic/concept mention
  python3 scout-db.py topic-trending [days]            # Trending topics in last N days
  python3 scout-db.py stats                            # Overall vault stats
  python3 scout-db.py stale-notes [days]               # Notes not updated in N days
  python3 scout-db.py init                             # Initialize/create tables

The DB lives at ~/vault/meta/scout.db. All writes are atomic.
"""

import sqlite3
import hashlib
import sys
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

DB_PATH = os.path.expanduser("~/vault/meta/scout.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # crash-safe
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS processed (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash    TEXT UNIQUE NOT NULL,
            url         TEXT,
            arxiv_id    TEXT,
            title       TEXT NOT NULL,
            depth_tier  TEXT NOT NULL,        -- deep-dive | notable | signal
            wiki_note   TEXT,                  -- [[wiki-note-name]] or daily/YYYY-MM-DD
            source_tier TEXT,                  -- T1 | T2 | T3 | T4
            first_seen  TEXT NOT NULL,         -- ISO date
            last_updated TEXT NOT NULL,        -- ISO date
            update_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sources (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT UNIQUE NOT NULL,
            url             TEXT,
            tier            TEXT NOT NULL,      -- T1 | T2 | T3 | T4
            items_produced  INTEGER DEFAULT 0,
            deep_dives_produced INTEGER DEFAULT 0,
            first_seen      TEXT,
            last_seen       TEXT,
            quality_score   REAL DEFAULT 0,     -- computed: deep_dives / max(1, items)
            pruned          INTEGER DEFAULT 0   -- 1 = removed from active monitoring
        );

        CREATE TABLE IF NOT EXISTS topics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic           TEXT UNIQUE NOT NULL,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            mention_count   INTEGER DEFAULT 1,
            related_notes   TEXT                 -- comma-separated [[note]] links
        );

        CREATE INDEX IF NOT EXISTS idx_processed_hash ON processed(url_hash);
        CREATE INDEX IF NOT EXISTS idx_processed_arxiv ON processed(arxiv_id);
        CREATE INDEX IF NOT EXISTS idx_topics_last ON topics(last_seen);
    """)
    conn.commit()
    conn.close()
    print(f"OK: Database initialized at {DB_PATH}")

def make_hash(identifier):
    """Normalize an identifier (URL or arxiv ID) and hash it for dedup."""
    identifier = identifier.strip().lower()
    # Normalize arxiv URLs to just the ID
    if "arxiv.org/abs/" in identifier:
        identifier = identifier.split("arxiv.org/abs/")[-1].split("v")[0]
    elif "arxiv.org/pdf/" in identifier:
        identifier = identifier.split("arxiv.org/pdf/")[-1].replace(".pdf", "").split("v")[0]
    # Normalize trailing slashes
    identifier = identifier.rstrip("/")
    return hashlib.sha256(identifier.encode()).hexdigest()[:16], identifier

def extract_arxiv_id(identifier):
    """Extract arxiv ID if present, else None."""
    identifier = identifier.strip().lower()
    for prefix in ["arxiv.org/abs/", "arxiv.org/pdf/"]:
        if prefix in identifier:
            aid = identifier.split(prefix)[-1].replace(".pdf", "").split("v")[0]
            return aid
    return None

def dedup_check(identifier):
    """Check if an item has already been processed. Returns JSON-ish output."""
    h, normalized = make_hash(identifier)
    conn = get_db()
    row = conn.execute("SELECT * FROM processed WHERE url_hash = ?", (h,)).fetchone()
    conn.close()
    
    if row:
        print(f"DUPLICATE")
        print(f"hash:{h}")
        print(f"first_seen:{row['first_seen']}")
        print(f"depth:{row['depth_tier']}")
        print(f"wiki_note:{row['wiki_note']}")
        print(f"update_count:{row['update_count']}")
        print(f"title:{row['title']}")
    else:
        print("NEW")
        print(f"hash:{h}")

def register(identifier, title, depth, wiki_note, source_tier=None):
    """Register a new processed item."""
    h, normalized = make_hash(identifier)
    aid = extract_arxiv_id(identifier)
    now = datetime.now().isoformat(timespec="seconds")
    
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO processed (url_hash, url, arxiv_id, title, depth_tier, wiki_note, source_tier, first_seen, last_updated, update_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (h, normalized, aid, title, depth, wiki_note, source_tier, now, now))
        conn.commit()
        print(f"OK: Registered '{title}' [{depth}] -> {wiki_note}")
    except sqlite3.IntegrityError:
        print(f"WARN: Already registered (hash:{h}). Use 'update' instead.")
    conn.close()

def update(identifier):
    """Bump update count for an existing item (new info appended to wiki note)."""
    h, normalized = make_hash(identifier)
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    result = conn.execute("""
        UPDATE processed SET update_count = update_count + 1, last_updated = ?
        WHERE url_hash = ?
    """, (now, h))
    conn.commit()
    if result.rowcount > 0:
        print(f"OK: Updated (hash:{h}, new count: will be fetched)")
    else:
        print(f"ERROR: Not found (hash:{h}). Use 'register' first.")
    conn.close()

def source_add(name, url, tier):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO sources (name, url, tier, first_seen, last_seen, quality_score)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (name, url, tier, now, now))
        conn.commit()
        print(f"OK: Source '{name}' added as {tier}")
    except sqlite3.IntegrityError:
        print(f"WARN: Source '{name}' already exists.")
    conn.close()

def source_touch(name, items=1, deep_dives=0):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    row = conn.execute("SELECT * FROM sources WHERE name = ?", (name,)).fetchone()
    if row:
        new_items = row["items_produced"] + items
        new_deep = row["deep_dives_produced"] + deep_dives
        score = new_deep / max(1, new_items)
        conn.execute("""
            UPDATE sources SET items_produced = ?, deep_dives_produced = ?, 
            last_seen = ?, quality_score = ?
            WHERE name = ?
        """, (new_items, new_deep, now, score, name))
        conn.commit()
        print(f"OK: '{name}' now {new_items} items, {new_deep} deep-dives, score={score:.2f}")
    else:
        print(f"ERROR: Source '{name}' not found. Use 'source-add' first.")
    conn.close()

def source_prune(name):
    conn = get_db()
    conn.execute("UPDATE sources SET pruned = 1 WHERE name = ?", (name,))
    conn.commit()
    print(f"OK: Source '{name}' marked as pruned")
    conn.close()

def source_stats():
    conn = get_db()
    rows = conn.execute("""
        SELECT name, tier, items_produced, deep_dives_produced, quality_score, pruned, last_seen
        FROM sources WHERE pruned = 0
        ORDER BY quality_score DESC, deep_dives_produced DESC
    """).fetchall()
    conn.close()
    if not rows:
        print("No sources tracked yet.")
        return
    print(f"{'Source':<35} {'Tier':<4} {'Items':>5} {'Deep':>5} {'Score':>6} {'Last Seen'}")
    print("-" * 85)
    for r in rows:
        print(f"{r['name']:<35} {r['tier']:<4} {r['items_produced']:>5} {r['deep_dives_produced']:>5} {r['quality_score']:>6.2f} {r['last_seen'][:10]}")

def topic_touch(topic, note=None):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    row = conn.execute("SELECT * FROM topics WHERE topic = ?", (topic,)).fetchone()
    if row:
        new_count = row["mention_count"] + 1
        related = row["related_notes"] or ""
        if note and note not in related:
            related = (related + "," + note).strip(",") if related else note
        conn.execute("""
            UPDATE topics SET mention_count = ?, last_seen = ?, related_notes = ?
            WHERE topic = ?
        """, (new_count, now, related, topic))
        conn.commit()
        print(f"OK: Topic '{topic}' now {new_count} mentions")
    else:
        conn.execute("""
            INSERT INTO topics (topic, first_seen, last_seen, mention_count, related_notes)
            VALUES (?, ?, ?, 1, ?)
        """, (topic, now, now, note))
        conn.commit()
        print(f"OK: New topic '{topic}' registered")
    conn.close()

def topic_trending(days=7):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    conn = get_db()
    rows = conn.execute("""
        SELECT topic, mention_count, last_seen, related_notes
        FROM topics WHERE last_seen >= ? AND topic != ''
        ORDER BY mention_count DESC, last_seen DESC
        LIMIT 20
    """, (cutoff,)).fetchall()
    conn.close()
    if not rows:
        print(f"No topics active in last {days} days.")
        return
    print(f"📈 Trending topics (last {days} days):")
    print(f"{'Topic':<40} {'Mentions':>8} {'Last Seen':<12}")
    print("-" * 65)
    for r in rows:
        print(f"{r['topic']:<40} {r['mention_count']:>8} {r['last_seen'][:10]}")

def stats():
    conn = get_db()
    p_count = conn.execute("SELECT COUNT(*) as c FROM processed").fetchone()["c"]
    p_deep = conn.execute("SELECT COUNT(*) as c FROM processed WHERE depth_tier = 'deep-dive'").fetchone()["c"]
    p_notable = conn.execute("SELECT COUNT(*) as c FROM processed WHERE depth_tier = 'notable'").fetchone()["c"]
    p_signal = conn.execute("SELECT COUNT(*) as c FROM processed WHERE depth_tier = 'signal'").fetchone()["c"]
    p_updates = conn.execute("SELECT SUM(update_count) as c FROM processed").fetchone()["c"] or 0
    s_active = conn.execute("SELECT COUNT(*) as c FROM sources WHERE pruned = 0").fetchone()["c"]
    s_pruned = conn.execute("SELECT COUNT(*) as c FROM sources WHERE pruned = 1").fetchone()["c"]
    t_count = conn.execute("SELECT COUNT(*) as c FROM topics").fetchone()["c"]
    
    print("📊 Vault Statistics")
    print("=" * 50)
    print(f"Items processed:    {p_count}")
    print(f"  Deep-dives:       {p_deep}")
    print(f"  Notable:          {p_notable}")
    print(f"  Signal:           {p_signal}")
    print(f"  Updates (append): {p_updates}")
    print(f"Sources tracked:    {s_active} active, {s_pruned} pruned")
    print(f"Topics tracked:     {t_count}")
    conn.close()

def stale_notes(days=30):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    conn = get_db()
    rows = conn.execute("""
        SELECT title, wiki_note, last_updated, depth_tier
        FROM processed 
        WHERE depth_tier IN ('deep-dive', 'notable') 
          AND last_updated < ?
        ORDER BY last_updated ASC
        LIMIT 20
    """, (cutoff,)).fetchall()
    conn.close()
    if not rows:
        print(f"No stale notes (all deep-dive/notable updated within {days} days).")
        return
    print(f"📋 Stale notes (not updated in {days}+ days):")
    print(f"{'Title':<50} {'Last Updated':<12} {'Note'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['title'][:50]:<50} {r['last_updated'][:10]:<12} {r['wiki_note']}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        init()
    elif cmd == "dedup-check":
        if len(sys.argv) < 3:
            print("ERROR: Missing identifier. Usage: dedup-check <url_or_id>")
            sys.exit(1)
        dedup_check(sys.argv[2])
    elif cmd == "register":
        if len(sys.argv) < 6:
            print("ERROR: Usage: register <url> <title> <depth> <wiki_note> [source_tier]")
            sys.exit(1)
        source_tier = sys.argv[5] if len(sys.argv) > 5 else None
        register(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "", source_tier)
    elif cmd == "update":
        if len(sys.argv) < 3:
            print("ERROR: Missing identifier. Usage: update <url_or_id>")
            sys.exit(1)
        update(sys.argv[2])
    elif cmd == "source-add":
        if len(sys.argv) < 5:
            print("ERROR: Usage: source-add <name> <url> <tier>")
            sys.exit(1)
        source_add(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "source-touch":
        if len(sys.argv) < 3:
            print("ERROR: Usage: source-touch <name> [items] [deep_dives]")
            sys.exit(1)
        items = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        deep = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        source_touch(sys.argv[2], items, deep)
    elif cmd == "source-prune":
        if len(sys.argv) < 3:
            print("ERROR: Usage: source-prune <name>")
            sys.exit(1)
        source_prune(sys.argv[2])
    elif cmd == "source-stats":
        source_stats()
    elif cmd == "topic-touch":
        if len(sys.argv) < 3:
            print("ERROR: Usage: topic-touch <topic> [note]")
            sys.exit(1)
        note = sys.argv[3] if len(sys.argv) > 3 else None
        topic_touch(sys.argv[2], note)
    elif cmd == "topic-trending":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        topic_trending(days)
    elif cmd == "stats":
        stats()
    elif cmd == "stale-notes":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        stale_notes(days)
    else:
        print(f"ERROR: Unknown command '{cmd}'")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
