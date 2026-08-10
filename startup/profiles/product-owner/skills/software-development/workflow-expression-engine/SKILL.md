---
name: workflow-expression-engine
description: "The expression and variable-resolution layer of workflow engines: template substitution (${...} patterns), condition evaluation (operators, boolean composition), and cross-engine comparison. Load when extending the resolver, adding operators, debugging a condition that silently fails, comparing Hermes's evaluator against another engine (e.g. nginbot-api), or planning a migration/merge of expression syntax."
triggers:
  - expression engine
  - variable resolution
  - template substitution
  - condition evaluation
  - evaluate_condition
  - resolve_template
  - TEMPLATE_RE
  - workflow condition
  - workflow variable
  - expression comparison
  - migrate expression engine
  - nginbot expression
  - expr-eval
---

# Workflow Expression Engine

The expression layer is the part of a workflow engine that resolves variable references (`${nodes.X.output.Y}`) in templates and evaluates condition strings (`${var} == 'value'`). It sits between the template JSON (structure) and the tick loop (execution): templates *declare* expressions, the resolver/evaluator *interprets* them at runtime.

Load this skill when:
- Adding a new operator, variable namespace, or comparison form to the condition evaluator
- Debugging a condition that silently never fires (typo → stripped to empty → False)
- Comparing Hermes's expression engine against another system's (nginbot-api, n8n, Temporal)
- Planning a migration or syntax merge between expression engines
- Reasoning about what `${...}` patterns exist and how they resolve

## Hermes expression layer (model.py)

### Variable resolution — `resolve_template()` (~L537)

**There is no compiled `TEMPLATE_RE`.** Resolution is `str.replace()` over a flat context dict:

1. For each `(key, value)` in context:
   - If `value` is a dict: expand one level of dot-paths (`${key.sub}` → `value["sub"]`), then stringify the whole dict as `${key}`.
   - If `value` is a list: stringify wholesale (no per-element pathing inside templates).
   - Otherwise: `str.replace("${" + key + "}", str(value))`.
2. Unresolved `${...}` are **stripped to `""`** via `re.sub(r"\$\{[^}]+\}", "")` — not raised. **A typo in a variable name silently produces an empty string.** This is the #1 cause of conditions that never fire.

### Complete variable inventory

| Pattern | Resolves to | Set by |
|---|---|---|
| `${nodes.<id>.output.<field>}` | A completed node's output field | runtime fills context with node outputs |
| `${nodes.<id>.output.<field>.<sub>}` | Nested dot-path into output dict | resolve_template one-level expansion |
| `${trigger.<key>}` | Trigger context value (card_id, task, build_id, metadata.*) | runtime spreads trigger payload |
| `${item}` | Whole current foreach item | foreach iterator |
| `${item.<field>}` | Field of current foreach item | resolve_template one-level expansion on item dict |
| `${item_index}` | Integer foreach iteration index | foreach iterator |
| `${<any.context.key>}` | Generic escape hatch — any key the runtime placed in context | runtime |

Variable namespaces are **conventional, not enforced**: the resolver matches whatever `${...}` string is present. `nodes.`/`trigger.`/`item` are produced by the runtime filling the dict, not recognized by the resolver.

### Condition evaluation — `evaluate_condition()` (~L657)

```
condition := clause ( OR clause )*
clause    := atom  ( AND atom )*
atom      := ${var} <op> <value>
```

- **Parsed by `str.split(" OR ")` then `str.split(" AND ")`** — not a tokenizer. Whitespace around `AND`/`OR` is significant.
- AND binds tighter than OR. Left-to-right, short-circuits.
- **No parentheses, no arithmetic, no functions.** `(A OR B) AND C` is not expressible — must be unrolled or split across edges.

#### Operators (`_evaluate_single_clause`, ~L565)

| Operator | Forms | Notes |
|---|---|---|
| `==` | `${var} == 'x'` (quoted) or `${var} == bare` | Bare RHS coerces `True`/`False`/`true`/`false`/`null`/`None`. Use quotes for plain strings. |
| `!=` | `${var} != 'x'` or `${var} != bare` | Inverse, same coercion |
| `exists` | `${var} exists` | Truthy check via `bool(context.get(var))` |
| `is empty` | `${var} is empty` | Falsy check |
| `<` `<=` `>` `>=` | `${var} < 3` or `${var} <= '3'` | Numeric: tries `float()` on both sides; falls back to string if either fails. Never stringify-then-compare (avoids `"10" < "3"` being True). |

Unknown forms → `False` (safe default).

### `strip_template_var()` (~L526)

Strips a `${...}` wrapper returning the inner key, or returns the string unchanged if not wrapped. Used to extract a raw path from a single-variable expression.

## Cross-engine comparison: nginbot-api

nginbot-api (TypeScript) has **two cooperating mechanisms** — see [`references/expression-engine-comparison.md`](references/expression-engine-comparison.md) for the full side-by-side, mapping tables, and a merged-syntax proposal.

**Headline:** nginbot is a **strict superset** of Hermes's condition power. It adds arithmetic, parentheses, a mutable store, reduce/prev-value, and storeUpdater write-back. Hermes cannot host nginbot expressions without substantial new code. The reverse migration (Hermes → nginbot) is feasible with two gaps: nginbot lacks `${item_index}`, and the two engines disagree on missing-var policy (Hermes strips, nginbot throws).

### nginbot source directives (`sourceExtractor.ts`)

Regex: `/^(?:(\w+|#):)?(store|node|input)(?::((?:#|\w)[\w.]*))?$/`

| Directive | Meaning |
|---|---|
| `store:<path>` | mutable graph-level store |
| `node:<Id>.output.<path>` | named node output |
| `input:<name>` | graph-level input |
| `node:#.output.<path>` | `#` = previous step's node id |
| `<srcNode>:<type>:<path>` | multi-state source qualifier |

### nginbot expression engine (`expr-eval`)

Full math, boolean with parentheses, library functions. Reserved symbols: `$` (list item → `_item`), `#` (default state), `_` (prev value / reduce).

## Pitfalls

- **Typo → silent empty string.** `${nodes.buld.output.verdict}` (misspelled node) resolves to `""`, and `"" == 'PASS'` is False. The condition never fires, no error. Always test conditions end-to-end.
- **`str(True)` is `"True"` (capital T).** Comparing against `'true'` (lowercase) fails. Use `type: "boolean"` in output schema, or compare against the Python form.
- **Whitespace around AND/OR is significant.** `"${a}=='PASS'AND ${b}=='PASS'"` (no spaces) won't split correctly.
- **No parentheses means no complex grouping.** `A AND B OR C AND D` works (groups as `(A AND B) OR (C AND D)`), but `(A OR B) AND C` does not. Unroll or use multiple edges.
- **`resolve_template` only expands one level of dot-path.** `${item.a.b}` (two levels) does NOT resolve to `item["a"]["b"]`; it resolves `${item.a}` to `str(item["a"])` (the dict repr) and leaves `.b}` dangling.

## Condition-aware reachability — evaluate_condition in _reachable_nodes

`_reachable_nodes` (runtime.py:1661) now calls `evaluate_condition` to determine which edges are live during its BFS traversal. Edges whose condition evaluates False against the current context are excluded — they are "dead" and should not mark downstream nodes as reachable.

**Why this matters:** In a verify→fix→re-verify→fix conditional cycle, when verify PASSES, the verify→fix edge (condition: `verdict=='FAIL'`) is dead. The old code followed it anyway, making `fix` reachable. Since `fix` was reachable but pending, `_check_completion` returned False forever — the instance was stuck `active`.

**The filter (runtime.py):**
```python
live_edges = [e for e in raw_edges
              if e.condition is None or evaluate_condition(e.condition, ctx)]
return bfs_reachable(live_edges, seeds, node_ids)
```

Unconditional edges (`condition is None`) are always traversed. Only conditional edges with a False evaluation are excluded.

### Unit-testing evaluate_condition — context keys are FLATTENED

`evaluate_condition` and `_evaluate_single_clause` do `context.get(var_path)` where `var_path` is the full dotted string from inside `${}`. The context dict must use FLATTENED keys matching how `_build_ctx` constructs runtime context:

```python
# WRONG — nested dict; condition silently returns False
ctx = {"nodes": {"verify": {"output": {"verdict": "PASS"}}}}

# CORRECT — flat dotted keys (matches _build_ctx: ctx[f"nodes.{node_id}.output.{k}"] = v)
ctx = {"nodes.verify.output.verdict": "PASS"}
```

This is the #1 gotcha when writing unit tests that call `evaluate_condition` directly. The runtime flattens via `_build_ctx` (runtime.py:1118), so real runtime context is always flat — but hand-constructed test context often uses nested dicts out of habit.

### node_phase state format for unit tests

When constructing `state_nodes` dicts for tests of `_reachable_nodes` or `_check_completion`, `node_phase()` derives phase from specific fields, NOT a generic `"status"` key:

- **task nodes:** `card_status` field (`"done"`, `"archived"`, `"todo"`, `"ready"`, `"running"`, `"blocked"`)
- **command/wait/noop nodes:** `done` boolean flag
- **terminal flags:** `skipped` or `failed` boolean (checked first, overrides card state)

```python
# WRONG — "status" is not read by node_phase
state_nodes = {"verify": {"status": "done"}}

# CORRECT
state_nodes = {
    "verify": {"card_status": "done", "output": {"verdict": "PASS"}},
    "done":   {"done": True},  # noop/command node
}
```

### Building test Engine and Workflow objects

```python
from workflow_engine.model import Workflow
from workflow_engine.runtime import Engine, StateDB

# StateDB auto-inits schema in __init__ — no init_db() method exists
engine = Engine(tmpdir / "templates")
engine.state = StateDB(tmpdir / "state.db")

# Use Workflow.from_dict, NOT resolve_template (which is for string substitution)
wf = Workflow.from_dict(template_dict)
# Back-edges need max_iterations or iteration-referencing condition or load validation rejects
```

## When extending the evaluator

If adding a new operator or variable namespace:
1. Read `_evaluate_single_clause` and `resolve_template` in `model.py` — they are the entire engine.
2. There is no `TEMPLATE_RE` to update; resolution is `str.replace`-based. If you need regex matching (e.g. for nested paths), you must introduce one.
3. Conditions are split on `" OR "` / `" AND "` — any new operator must be self-contained within a single clause (no clause-spanning logic).
4. Test with `test_composition.py`'s `FakeWorld` harness — do not hand-roll probes against the live board.
