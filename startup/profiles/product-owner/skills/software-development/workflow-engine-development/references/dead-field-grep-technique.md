# Dead-field grep: catching vapor config in declarative engines

## The problem

In a declarative engine (workflow engine, config-driven dispatcher, rule engine), a field can exist in three states:

1. **Parsed and used** — defined in the model, read by the runtime, affects behavior.
2. **Parsed but dead** — defined in the model, parsed from JSON, but NEVER read by the runtime. Vapor config.
3. **Not defined** — doesn't exist in the model at all.

State 2 is the most insidious. Tests that check parsing pass. Templates that use the field load without error. But the field has zero behavioral effect. It's a green checkmark on a red wall.

## The technique

**Grep the runtime (execution layer), not the model (parse layer).**

```bash
# For each field the requirements spec mentions:
grep <field> runtime.py    # the dispatch/execution layer
grep <field> model.py      # the parse layer (should hit — proves it's parsed)
```

If the model grep hits but the runtime grep returns 0, the field is dead.

## Worked example (2026-07-31)

The spec said: *"card creation modes: template/delegate/chain."*

- `Node.card_mode` was defined in `model.py:42`
- Parsed at `model.py:102` via `n.get("card_mode", "template")`
- Appeared in workflow templates
- `grep card_mode runtime.py` returned **0 hits**
- `_dispatch_node` always created a single card regardless of `card_mode` value

Two of three modes were vapor. Model-level tests (does it parse?) would never catch this. Only the runtime grep does.

## When to apply

Run this check as part of any spec-axis code review on a declarative engine. Check every enum/flag/option field:

- Trigger sources (`bead_ready`, `card_completed`)
- Validation modes (`hard`, `soft`)
- Composition types (`subworkflow`, `foreach`)
- Card modes (`template`, `delegate`, `chain`)
- Any field with a default value the runtime never overrides

A field with a default value that the runtime never branches on is a no-op.

## Fixing dead fields

Two options:

1. **Implement the behavior** — add the runtime branch that reads the field and changes behavior.
2. **Remove the field** — if the requirement is out of scope, delete the field from the model and from `from_dict`. Don't leave it as vapor.

Never leave a parsed-but-dead field in the model. It misleads every future reader into thinking the feature works.
