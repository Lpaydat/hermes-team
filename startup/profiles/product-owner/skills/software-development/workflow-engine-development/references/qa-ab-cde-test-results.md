# QA Workflow A/B/C/D/E Test Results

## Validation cycle (user's required process — not optional)

For EVERY workflow template:
1. Build 2-3 versions with different approaches
2. Run A/B/C tests in parallel on identical inputs (dual-board, cloned repos)
3. Deep analysis with 8+ subagents (verdict quality, metadata, execution rigor, cost, engine mechanics)
4. Pin winner, ditch losers (.disabled suffix, keep in git)
5. Fork from winner, fix gaps
6. Repeat until full marks on every aspect

## Score progression

| Version | Approach | Verdict quality | Execution rigor | Status |
|---------|----------|----------------|-----------------|--------|
| A (cron) | Old cron phase_qa_trigger | 28/60 | 4/10 | Disabled |
| B (engine 1-card) | Full 8-phase protocol in one card body | 34/60 | 5/10 | Disabled |
| C (engine 7-card) | Fan-out with parallel test cards | 52/60 | 7/10 | Disabled |
| D (engine 7-card) | C + 6 gap fixes | Improved | Improved | Disabled |
| E (engine 10-node) | D + adaptive sizing + intermediate schemas | Current | Current | Active |

## Key finding

**Card structure drives execution depth, not protocol text.**

Same 8-phase live-testing protocol:
- In 1 card → QA skips 5 phases (scored 5/10 execution rigor)
- In 7 cards → QA executes all 7 phases (scored 7-9/10)

Proven empirically with 5 subagent deep analysis on identical inputs.

## Template pitfalls discovered (from A/B/C/D/E testing)

1. **Boolean values**: `str(True)` = `"True"` not `"true"`. Output lowercase strings from command scripts.
2. **Schema type mismatches**: QA writes Python booleans. Use `"type": "boolean"`, never string enums.
3. **Optional fields break validation**: If sometimes None (e.g. `image_tag`), omit from schema.
4. **`depends_on` unreachable with explicit edges**: Add explicit edges for every dependency.
5. **`skill` field is a no-op on task nodes**: Skills load via `skill_enforcer.mandatory` in profile config.
6. **Verdict vocabulary drift**: Standardize ALL intermediate cards to uppercase PASS/FAIL via output schema.
7. **Verdict card needs findings[] array**: Not just count. Downstream bug-router needs the actual array.
8. **Verdict card needs inline evidence**: One key command/exit-code per phase cited in verdict body.
9. **Corrupt board DBs crash engine**: Guard `_boards_to_check` with `SELECT 1 FROM tasks LIMIT 1`.
10. **Command scripts replace cron**: Old cron logic → command node scripts outputting JSON for edge conditions.

## loop_engine and kanban_chains usage (corrected from session)

- **loop_engine** is NOT debugger-only. Used by: architect, builder, debugger (3 profiles).
- **kanban_chains** is NOT tech-lead-only. It's universal — every profile has it enabled.
- **QA uses kanban_chains** for medium/large fan-out (via `hermes kanban swarm`), NOT loop_engine.
- QA does NOT converge on hypotheses. It tests empirically and reports findings.

## Debugger output contract (mismatch found)

dev-dispatch.json route-bug expects `verdict: "root-caused" | "cannot-reproduce"`.
Debugger actually outputs `verdict: "fixed" | "escalated-design" | "blocked-hitl"`.
This is a LIVE MISMATCH that needs fixing in dev-dispatch.json.

## Architect has no debugger escalation path

Debugger SOUL.md references routing to architect on `escalated-design`.
But architect profile has ZERO documented handling for debugger cards.
Real path: debugger → PO → PO opens architect gate.
