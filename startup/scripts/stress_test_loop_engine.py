#!/usr/bin/env python3
"""
Stress test: loop_engine prompt consistency — round 2.

6 winning prompts from round 1, n=10 trials each = 60 cards.
Randomized dispatch order. Same slug (LeadPilot) for all.
Unique verify script paths per trial to prevent cache reuse.

SUCCESS: loop_engine child cards traceable via idempotency key.

Run: python3 stress_test_loop_engine.py              # dispatch
     python3 stress_test_loop_engine.py --check       # results
"""
import json
import sqlite3
import random
import subprocess
import time
from pathlib import Path

BOARD = "stress-loop-test"
BOARD_DB = Path.home() / f".hermes-teams/startup/kanban/boards/{BOARD}/kanban.db"
SLUG = "leadpilot-ai-local-smb-lead-gen"
NAME = "LeadPilot"
TRIALS_PER_PROMPT = 10

# ═══════════════════════════════════════════════════════════════════════════
# 6 WINNING PROMPTS (exact bodies from round 1)
# ═══════════════════════════════════════════════════════════════════════════

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

    "C1_constraint_block": f"""Slug: {SLUG}

CONSTRAINT: You may NOT write any prototype files directly. You MUST use loop_engine.
If you find yourself writing to ~/projects/{SLUG}/prototype/ without having called loop_engine, STOP — you are violating the build process.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{{VERIFY_KEY}}.py (20+ checks)
3. Call loop_engine (MANDATORY — see venture-prototype skill lines 135-180)
4. Write README.md and review handoff

The constraint is: loop_engine creates the child cards that do the actual building.
Your job is to orchestrate, not to build directly.
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

    "G1_combo_all": f"""Slug: {SLUG}

You are an ORCHESTRATOR. Your ONLY job is to call loop_engine.

STEP 1 (Phase 0): Write verify script at /tmp/verify-{{VERIFY_KEY}}.py
  - Use verify-script-template from venture-prototype skill
  - 20+ checks, MUST include runtime execution (category 5)

STEP 2 (Phase 1+2): Call loop_engine tool with:
  loop_engine(
    goal: "Build {NAME} prototype from context/ grill decisions",
    blackboard: {{ spec_path: "~/projects/{SLUG}/context/" }},
    phases: [
      {{ execution: build prototype, verifier: run /tmp/verify-{{VERIFY_KEY}}.py, max_iterations: 2 }},
      {{ execution: write README }}
    ]
  )

CONSTRAINT: Do NOT write any prototype files directly. loop_engine's child agents build.
GATE: Your work will be checked for loop_engine usage. No loop_engine = FAILED card.

STEP 3: Write review handoff (prototype-review-handoff skill).
NEVER put artifacts in ~/vault/.""",
}


def create_board():
    subprocess.run(["hermes", "kanban", "boards", "create", BOARD],
                   capture_output=True, text=True)
    return BOARD_DB.exists()


def create_card(title, body):
    result = subprocess.run(
        ["hermes", "kanban", "--board", BOARD, "create", title,
         "--assignee", "builder", "--body", body, "--json"],
        capture_output=True, text=True, timeout=30
    )
    try:
        return json.loads(result.stdout).get("id", "")
    except (json.JSONDecodeError, TypeError):
        return ""


def dispatch():
    print(f"{'='*70}")
    print(f"Stress Test: loop_engine Prompt Consistency (Round 2)")
    print(f"{'='*70}")
    print(f"Board: {BOARD}")
    print(f"Prompts: {len(PROMPTS)} | Trials each: {TRIALS_PER_PROMPT} | Total: {len(PROMPTS) * TRIALS_PER_PROMPT}")
    print(f"{'='*70}\n")

    if not create_board():
        print(f"ERROR: Could not create board {BOARD}")
        return

    # Build all trials with unique verify keys
    trials = []
    for prompt_id, body_template in PROMPTS.items():
        for trial_num in range(1, TRIALS_PER_PROMPT + 1):
            verify_key = f"{prompt_id}_{trial_num}"
            body = body_template.replace("{VERIFY_KEY}", verify_key)
            title = f"S{trial_num:02d} [{prompt_id}] Build: {NAME}"
            trials.append({
                "prompt_id": prompt_id,
                "trial": trial_num,
                "title": title,
                "body": body,
                "verify_key": verify_key,
            })

    # Shuffle for random dispatch order
    random.seed(42)
    random.shuffle(trials)

    print("Dispatching 60 cards in random order...")
    cards = []
    for i, t in enumerate(trials):
        card_id = create_card(t["title"], t["body"])
        if card_id:
            cards.append({**t, "card_id": card_id})
            print(f"  {i+1:02d}/60 {t['title'][:50]:50s} → {card_id}")
        else:
            print(f"  {i+1:02d}/60 FAILED")
        time.sleep(0.3)  # avoid overwhelming the board

    mapping_path = Path("/tmp/stress-test-mapping.json")
    mapping_path.write_text(json.dumps(cards, indent=2))
    print(f"\nMapping saved to {mapping_path}")
    print(f"\n{'='*70}")
    print(f"All {len(cards)} cards dispatched. Builder processes 5 concurrent.")
    print(f"Check: python3 stress_test_loop_engine.py --check")
    print(f"{'='*70}")


def check():
    mapping_path = Path("/tmp/stress-test-mapping.json")
    if not mapping_path.exists():
        print("No mapping file. Run without --check first.")
        return

    mapping = json.loads(mapping_path.read_text())
    conn = sqlite3.connect(str(BOARD_DB))

    # Build parent map from loop_engine root cards
    loop_roots = conn.execute(
        "SELECT id, idempotency_key FROM tasks WHERE title LIKE 'Loop:%'"
    ).fetchall()
    parent_map = {}
    for lr in loop_roots:
        key = lr[1] or ""
        if ":" in key:
            parent_map[key.split(":")[1]] = lr[0]

    # Results per prompt
    results = {}
    for prompt_id in PROMPTS:
        results[prompt_id] = {"total": 0, "done": 0, "le": 0, "running": 0, "todo": 0, "failed": 0}

    print(f"{'='*70}")
    print(f"Stress Test Results: Round 2")
    print(f"{'='*70}\n")

    print(f"{'Prompt':<28} {'Done':>5} {'loop':>5} {'run':>5} {'todo':>5} {'Rate':>7}")
    print("-" * 60)

    for m in mapping:
        card_id = m["card_id"]
        pid = m["prompt_id"]
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (card_id,)).fetchone()
        status = row[0] if row else "unknown"

        results[pid]["total"] += 1
        if status == "done":
            results[pid]["done"] += 1
        elif status == "running":
            results[pid]["running"] += 1
        elif status in ("todo", "ready"):
            results[pid]["todo"] += 1
        elif status in ("failed", "crashed"):
            results[pid]["failed"] += 1

        if card_id in parent_map:
            results[pid]["le"] += 1

    for pid in sorted(results.keys()):
        r = results[pid]
        rate = f"{r['le']}/{r['done']}" if r["done"] > 0 else f"0/{r['done']}"
        pct = f"{r['le']/r['done']*100:.0f}%" if r["done"] > 0 else "—"
        print(f"{pid:<28} {r['done']:>5} {r['le']:>5} {r['running']:>5} {r['todo']:>5} {pct:>7}")

    total_done = sum(r["done"] for r in results.values())
    total_le = sum(r["le"] for r in results.values())
    total_all = sum(r["total"] for r in results.values())
    print("-" * 60)
    print(f"{'TOTAL':<28} {total_done:>5} {total_le:>5} {'':>5} {'':>5} {total_le/total_done*100:.0f}%" if total_done > 0 else f"{'TOTAL':<28} {total_done:>5}")
    print(f"\nCards completed: {total_done}/{total_all}")

    # Per-trial detail for completed prompts
    any_complete = any(r["done"] == TRIALS_PER_PROMPT for r in results.values())
    if any_complete:
        print(f"\n{'='*70}")
        print("Per-trial detail (completed prompts):")
        for pid in sorted(results.keys()):
            r = results[pid]
            if r["done"] < TRIALS_PER_PROMPT:
                continue
            trials_le = []
            for m in mapping:
                if m["prompt_id"] != pid:
                    continue
                used = m["card_id"] in parent_map
                trials_le.append("Y" if used else ".")
            bar = " ".join(trials_le)
            print(f"  {pid:<28} [{bar}]")

    conn.close()
    print(f"\n{'='*70}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check()
    else:
        dispatch()
