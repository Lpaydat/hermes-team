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

### Success criteria — CORRECTED methodology

**CRITICAL: Do not only check for `Loop:%` card titles.** Most builders use `kanban_chains` instead of `loop_engine`, which creates different card structures (root, build, verify, README). You must check ALL signals:

```python
# Signal 1: Loop:% root cards (loop_engine)
loop_roots = conn.execute(
    "SELECT idempotency_key FROM tasks WHERE title LIKE 'Loop:%'"
).fetchall()
parent_ids = {key.split(":")[1] for key in (lr[0] or "") if ":" in key}

# Signal 2: Heartbeat events mentioning loop_engine/kanban_chains
heartbeat_parents = {row[0] for row in conn.execute(
    "SELECT task_id FROM task_events WHERE kind='heartbeat' "
    "AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
)}

# Signal 3: Completion events mentioning loop_engine/kanban_chains
completed_parents = {row[0] for row in conn.execute(
    "SELECT task_id FROM task_events WHERE kind='completed' "
    "AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
)}

# Combined
all_le = parent_ids | heartbeat_parents | completed_parents
```

The initial checker that only looked at `Loop:%` titles reported C3 at 90% and all others much lower. The corrected checker (above) found 4 prompts at 100% — the difference was kanban_chains usage invisible to the title-only check.

### Schema notes

- `task_events` uses `payload` column (NOT `data`)
- `tasks` table has NO `parent_id` column — parent-child linkage is via `idempotency_key`
- loop_engine root idempotency key: `loop:<parent_card_id>:<hash>`
- kanban_chains root: has `[swarm:blackboard]` comment

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

## 4-Round Results (140 cards total, loop_engine enforcement)

### Round 1 — Broad screen (20 prompts, n=1, glm-5.2)

6/20 triggered loop_engine (30%). Winners: A3_prose_caps, C1_constraint_block, C3_constraint_gate, F1_threat_reject, F2_threat_observed, G1_combo_all.

**Pattern: consequence-based framing works. Instruction-based framing fails.** Tool invocation (0/3), skill injection (0/3), examples (0/2), minimal (0/2) all completely failed.

### Round 2 — Stress test winners (6 prompts, n=10, glm-5.2)

**CORRECTED RESULTS** (initial checker was buggy — only matched `Loop:%` titles, missed kanban_chains usage):

| Prompt | Rate | Strategy |
|--------|------|----------|
| **A3_prose_caps** | **10/10 (100%)** | "CRITICAL WARNING: failing the build" |
| **C3_constraint_gate** | **10/10 (100%)** | "Quality gate — will be checked — REJECTED" |
| **F1_threat_reject** | **10/10 (100%)** | "Card will be FAILED and re-dispatched" |
| **F2_threat_observed** | **10/10 (100%)** | "#1 known failure mode — you are not special" |
| C1_constraint_block | 9/10 (90%) | "You may NOT write files directly" |
| G1_combo_all | 7/10 (70%) | Orchestrator + constraint + example |

On the strong model (glm-5.2), all 4 top prompts are equally effective.

### Round 3 — Weaker model test (4 winners, n=10, glm-4.6)

| Prompt | glm-5.2 | glm-4.6 | Degradation |
|--------|---------|---------|-------------|
| C3_constraint_gate | 100% | **80%** | -20% |
| F1_threat_reject | 100% | **80%** | -20% |
| F2_threat_observed | 100% | **80%** | -20% |
| A3_prose_caps | 100% | **40%** | -60% |

A3 collapsed — emotional urgency ("CRITICAL WARNING") is model-dependent. C3/F1/F2 held at 80% — consequence framing is model-robust. The 20% floor is likely glm-4.6's instruction-following ceiling.

**Lesson: ALWAYS test on the weakest model you'll deploy to.** A prompt that works on the strong model may collapse on the weak one.

### Round 4 — Combined prompt test (n=20, glm-4.6)

Combined the best elements of C3 (gate) + F1 (token waste + line pointers) + F2 (observed behavior + identity kill) into one prompt.

**Result: 55% — WORSE than individual winners (80%).**

Combining elements diluted the signal. More text gave the weaker model more room to "creatively interpret" instead of following a single clear consequence. **Do not combine winning prompts — pick the simplest individual winner.**

## Winning prompt characteristics

The three robust winners (C3, F1, F2) share these traits:
1. **Concrete consequence** — "card will be FAILED", "work will be checked", "token budget wasted"
2. **No ambiguity** — "REQUIRED" not "preferred", "if not, rejected"
3. **Short** — under 200 tokens
4. **No code examples** — the agent knows HOW, it needs a reason to not shortcut

F2_threat_observed is the recommended choice — shortest, most robust, uses observed-behavior framing that anticipates rationalization.

## Why builders use kanban_chains instead of loop_engine

The venture-prototype skill documents both. `loop_engine` is intended for single-prototype builds (phases with verifier gates). `kanban_chains` is documented for "parallel builds" but builders use it for single builds too because it's simpler. Both create the same structure (child cards with verify gates). This is acceptable — the key metric is whether structured verification happened, not which API was used.

## Prototype-verification skill deployment

loop_engine/kanban_chains creates verifier child cards assigned to the `verifier` profile with `skills: ["prototype-verification"]`. If that skill doesn't exist on the verifier profile, the verifier agent crashes (exit code 1) and the card blocks after 2 crash retries.

FIX: `prototype-verification` must be in `shared-skills/` and symlinked from BOTH builder AND verifier profiles.

## Scripts

- `~/.hermes-teams/startup/scripts/ab_test_loop_engine.py` — round 1 (20 variants)
- `~/.hermes-teams/startup/scripts/stress_test_loop_engine.py` — round 2 (6 winners x 10)
- `~/.hermes-teams/startup/scripts/stress_test_round3.py` — round 3 (4 winners x 10, glm-4.6)
- `~/.hermes-teams/startup/scripts/stress_test_round4.py` — round 4 (combined prompt x 20, glm-4.6)

All scripts are reusable templates — swap the PROMPTS dict and SLUG for a different behavior under test.

## Quality comparison methodology

When comparing engine workflow output vs original pipeline (scripts):

1. **Grill depth**: Count Q&A rounds (`^Q[0-9]` in context/*.md) and decisions (`Lock D[0-9]` or `D[0-9]+:` patterns). Don't use `^## Q` — the format is `Q1`, `Q2`, not markdown headers.
2. **Prototype files**: Check `~/projects/<slug>/prototype/` exists and has the expected type (HTML, CLI, API).
3. **Verify scripts**: Check `/tmp/verify-<slug>.py` exists and runs (exit code 0).
4. **Tool usage**: Search heartbeat AND completion events (not just Loop:% titles) for tool mentions.
5. **Portfolio entries**: Check `~/vault/ventures/portfolio.md` for "Awaiting Review" entries with the slug.
6. **Card body diff**: Compare engine-generated card body against what the original script would produce. Missing enforcement lines cause behavior changes.
