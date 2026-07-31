# Bad-Input / Robustness Testing

The fourth test class for the workflow engine. Feeds garbage to the
**parsing/load boundary** — `Workflow.from_dict()`, `Workflow.from_file()`,
`TemplateStore.load()`, `resolve_template()`, `evaluate_condition()` — and
asserts the engine either rejects gracefully (returns `None`, raises
`ValueError`) or handles without crashing. Lives in `test_bad_templates.py`
(62 tests — **all regular passing tests as of 2026-07-31**; the 4 former
`xfail(strict=True)` crash-gaps were resolved when `TemplateStore.load`'s
exception handler was broadened, and the decorators were removed).

This differs from the other three classes by *what it attacks*:

| Class | Attack surface | Goal |
|-------|----------------|------|
| happy-path (test_engine) | tick loop, correct templates | prove mechanics |
| unhappy-path (test_unhappy) | known runtime error conditions | prove graceful handling |
| adversarial (test_adversarial) | find bugs, force races | find+fix real bugs |
| **bad-input (test_bad_templates)** | **parser/store on malformed input** | **document crash-gaps, prove graceful reject** |

## Methodology: probe FIRST, then write assertions

**Never assume how the engine behaves on a malformed input.** The exception
handlers are narrow and inconsistent (see crash-gaps below), and
seemingly-similar inputs split between "caught gracefully" and "unhandled
crash." Probe each one empirically before writing the assertion.

Workflow:

1. Write a throwaway probe script (`/tmp/probe.py`, deleted after use).
2. For each malformed input you plan to test, construct it, run it through the
   real parser/store, and print the actual result or exception
   (`{type(e).__name__}: {e}`).
3. Read the probe output. Now you KNOW: does it return `None`? Raise
   `KeyError`? Raise `TypeError`? Return a broken-but-non-None object?
4. Encode the *observed* behavior as the assertion. A test that asserts
   guessed behavior is fiction.

Concrete probe example (the one that founded this file):

```python
from workflow_engine.model import Workflow, resolve_template, evaluate_condition
from workflow_engine.store import TemplateStore

# null file via store
store = TemplateStore(tmpdir); (tmpdir/"null.json").write_text("null")
try: store.load("null")
except Exception as e: print(f"null: CRASH {type(e).__name__}")  # → TypeError

# binary file
(tmpdir/"binary.json").write_bytes(b"\x00\x01\xff")
try: store.load("binary")
except Exception as e: print(f"binary: CRASH {type(e).__name__}")  # → UnicodeDecodeError

# evaluate_condition operators you THINK are unsupported
print(evaluate_condition("${x} != 'a'", {"x": "b"}))  # → True (!= IS supported)
print(evaluate_condition("${x} >= '5'", {"x": "9"}))  # → False (unsupported → False)
```

The probe revealed two surprises that changed the test design:
- `!=` IS supported by `evaluate_condition` (the task brief listed it as
  unsupported — it isn't).
- `store.load` only catches `(JSONDecodeError, KeyError)`, so four inputs that
  "should" be rejected as `None` actually crash.

## The three test postures (reuse across all engine test classes)

| Posture | When to use | Suite state | What the assertion does |
|---------|-------------|-------------|-------------------------|
| **bug-finder** (adversarial) | Engine has a real bug you found | **FAILs** — the `BUG:` message is the report | asserts desired behavior; passes only after engine fix |
| **unhappy-path** | Known error condition engine already handles | all-green | asserts graceful handling (no crash, returns list) |
| **crash-gap (`xfail`-strict)** | Engine CURRENTLY crashes; you want the gap visible without breaking green | green (xfailed) | asserts the DESIRED graceful behavior; xfailed because engine can't deliver it yet |

### When to use `xfail(strict=True)` vs just fixing it

Use xfail-strict when:
- The input genuinely crashes the engine today (uncaught exception propagates).
- The fix is a real hardening task (broaden an exception handler in
  `store.load`), not a one-line validation you should just do now.
- You want the gap visible in the suite output (4 xfailed lines in the pytest
  summary) rather than hidden as a passing-for-wrong-reason test.

Do NOT use xfail when:
- The engine already handles the input gracefully → write a normal positive
  assertion (`assert store.load("bad") is None`).
- You can fix it in <5 min → fix it, then write the positive assertion.

**Why `strict=True` is mandatory:** without it, a future hardening silently
turns the xfail into a passing-with-xfail-marker test — a lie. With `strict`,
hardening causes XPASS, which pytest reports as FAILURE, forcing conversion
from xfail → positive assertion. The `reason=` string must name what's broken
AND the shape of the fix so the future converter knows what to assert.

## The four crash-gaps (RESOLVED 2026-07-31)

`store.load()` historically wrapped `Workflow.from_dict()` in
`except (json.JSONDecodeError, KeyError)` ONLY. These four inputs raised
*other* exception types and propagated uncaught:

| Input | File content | Exception | Root cause |
|-------|--------------|-----------|------------|
| wrong-type `nodes` | `{"id":"x","name":"y","nodes":5}` | `TypeError` | `from_dict` iterates `nodes`; an int isn't iterable |
| `null` template | `null` | `TypeError` | `json.loads("null")` → `None`; `None in data` → TypeError |
| binary file | `\x00\x01\xff\xfe` | `UnicodeDecodeError` | `path.read_text()` can't decode non-UTF-8 bytes |
| double-encoded JSON | `json.dumps(json.dumps({...}))` | `AttributeError` | outer `json.loads` yields a `str`; `str.get` doesn't exist |

**Resolution:** the handler in `store.load` was broadened to catch the full set
(`TypeError, UnicodeDecodeError, AttributeError, ValueError`, or a blanket
`except Exception`). The four `@pytest.mark.xfail(strict=True)` decorators were
removed; the test **bodies were left intact** — they already asserted the
desired graceful behavior (`assert store.load("wf") is None`), which is now
what the hardened engine delivers.

### The conversion that was done (a reusable pattern)

When you harden `store.load` (or `from_dict`), the conversion is NOT always
limited to the xfail-decorated tests:

1. **Decorator-only removal.** Each xfail test's body stays; the assertion it
   carried *was* the desired-behavior assertion, which now passes for real.
2. **Sibling tests may break.** The same hardening often tightens
   `from_dict` validation. In the 2026-07-31 conversion, the same change that
   closed the 4 crash-gaps also made `from_dict` reject `depends_on`-as-string
   (now `TypeError`) and made non-dict `output` no longer raise
   `AttributeError`. Two OTHER bad-input tests written against the old loose
   behavior (`test_depends_on_as_string_silently_stored`,
   `test_output_not_a_dict`) started failing — they need their assertions
   updated to the new hardened behavior via the dual-nature triage (these are
   category-2 "old-behavior assertion" updates, not engine bugs).
3. **Verify the converted tests in isolation.** Run pytest on JUST the
   converted node IDs and assert outcomes explicitly: 0 xfail, 0 XPASS, N/N
   PASSED. A full-file run is fine for the final check but may contain the
   sibling-test failures above, which can obscure whether the xfail conversion
   itself succeeded.

**Note:** `store.all()` loops over `store.load()`, so before the hardening a
single crash-gap file in the templates dir crashed `store.all()` too — not just
`load()`. Post-hardening this is no longer a risk. The
`test_store_all_skips_unloadable_templates` test deliberately used only
caught-exception files (`JSONDecodeError`/`KeyError` triggers) at the time; it
could now be broadened, but leaving it conservative is harmless.

## The 62-test catalog (test_bad_templates.py)

Grouped by category. As of 2026-07-31 all 62 are regular passing tests; the
four former `xfail(strict=True)` store-via-load variants (categories 3, 11,
17, 18) are now ordinary positive assertions after the handler broadening.

**1. JSON syntax errors (6)** — missing bracket, trailing comma, missing colon,
bare `{`, empty file, plain text. All → `store.load` returns `None`
(JSONDecodeError caught). `from_file` propagates JSONDecodeError (documented
contract — store is the softening layer).

**2. Missing required top-level fields (3)** — missing `id` / `name` →
`KeyError` (from_dict); missing `nodes` → valid empty list (optional).

**3. 'nodes' wrong type (5)** — int / str / bool / dict → `TypeError` from
from_dict. The store-via-load variant was xfailed (TypeError uncaught); now a
regular passing test after the handler was broadened.

**4. Node missing id/profile (2)** — direct KeyError. Node missing optional
fields (skill/body/depends_on) → valid defaults.

**5. Duplicate IDs (1)** — store keys on filename stem, not internal `id`;
two files can't collide on stem. Internal-id-mismatching-filename is benign
(documented, latent inconsistency).

**6. depends_on as string (1)** — stored verbatim, NOT coerced to list. Latent
bug: `for dep in node.depends_on` would iterate chars. Documented for a future
validator.

**7. body_template as number (2)** — stored verbatim as `42`;
`resolve_template(42, {})` → TypeError at resolution time (not parse time).
`None` body resolves fine (runtime guards with `or ""`).

**8. Trigger with no nodes (1)** — parses fine, just can't produce work.
Missing `source` key → KeyError. Trigger as non-dict → TypeError.

**9. Extra unknown fields (1)** — silently ignored (`.get()` everywhere). No
strict schema validation.

**10. Empty `{}` (2)** — valid JSON, lacks id/name → KeyError (store: None).

**11. Double-encoded JSON (2)** — ✗ store variant xfailed (AttributeError);
from_dict variant documents the AttributeError directly.

**12. Circular / self depends_on (2)** — no cycle detection at parse; silently
accepted, deadlock is runtime-only. `entry_nodes()` returns `[]`.

**13. Invalid JSON Schema (2)** — stored verbatim, no schema validation at
parse. `output` as non-dict → AttributeError.

**14. Deeply nested JSON (2)** — 100 levels fine. CPython's json *decoder* is
iterative and handles 5000 levels without RecursionError (the *encoder*
`json.dumps` is the recursive one, but the engine only decodes from disk).

**15. 1000 nodes (2)** — parses in <5s, `to_mermaid()` renders 1000 nodes +
999 edges without crash. Store round-trip survives.

**16. Condition operators (3)** — parametrized: `==`/`!=`/`exists`/`is empty`
supported (positive controls); `>=`/`contains`/`~=`/`<`/`in` unsupported →
`False` (no crash). Garbage conditions / None values → `False`.

**17. null template (2)** — ✗ store variant xfailed (TypeError); from_dict
documents the TypeError.

**18. Binary file (2)** — ✗ store variant xfailed (UnicodeDecodeError);
from_file documents the UnicodeDecodeError.

**19. resolve_template robustness (4)** — missing vars stripped to `""`; `None`
value → `"None"` (str'd); non-string template → TypeError; list value → repr.

**20. Cross-layer store.all() (1)** — skips unloadable templates whose
`load()` raises caught exceptions; good templates survive. (Does NOT test the
crash-gap files — those crash `all()`; see crash-gap note above.)

## Pitfall: don't write tautological passing tests

A bad-input test is only valuable if its assertion reflects REAL engine
behavior. Two failure modes:

1. **Asserting guessed behavior.** You assume `store.load("null.json")` returns
   `None`, but it actually raises `TypeError`. The test fails confusingly at
   runtime, or worse, you write `assert ... is None` and it passes because
   `None` happens to be... no. Probe first.
2. **The `store.all()` contamination trap.** You write a `store.all()` test
   that includes a TypeError-crash file in the temp dir alongside a good file.
   `store.all()` crashes on the bad file and the test fails — but the test's
   *intent* (skips unloadable) is only true for caught-exception files. Either
   limit the dir to caught-exception files, or assert the crash separately.

The ad-hoc verification script (`/tmp/hermes-verify-*.py`, deleted after use)
that confirmed this file's tests independently re-derived each assertion
against the real engine and caught the `store.all()` contamination trap in
the verification script itself before it leaked into the test file.
