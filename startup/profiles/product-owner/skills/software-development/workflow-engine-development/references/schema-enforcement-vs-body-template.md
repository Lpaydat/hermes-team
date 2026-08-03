# Schema Enforcement vs Body Template

Critical lesson from 7 rounds of QA workflow A/B testing (see qa-ab-test-results.md).

## The problem

`body_template` serves as **instructions to the agent**, not an **output format**. The agent reads body text as guidance but writes whatever summary it wants. Structured output requirements written in body prose are ignored.

## Proof — version F (failed)

F added to qa-quick's body_template:
- Per-claim evidence table (markdown table: `| Claim | Command | Result | Verdict |`)
- Enumerated security checklist (`PASS/FAIL/SKIP — reason` per check)
- Testability feedback section

**Result:** agent produced a 627-char narrative paragraph. Zero structured sections appeared in output. Structural markers (`### Per-claim`, `| Claim |`, `Security checklist`, `PASS/SKIP`) all absent.

**Worse:** F produced a **false negative** — missed a real stale-label bug that E caught. The rigid structured format made QA check .driver/ docs for existence only ("docs created with discovery content"), never inspecting their content. F tested 8 claims (vs E's 6) but with shallower inspection per claim.

## The fix — output.schema required fields (version G)

Add structured arrays as **required** fields in the node's `output.schema`:

```json
"output": {
  "schema": {
    "type": "object",
    "required": ["verdict", "findings_count", "commit_tested", "verdicts", "checks"],
    "properties": {
      "verdicts": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["claim_id", "claim", "verdict", "evidence"],
          "properties": {
            "claim_id": {"type": "string"},
            "claim": {"type": "string"},
            "verdict": {"type": "string", "enum": ["proven", "disproven", "untested"]},
            "evidence": {"type": "string"}
          }
        }
      },
      "checks": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["check", "result", "reason"],
          "properties": {
            "check": {"type": "string"},
            "result": {"type": "string", "enum": ["pass", "fail", "skip"]},
            "reason": {"type": "string"}
          }
        }
      }
    }
  }
}
```

If QA doesn't produce these arrays, the card **fails validation and retries**.

## Why schema enforcement works where body text doesn't

- **Schema = tool-level enforcement.** The engine rejects non-compliant output mechanically. The agent has no choice.
- **Body text = prompting.** The agent reads instructions as suggestions. It optimizes for writing a good summary, not for following a format.
- **Schema preserves flexibility.** Required fields enforce structured *reporting* without constraining *how* the agent works. The agent can still explore freely — it just must report results in the required format.
- **Body text suppresses exploration.** Rigid checklists in body make the agent test for breadth (checking off items) rather than depth (probing for bugs).

## When to use each

| Want | Use |
|------|-----|
| Agent to produce structured output (evidence arrays, checklists) | `output.schema` required fields |
| Agent to understand what to do | `body_template` prose |
| Agent to explore and find bugs | Flexible body + schema for reporting |
| Agent to follow exact steps | Multiple cards (fan-out) — card structure drives depth |

## Related pitfalls

1. **Boolean fields**: use `{"type": "boolean"}`, NOT `{"type": "string", "enum": ["true"]}`. Python's `str(True)` is `"True"`.
2. **Optional fields**: if null is valid (e.g., `image_tag` when no container), omit from schema. `{"type": "string"}` rejects null.
3. **Command script booleans**: scripts must output lowercase strings (`"true"`/`"false"`) for edge condition matching, not Python booleans.
