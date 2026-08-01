# Foreach Enhancements — title_template + dot-path resolution

## title_template field

Added to Node dataclass: `title_template: str = ""`. When set on a foreach node, each card gets a custom title instead of the default `[node#idx] skill`.

```json
{
  "id": "grill",
  "foreach": "${nodes.parse.output.ideas}",
  "title_template": "Grill: ${item.name}",
  "body_template": "Slug: ${item.slug}, Score: ${item.score}"
}
```

Supports `${item}` (for string items) and `${item.field}` (for dict items via dot-path resolution).

When absent, falls back to `f"[{node.id}#{idx}] {node.skill or 'task'}"`.

## Dot-path resolution in resolve_template()

When a context value is a dict, `${key.field}` resolves to `value["field"]`:

```python
ctx = {"item": {"slug": "my-idea", "name": "My Idea", "score": 18}}
result = resolve_template("Build ${item.name} (${item.slug})", ctx)
# → "Build My Idea (my-idea)"
```

Implementation in `model.py resolve_template()`:
```python
if isinstance(value, dict):
    for sub_key, sub_val in value.items():
        result = result.replace("${" + key + "." + sub_key + "}", str(sub_val))
    result = result.replace("${" + key + "}", str(value))
```

## Foreach command nodes

When a foreach node has `type="command"`, the command runs per-item without creating kanban cards. Each iteration gets `${item}` and `${item_index}`. Results aggregated as `{"results": [...]}`.

This is distinct from foreach on task nodes, which creates one card per item.

## Trigger context double-prefix bug

When `cmd_start` injects trigger context for manual workflow starts, use BARE keys (`board`, `source`, `project_dir`), NOT pre-prefixed keys (`trigger.board`). The `context()` method in StateDB adds the `trigger.` prefix when merging into context:

```python
# WRONG — produces trigger.trigger.board
context["trigger.board"] = args.board

# CORRECT — produces trigger.board
context["board"] = args.board
```

Symptom: `${trigger.board}` resolves to empty string in templates. The command runs with `--board ` (empty). Verify with:
```python
from workflow_engine.model import resolve_template
print(resolve_template("board=${trigger.board}", ctx))  # should show board name, not empty
```

This only affects `cmd_start` (manual starts). Trigger-based starts (card_completed, bead_ready) inject context correctly because they go through the trigger detection path which already uses bare keys.

## Testing

9 tests in `test_foreach_enhancements.py`:
- Dot-path resolution (4 tests: basic, missing field, nested alongside flat keys, dict as string)
- Title template (4 tests: custom titles, dict items with dot-path, default fallback, special chars)
- Command output feeds foreach (1 test: command JSON → foreach iteration)
