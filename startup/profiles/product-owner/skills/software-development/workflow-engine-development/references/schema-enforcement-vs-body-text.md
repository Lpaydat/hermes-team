# Schema Enforcement vs Body Text — Empirical Results

> **TL;DR**: Output schemas enforce structured output. Body templates don't. This was proven across 8 QA template versions (A through H).

## The experiment

We A/B tested QA workflow templates to find what produces the best evidence depth. The key finding came from comparing versions F, G, and H.

## Version F — body text approach (FAILED)

F strengthened the qa-quick card's `body_template` with:
- Per-claim evidence table format (`| Claim | Command | Result | Verdict |`)
- Security checklist (PASS/FAIL/SKIP with reasons)
- Testability feedback requirement

**Result**: The agent IGNORED the formatting instructions entirely. It read them (referenced claims and commands in prose) but produced a narrative summary instead of filling the structured sections.

Score: evidence specificity 3/10, security checklist 2/10, testability 1/10. **FALSE NEGATIVE** — missed a real stale-label bug.

## Version G — schema enforcement (SUCCEEDED)

G used the SAME structured fields but as `output.schema.required` arrays:

```json
"required": ["verdict", "findings_count", "commit_tested", "verdicts", "checks"],
"properties": {
  "verdicts": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["claim_id", "claim", "verdict", "evidence"],
      "properties": { ... }
    }
  },
  "checks": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["check", "result", "reason"],
      "properties": { ... }
    }
  }
}
```

**Result**: The agent produced full structured arrays. 4 verdicts with exact commands + exit codes. 4 security checks with results + reasons. Evidence depth 9/10.

The body_template explained the contract: "Your metadata MUST include these fields (the engine validates them — missing fields = card FAILS and retries)."

## Version H — exploration field

G achieved 9/10 evidence depth but MISSED a real bug (stale .driver/ labels) that E's loose exploratory approach caught. Structured formats suppress exploration — the agent checks boxes instead of probing content.

H added `exploration[]` as a required schema field:

```json
"exploration": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["probe", "result", "finding"],
    "properties": { ... }
  }
}
```

This forces QA to inspect the CONTENT of every delta file (not just existence) and report what it probed.

## Why it works

The engine calls `validate_against_schema()` at card completion. Invalid output → node marked FAILED → downstream SKIPPED. The failure path is tested (`test_engine.py::test_output_schema_validation`).

The validation threat is what changes behavior. F's body said "you should produce a table." G's schema said "if you don't produce `verdicts[]`, your card fails." The agent responds to the enforcement, not the instruction.

## Rule

**If you need structured output from an agent, put it in `output.schema.required`, not in body_template prose.**

Body text should EXPLAIN the contract with examples so the agent knows what shape to produce. The schema is what enforces it.

## Schema pitfalls (empirically discovered)

| Pitfall | Cause | Fix |
|---------|-------|-----|
| Boolean validation fails | JSON `true` ≠ `"type": "string"` | Use `"type": "boolean"` |
| Null field validation fails | `null` ≠ `"type": "string"` | Remove from `required`, or `"type": ["string", "null"]` |
| Verdict vocabulary drift | Agent writes `"pass"`, `"clean"`, `"ok"` | Enforce `enum: ["PASS", "FAIL"]` |
| `skill` field no-op | Setting `"skill": "X"` on node doesn't inject into card | Profile's `skill_enforcer.mandatory` controls what loads |

## Adaptive sizing pattern

Conditional routing on a sizing field:

```
qa-receive outputs sizing
  ├── sizing == 'small' → qa-quick (1 card, ~30K tokens, 3× cheaper)
  └── sizing != 'small' → qa-build → 4 parallel → qa-verdict (7 cards, ~110K tokens)
```

Dead-branch skip automatically prunes the unused path. No manual skip logic needed.

Proven across versions E and G:
- Small path: 2 cards, 235s wall, 138s active, ~30K tokens
- Fan-out path: 7 cards, 444s wall, 291s active, ~110K tokens
- Same verdict quality, 3× cost difference

## Full scorecard

| Version | Evidence | Security | Findings | Cost | Key change |
|---------|----------|----------|----------|------|------------|
| A (cron) | 7/10 | 0 | 0 | ~20K | Baseline |
| B (1-card) | 9/10 | 0 | 0 | ~28K | Best single-card evidence |
| C (7-card) | 7/10 | 8/10 | 0 | ~110K | Fan-out depth |
| D (C+fixes) | 9/10 | 8/10 | 0 | ~110K | Delta-first, vocabulary fixed |
| E (adaptive) | 6/10 | 3/10 | **1** | ~30K | Adaptive sizing, real finding |
| F (body text) | 3/10 | 2/10 | 0 | ~25K | FAILED — agent ignored structure |
| G (schema) | **9/10** | **9/10** | 0 | ~30K | Schema enforcement works |
| H (G+explore) | **9/10** | **9/10** | **TBD** | ~30K | Exploration[] enforced |
