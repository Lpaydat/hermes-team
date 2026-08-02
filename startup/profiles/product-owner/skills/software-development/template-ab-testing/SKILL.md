---
name: template-ab-testing
description: "A/B test workflow templates against each other on identical inputs, deep-analyze with subagents, pin the winner, ditch the losers. Use when improving a workflow template through iterative comparison — building competing versions, running them head-to-head, and empirically selecting the best."
---

# Template A/B Testing

Drive workflow templates to full marks through empirical competition. Each **round** builds 2–3 versions, tests them head-to-head on identical inputs, deep-analyzes with subagents, and pins exactly one winner.

## Leading word: *the gauntlet*

The process is **the gauntlet** — a structured arena where template versions compete under identical conditions, scored on every dimension, until only the strongest survives. Each round narrows the field. The gauntlet runs until a version earns full marks or you hit a wall that needs new infrastructure.

## Steps

### 1. Fork the pinned version

Copy the current pinned template to a new version letter (`qa-test-e.json` → `qa-test-f.json`). Change the `id` field. Each version is one `.json` file in `startup/scripts/workflow_engine/templates/`.

```
cp templates/qa-test-e.json templates/qa-test-f.json
```

**Completion criterion:** new template file exists, `id` changed, loads via `Workflow.from_dict(json.load(open(path)))`.

### 2. Make exactly one change per version

Each competing version changes ONE thing. Isolate the variable. If you change evidence depth AND adaptive sizing in the same fork, you can't tell which fix drove the result.

**Completion criterion:** the diff between fork and parent is one logical change, describable in one sentence.

### 3. Set up dual-board test

Each version gets its own kanban board and cloned repo — identical inputs, isolated execution:

```
hermes kanban boards create qa-ab-f
cp -rf /tmp/ab-test/repo-a /tmp/ab-test/repo-f
```

Update `active-projects.json` with all test boards. Add the new board suffix to the cron skip list so the old cron doesn't interfere. Seed the merge-check state file for each board to the pre-change SHA.

**Completion criterion:** every competing version has a board + repo + verifier PASS card, seeded to the same pre-change state. The engine tick dispatches the first card.

### 4. Run the gauntlet

Tick the engine every 90 seconds. Each version runs in parallel — the engine processes all boards in one tick. Monitor with a background process:

```bash
for i in $(seq 1 8); do
    sleep 90
    python3 workflow_engine/main.py tick 2>&1 | grep -v "Template not found"
    # break on WORKFLOW COMPLETE or VALIDATION FAILED
done
```

**Completion criterion:** all competing workflows reach COMPLETE or FAILED. Record the tick-by-tick timeline.

### 5. Deep analysis with subagents

Dispatch 5–8 subagents in parallel batches, each analyzing one dimension. Never skip this — the raw metrics lie without expert interpretation.

Standard analysis dimensions:
- **Verdict quality** (evidence specificity, self-containedness, decision justification)
- **Metadata compliance** (schema match, field correctness, downstream usability)
- **Execution rigor** (commands run, delta-first, findings filed, false negatives)
- **Cost-efficiency** (wall-clock, active time, token estimate, parallelism)
- **Engine mechanics** (validation failures, routing correctness, race conditions)
- **Finding quality** (are findings real? verified by grep? correct severity?)

Pass each subagent the exact card IDs and board names. Read the consolidated reports before deciding.

**Completion criterion:** all subagent batches returned, consolidated scorecard produced.

### 6. Pin one, ditch the rest

The winner becomes the pinned version. Losers get renamed `.disabled` (or `.failed` for experiments that backfired). Both stay in git history.

```bash
mv templates/qa-test-e.json templates/qa-test-e.json.disabled
# winner stays active
```

**Completion criterion:** one active template, all others `.disabled` or `.failed`, commit documents the A/B result and rationale.

### 7. Identify gaps for next round

List every dimension where the winner didn't score full marks. Each gap becomes the hypothesis for the next fork. If no template-addressable gaps remain, the gauntlet is complete.

**Completion criterion:** gap list written, each gap classified as template-addressable or infrastructure-blocked.

## Reference

### Enforcement hierarchy

The most important lesson from 8 rounds: how you enforce behaviour matters more than what you ask for.

```
Output schema (required fields)  ← ENFORCED. Card fails validation, retries.
  > Body template (structured)    ← IGNORED. Agent reads it, writes what it wants.
  > Body template (prose hints)   ← WEAKER. Suggestion, not contract.
  > Skill loading                  ← NO-OP if skill_enforcer mandates it anyway.
```

Schema enforcement beat body text every time. F asked for per-claim evidence tables in the body — agent ignored it. G required `verdicts[]` in the output schema — agent produced it. This is tool-level enforcement over prompting.

### What changes behaviour vs what doesn't

| Change | Effect | Evidence |
|--------|--------|----------|
| Card structure (1 card vs 7 cards) | **Drives depth** — 7 cards executed all phases, 1 card skipped 5 | C vs B |
| Output schema required fields | **Enforces output** — missing fields fail validation | G vs F |
| Body template strengthening | **No effect** — agent ignores structured format | F vs E |
| Adaptive routing (conditional edges) | **Works** — sizing field routes correctly | E |
| Boolean values in conditions | **Bug trap** — `True != 'true'`, use schema `type: boolean` | C |

### Dual-board setup checklist

- [ ] Board created: `hermes kanban boards create qa-ab-X`
- [ ] Repo cloned: `cp -rf /tmp/ab-test/repo-a /tmp/ab-test/repo-X`
- [ ] active-projects.json updated with board + repo path
- [ ] Cron skip list updated (add `-X` suffix)
- [ ] check-merge state seeded to pre-change SHA
- [ ] Verifier PASS card created on board
- [ ] Engine state cleared: `rm -f workflow-state.db*`
- [ ] Tick 1 dispatches qa-receive

### Subagent dispatch template

```
goal: Compare [DIMENSION] between [VERSION-X] and [VERSION-Y].
Read: hermes kanban --board qa-ab-X show t_CARDID
      hermes kanban --board qa-ab-Y show t_CARDID
Score each 1-10 on: [specific criteria]
Report as scored table.
```

Dispatch 5–8 in parallel batches of 3. Read consolidated reports before deciding.

### When to stop the gauntlet

Stop when remaining gaps are **infrastructure-blocked** — they need a real project repo, an injected bug, or an engine feature, not another template fork. Template-addressable gaps are exhausted when:

- All output schemas enforce structured evidence
- All routing paths tested (small + medium/large)
- No validation failures
- Schema enforcement is the enforcement mechanism (not body text)

## Choosing the right building block

A workflow can use three orchestration systems. Which one depends on how much you know at design time.

See [`references/building-blocks.md`](references/building-blocks.md) for the full decision tree and verified API details for all three: declarative workflow engine (static), kanban_chains (parallel fan-out), loop_engine (dynamic iteration).

The short version: static routing → JSON template. Dynamic fan-out → profile calls kanban_chains inside a template-dispatched card. Dynamic iteration → profile calls loop_engine inside a template-dispatched card.
