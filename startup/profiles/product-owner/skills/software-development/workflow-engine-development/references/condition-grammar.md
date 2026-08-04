# Condition Grammar Reference

The condition engine evaluates edge `condition` strings and `wait_condition` strings.

## Grammar

```
condition := clause (OR clause)*
clause    := atom (AND atom)*
atom      := ${var} <op> <value>
```

- AND binds tighter than OR. No parentheses.
- Left-to-right evaluation. AND short-circuits on first False. OR short-circuits on first True group.

## Operators

| Operator | Form | Example | Notes |
|----------|------|---------|-------|
| `==` (quoted) | `${x} == 'val'` | `${verdict} == 'PASS'` | Exact string equality. Always works. |
| `==` (bare) | `${x} == True` | `${plan_complete} == True` | Bare booleans, null, numbers. Fixed in f498e77. |
| `!=` (quoted) | `${x} != 'val'` | `${verdict} != 'FAIL'` | Exact string inequality. |
| `!=` (bare) | `${x} != null` | `${fix_commit} != null` | Bare value inequality. |
| `exists` | `${x} exists` | `${plan_complete} exists` | Truthy check. Works for all types. **Preferred for boolean gates.** |
| `is empty` | `${x} is empty` | `${findings} is empty` | Falsy check. |
| `<`, `<=`, `>`, `>=` | `${x} < 3` | `${iteration} < 10` | Numeric with float coercion. Falls back to string comparison if either side isn't a number. |

## Bare value types

Bare (unquoted) values are coerced:
- `True` / `true` → boolean True
- `False` / `false` → boolean False
- `null` / `None` → None
- Numbers → float comparison
- Anything else → string comparison

## Defensive rules

1. **Prefer `exists` for boolean gates.** `${plan_complete} exists` works regardless of type. Avoid `== True`.
2. **Quoted strings for enums.** `${verdict} == 'PASS'` is the correct form for string enums.
3. **Test before deploying.** If a conditional edge silently fails (node dead-branched), test with:
   ```python
   from workflow_engine.model import evaluate_condition
   evaluate_condition("${x} == True", {"x": True})  # should be True
   ```

## Variables

- `${trigger.*}` — trigger context fields (card_id, board, assignee, title, metadata spread flat)
- `${nodes.X.output.*}` — output fields from completed node X
- `${nodes.X.iteration}` — current iteration count for node X (back-edge loops)
- `${item}`, `${item_index}` — foreach loop variables
