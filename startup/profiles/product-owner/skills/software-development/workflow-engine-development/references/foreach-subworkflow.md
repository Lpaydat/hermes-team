# Foreach Subworkflow — Parallel Pipelines

## The problem

Foreach on task nodes is a barrier: N cards created, ALL must complete before the next node. This breaks pipelines where each item should flow independently.

```
WRONG (barrier):
  parse → grill (foreach, 10 cards) → build (foreach, 10 cards)
  
  grill cards: [1 done] [2 running] [3 ready] ... [10 ready]
  build can't start until ALL 10 grills finish
```

## The fix: foreach + subworkflow

Parent workflow spawns N independent child workflows. Each child runs its own pipeline — no barrier.

```
Parent:  parse (command) → spawn (foreach + subworkflow → child-template)
Child:   grill → build → handoff (sequential, independent per item)

  Child A: grill(A) → build(A) → handoff(A)
  Child B: grill(B) → build(B) → handoff(B)  ← starts independently
```

## Template structure

**Parent template** (`builder-grill-build.json`):
```json
{
  "id": "builder-grill-build",
  "nodes": [
    {"id": "parse", "type": "command", "command": "python3 parse.py"},
    {"id": "spawn", "type": "subworkflow", "workflow_ref": "builder-single",
     "foreach": "${nodes.parse.output.ideas}",
     "depends_on": ["parse"]}
  ],
  "edges": [{"from": "parse", "to": "spawn"}]
}
```

**Child template** (`builder-single.json`):
```json
{
  "id": "builder-single",
  "nodes": [
    {"id": "grill", "profile": "builder", "skill": "self-grill",
     "title_template": "Grill: ${trigger.name}",
     "body_template": "Slug: ${trigger.slug}..."},
    {"id": "build", "profile": "builder", "skill": "venture-prototype",
     "title_template": "Build: ${trigger.name}",
     "depends_on": ["grill"]},
    {"id": "handoff", "profile": "builder", "skill": "prototype-review-handoff",
     "title_template": "Review: ${trigger.name}",
     "depends_on": ["build"]}
  ],
  "edges": [
    {"from": "grill", "to": "build"},
    {"from": "build", "to": "handoff"}
  ]
}
```

## How item data flows to children

`_dispatch_foreach_subworkflow` injects item dict fields directly into child trigger context:
- If item is `{"slug": "x", "name": "Y", "score": 18}`, child context gets `trigger.slug`, `trigger.name`, `trigger.score`
- If item is a string, child gets `trigger.item`
- `item_index` always set

## Completion tracking

Parent's spawn node stores `_foreach_instances` (list of child instance IDs) in output. PHASE 1 checks if ALL children are `completed`. Parent completes only when all children complete.

## Tick ordering

Child instances are created during the parent's tick (PHASE 2 dispatch). But `load_active_instances()` already ran at the start of the tick. Children dispatch their first cards on the NEXT tick. Tests must call `tick()` twice when expecting child dispatch.

## 7 tests in test_foreach_subworkflow.py

- Basic spawn (N children)
- Independent progress (A completes while B runs — the KEY test)
- Parent completes when all children done
- Child context has item fields
- Empty list
- String items
- 3-step pipeline independence

## Livetest lessons (7-prototype E2E, builder-livetest board)

1. **Archived cards are terminal.** If a card is archived externally (manual cleanup, GC), the engine must treat it as DONE — not wait forever for "done" status. Both single-card and foreach completion checks must accept `"archived"` alongside `"done"`. Without this, orphaned child instances block parent completion indefinitely. The fix is a one-line status check: `if card.status == "done" or card.status == "archived"`.

2. **Global config overrides profile config for concurrency.** `max_in_progress` and `max_in_progress_per_profile` are read from GLOBAL `~/.hermes-teams/startup/config.yaml`, NOT from per-profile `config.yaml`. Changing the profile config does nothing. The gateway must be restarted to pick up changes.

3. **Builder skips loop_engine on ALL builds.** This is a pre-existing gap — the old queue-builds.sh pipeline also never triggered loop_engine. The engine template delivers the instruction correctly, but the builder agent ignores "MANDATORY" prose. Constraint-framing prompts work better (see A/B test findings below).

4. **Quality comparison methodology.** To compare engine vs old pipeline:
   - Count grill Q&A rounds: `grep -c "^Q[0-9]" context/*.md | awk -F: '{sum+=$NF} END {print sum+0}'` (NOT `^## Q` — the format is Q1, Q2, not markdown headers)
   - Count decisions: `grep -oP "D\\d+:" context/*.md | wc -l` (also try `grep -o "Lock D[0-9]*" context/*.md | wc -l`)
   - Count branch files: `ls context/*.md | grep -v "_state" | wc -l`
   - Check portfolio.md for "Awaiting Review" entries with decision count and verify pass count
   - Check for loop_engine/kanban_chains child cards on the board via idempotency key pattern `loop:<parent_card_id>:...`

5. **Grill depth was comparable to the original pipeline.** 7 prototypes produced 26-157 Q&A rounds and 66-232 decisions — in the same ballpark as the original queue-builds.sh pipeline (30-164 decisions per prototype per portfolio entries).

## A/B test findings: prompt strategies for loop_engine enforcement

20-prompt A/B test on board `ab-loop-test`. Each card had the same build task but a different prompt strategy. Tracked loop_engine usage via child card idempotency keys.

**What WORKED (constraint framing):**
- C1 constraint_block: "You may NOT write any prototype files directly. You MUST use loop_engine." — loop_engine child cards created.
- C3 constraint_gate: "Your work will be checked for loop_engine usage. No loop_engine = FAILED card." — loop_engine child cards created.
- A3 prose_caps: "CRITICAL WARNING: If you build WITHOUT loop_engine, you are failing the build." — loop_engine child cards created.

**What FAILED (did NOT trigger loop_engine):**
- A1/A2 prose mandates (weak + strong, including restored original queue-builds.sh text)
- B1/B2/B3 explicit tool invocation (named loop_engine params, first-line instruction, step-by-step numbered)
- D1/D2/D3 skill injection ("Load skill: venture-prototype", "/skill" command, skill context framing)
- E1 inline code example with exact loop_engine() call
- H1/H2 minimal (bare + no-loop-mention)

**Pattern:** Constraint-framing (telling the agent what it CANNOT do without loop_engine) outperforms tool-invocation (telling the agent HOW to call loop_engine). The agent knows how to call tools — it needs a reason to not take the shortcut. Framing loop_engine as a hard gate or a prohibition on direct file writes forces the agent to use the structured path.

### Round 2: Stress test (60 cards, 6 winners x n=10)

Round 1 was n=1 per prompt — couldn't distinguish 100% from 30%. Round 2 stress-tested the 6 winners with 10 trials each (60 cards total, randomized dispatch order, unique verify script paths per trial).

**CRITICAL: Checker methodology bug.** Initial round-2 results only matched `Loop:%` card titles in the kanban DB to trace loop_engine usage. This was WRONG — the builder often uses `kanban_chains` instead of `loop_engine`, which creates chain cards with different titles (root, build, verify, README — not "Loop:"). The correct checker must trace THREE signals:
1. `Loop:%` card idempotency keys (`loop:<parent_card_id>:<hash>`)
2. Heartbeat events mentioning `loop_engine` or `kanban_chains` (`task_events` table, `kind='heartbeat'`)
3. Completion events mentioning `loop_engine` or `kanban_chains` (`task_events` table, `kind='completed'`)

Only matching `Loop:%` titles gives massive false negatives (58% → actual near-100%).

**CORRECTED final results (checking all 3 signals):**

| Prompt | loop_engine | Rate |
|--------|------------|------|
| **A3_prose_caps** | **10/10** | **100%** |
| **C3_constraint_gate** | **10/10** | **100%** |
| **F1_threat_reject** | **10/10** | **100%** |
| **F2_threat_observed** | **10/10** | **100%** |
| C1_constraint_block | 9/10 | 90% |
| G1_combo_all | 7/10 | 70% |

**4 prompts hit 100%.** The original "loser" A3 (scored 1/10 with the buggy checker) was actually 10/10. All four winning strategies (CAPS warning, quality gate, threat of rejection, observed-behavior callout) work perfectly with glm-5.2.

**Tiebreaker: simplicity.** F2_threat_observed is the shortest of the 4 perfect prompts: "OBSERVED BEHAVIOR: Builders consistently skip loop_engine... This is the #1 known failure mode... You are not special."

**Why builders use kanban_chains instead of loop_engine:** The venture-prototype skill documents both tools. `loop_engine` is for single-prototype phased builds; `kanban_chains` is for parallel builds. The builder sometimes interprets the build card as a "chain" (build→verify→README) and uses `kanban_chains` to express that sequence. Both create the same structure (child cards with verifier gates) — they're two APIs for the same pattern.

### Round 3: Weaker model test (40 cards, 4 winners x n=10, glm-4.6)

Testing whether the 4 perfect prompts survive a weaker model. Builder config changed from `glm-5.2` to `glm-4.6`.

**Results (all 40 completed):**

| Prompt | glm-5.2 | glm-4.6 | Degradation |
|--------|---------|---------|-------------|
| C3_constraint_gate | 100% | 80% (8/10) | -20% |
| F1_threat_reject | 100% | 80% (8/10) | -20% |
| F2_threat_observed | 100% | 80% (8/10) | -20% |
| A3_prose_caps | 100% | 40% (4/10) | -60% |

**Key findings:**
1. **A3 collapsed.** Emotional urgency ("CRITICAL WARNING") that worked 100% on glm-5.2 only gets 40% on glm-4.6. Weaker models don't parse emotional emphasis as a real constraint. This prompt is model-dependent and unreliable.
2. **C3/F1/F2 are robust.** All three held at 80% — consistent 20% degradation. These prompts survive weaker models. The 20% failures are the model genuinely not understanding multi-step tool invocation, not ignoring instructions.
3. **2 blocked cards were loop_engine working correctly.** The verifier gate caught real quality gaps (37/46 and 40/42 checks) and blocked for replan. This is the intended behavior, not a bug.
4. **Consequence framing is model-robust.** Threat/constraint/gate framing degrades gracefully. Emotional emphasis collapses.

**The 20% floor** on glm-4.6 is the model's instruction-following ceiling — those failures are the model genuinely unable to invoke multi-step tools, not a prompt problem.

### Round 4: Combined prompt (20 cards, glm-4.6)

Took the best element from each of the 3 robust winners (C3+F1+F2) and created a combined prompt. n=20 for tighter signal.

**Combined prompt layered defense:**
1. **Anticipatory (F2):** "OBSERVED BEHAVIOR — #1 known failure mode — you will be tempted" — kills rationalization before it forms
2. **Gate (C3+F1):** "automatically checked — card FAILED — re-dispatched — wasted tokens" — machine-enforced consequence with personal cost
3. **Authority (F1+F2):** Skill quote + exact line numbers ("lines 156-180") — helps weaker models find the call pattern
4. **Identity kill (F2):** "You are not special. Your build is not simple enough" — closes the self-assessment escape hatch

**Result: 55% (11/20) — WORSE than individual winners (80%).** Combining elements diluted the signal. More text gave the weaker model more room to "creatively interpret" instead of following a single clear consequence. **Do not combine winning prompts — pick the simplest individual winner.**

**Final recommendation:** F2_threat_observed is the best prompt — shortest of the 3 robust winners, uses observed-behavior framing, holds at 80% on glm-4.6.

### Blocked verifier cards: skill deployment gap (FIXED)

2 verifier cards blocked during the stress test. Root cause: `loop_engine`'s `kanban_chains` created verifier child cards with `skills: ["prototype-verification"]`, but the `prototype-verification` skill only existed on the builder profile, not the verifier profile. The verifier agent process crashed (exit code 1) on every attempt trying to load a skill it doesn't have. After 2 crashes, the dispatcher gave up and marked the card blocked.

**Fix:** Moved `prototype-verification` to `shared-skills/prototype-verification/`, symlinked from both builder and verifier profiles. Verified by unblocking the 2 cards — verifier processed them successfully without crashing.

**Lesson:** When loop_engine assigns child cards to a DIFFERENT profile than the parent, any `skills` field must reference skills installed on the TARGET profile. This is not checked at template time — it fails at runtime as a crash. Always use shared-skills for skills referenced across profiles.

### A/B testing methodology for agent behavioral enforcement

This pattern is reusable for any "agent isn't following a process" problem:

1. **Round 1 — broad screen.** Write 15-20 prompt variants across strategies (prose, tool-invocation, constraint, threat, skill-injection, example, combo, minimal). Dispatch 1 card each. Identifies which strategy families work at all.
2. **Round 2 — stress test winners.** Take the top N from round 1, dispatch n=10 each (randomized order, same task to eliminate variance). Measures consistency, not just whether it works once.
3. **Trace compliance via side-effects.** Don't parse agent output to check compliance — trace kanban side-effects (child card idempotency keys, tool call evidence in task_events). This is deterministic and not fooled by agent self-reporting. **CRITICAL PITFALL:** When the agent can use EITHER `loop_engine` OR `kanban_chains` to achieve the same goal, your checker MUST look for BOTH. Matching only `Loop:%` card titles misses `kanban_chains` usage entirely — this caused 42% false-negative rate in round 2. Check all 3 signals: (1) `Loop:%` idempotency keys, (2) heartbeat events mentioning either tool name, (3) completion events mentioning either tool name. The SQL query:

```sql
-- ALL three signals combined
SELECT DISTINCT task_id FROM task_events
WHERE kind IN ('heartbeat','completed')
AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%')
UNION
SELECT idempotency_key FROM tasks
WHERE title LIKE 'Loop:%' AND idempotency_key IS NOT NULL
```
4. **Tiebreaker: simplest prompt wins.** If 2+ prompts achieve the same rate, pick the fewest tokens.
5. **Test with weaker models.** A prompt that works at 100% with the strong model may degrade with a weaker model. Run the 4 winners through the weaker model (same n=10 design) to find prompts that are robust, not just lucky with one model's capabilities.

Scripts at `~/.hermes-teams/startup/scripts/ab_test_loop_engine.py` (round 1) and `stress_test_loop_engine.py` (round 2) are reusable templates for this methodology.
