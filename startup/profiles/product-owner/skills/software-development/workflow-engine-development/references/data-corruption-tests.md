# Data Corruption Tests

20 adversarial tests targeting **malformed inputs** rather than graph
topology — null values where strings are expected, unicode/emoji/null-bytes,
huge payloads, condition-parser edge cases, and template-injection via data.
All pass against the current engine (verified via `pytest -k test_adv_data`).
Two surfaced confirmed engine bugs (annotated `BUG:` in test output); the
rest document current (often questionable) behavior so a future hardening
pass is caught.

All tests follow the FakeWorld pattern (monkey-patched `KANBAN_HOME`, fake
`create_card` writing to temp SQLite). Append to `test_engine.py`.

## How this category differs from graph-pathology tests

- **graph-pathology tests** attack the *shape* of the workflow (cycles, dead
  branches, fan-out). Weakness found: silent eternal deadlock.
- **data-corruption tests** attack the *content* of individual fields (a null
  body_template, a dict where a string is expected, a 10k-char node id).
  Weaknesses found: crashes on null fields + `str()`-based data corruption.

## The methodology: name the weakness BEFORE writing the test

Read all engine source first (`model.py`, `runtime.py`, `kanban_adapter.py`,
`store.py`), then list concrete code-level weaknesses. Each test's docstring
states the weakness it targets (`WEAKNESS: ...`). This keeps tests honest:
the assertion encodes current behavior (passing) OR catches the bug
(failing → now a regression guard after the fix). Never write a test where
you can't articulate the specific line of code it stresses.

## Tests that found bugs (confirmed)

### test_adv_data_null_body_template → BUG CONFIRMED

**Bug:** `from_dict` does `n.get("body_template", "")` which returns `None`
(not `""`) when the key exists with JSON `null`. Downstream
`resolve_template(None, ctx)` → `re.sub` throws
`TypeError: expected string or bytes-like object, got 'NoneType'`.

**Root cause:** `.get(key, default)` returns the default only when the *key
is absent*; an explicit `null` value is returned as `None`. This is the
classic JSON-null-vs-missing-key trap.

**Fix:** coerce every optional string field:
`n.get("body_template") or ""`. The `or ""` maps both missing AND `None`
AND empty string to `""`. Same applies to `profile`, `skill`, `condition`,
`foreach`.

### test_adv_data_null_profile → BUG CONFIRMED

**Bug:** `profile: null` flows unchecked into `create_card(assignee=None)`
and the card is written to the board with a **NULL assignee column**. No
validation anywhere on the path from `from_dict` → `Node` → `_dispatch_node`
→ `create_card`.

**Same root cause** as null body_template. `Node.profile = n["profile"]`
would KeyError on missing, but `Node(profile=n.get("profile"))` lets `None`
through. Either reject at `from_dict` or validate before dispatch.

## Tests documenting current (questionable) behavior

### test_adv_data_resolve_dict_value / test_adv_data_resolve_list_value

`resolve_template` calls `str(value)` on every context value. For dicts and
lists this embeds **Python repr**, not JSON:
`"Config: ${trigger.config}"` → `"Config: {'nested': 'value', 'num': 42}"`.
Single quotes, Python syntax. This is silent **data corruption** for any
non-string output that flows through a template. Fix: `json.dumps()` for
non-string values, or refuse to interpolate them.

### test_adv_data_condition_double_quotes

`evaluate_condition` regex uses `'(.+?)'` — only single-quoted values match.
`${var} == "value"` (double quotes) silently returns `False`. No error, no
warning — the node just never dispatches.

### test_adv_data_condition_trailing_garbage

`evaluate_condition` uses `re.match`, not `re.fullmatch`. Trailing content
is ignored: `${var} == 'val' EVIL TRAILING` evaluates as True. A typo like
`${var} == 'val''` still matches.

### test_adv_data_condition_malformed

A bare `${var}` (no operator), empty string, whitespace, or random text all
return `False` silently. The user may expect a truthy check for a bare
variable but gets a dead branch with no diagnostic.

### test_adv_data_conflicting_trigger_keys

A trigger with both `title_prefix: "[verify]"` AND `title_not_prefix: "[verify]"`
is an impossible conjunction (the card must start with the prefix AND not
start with it). The engine ANDs all conditions and **silently never fires**.
No warning that the trigger is unsatisfiable.

### test_adv_data_template_var_in_condition_value

Condition comparison values are compared **literally**, not resolved. If
context value is `"${other}"`, then `${var} == '${other}'` matches (both
sides are the literal string `${other}`), but `${var} == 'resolved_val'`
does not. No nested resolution happens inside `evaluate_condition`.

## Tests that validated correct behavior (no bugs)

### test_adv_data_nested_json_template_vars

Upstream output containing `${nodes.a.output.evil}` text. `resolve_template`
does plain string replacement (no recursion), so the `${}` is either
embedded literally or swept away by the final `re.sub(r"\$\{[^}]+\}", "")`
regex. **No injection possible** — but note the regex sweep DOES delete
any `${...}` text that happens to appear in data, which is a form of data
loss (see resolve_dict_value above).

### test_adv_data_empty_node_id / huge_node_id / unicode_node_id / null_byte_in_body / newline_in_node_id

Empty string, 10k-char, emoji, null-byte, and newline node IDs all flow
through unvalidated. Most don't crash (empty produces a `[]` title and a
trailing-colon idempotency key; huge produces a massive title; unicode
stores fine in SQLite). The takeaway: **there is zero input validation on
node IDs, profiles, or body templates.** All pass, documenting the absence
of validation.

### test_adv_data_body_no_vars / body_only_vars

`resolve_template` handles the two extremes correctly: zero variables
passes through unchanged; a body that is entirely `${a}${b}${c}` resolves
fully. These are regression guards for the template engine.

### test_adv_data_empty_everything

A workflow with no trigger and no nodes starts, ticks once, and produces no
actions. The `all_done` completion check is guarded by `and wf.nodes` so an
empty node list doesn't spuriously complete. Correct.

## File-organization pitfall (test_engine.py)

**Do NOT append new test functions AFTER the `if __name__ == "__main__"`
runner block.** The runner calls `sys.exit(0 if failed == 0 else 1)` at the
end — any functions defined after that line are never reached, so they're
never defined when the runner's loop tries to reference them →
`NameError: name 'X' is not defined`.

Always insert new test function definitions *before* the `# RUN ALL TESTS`
section header, and add them to the `tests = [...]` list inside the runner.
If a concurrent worker is editing the same file, verify with
`grep -n 'if __name__\|def run_'` that helpers are defined above the
runner before executing.
