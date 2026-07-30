# Profile SOUL.md Refactor Audit

Complete audit of all 12 startup profiles. Identifies what's embedded vs already
extracted to skills, enabling safe refactoring to identity-only SOUL.md files.

## The two-part refactor pattern (proven on builder + PO)

1. **SOUL.md → identity-only** via `writing-great-soul` — strip roster rot, inlined
   procedures, negations, duplicated definitions. Keep: stance, handoffs, skill index
   (names + triggers only).
2. **Workflows → skills** via `create-workflow` — extract embedded procedures from
   SOUL.md into standalone skills. Profile loads the skill on demand.

## Complete profile inventory (as of 2026-07-30)

### Already refactored (2 profiles)

| Profile | SOUL specialty lines | Skills | Symlinks | Scripts | Cron | Mandatory |
|---------|---------------------|--------|----------|---------|------|-----------|
| product-owner | 29 | 16 | 9 | 4 | 3 jobs | 2 |
| builder | 23 | 28 | 6 | 7 | 4 jobs | 6 |

### Remaining (10 profiles, not yet refactored)

| Profile | SOUL specialty | Skills | Symlinks | Scripts | Cron | What's embedded |
|---------|---------------|--------|----------|---------|------|-----------------|
| architect | 52 | 7 | 4 | 0 | 0 | T0-T3 gate ceremony, design partner mode steps, hard rules |
| tech-lead | 44 | 13 | 6 | 5 | 2 jobs | 5-phase loop, memory architecture, delegation rules, constraints |
| developer | 22 | 9 | 5 | 0 | 0 | 5-step per-card loop, hard rules |
| verifier | 22 | 9 | 5 | 0 | 0 | 3-stage protocol, merge steps, escalation rules |
| debugger | 45 | 6 | 3 | 1 | 0 | 2-exit logic, doctrine sources, 3 refinements, stakes tiers |
| qa | 44 | 10 | 4 | 0 | 0 | 7-step testing protocol, program types, hard rules |
| researcher | 55 | 14 | 4 | 0 | 0 | 6-step research process, fan-out via kanban_chains, writing principles |
| scout | 28 | 14 | 4 | 2 | 2 jobs | 5-step scan process, source tiers |
| ops | 26 | 22 | 4 | 3 | 2 jobs | 5 job areas, how-you-work principles |
| advisor | 35 | 20 | 4 | 0 | 0 | 5-step sparring protocol, sector lean, tone |

## Refactor phases (safe to risky)

### Phase 1: Already-skilled (SOUL cleanup only)
- **developer** — `developer-loop` skill already exists. Trim hard rules to stance.
- **verifier** — `adversarial-review` skill already exists. Trim protocol details to stance.

### Phase 2: Need skill verification + SOUL cleanup
- **architect** — verify `design-council` has T0-T3 gate ceremony. Trim SOUL.
- **tech-lead** — verify `loops-engineering` has the 5-phase loop. Trim SOUL.
- **debugger** — verify `debug-loop` has the 2-exit logic + refinements. Trim SOUL.
- **qa** — verify/create `live-testing` skill with the 7-step protocol. Trim SOUL.

### Phase 3: Need skill creation + SOUL cleanup
- **researcher** — extract research methodology to skill. Trim SOUL.
- **scout** — extract scan methodology to skill. Trim SOUL.
- **ops** — extract health monitoring to skill. Trim SOUL.
- **advisor** — verify `startup-advisory` skill exists. Trim SOUL.

## Safety protocol per profile

1. Read current SOUL.md
2. Verify the referenced skill EXISTS and CONTAINS the procedure
3. If skill is missing or incomplete → create/patch it FIRST
4. Rewrite SOUL.md to identity-only (stance, handoffs, skill index)
5. Commit
6. Don't restart gateway yet — wait until batch is done

## Cron JSON parsing

Profile cron jobs.json has a wrapper structure: `{"jobs": [...], "updated_at": "..."}`.
NOT a bare JSON array. Always extract `data.get("jobs", [])`.

### Active cron jobs by profile

- **PO**: workflow-engine (1-min), hygiene-guard (4h), weekly sprint report
- **builder**: pipeline-guard (4x daily), queue-builds (6h), scan-guard (3h), requesthunt (3x/week)
- **tech-lead**: 2 jobs
- **scout**: 2 jobs
- **ops**: 2 jobs
- All others: 0 jobs

## Deleted profiles

- **venture-builder** — deleted 2026-07-30. Was the old version of current `builder` profile.
