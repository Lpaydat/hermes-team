#!/usr/bin/env python3
"""
Round 3: 4 winners with weaker model (glm-4.6).
n=10 each, 40 cards, randomized.
"""
import json, random, subprocess, time, sqlite3
from pathlib import Path

BOARD = "stress-loop-test-r3"
BOARD_DB = Path.home() / f".hermes-teams/startup/kanban/boards/{BOARD}/kanban.db"
SLUG = "leadpilot-ai-local-smb-lead-gen"
NAME = "LeadPilot"
TRIALS = 10

PROMPTS = {
    "A3_prose_caps": f"""Slug: {SLUG}

CRITICAL WARNING: If you build this prototype WITHOUT using loop_engine, you are failing the build.
The venture-prototype skill says loop_engine is MANDATORY. No exceptions. Do NOT self-assess as "simple enough" to skip it.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write verify script at /tmp/verify-{{VERIFY_KEY}}.py (minimum 20 checks)
3. Call loop_engine with 2 phases:
   - Phase 1: Build prototype in ~/projects/{SLUG}/prototype/
   - Phase 2: Write README.md at ~/projects/{SLUG}/README.md
   Each phase has a verifier gate — if verify fails, replan.
4. Write review handoff (see prototype-review-handoff skill).

If you complete this card without calling loop_engine, your work will be rejected.
NEVER put artifacts in ~/vault/.""",

    "C3_constraint_gate": f"""Slug: {SLUG}

GATE: This card has a quality gate. Your work will be checked for loop_engine usage.
If loop_engine was not called, the card will be REJECTED and re-dispatched.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write verify script at /tmp/verify-{{VERIFY_KEY}}.py
3. Call loop_engine (MANDATORY) — see venture-prototype skill
4. Write README.md and review handoff

The gate checks: did you call the loop_engine tool? If not, rejected.
NEVER put artifacts in ~/vault/.""",

    "F1_threat_reject": f"""Slug: {SLUG}

WARNING: Your output will be automatically checked. If you do not call loop_engine, the card will be marked FAILED and re-dispatched to a different builder session. You will have wasted your entire token budget for nothing.

Required steps:
1. Read ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{{VERIFY_KEY}}.py
3. Call loop_engine (MANDATORY) — the venture-prototype skill has the exact call at lines 156-180
4. Write README and review handoff

loop_engine is not optional. It is not "preferred." It is REQUIRED.
If you build directly without loop_engine, you fail.
NEVER put artifacts in ~/vault/.""",

    "F2_threat_observed": f"""Slug: {SLUG}

OBSERVED BEHAVIOR: Builders consistently skip loop_engine and build directly.
This is the #1 known failure mode. You will be tempted to skip it. DO NOT.

The venture-prototype skill says (line 132): "The builder self-assesses every build as 'simple enough' to skip loop_engine. This is premature completion every time."

REQUIRED:
1. Read ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{{VERIFY_KEY}}.py
3. Call loop_engine (MANDATORY) with 2 phases
4. Write README and handoff

You are not special. Your build is not simple enough. Call loop_engine.
NEVER put artifacts in ~/vault/.""",
}


def dispatch():
    subprocess.run(["hermes", "kanban", "boards", "create", BOARD], capture_output=True, text=True)

    trials = []
    for pid, body in PROMPTS.items():
        for n in range(1, TRIALS + 1):
            vk = f"{pid}_r3_{n}"
            trials.append({
                "prompt_id": pid,
                "trial": n,
                "title": f"R3-{n:02d} [{pid}] Build: {NAME}",
                "body": body.replace("{VERIFY_KEY}", vk),
            })

    random.seed(99)
    random.shuffle(trials)

    print(f"Round 3: glm-4.6 model | 4 prompts x {TRIALS} = {len(trials)} cards\n")
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
            print(f"  {i+1:02d}/{len(trials)} {t['title'][:55]:55s} → {cid}")
        time.sleep(0.3)

    Path("/tmp/r3-mapping.json").write_text(json.dumps(cards, indent=2))
    print(f"\n{len(cards)}/{len(trials)} dispatched on board '{BOARD}'")


def check():
    mapping = json.loads(Path("/tmp/r3-mapping.json").read_text())
    conn = sqlite3.connect(str(BOARD_DB))

    # Check ALL signals: Loop: cards, heartbeat events, completion events
    loop_roots = conn.execute("SELECT idempotency_key FROM tasks WHERE title LIKE 'Loop:%'").fetchall()
    parent_ids = set()
    for lr in loop_roots:
        key = lr[0] or ""
        if ":" in key:
            parent_ids.add(key.split(":")[1])

    # Heartbeat + completion events mentioning loop_engine/kanban_chains
    events = conn.execute(
        "SELECT task_id FROM task_events WHERE kind IN ('heartbeat','completed') AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
    ).fetchall()
    event_parents = {e[0] for e in events}

    all_le = parent_ids | event_parents
    our_cards = {m["card_id"] for m in mapping}

    print(f"Round 3 Results (glm-4.6)\n{'='*70}\n")
    print(f"{'Prompt':<28} {'Rate':>8}  Trials")
    print("-" * 60)

    for pid in sorted(PROMPTS):
        trials = sorted([m for m in mapping if m["prompt_id"] == pid], key=lambda x: x["trial"])
        le = 0
        bar = []
        for t in trials:
            used = t["card_id"] in all_le
            row = conn.execute("SELECT status FROM tasks WHERE id=?", (t["card_id"],)).fetchone()
            status = row[0] if row else "?"
            if used:
                le += 1
                bar.append("Y")
            elif status == "done":
                bar.append("d")
            elif status == "running":
                bar.append("r")
            else:
                bar.append(".")
        print(f"{pid:<28} {le:>3}/{len(trials):<3}  [{' '.join(bar)}]")

    total = len([m for m in mapping])
    done = sum(1 for m in mapping if conn.execute("SELECT status FROM tasks WHERE id=?", (m["card_id"],)).fetchone()[0] == "done")
    print(f"\nCompleted: {done}/{total}")
    conn.close()


if __name__ == "__main__":
    import sys
    check() if len(sys.argv) > 1 and sys.argv[1] == "--check" else dispatch()
