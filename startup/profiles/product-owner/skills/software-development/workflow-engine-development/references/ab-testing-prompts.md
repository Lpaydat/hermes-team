# A/B Testing Card Body Prompt Strategies

## The problem

Agents ignore instructions in card bodies. Even when a card says "MANDATORY: use loop_engine", the builder consistently skips it and builds directly. Prose mandates don't work — the agent self-assesses as "simple enough" to skip the mandated tool.

This is not an engine problem. The engine delivers the card body correctly. The problem is prompt design: HOW do you phrase a card body so the agent actually follows it?

## The A/B test framework

Dispatch N cards on a test board, each with the SAME task but a DIFFERENT prompt strategy. The builder gateway processes them (respecting concurrency limits). After all complete, check which prompts triggered the desired behavior.

### Setup

1. Create a dedicated test board: `hermes kanban boards create ab-loop-test`
2. Write a Python script that creates N cards with different bodies
3. Dispatch all cards at once
4. Wait for completion (10-20 min per card at the builder's pace)
5. Check each card's task_events/comments for evidence of the target behavior

### Success criteria

For loop_engine enforcement, check:
- `task_events` data for `loop_engine` or `kanban_chains` tool calls
- Card comments for loop_engine mentions
- Child cards created on the board (loop_engine creates develop/verify child cards)

```python
def check_loop_engine_usage(card_id):
    conn = sqlite3.connect(board_db)
    # Check task_events
    events = conn.execute(
        "SELECT data FROM task_events WHERE task_id=? AND data LIKE '%loop_engine%'",
        (card_id,)).fetchall()
    if events:
        return True
    # Check comments
    comments = conn.execute("SELECT body FROM task_comments WHERE task_id=?", (card_id,)).fetchall()
    for c in comments:
        if "loop_engine" in c[0].lower():
            return True
    return False
```

## 20 prompt strategy groups

| Group | Strategy | Hypothesis |
|-------|----------|------------|
| A (prose) | Increasing force of prose mandate | Stronger language → compliance |
| B (tool_invocation) | Name the exact tool + parameters | Explicit invocation → action |
| C (constraint) | Frame as constraint/blocker | "You may NOT do X" → compliance |
| D (skill_injection) | "Load skill X" framing | Skill context → compliance |
| E (example) | Show the exact code pattern | Copy-paste → action |
| F (threat) | Threaten rejection/consequences | Fear of waste → compliance |
| G (combo) | Best elements combined | Combined force → compliance |
| H (minimal) | Bare minimum, no mandate | Control group — should fail |

## Round 1 Results (n=1 per prompt, 20 prompts total)

6/20 prompts triggered loop_engine (30% success rate).

### Winners (triggered loop_engine)

| Variant | Group | Strategy | loop_engine |
|---------|-------|----------|-------------|
| V03 A3_prose_caps | prose | CAPS threat: "CRITICAL WARNING: failing the build" | YES |
| V07 C1_constraint_block | constraint | "You may NOT write prototype files directly" | YES |
| V09 C3_constraint_gate | constraint | "Quality gate — will be checked — REJECTED" | YES |
| V15 F1_threat_reject | threat | "Card will be FAILED and re-dispatched" | YES |
| V16 F2_threat_observed | threat | "#1 known failure mode — you are not special" | YES |
| V17 G1_combo_all | combo | Orchestrator + gate + example combined | YES |

### Losers (did NOT trigger loop_engine)

| Group | Variants | Win rate |
|-------|----------|----------|
| tool_invocation | B1 (named params), B2 (first line), B3 (step-by-step) | 0/3 (0%) |
| skill_injection | D1 (load skill), D2 (/skill command), D3 (skill context) | 0/3 (0%) |
| example | E1 (inline code), E2 (copy pattern) | 0/2 (0%) |
| minimal | H1 (bare), H2 (no-loop-mention) | 0/2 (0%) |
| prose | A1 (weak), A2 (strong) | 0/2 (0%) |
| constraint | C2 (orchestrator framing only) | 0/1 (0%) |
| combo | G2 (minimal combo) | 0/1 (0%) |

### Win rate by group

- **threat: 2/2 (100%)** — strongest signal
- **constraint: 2/3 (67%)** — strong (the pure constraint worked, the soft "orchestrator" framing didn't)
- **combo: 1/2 (50%)** — the full combo worked, the minimal combo didn't
- **prose: 1/3 (33%)** — only the CAPS threat version worked
- **tool_invocation: 0/3 (0%)** — explicit tool params don't help
- **skill_injection: 0/3 (0%)** — skill loading language doesn't help
- **example: 0/2 (0%)** — code examples don't help
- **minimal: 0/2 (0%)** — control group confirmed

### The pattern

**Consequence-based framing works. Instruction-based framing fails.**

The agent knows HOW to call loop_engine — it doesn't need tool parameters, code examples, or skill-loading language. It needs a reason to not take the shortcut. Framing loop_engine as a hard constraint with consequences ("your work will be rejected", "you may NOT write files directly", "you are failing the build") forces the agent to use the structured path.

### Important: this is an agent-behavior problem, not an engine problem

The engine delivers the card body verbatim. The issue is that LLM agents:
1. Self-assess complexity and skip steps they deem unnecessary
2. Don't load skills referenced in prose (they'd need a tool call)
3. Prioritize task completion over process compliance
4. Treat "MANDATORY" as a suggestion, not an enforcement mechanism

The real fix may be STRUCTURAL (output schema validation, post-completion gate) rather than PROMPT-BASED.

## Round 2: Stress test methodology (n=10 per winner)

Round 1 was n=1 — can't distinguish 100% from 30%. The stress test runs the 6 winners at n=10 each (60 cards total) with randomized dispatch order to eliminate position bias.

### Design

- **Same slug** for all 60 cards (LeadPilot) — eliminates grill-quality variance
- **Randomized dispatch order** — eliminates position bias (builder might be "warmer" on early cards)
- **Unique verify script path** per trial (`/tmp/verify-<prompt_id>-<trial>.py`) — prevents cache reuse
- **Success metric**: loop_engine child cards traceable via idempotency key `loop:<parent_card_id>:<hash>`
- **Tiebreaker**: if 2+ prompts go 10/10, pick the simplest one (fewest tokens = cheapest to deploy)

### Script location

`startup/scripts/stress_test_loop_engine.py` — dispatches 60 cards in random order, `--check` flag shows per-prompt win rate.

### What n=10 tells us

- 10/10 = the prompt is reliable (adopt it)
- 7-9/10 = the prompt helps but isn't reliable (needs structural enforcement)
- <7/10 = the prompt doesn't scale (ditch it)

## Tracking loop_engine via idempotency keys

The `task_events` table uses `payload` column (NOT `data`), and parent-child linkage is via `idempotency_key` on the tasks table (NOT a `parent_id` column — that doesn't exist on the kanban tasks schema).

```python
# Correct way to trace loop_engine usage
loop_roots = conn.execute(
    "SELECT id, title, idempotency_key FROM tasks WHERE title LIKE 'Loop:%'"
).fetchall()
parent_map = {}
for lr in loop_roots:
    key = lr[2] or ""
    if ":" in key:
        parent_id = key.split(":")[1]  # loop:<parent_card_id>:<hash>
        parent_map[parent_id] = lr[0]

# Then check: card_id in parent_map
```

## Script location

`startup/scripts/ab_test_loop_engine.py` — 20 prompt variants, creates cards on `ab-loop-test` board, check results with `--check` flag.

## Quality comparison methodology

When comparing engine workflow output vs original pipeline (scripts):

1. **Grill depth**: Count Q&A rounds (`^Q[0-9]` in context/*.md) and decisions (`Lock D[0-9]` or `D[0-9]+:` patterns). Don't use `^## Q` — the format is `Q1`, `Q2`, not markdown headers.
2. **Prototype files**: Check `~/projects/<slug>/prototype/` exists and has the expected type (HTML, CLI, API).
3. **Verify scripts**: Check `/tmp/verify-<slug>.py` exists and runs (exit code 0).
4. **Tool usage**: Search task_events and task_comments on the board DB for tool names.
5. **Portfolio entries**: Check `~/vault/ventures/portfolio.md` for "Awaiting Review" entries with the slug.
6. **Card body diff**: Compare engine-generated card body against what the original script would produce. Missing enforcement lines cause behavior changes.
