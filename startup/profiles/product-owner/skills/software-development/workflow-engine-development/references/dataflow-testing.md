# Dataflow & Variable-Resolution Testing

`test_dataflow.py` — 62 tests (37 unit + 25 integration) probing the trickiest
part of the engine: how data flows between nodes (template resolution,
condition evaluation, metadata propagation across ticks).

Two layers:
- **Unit tests** call `resolve_template` / `evaluate_condition` directly with
  hand-built contexts. These pin the *exact string* the engine produces for
  each value type so a coercion change is caught immediately.
- **Integration tests** use a body-readback FakeWorld to verify resolved
  templates land in real card rows end-to-end.

## Probe-before-pin methodology

Before writing assertions on edge-case coercion behavior, **empirically probe
the actual output** rather than guessing. `str()` behavior on dicts, lists,
None, bool, and nested structures is not obvious, and the regex cleanup pass
has non-obvious boundary behavior.

```bash
cd .../scripts && python3 -c "
from workflow_engine.model import resolve_template, evaluate_condition

# What does str(None) produce inside a template?
print(repr(resolve_template('val: \${x}', {'x': None})))
# → 'val: None'  (not empty!)

# Does empty \${} survive the cleanup regex?
print(repr(resolve_template('before \${} after', {})))
# → 'before \${} after'  (regex needs 1+ chars, so \${} is NOT stripped)

# Is recursive expansion order-dependent?
print(repr(resolve_template('\${\${a}}', {'a':'b','b':'yes'})))  # → 'yes'
print(repr(resolve_template('\${\${a}}', {'b':'yes','a':'b'})))  # → ''
"
```

Only after you see the real output do you write the assertion. Pinning a
guessed behavior produces tests that are confidently wrong.

## The two undocumented edge cases this category found

### 1. Recursive expansion `${${inner}}` is dict-iteration-order-dependent

`resolve_template` does a single replace pass over `context.items()` (dict
iteration is insertion order in Python 3.7+). Nested `${${inner}}` resolves
**only if** the outer key appears AFTER the inner key in iteration order:

- `{'a':'b','b':'yes'}` + `"${${a}}"` → `'yes'` (a first: `${b}` → then b → `yes`)
- `{'b':'yes','a':'b'}` + `"${${a}}"` → `''` (a first: `${b}` not in context
  yet as a *template form* — the context key is the literal `b`, not `${b}`)

This is **fragile and silent** — the same workflow definition produces
different output depending on dict construction order. A test that pins this
asymmetry (one passing, one empty) catches a future hardening.

### 2. Empty `${}` survives the cleanup regex

The cleanup pass is `re.sub(r"\$\{[^}]+\}", "", result)` — the `[^}]+`
requires **at least one character** between the braces. An empty `${}` has
zero chars, so it is NOT matched and survives as a literal `"${}"` in the
output. This is an asymmetry:

- `${x}` (key absent) → `` (removed by regex)
- `${}` (empty) → `${}` (NOT removed, literal survives)

If someone adds context key `""`, then `${}` *does* substitute, making this
even more surprising.

## Type coercion table (what str(value) produces in templates)

| Value in context | `str()` in template | Notes |
|------------------|---------------------|-------|
| `"text"` | `text` | Normal |
| `42` | `42` | |
| `3.14` | `3.14` | |
| `0` | `0` | Not empty |
| `""` | `` (empty) | |
| `None` | `None` (4 chars) | **Not empty** — truthy-looking string |
| `True` | `True` | **Not `true`** (Python, not JSON) |
| `False` | `False` | **Not `false`** |
| `{"k": "v"}` | `{'k': 'v'}` | **Python repr, not JSON** — single quotes |
| `["a","b"]` | `['a', 'b']` | Python repr |
| `{"a": {"b": "c"}}` | `{'a': {'b': 'c'}}` | Full nested repr |

**WEAKNESS:** `None` → `"None"` is the most dangerous — downstream conditions
see a truthy-looking string, and `${x} == 'None'` actually matches. Dicts/lists
embed Python repr, not JSON, corrupting any downstream parser that expects JSON.

## Condition evaluation edge cases

- `str(True) == 'True'` but `!= 'true'` — case-sensitive, Python-style
- `str(None) == 'None'` — matches literal `'None'`, and `exists` → False (None is falsy)
- Condition values containing regex special chars (`/tmp/[test]/`) compare
  **literally** (plain `str ==`, not regex), so brackets don't need escaping
- `evaluate_condition` uses `re.match` (not `fullmatch`) — see
  `references/data-corruption-tests.md` for the trailing-garbage weakness

## The body-readback FakeWorld pattern

To verify variable resolution *end-to-end* (not just that a card was created,
but what resolved body it received), the fake `create_card` must **persist the
`body` argument** into the `tasks.body` column. The base FakeWorld skeleton
discards it. Add `body` to the INSERT and a `get_card_body(card_id)` helper:

```python
def _fake_create_card(self, ..., body="", ...):
    conn.execute(
        "INSERT INTO tasks (id, title, assignee, status, idempotency_key, "
        "body, created_at) VALUES (?, ?, ?, 'todo', ?, ?, ?)",
        (card_id, title, assignee, idempotency_key, body, int(time.time())),
    )

def get_card_body(self, card_id):
    conn = sqlite3.connect(str(self.board_db))
    row = conn.execute("SELECT body FROM tasks WHERE id = ?", (card_id,)).fetchone()
    conn.close()
    return row[0] if row else ""
```

Then assert: `assert world.get_card_body(sink_card) == "Config is {'k': 'v'}"`.

**Gotcha:** the engine resolves variables in `body_template` ONLY — the card
title is hardcoded as `f"[{node.id}] {skill}"`. There is no `title_template`
field. A test that documents "titles never contain resolved variables" guards
against someone assuming otherwise.

## Output mutation between ticks (snapshot semantics)

Once a node is marked DONE, the engine does **not re-read its card metadata** on
subsequent ticks (it only checks for regression to todo/ready/running). So:

- The value captured at the tick where `status` first becomes `done` is the
  value downstream nodes see — even if the card's metadata is edited afterward.
- The state DB retains the snapshot (not updated post-done).
- A downstream card body, once dispatched, is immutable — it captured the value
  at dispatch time.

Test this by: completing src with metadata v1, ticking to dispatch sink,
asserting sink body has v1, then mutating src's card metadata to v2 (insert a
new `task_run`), ticking again, asserting sink body is STILL v1 and the state
DB still has v1.
