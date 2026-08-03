# Verify→Fix→Re-verify Loop Pattern

The proven template design for any node that produces a verdict (PASS/FAIL/ESCALATE) and feeds into a "close/ship/merge" node.

## The problem

An unconditional edge from verify to close means verify FAIL flows straight to close. Close then merges despite FAIL — shipping bugs. This is lesson #13.

## The fix — conditional DAG with fix loop

```
plan → verify ─┬─ PASS/ESCALATE → close
               └─ FAIL → fix → re-verify ─┬─ PASS/ESCALATE → close
                                          └─ FAIL → fix (back-edge, max_iterations: 3)
```

### Edge JSON

```json
"edges": [
  {"from": "plan", "to": "verify", "condition": "${nodes.plan.output.plan_complete} exists"},
  {"from": "verify", "to": "close", "condition": "${nodes.verify.output.verdict} == 'PASS' OR ${nodes.verify.output.verdict} == 'ESCALATE'"},
  {"from": "verify", "to": "fix", "condition": "${nodes.verify.output.verdict} == 'FAIL'", "max_iterations": 10},
  {"from": "fix", "to": "re-verify", "max_iterations": 10},
  {"from": "re-verify", "to": "close", "condition": "${nodes.re-verify.output.verdict} == 'PASS' OR ${nodes.re-verify.output.verdict} == 'ESCALATE'"},
  {"from": "re-verify", "to": "fix", "condition": "${nodes.re-verify.output.verdict} == 'FAIL'", "max_iterations": 10}
]
```

### Node requirements

- **verify**: `output.schema.required` must include `verdict` and `findings_count`. Body must NOT say "create fix cards" — the template handles fix routing.
- **fix**: `output.schema.required` must include `fixed` and `findings_fixed`. Body must detail finding structure (ID, severity, file:line, repro).
- **re-verify**: Same schema as verify. Must run fresh-eyes pass (not just delta check).
- **close**: Body must read BOTH verify and re-verify verdicts. `tasks_planned`/`tasks_completed` should reference `${nodes.plan.output.task_count}` — never hardcode.

### Known gap: dead-branch skip fails when verify=PASS (round 5)

When verify returns PASS, fix and re-verify are never entered. But they're pending in a cycle — dead-branch skip can't fire (gauntlet lesson #17). The instance stays `active` and must be manually completed. This is an engine-level issue, not a template design flaw.

### Production-mode testing — enforce via schema, not body text

The verify node must test with TESTING=False. Test fixtures (conftest.py) mask deployment bugs. Round 5 missed a Critical that round 4 caught — same code, same bug, different verifier behavior.

Add `production_mode_tested` as a required boolean in the verify output schema:

```json
"required": ["verdict", "findings_count", "production_mode_tested"],
"properties": {
  "production_mode_tested": {"type": "boolean"}
}
```

The body should include: "test the application with TESTING=False (or production config). Boot the app in production mode and exercise EVERY endpoint — any 500 is a Critical finding."

### Live test results

- **Round 4:** verify FAIL → fix → re-verify ESCALATE → close(escalated). WORKFLOW COMPLETE.
- **Round 5:** verify PASS → close(merged, tasks_planned=2, tasks_completed=2). Instance required manual completion (dead-branch gap).
- **Round 6:** verify FAIL (7 findings, production_mode_tested=True) → fix (7 fixed) → re-verify PASS → close(merged). WORKFLOW COMPLETE.
- **Unbiased livetest (5 specs):** 4 of 5 work complete. Tic-Tac-Toe + String Validator instances completed. Markdown + CSV work done but instances stuck (dead-branch-cycle). URL Shortener still iterating. All 5 built autonomously with zero hints.

### Iteration cap: user preference is 10

User explicitly requested `max_iterations: 10` for fix→re-verify cycles. A cap of 3 stops the loop too early on complex bugs. Use 10 for all cycle edges.

### Close body template — don't hardcode verdicts

```json
// BAD — hardcoded verdict literal
"body_template": "**Verdict:** FAIL"

// GOOD — read from upstream nodes
"body_template": "Read the verify card verdict: ${nodes.verify.output.verdict}\nIf the fix→re-verify loop ran, read: ${nodes.re-verify.output.verdict}"
```

And use node references for task counts:

```json
// BAD — hardcoded
"body_template": "tasks_planned: N"

// GOOD — reference plan output
"body_template": "tasks_planned: ${nodes.plan.output.task_count}"
```
