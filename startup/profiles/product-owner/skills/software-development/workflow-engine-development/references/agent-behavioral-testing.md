# A/B Testing Agent Behavioral Enforcement

When an agent consistently skips a required process (loop_engine, kanban_chains, verify scripts, etc.), don't guess at prompt fixes — run a structured experiment.

## The 4-round methodology

### Round 1 — Broad screen (n=1 per variant)

Write 15-20 prompt variants across distinct strategy families:
- **Prose mandate** — "loop_engine is MANDATORY"
- **Tool invocation** — explicit parameters, first-line instruction, step-by-step numbered
- **Constraint** — "You may NOT write files directly", "quality gate will check"
- **Threat** — "card will be FAILED and re-dispatched"
- **Skill injection** — "Load skill: venture-prototype", "/skill" command
- **Example** — inline code block showing the exact call
- **Combo** — orchestrator framing + constraint + example
- **Minimal** — bare instruction (control group)

Dispatch 1 card per variant on a test board. Identical task, different prompt body. Track which ones produce the desired side-effect.

### Round 2 — Stress test winners (n=10 per winner, strong model)

Take the top N from round 1. Dispatch 10 trials each. Key controls:
- **Same task** for all cards (eliminates variance from task complexity)
- **Randomized dispatch order** (eliminates position bias)
- **Unique verify script paths** per trial so the agent can't reuse cached work

### Round 3 — Weaker model test (n=10 per winner)

**CRITICAL STEP.** Switch the agent's model to a weaker one (e.g., glm-4.6 instead of glm-5.2) and rerun. Prompts that scored 100% on the strong model may collapse on the weak model. This reveals which prompts are model-robust vs model-dependent.

To switch the builder model: edit `~/.hermes-teams/startup/profiles/builder/config.yaml`, change `model.default`, then restart the builder gateway:
```bash
kill $(pgrep -f "hermes_cli.*--profile builder gateway")
# Wait, then start fresh
cd ~/.hermes-teams/startup && hermes --profile builder gateway run &
```

**Always restore the model after testing.**

### Round 4 — Combination test (optional)

If multiple winners exist, try combining the best elements. WARNING: in practice, the combined prompt scored 55% vs 80% for individual winners on the weak model. More text dilutes the signal. **Prefer the simplest individual winner over a combination.**

### How to trace compliance — CORRECTED

Do NOT parse agent output text to check compliance — agents self-report falsely. Instead trace deterministic kanban side-effects.

**CRITICAL: Check ALL three signals, not just one.** The initial checker only looked at `Loop:%` card titles and missed 70% of kanban_chains usage, producing wrong results.

```python
# Signal 1: Loop:% root cards (loop_engine creates these)
loop_roots = conn.execute(
    "SELECT idempotency_key FROM tasks WHERE title LIKE 'Loop:%'"
).fetchall()
parent_ids = {key.split(":")[1] for key in (lr[0] or "") if ":" in key}

# Signal 2: Heartbeat events mentioning the tool
heartbeat_parents = {row[0] for row in conn.execute(
    "SELECT task_id FROM task_events WHERE kind='heartbeat' "
    "AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
)}

# Signal 3: Completion events mentioning the tool
completed_parents = {row[0] for row in conn.execute(
    "SELECT task_id FROM task_events WHERE kind='completed' "
    "AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')"
)}

all_le = parent_ids | heartbeat_parents | completed_parents
```

### Schema notes

- `task_events` uses `payload` column (NOT `data`)
- `tasks` table has NO `parent_id` column
- loop_engine root idempotency key: `loop:<parent_card_id>:<hash>`
- kanban_chains root: has `[swarm:blackboard]` comment

## Loop_engine enforcement results (140 cards, 4 rounds)

### Round 1 (20 prompts, n=1, glm-5.2)
6/20 triggered loop_engine. Threat (2/2), constraint (2/3), combo (1/2), prose-caps (1/3).

### Round 2 (6 winners, n=10, glm-5.2)
4 prompts at 100%: A3_prose_caps, C3_constraint_gate, F1_threat_reject, F2_threat_observed.

### Round 3 (4 winners, n=10, glm-4.6)
| Prompt | glm-5.2 | glm-4.6 |
|--------|---------|---------|
| C3_constraint_gate | 100% | 80% |
| F1_threat_reject | 100% | 80% |
| F2_threat_observed | 100% | 80% |
| A3_prose_caps | 100% | 40% (collapsed) |

### Round 4 (combined prompt, n=20, glm-4.6)
55% — worse than individual winners. Do not combine.

## Key insights

1. **Consequence framing > instruction framing.** Threats of rejection/waste work. Code examples, tool params, skill-loading language, and step-by-step instructions all fail completely.

2. **Test on the weak model.** Prompts that work at 100% on a strong model may collapse to 40% on a weaker one. Model robustness is a selection criterion.

3. **Don't combine winners.** A single clear consequence outperforms a layered combination. More text = more room for creative interpretation.

4. **The 20% floor is the model's ceiling.** When 3 different prompts all plateau at 80% on a weak model, that's the model's instruction-following limit — better prompts won't fix it.

5. **Verifiable consequences > emotional urgency.** "Your work will be checked" (gate) beats "CRITICAL WARNING" (emotion) on weak models. Strong models handle both; weak models only handle the gate.

## Blocked cards are sometimes correct behavior

Loop_engine verifier gates catch quality issues and block the phase for replan. A blocked verifier child card means loop_engine IS WORKING — it found real gaps (e.g., 37/46 verify checks failed). This is NOT a bug or a crash.

The difference:
- **Crash block**: verifier agent exits non-zero because it can't load a required skill → infrastructure bug
- **Quality block**: verifier ran successfully, found real gaps → loop_engine working correctly

## Scripts

All reusable — swap the PROMPTS dict and SLUG for a different behavior under test.
- `~/.hermes-teams/startup/scripts/ab_test_loop_engine.py` — round 1
- `~/.hermes-teams/startup/scripts/stress_test_loop_engine.py` — round 2
- `~/.hermes-teams/startup/scripts/stress_test_round3.py` — round 3
- `~/.hermes-teams/startup/scripts/stress_test_round4.py` — round 4
