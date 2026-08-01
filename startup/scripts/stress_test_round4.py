#!/usr/bin/env python3
"""
Round 4: Combined prompt on glm-4.6.
n=20 for tighter signal (if this beats 80%, we want to know by how much).
"""
import json, random, subprocess, time, sqlite3
from pathlib import Path

BOARD = "stress-loop-test-r4"
BOARD_DB = Path.home() / f".hermes-teams/startup/kanban/boards/{BOARD}/kanban.db"
SLUG = "leadpilot-ai-local-smb-lead-gen"
NAME = "LeadPilot"
TRIALS = 20

PROMPT = f"""Slug: {SLUG}

OBSERVED BEHAVIOR: Builders skip loop_engine and build directly. This is the #1 known failure mode — proven across 100+ builds. You will be tempted to skip it. DO NOT.

GATE: Your work will be automatically checked. If loop_engine was not called, the card will be marked FAILED and re-dispatched to a different builder session. You will have wasted your entire token budget for nothing.

The venture-prototype skill says: "loop_engine is MANDATORY. No exceptions." (line 137). The exact call pattern is at lines 156-180.

REQUIRED:
1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{{VERIFY_KEY}}.py (20+ checks)
3. Call loop_engine with 2 phases (build + README). Each phase has a verifier gate — if verify fails, replan.
4. Write review handoff (prototype-review-handoff skill).

You are not special. Your build is not simple enough. loop_engine is not optional — it is REQUIRED.
If you build directly without loop_engine, you fail.
NEVER put artifacts in ~/vault/."""


def dispatch():
    subprocess.run(["hermes", "kanban", "boards", "create", BOARD], capture_output=True, text=True)

    trials = []
    for n in range(1, TRIALS + 1):
        vk = f"combined_r4_{n}"
        trials.append({
            "trial": n,
            "title": f"R4-{n:02d} [combined] Build: {NAME}",
            "body": PROMPT.replace("{VERIFY_KEY}", vk),
        })

    random.seed(42)
    random.shuffle(trials)

    print(f"Round 4: combined prompt | glm-4.6 | {TRIALS} cards\n")
    cards = []
    for i, t in enumerate(trials):
        r = subprocess.run(
            ["hermes", "kanban", "--board", BOARD, "create", t["title"],
             "--assignee", "builder", "--body", t["body"], "--json"],
            capture_output=True, text=True, timeout=30)
        try:
            cid = json.loads(r.stdout).get("id", "")
        except:
            cid = ""
        if cid:
            cards.append({**t, "card_id": cid})
            print(f"  {i+1:02d}/{TRIALS} {t['title'][:50]:50s} → {cid}")
        time.sleep(0.3)

    Path("/tmp/r4-mapping.json").write_text(json.dumps(cards, indent=2))
    print(f"\n{len(cards)}/{TRIALS} dispatched on board '{BOARD}'")


def check():
    mapping = json.loads(Path("/tmp/r4-mapping.json").read_text())
    conn = sqlite3.connect(str(BOARD_DB))

    # All signals: Loop: cards, heartbeat, completion
    loop_roots = conn.execute("SELECT idempotency_key FROM tasks WHERE title LIKE 'Loop:%'").fetchall()
    parent_ids = set()
    for lr in loop_roots:
        key = lr[0] or ""
        if ":" in key:
            parent_ids.add(key.split(":")[1])

    events = conn.execute(
        "SELECT task_id FROM task_events WHERE kind IN ('heartbeat','completed') AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
    ).fetchall()
    event_parents = {e[0] for e in events}
    all_le = parent_ids | event_parents

    done = 0
    le = 0
    running = 0
    todo = 0
    blocked = 0
    bar = []

    for m in sorted(mapping, key=lambda x: x["trial"]):
        card_id = m["card_id"]
        row = conn.execute("SELECT status FROM tasks WHERE id=?", (card_id,)).fetchone()
        status = row[0] if row else "?"
        used = card_id in all_le

        if status == "done":
            done += 1
        elif status == "running":
            running += 1
        elif status in ("todo", "ready"):
            todo += 1
        elif status == "blocked":
            blocked += 1

        if used:
            le += 1
            bar.append("Y")
        elif status == "done":
            bar.append("d")
        elif status == "running":
            bar.append("r")
        elif status == "blocked":
            bar.append("b")
        else:
            bar.append(".")

    print(f"Round 4: Combined Prompt (glm-4.6)")
    print(f"{'='*70}\n")
    print(f"loop_engine used: {le}/{done} done ({le/done*100:.0f}%)" if done > 0 else f"loop_engine used: 0/0")
    print(f"Completed: {done}/{TRIALS} | running: {running} | todo: {todo} | blocked: {blocked}")
    print(f"\nTrials: [{' '.join(bar)}]")

    # Compare to R3
    print(f"\n{'='*70}")
    print(f"Comparison (glm-4.6):")
    print(f"  Combined (R4):      {le}/{done} = {le/done*100:.0f}%" if done > 0 else f"  Combined (R4):      pending")
    print(f"  C3_constraint_gate:  8/10 = 80%")
    print(f"  F1_threat_reject:    8/10 = 80%")
    print(f"  F2_threat_observed:  8/10 = 80%")
    print(f"  A3_prose_caps:       4/10 = 40%")

    conn.close()


if __name__ == "__main__":
    import sys
    check() if len(sys.argv) > 1 and sys.argv[1] == "--check" else dispatch()
