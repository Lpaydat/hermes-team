# A/B Testing Agent Behavioral Enforcement

When an agent consistently skips a required process (loop_engine, kanban_chains, verify scripts, etc.), don't guess at prompt fixes — run a structured experiment.

## The 2-round methodology

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

### Round 2 — Stress test winners (n=10 per winner)

Take the top N from round 1. Dispatch 10 trials each (60 cards for 6 winners). Key controls:
- **Same task** for all cards (eliminates variance from task complexity)
- **Randomized dispatch order** (eliminates position bias — early cards might get more "care")
- **Unique verify script paths** per trial (`/tmp/verify-<prompt_id>-<trial>.py`) so the agent can't reuse cached work

### How to trace compliance

Do NOT parse agent output text to check compliance — agents self-report falsely. Instead trace deterministic kanban side-effects:

- **loop_engine usage**: child cards with idempotency key pattern `loop:<parent_card_id>:<suffix>`. Query: `SELECT id, idempotency_key FROM tasks WHERE title LIKE 'Loop:%'` then extract parent from key.
- **kanban_chains usage**: root card with `[swarm:blackboard]` comment.
- **Tool calls**: `SELECT payload FROM task_events WHERE task_id = ? AND payload LIKE '%loop_engine%'`

### Loop_engine enforcement results (80 cards total)

**Round 1 (20 cards):** 6/20 triggered loop_engine. Constraint (2/3), threat (2/2), combo (1/2), prose-caps (1/3).

**Round 2 (60 cards, 6 winners x n=10):**

| Prompt | Rate | Strategy |
|--------|------|----------|
| **C3_constraint_gate** | **90%** | "Your work will be checked. No loop_engine = FAILED card." |
| F1_threat_reject | 50% | "Card will be FAILED and re-dispatched" |
| F2_threat_observed | 30% | "#1 known failure mode, builders skip it" |
| C1_constraint_block | 20% | "You may NOT write files directly" |
| G1_combo_all | 20% | Orchestrator + constraint + example |
| A3_prose_caps | 10% | "CRITICAL WARNING" |

**Winner: C3_constraint_gate (90%).**

### Key insight: verifiable consequences > stated consequences

C3 won because it frames a downstream check the builder believes will execute. A3 (which won round 1 at 1/1 but collapsed to 1/10 in round 2) uses emotional urgency ("CRITICAL WARNING") that the builder dismisses. The builder responds to gates it believes will fire, not threats it can't verify.

This generalizes: when enforcing agent behavior, frame the consequence as a mechanical check, not an emotional appeal.

### Scripts

- `~/.hermes-teams/startup/scripts/ab_test_loop_engine.py` — round 1 dispatcher + checker
- `~/.hermes-teams/startup/scripts/stress_test_loop_engine.py` — round 2 dispatcher + checker

Both are reusable templates — swap the PROMPTS dict and SLUG for a different behavior under test.
