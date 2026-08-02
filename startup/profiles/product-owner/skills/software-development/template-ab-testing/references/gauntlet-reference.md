# Gauntlet Reference

Material consulted during specific gauntlet steps — not needed every run.

## Enforcement hierarchy

How you enforce behaviour matters more than what you ask for.

```
Output schema (required fields)  ← ENFORCED. Card fails validation, retries.
  > Body template (structured)    ← IGNORED. Agent reads it, writes what it wants.
  > Body template (prose hints)   ← WEAKER. Suggestion, not contract.
  > Skill loading                  ← NO-OP if skill_enforcer mandates it anyway.
```

Schema enforcement beat body text every time. F asked for per-claim evidence tables in the body — agent ignored it. G required `verdicts[]` in the output schema — agent produced it. This is tool-level enforcement over prompting.

## What changes behaviour vs what doesn't

| Change | Effect | Evidence |
|--------|--------|----------|
| Card structure (1 card vs 7 cards) | **Drives depth** — 7 cards executed all phases, 1 card skipped 5 | C vs B |
| Output schema required fields | **Enforces output** — missing fields fail validation | G vs F |
| Body template strengthening | **No effect** — agent ignores structured format | F vs E |
| Adaptive routing (conditional edges) | **Works** — sizing field routes correctly | E |
| Boolean values in conditions | **Bug trap** — `True != 'true'`, use schema `type: boolean` | C |

## Dual-board setup checklist

- [ ] Board created: `hermes kanban boards create qa-ab-X`
- [ ] Repo cloned: `cp -rf /tmp/ab-test/repo-a /tmp/ab-test/repo-X`
- [ ] active-projects.json updated with board + repo path
- [ ] Cron skip list updated (add `-X` suffix)
- [ ] check-merge state seeded to pre-change SHA
- [ ] Verifier PASS card created on board
- [ ] Engine state cleared: `rm -f workflow-state.db*`
- [ ] Tick 1 dispatches qa-receive

## Subagent dispatch template

```
goal: Compare [DIMENSION] between [VERSION-X] and [VERSION-Y].
Read: hermes kanban --board qa-ab-X show t_CARDID
      hermes kanban --board qa-ab-Y show t_CARDID
Score each 1-10 on: [specific criteria]
Report as scored table.
```

Dispatch 5–8 in parallel batches of 3. Read consolidated reports before deciding.
