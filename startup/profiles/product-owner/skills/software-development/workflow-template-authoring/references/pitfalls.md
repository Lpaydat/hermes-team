# Template Pitfalls

Real bugs and behavioral findings discovered through empirical testing across 8 A/B rounds. Each was caught and fixed in production templates.

## Output schema enforcement > body text

The most important lesson. A `body_template` tells the agent what to do. An `output.schema` with `required` fields forces the agent to produce it — or the card fails validation and retries. Body text instructions are routinely ignored by the agent.

```
output.schema (required fields) → ENFORCED (card fails, retries)
body_template (structured text) → IGNORED (agent writes what it wants)
skill field on node             → NO-OP (skill_enforcer handles it)
```

If you need structured output (per-claim evidence, security checklists, exploration results), put them as required arrays in the output schema:

```json
"output": {
  "schema": {
    "type": "object",
    "required": ["verdict", "verdicts", "checks"],
    "properties": {
      "verdicts": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["claim_id", "claim", "verdict", "evidence"],
          "properties": { ... }
        }
      }
    }
  }
}
```

## Boolean values and conditions

Python `str(True)` produces `"True"` (capital T). Condition comparisons against `'true'` (lowercase) fail silently. Fix: use `type: "boolean"` in the output schema, and compare in conditions with the Python form.

## Optional fields in output schema

If a field might be `None` (e.g., `image_tag` when there's no container), don't put it in `required` or set a strict `type: "string"` — the engine will reject `None`. Either omit from schema or make it nullable.

## `depends_on` with explicit edges

If you use explicit `edges`, nodes declared in `depends_on` must also have corresponding explicit edges — otherwise they're unreachable and the template won't validate.

## `skill` field is a no-op

Setting `"skill": "live-testing"` on a node does not load the skill on the card. The profile's `skill_enforcer` config handles skill loading. The field is safe to set (documents intent) but has no runtime effect.
