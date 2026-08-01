#!/usr/bin/env python3
"""
A/B test: 20 prompt strategies for enforcing loop_engine in build cards.

Each card gets the SAME slug/prototype but a different prompt strategy.
The builder gateway processes them (5 concurrent).
After all complete, we check which ones actually used loop_engine.

SUCCESS CRITERIA: loop_engine or kanban_chains tool calls visible in
the card's task_events or task_runs.

Run: python3 ab_test_loop_engine.py
"""
import json
import sqlite3
import time
import subprocess
import os
from pathlib import Path
from datetime import datetime

BOARD = "ab-loop-test"
BOARD_DB = Path.home() / f".hermes-teams/startup/kanban/boards/{BOARD}/kanban.db"

# Use a simple slug that already has grill context
SLUG = "leadpilot-ai-local-smb-lead-gen"
NAME = "LeadPilot"

# ═══════════════════════════════════════════════════════════════════════════
# 20 PROMPT VARIANTS
# ═══════════════════════════════════════════════════════════════════════════

PROMPTS = [
    # --- Group A: Prose mandates (increasing force) ---
    {
        "id": "A1_prose_weak",
        "group": "prose",
        "title": f"[A1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

The dossier and grill are DONE. Do NOT re-grill or re-research.
Read grill decisions at ~/projects/{SLUG}/context/

YOUR JOB — Build ONLY.

1. Build prototype using loop_engine (MANDATORY — see venture-prototype skill).
   - Write verify script at /tmp/verify-{SLUG}.py BEFORE building
   - Use loop_engine with 2 phases: (1) build prototype, (2) write README
   - Drop in ~/projects/{SLUG}/prototype/
2. Write README.md at ~/projects/{SLUG}/README.md
3. Write review handoff — update ~/vault/ventures/portfolio.md 'Awaiting Review' section.

NEVER put artifacts in ~/vault/. Everything in ~/projects/{SLUG}/.""",
    },
    {
        "id": "A2_prose_strong",
        "group": "prose",
        "title": f"[A2] Build: {NAME}",
        "body": f"""Slug: {SLUG}

YOUR JOB — Build ONLY. This card exists to isolate loop_engine in a fresh context.

1. Build prototype using loop_engine (MANDATORY — see venture-prototype skill).
   - Write verify script at /tmp/verify-{SLUG}.py BEFORE building
   - Parse every decision from ~/projects/{SLUG}/context/*.md
   - Use loop_engine with 2 phases: (1) build prototype, (2) write README
   - Each phase has a verifier gate — if verify fails, replan
   - Drop in ~/projects/{SLUG}/prototype/
2. Write README.md at ~/projects/{SLUG}/README.md (all 9 sections — see venture-prototype template).
3. Write review handoff (see prototype-review-handoff skill — portfolio entry + kanban comment).
   Update ~/vault/ventures/portfolio.md 'Awaiting Review' section.

This card's ONLY job is to build with loop_engine. Do not skip it.
NEVER put artifacts in ~/vault/ (Obsidian only). Everything goes in ~/projects/{SLUG}/.""",
    },
    {
        "id": "A3_prose_caps",
        "group": "prose",
        "title": f"[A3] Build: {NAME}",
        "body": f"""Slug: {SLUG}

CRITICAL WARNING: If you build this prototype WITHOUT using loop_engine, you are failing the build.
The venture-prototype skill says loop_engine is MANDATORY. No exceptions. Do NOT self-assess as "simple enough" to skip it.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write verify script at /tmp/verify-{SLUG}.py (minimum 20 checks)
3. Call loop_engine with 2 phases:
   - Phase 1: Build prototype in ~/projects/{SLUG}/prototype/
   - Phase 2: Write README.md at ~/projects/{SLUG}/README.md
   Each phase has a verifier gate — if verify fails, replan.
4. Write review handoff (see prototype-review-handoff skill).

If you complete this card without calling loop_engine, your work will be rejected.
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group B: Explicit tool invocation ---
    {
        "id": "B1_tool_naming",
        "group": "tool_invocation",
        "title": f"[B1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

Read grill decisions at ~/projects/{SLUG}/context/*.md

STEP 1: Write verify script at /tmp/verify-{SLUG}.py (20+ checks using verify-script-template).

STEP 2: Call loop_engine tool with these exact parameters:
  goal: "Build {NAME} prototype from context/ grill decisions"
  blackboard: {{ spec_path: "~/projects/{SLUG}/context/", extra: {{ "slug": "{SLUG}" }} }}
  phases: [
    {{ execution: {{ assignee: "builder", title: "Build prototype", body: "Read ~/projects/{SLUG}/context/*.md for locked decisions. Build in ~/projects/{SLUG}/prototype/." }}, verifier: {{ assignee: "builder", title: "Verify", body: "Run: python3 /tmp/verify-{SLUG}.py. If exit != 0, replan." }}, max_iterations: 2 }},
    {{ execution: {{ assignee: "builder", title: "Write README", body: "Write README.md at ~/projects/{SLUG}/README.md" }} }}
  ]

STEP 3: Write review handoff (see prototype-review-handoff skill).
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "B2_tool_first_line",
        "group": "tool_invocation",
        "title": f"[B2] Build: {NAME}",
        "body": f"""FIRST ACTION: Call loop_engine tool. This is non-negotiable.

Load venture-prototype skill. Follow the "Build with loop_engine (MANDATORY)" section exactly.

Slug: {SLUG}
Grill decisions: ~/projects/{SLUG}/context/*.md
Verify script: /tmp/verify-{SLUG}.py (write this FIRST, before loop_engine)
Prototype dir: ~/projects/{SLUG}/prototype/
README: ~/projects/{SLUG}/README.md

The loop_engine call is at lines 156-180 of the venture-prototype skill. Copy that pattern.
Each phase gets a verifier gate. If verify fails, the phase replans.

After loop_engine completes: write review handoff (prototype-review-handoff skill).
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "B3_tool_step_by_step",
        "group": "tool_invocation",
        "title": f"[B3] Build: {NAME}",
        "body": f"""Slug: {SLUG}

DO THESE STEPS IN ORDER. Do not skip any step.

Step 1: Load venture-prototype skill (skill_view name='venture-prototype').
Step 2: Read ~/projects/{SLUG}/context/*.md for all locked decisions.
Step 3: Write /tmp/verify-{SLUG}.py using the verify-script-template (20+ checks).
Step 4: Call the loop_engine tool. See venture-prototype skill lines 156-180 for the exact call.
        Use 2 phases: build + README. Each phase has a verifier that runs the verify script.
Step 5: Write review handoff using prototype-review-handoff skill.

If you reach step 5 without having called loop_engine in step 4, go back and do step 4.
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group C: Constraint/framing
    {
        "id": "C1_constraint_block",
        "group": "constraint",
        "title": f"[C1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

CONSTRAINT: You may NOT write any prototype files directly. You MUST use loop_engine.
If you find yourself writing to ~/projects/{SLUG}/prototype/ without having called loop_engine, STOP — you are violating the build process.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{SLUG}.py (20+ checks)
3. Call loop_engine (MANDATORY — see venture-prototype skill lines 135-180)
4. Write README.md and review handoff

The constraint is: loop_engine creates the child cards that do the actual building.
Your job is to orchestrate, not to build directly.
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "C2_constraint_workflow",
        "group": "constraint",
        "title": f"[C2] Build: {NAME}",
        "body": f"""Slug: {SLUG}

You are an ORCHESTRATOR, not a builder. Your job:

1. Read ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{SLUG}.py
3. Orchestrate the build via loop_engine:
   - loop_engine creates child cards for each phase
   - Each phase has a verifier gate
   - The verifier runs /tmp/verify-{SLUG}.py
   - If verify fails, the phase replans (up to max_iterations)
4. After loop_engine completes all phases, write review handoff

Do NOT write prototype code yourself. loop_engine's child agents do the building.
You are the conductor, not the musician.
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "C3_constraint_gate",
        "group": "constraint",
        "title": f"[C3] Build: {NAME}",
        "body": f"""Slug: {SLUG}

GATE: This card has a quality gate. Your work will be checked for loop_engine usage.
If loop_engine was not called, the card will be REJECTED and re-dispatched.

1. Read grill decisions at ~/projects/{SLUG}/context/*.md
2. Write verify script at /tmp/verify-{SLUG}.py
3. Call loop_engine (MANDATORY) — see venture-prototype skill
4. Write README.md and review handoff

The gate checks: did you call the loop_engine tool? If not, rejected.
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group D: Skill-injection style
    {
        "id": "D1_skill_load",
        "group": "skill_injection",
        "title": f"[D1] Build: {NAME}",
        "body": f"""Load skill: venture-prototype
Load skill: prototype-verification
Load skill: prototype-review-handoff

Slug: {SLUG}
Grill decisions: ~/projects/{SLUG}/context/*.md

Follow venture-prototype skill EXACTLY. It mandates loop_engine with 2 phases.
The skill has the exact loop_engine call pattern at lines 156-180.

Do not deviate from the skill. Do not skip loop_engine. Do not self-assess as "simple enough".
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "D2_skill_invocation",
        "group": "skill_injection",
        "title": f"[D2] Build: {NAME}",
        "body": f"""/skill venture-prototype

Slug: {SLUG}

Build this prototype following the venture-prototype skill completely.
The skill defines a mandatory loop_engine workflow. Follow it.
Write verify script first, then call loop_engine, then write handoff.

Grill decisions at ~/projects/{SLUG}/context/*.md
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "D3_skill_context",
        "group": "skill_injection",
        "title": f"[D3] Build: {NAME}",
        "body": f"""Slug: {SLUG}

You have 3 skills loaded: venture-prototype, prototype-verification, prototype-review-handoff.

Your venture-prototype skill defines the build process:
  Phase 0: Write verify script (20+ checks)
  Phase 1: loop_engine — build prototype (verifier gate)
  Phase 2: loop_engine — write README (verifier gate)
  Phase 3: Review handoff

This is not optional. The skill says "loop_engine is MANDATORY. No exceptions."
Execute each phase in order. Do not skip to phase 3 without phases 0-2.

Grill decisions: ~/projects/{SLUG}/context/*.md
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group E: Example-driven
    {
        "id": "E1_example_inline",
        "group": "example",
        "title": f"[E1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

Here is how to build this prototype:

EXAMPLE (from venture-prototype skill):
```python
loop_engine(
  goal: "Build {NAME} prototype from context/ grill decisions",
  blackboard: {{
    spec_path: "~/projects/{SLUG}/context/",
    extra: {{ "slug": "{SLUG}", "verify_script": "/tmp/verify-{SLUG}.py" }}
  }},
  phases: [
    {{
      execution: {{
        assignee: "builder",
        title: "Build prototype",
        body: "Read ~/projects/{SLUG}/context/*.md. Build in ~/projects/{SLUG}/prototype/."
      }},
      verifier: {{
        assignee: "builder",
        title: "Verify prototype",
        body: "Run: python3 /tmp/verify-{SLUG}.py. If exit != 0, replan."
      }},
      max_iterations: 2
    }},
    {{
      execution: {{
        assignee: "builder",
        title: "Write README",
        body: "Write README.md at ~/projects/{SLUG}/README.md"
      }}
    }}
  ]
)
```

Write the verify script FIRST, then call loop_engine exactly as shown above.
After loop_engine: write review handoff (prototype-review-handoff skill).
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "E2_example_copy",
        "group": "example",
        "title": f"[E2] Build: {NAME}",
        "body": f"""Slug: {SLUG}

Copy this pattern EXACTLY (from venture-prototype skill lines 156-180):

1. Write verify script:
   - At /tmp/verify-{SLUG}.py
   - 20+ checks using verify-script-template
   - MUST include runtime execution check (category 5)

2. Call loop_engine with this structure:
   loop_engine(
     goal: "Build {NAME} prototype",
     blackboard: {{ spec_path: "~/projects/{SLUG}/context/" }},
     phases: [
       {{ execution + verifier + max_iterations: 2 }},
       {{ execution only (README) }}
     ]
   )

3. After loop_engine: review handoff.

This is a copy-paste workflow. Follow it exactly.
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group F: Threat/consequence
    {
        "id": "F1_threat_reject",
        "group": "threat",
        "title": f"[F1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

WARNING: Your output will be automatically checked. If you do not call loop_engine, the card will be marked FAILED and re-dispatched to a different builder session. You will have wasted your entire token budget for nothing.

Required steps:
1. Read ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{SLUG}.py
3. Call loop_engine (MANDATORY) — the venture-prototype skill has the exact call at lines 156-180
4. Write README and review handoff

loop_engine is not optional. It is not "preferred." It is REQUIRED.
If you build directly without loop_engine, you fail.
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "F2_threat_observed",
        "group": "threat",
        "title": f"[F2] Build: {NAME}",
        "body": f"""Slug: {SLUG}

OBSERVED BEHAVIOR: Builders consistently skip loop_engine and build directly.
This is the #1 known failure mode. You will be tempted to skip it. DO NOT.

The venture-prototype skill says (line 132): "The builder self-assesses every build as 'simple enough' to skip loop_engine. This is premature completion every time."

REQUIRED:
1. Read ~/projects/{SLUG}/context/*.md
2. Write /tmp/verify-{SLUG}.py
3. Call loop_engine (MANDATORY) with 2 phases
4. Write README and handoff

You are not special. Your build is not simple enough. Call loop_engine.
NEVER put artifacts in ~/vault/.""",
    },
    # --- Group G: Mixed (best of each)
    {
        "id": "G1_combo_all",
        "group": "combo",
        "title": f"[G1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

You are an ORCHESTRATOR. Your ONLY job is to call loop_engine.

STEP 1 (Phase 0): Write verify script at /tmp/verify-{SLUG}.py
  - Use verify-script-template from venture-prototype skill
  - 20+ checks, MUST include runtime execution (category 5)

STEP 2 (Phase 1+2): Call loop_engine tool with:
  loop_engine(
    goal: "Build {NAME} prototype from context/ grill decisions",
    blackboard: {{ spec_path: "~/projects/{SLUG}/context/" }},
    phases: [
      {{ execution: build prototype, verifier: run /tmp/verify-{SLUG}.py, max_iterations: 2 }},
      {{ execution: write README }}
    ]
  )

CONSTRAINT: Do NOT write any prototype files directly. loop_engine's child agents build.
GATE: Your work will be checked for loop_engine usage. No loop_engine = FAILED card.

STEP 3: Write review handoff (prototype-review-handoff skill).
NEVER put artifacts in ~/vault/.""",
    },
    {
        "id": "G2_combo_minimal",
        "group": "combo",
        "title": f"[G2] Build: {NAME}",
        "body": f"""Slug: {SLUG}. Grill decisions at ~/projects/{SLUG}/context/*.md

Call loop_engine now. 2 phases: build + verify. Write verify script first at /tmp/verify-{SLUG}.py.
Then write README and review handoff. That's all.""",
    },
    # --- Group H: Minimalist (control) ---
    {
        "id": "H1_minimal_bare",
        "group": "minimal",
        "title": f"[H1] Build: {NAME}",
        "body": f"""Slug: {SLUG}

Build the prototype from grill decisions at ~/projects/{SLUG}/context/*.md
Drop in ~/projects/{SLUG}/prototype/. Write README. Write review handoff.""",
    },
    {
        "id": "H2_minimal_noloop",
        "group": "minimal",
        "title": f"[H2] Build: {NAME}",
        "body": f"""Slug: {SLUG}

Build prototype from grill decisions at ~/projects/{SLUG}/context/*.md.
Write verify script at /tmp/verify-{SLUG}.py.
Build in ~/projects/{SLUG}/prototype/. Write README. Write review handoff.""",
    },
]


def create_board():
    """Create the test board."""
    subprocess.run(["hermes", "kanban", "boards", "create", BOARD],
                   capture_output=True, text=True)
    # Verify
    if BOARD_DB.exists():
        return True
    # Board might already exist — check
    result = subprocess.run(["hermes", "kanban", "--board", BOARD, "list"],
                          capture_output=True, text=True)
    return BOARD in result.stdout


def create_card(prompt, index):
    """Create a card with the given prompt."""
    # Add sequence number to title for ordering
    title = f"V{index:02d} {prompt['title']}"
    result = subprocess.run(
        ["hermes", "kanban", "--board", BOARD, "create", title,
         "--assignee", "builder", "--body", prompt["body"], "--json"],
        capture_output=True, text=True, timeout=30
    )
    try:
        data = json.loads(result.stdout)
        return data.get("id", "")
    except (json.JSONDecodeError, TypeError):
        return ""


def check_loop_engine_usage(card_id):
    """Check if a card's task run used loop_engine or kanban_chains."""
    if not BOARD_DB.exists():
        return {"used_loop_engine": False, "evidence": "board DB not found"}

    conn = sqlite3.connect(str(BOARD_DB))
    try:
        # Check task_events for tool calls
        events = conn.execute(
            "SELECT data FROM task_events WHERE task_id = ? AND data LIKE '%loop_engine%'",
            (card_id,)
        ).fetchall()
        if events:
            return {"used_loop_engine": True, "evidence": f"loop_engine in task_events ({len(events)} hits)"}

        # Check task_runs for tool usage
        runs = conn.execute(
            "SELECT run_id FROM task_runs WHERE task_id = ?", (card_id,)
        ).fetchall()
        for run in runs:
            run_events = conn.execute(
                "SELECT data FROM task_events WHERE run_id = ? AND (data LIKE '%loop_engine%' OR data LIKE '%kanban_chains%')",
                (run[0],)
            ).fetchall()
            if run_events:
                return {"used_loop_engine": True, "evidence": f"loop_engine in run {run[0]}"}

        # Check comments for loop_engine evidence
        comments = conn.execute(
            "SELECT body FROM task_comments WHERE task_id = ?", (card_id,)
        ).fetchall()
        for c in comments:
            body = c[0] if c else ""
            if "loop_engine" in body.lower() or "kanban_chains" in body.lower():
                return {"used_loop_engine": True, "evidence": "loop_engine mentioned in comments"}

        return {"used_loop_engine": False, "evidence": "no loop_engine evidence found"}
    finally:
        conn.close()


def main():
    print(f"{'='*70}")
    print(f"A/B Test: loop_engine Prompt Strategies")
    print(f"{'='*70}")
    print(f"Board: {BOARD}")
    print(f"Slug: {SLUG}")
    print(f"Prompts: {len(PROMPTS)}")
    print(f"{'='*70}\n")

    # Create board
    if not create_board():
        print(f"ERROR: Could not create board {BOARD}")
        return

    # Create all cards
    print("Creating cards...")
    cards = []
    for i, prompt in enumerate(PROMPTS):
        card_id = create_card(prompt, i + 1)
        if card_id:
            cards.append({"card_id": card_id, "prompt": prompt, "index": i + 1})
            print(f"  V{i+1:02d} ({prompt['id']:25s}) → {card_id}")
        else:
            print(f"  V{i+1:02d} ({prompt['id']:25s}) → FAILED TO CREATE")
    print(f"\nCreated {len(cards)}/{len(PROMPTS)} cards\n")

    # Save card mapping for later analysis
    mapping = [{"card_id": c["card_id"], "prompt_id": c["prompt"]["id"],
                "group": c["prompt"]["group"], "title": c["prompt"]["title"],
                "index": c["index"]} for c in cards]
    mapping_path = Path("/tmp/ab-test-loop-engine-mapping.json")
    mapping_path.write_text(json.dumps(mapping, indent=2))
    print(f"Mapping saved to {mapping_path}")
    print(f"\n{'='*70}")
    print(f"All {len(cards)} cards dispatched to board '{BOARD}'.")
    print(f"Builder gateway will process them (5 concurrent).")
    print(f"Check results later with: python3 ab_test_loop_engine.py --check")
    print(f"{'='*70}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        # Check results
        mapping_path = Path("/tmp/ab-test-loop-engine-mapping.json")
        if not mapping_path.exists():
            print("No mapping file found. Run without --check first.")
            sys.exit(1)
        mapping = json.loads(mapping_path.read_text())
        print(f"{'='*70}")
        print(f"A/B Test Results: loop_engine Prompt Strategies")
        print(f"{'='*70}\n")
        results = []
        for m in mapping:
            r = check_loop_engine_usage(m["card_id"])
            status = "running" if not r["used_loop_engine"] and r["evidence"] == "no loop_engine evidence found" else ("DONE" if r["used_loop_engine"] else "no loop_engine")
            print(f"  V{m['index']:02d} [{m['group']:16s}] {m['prompt_id']:25s} → {r['used_loop_engine']}")
            results.append({**m, **r})
        print(f"\n{'='*70}")
        used = [r for r in results if r["used_loop_engine"]]
        print(f"Used loop_engine: {len(used)}/{len(results)}")
        if used:
            print(f"\nWinning prompts:")
            for r in used:
                print(f"  V{r['index']:02d} [{r['group']}] {r['prompt_id']}: {r['evidence']}")
        print(f"{'='*70}")
    else:
        main()
