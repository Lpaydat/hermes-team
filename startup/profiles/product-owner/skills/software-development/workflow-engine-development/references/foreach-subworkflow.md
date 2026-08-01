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

**Final results:**

| Prompt | loop_engine | Rate |
|--------|------------|------|
| **C3_constraint_gate** | **9/10** | **90%** |
| F1_threat_reject | 5/10 | 50% |
| F2_threat_observed | 3/10 | 30% |
| C1_constraint_block | 2/10 | 20% |
| G1_combo_all | 2/10 | 20% |
| A3_prose_caps | 1/10 | 10% |

**Winner: C3_constraint_gate (90%)** — "GATE: This card has a quality gate. Your work will be checked for loop_engine usage. If loop_engine was not called, the card will be REJECTED and re-dispatched."

**Key insight: verifiable consequences > stated consequences.** C3 won because it frames a downstream check the builder believes will execute. A3 (which won round 1 at 1/1 but collapsed to 1/10 in round 2) uses emotional urgency ("CRITICAL WARNING") that the builder dismisses. The builder responds to gates it believes will fire, not threats it can't verify.

**Adopt C3_constraint_gate as the build card body in builder-single.json.**

### Blocked verifier cards: skill deployment gap

2 verifier cards blocked during the stress test. Root cause: `loop_engine`'s `kanban_chains` created verifier child cards with `skills: ["prototype-verification"]`, but the `prototype-verification` skill only exists on the builder profile, not the verifier profile. The verifier agent process crashed (exit code 1) on every attempt trying to load a skill it doesn't have. After 2 crashes, the dispatcher gave up and marked the card blocked.

**Fix:** Either install the skill on the verifier profile, or don't reference it in loop_engine's verifier child cards — let the verifier use its own skills (`dod-verdict`, `adversarial-review`).

**Lesson:** When loop_engine assigns child cards to a DIFFERENT profile than the parent, any `skills` field must reference skills installed on the TARGET profile. This is not checked at template time — it fails at runtime as a crash.

### A/B testing methodology for agent behavioral enforcement

This pattern is reusable for any "agent isn't following a process" problem:

1. **Round 1 — broad screen.** Write 15-20 prompt variants across strategies (prose, tool-invocation, constraint, threat, skill-injection, example, combo, minimal). Dispatch 1 card each. Identifies which strategy families work at all.
2. **Round 2 — stress test winners.** Take the top N from round 1, dispatch n=10 each (randomized order, same task to eliminate variance). Measures consistency, not just whether it works once.
3. **Trace compliance via side-effects.** Don't parse agent output to check compliance — trace kanban side-effects (child card idempotency keys, tool call evidence in task_events). This is deterministic and not fooled by agent self-reporting.
4. **Tiebreaker: simplest prompt wins.** If 2+ prompts achieve the same rate, pick the fewest tokens.

Scripts at `~/.hermes-teams/startup/scripts/ab_test_loop_engine.py` (round 1) and `stress_test_loop_engine.py` (round 2) are reusable templates for this methodology.
