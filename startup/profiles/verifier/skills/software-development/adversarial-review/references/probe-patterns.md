# probe-patterns.md — reusable adversarial probe techniques

Proven probe patterns for fresh-eyes verification. Each pattern is a class of
defect, the trap to avoid, and a minimal probe shape that has caught it in real
sessions. Pull these in before writing probes from scratch — they cover the
failure modes that trip up fresh-eyes reviewers most often.

---

## 1. Self-verify before filing (the #1 fresh-eyes error)

**Defect class:** a probe "fails" not because the code is wrong, but because
the probe's own asserted expectation is wrong — a typo in the expected value,
conflating substring with regex, an off-by-one, aliasing a mutable default,
or (very common in eviction tests) miscounting how many keys are expired.

**Trap:** the reviewer sees `FAIL  probe_xyz  got 3` and files a finding.
The implementation was correct; the probe asserted the wrong expected value.

**Discipline:** before filing ANY failing probe, re-derive the expected value
by hand from the contract, independent of the probe's own assertion. Print
`repr(actual)` and `repr(expected)`, walk them against the contract sentence
by sentence, and only then decide code-vs-probe.

**Concrete example (real session):**
A cleanup-count probe asserted `cleanup() == 1` for a store holding THREE
expired keys (`ttl=0`, `ttl=-5`, `ttl=0`). The contract says cleanup removes
ALL currently-expired keys, so the correct expectation is 3. The probe's
expectation was wrong (it had been written assuming only the last `set`
counted). Code returned 3 — correct. The "failure" was a bug in the probe.

**Rule of thumb:** if the code's output matches a careful hand re-derivation,
the probe is wrong — fix the probe and re-run. Never file a finding whose
only evidence is a probe whose expectation you did not re-derive.

---

## 2. Torn-read / non-atomic-operation detection

**Defect class:** a method that should be atomic under concurrency is
implemented as two or more SEPARATE lock acquisitions, leaving a window where
inconsistent state is visible to concurrent readers. The contract forbids
this ("all access to X must be under the same lock as Y").

**Trap:** a single-threaded test always passes because no reader lands in the
gap. The bug only surfaces under concurrency, so it sails past the suite.

**Two-stage probe (do both):**

### Stage 1 — Structural proof (deterministic, no timing luck)

The goal: prove the window exists in the REAL code path, not just under a
subclass with an artificial delay. Override the method only to OBSERVE state
in the genuine gap — never widen it, never sleep.

```python
class Observer(RealClass):
    def the_method(self, ...):
        # Call the parent up to the point where the gap occurs.
        # For a load() that does super().load() then a separate lock+clear:
        Parent.the_method(self, ...)   # real parent, real internal locks
        # GENUINE WINDOW: the method's own lock is FREE here.
        # Observe consistency WITHOUT taking the lock (taking it masks the bug).
        inconsistent = [k for k in self._data if k in self._expiry]
        if inconsistent:
            gap_observed.append(inconsistent)
        with self._lock:
            self._expiry.clear()
```

If `gap_observed` is non-empty, the window exists structurally — no race
needed. This is your line-anchored contract violation evidence.

### Stage 2 — Public-API race (removes all doubt)

A structural proof is strong but a skeptic may argue the window is too small
to matter. Prove it is observable through the PUBLIC API with no subclassing:

```python
store = RealClass()
# pre-seed inconsistent state so the window has something stale to expose
store.set("k", "stale", expiry_flag=True)
def loader():
    while not stop:
        store.load(file_with_k_as_persistent)
        with store._lock: store._expiry["k"] = now - 1  # re-seed
def reader():
    while not stop:
        if store.get("k") is None: torn += 1   # public API only
```

Run ~1-3s. If `torn > 0`, a public-API reader saw inconsistent state — the
defect is real and exploitable. Report the raw `torn` count (often millions);
the magnitude makes "timing fluke" defenses untenable.

**Common shapes this catches:**
- `load()` / `reload()` that populates `_data` then separately clears metadata
- "clear then repopulate" split across two `with self._lock:` blocks
- Any "do X under lock, then do Y under lock" where X and Y must be atomic
  together but are written as independent acquisitions

---

## 3. Eviction-count verification (set-difference, not bookkeeping)

**Defect class:** an eviction method (`cleanup`, `gc`, `prune`, `expire`)
returns a count that disagrees with the keys actually removed from the
primary store, because the count is derived from secondary bookkeeping (an
expiry dict, a tombstone set) that can drift from the primary `_data`.

**Trap:** the probe asserts `count == expected_N` by computing expected_N from
the same secondary bookkeeping the implementation uses — so they agree even
when both are wrong.

**Probe shape — verify against the PRIMARY store via set-difference:**

```python
before = set(store._data.keys())
n = store.cleanup()
after = set(store._data.keys())
actually_removed = before - after
assert n == len(actually_removed), f"count {n} != actual removals {len(actually_removed)}"
assert actually_removed == expected_removed_set
assert after == expected_remaining_set
```

**Why this is stronger:** it independently reconstructs what the method DID
from the primary source of truth (`_data`) and checks the returned count
against that ground truth. If the implementation counts from `_expiry` but
fails to remove a key from `_data`, the set-diff catches it; a probe that
trusts `_expiry` would not.

**Extend with interleaving:** eviction counts are especially buggy when
interleaved with set/delete/clear/load. Build sequences that mix these and
assert the count after each — e.g. set expired → delete one → cleanup should
not count the deleted one; clear → cleanup should be 0.

---

## 4. Skip-as-fix detection (green suite, missing coverage)

**Defect class:** a developer resolves an earlier finding not by fixing the
code but by silencing the test — `@pytest.mark.skip`, `pytest.mark.xfail`,
deleting the test, commenting out the assertion, or guarding with
`if False:`. The suite goes green, the finding appears "resolved," but the
underlying defect remains and the contract item is now UNTESTED. A plausible
skip reason ("architecturally impossible," "frozen module") makes it look
legitimate to a delta-check that only asks "does the old repro still run?"

**Trap:** Phase A records FIXED because the failing test no longer exists or
no longer runs. The defect ships. This is the single highest-leverage
adversarial-evasion pattern to check for on iteration ≥ 2.

**Three-stage probe (do all three):**

### Stage 1 — Diff the test surface, not just the code

```bash
git diff <prev-review-SHA>..HEAD -- '*test*.py' | grep -E '^\+.*(skip|xfail|TODO|FIXME|pass$|raise NotImplementedError)'
# also: did any test FILE shrink in line count without a refactor commit msg?
git diff --stat <prev-review-SHA>..HEAD -- '*test*.py'
```

A `+@pytest.mark.skip` or `+    pass` body on a test that previously had real
assertions is the fingerprint. Cross-reference each newly-skipped test name
against prior findings — a skip landing on the EXACT test that covered a prior
finding is the red flag.

### Stage 2 — Prove the skip reason false (the constraint-drift check)

Skip reasons are load-bearing claims ("X is impossible because Y"). Treat Y
as a hypothesis, not a fact:

1. Extract the claimed constraint Y from the skip reason / design docstring.
2. Sweep the FULL comment thread (developer card + parent chain) newest-first
   for a later comment that lifts/supersedes Y — search terms: `OBSOLETE`,
   `superseded`, `SPEC GAP FIX`, `resolution`, `lifted`, `authorized to modify`,
   `constraint.*obsolete`, `do not auto-FAIL`.
3. Check the contract for a resolution section (often appended at the bottom)
   that authorizes the previously-forbidden change.
4. If a later comment supersedes Y → the skip reason is void. Reopen the
   finding as a Critical with evidence = the superseding comment quote + link.

### Stage 3 — Prove the behavior is actually testable (write the probe)

The strongest rebuttal to "impossible to test" is a working test. Write the
probe the developer claimed couldn't exist, using the means the superseding
comment authorized (e.g. if a frozen module is now unfrozen, write the probe
that modifies it; if cross-process state was the blocker, use `--file`/shared
storage):

```python
# Example: developer skipped T15/T16/T19 claiming "TTL can't persist across
# CLI subprocesses." The contract's SPEC GAP FIX section authorized modifying
# ttl.py. Probe writes a real cross-process test:
import subprocess, sys, tempfile, os
with tempfile.TemporaryDirectory() as td:
    f = os.path.join(td, "s.json")
    subprocess.run([sys.executable,'cli.py','set','k','v','--ttl','0','--file',f], capture_output=True)
    r = subprocess.run([sys.executable,'cli.py','get','k','--file',f], capture_output=True, text=True)
    assert r.returncode == 1 and r.stdout == '', f"T15 FAIL: got exit {r.returncode} stdout {r.stdout!r}"
```

Run it. If it FAILS, you have proven (a) the behavior is broken AND (b) it is
testable — both pillars of the skip reason are false. File as Critical and
quote both the failing output and the working probe in the finding.

**Mutation cross-check (optional but convincing):** apply the fix the
superseding comment authorized, re-run the now-unskipped tests. If they pass,
you have end-to-end proof the skip was unnecessary. (You are NOT fixing the
code for the developer — this is a local probe to validate your finding. Do
not commit it.)

**Common shapes this catches:**
- `@pytest.mark.skip(reason="architecturally impossible")` on a test whose
  blocker a later comment lifted.
- `pytest.mark.xfail(strict=False)` that silently passes even when the bug is
  fixed, hiding the resolution.
- Test body replaced with `pass` + a docstring rewrite that drops the original
  assertion.
- "Cannot test across process boundary" when the contract explicitly added a
  persistence mechanism (`--file`, shared DB, message queue) for exactly that.

---

## 5. Fake-binary-on-PATH (testing how the SUT handles malformed subprocess output)

**Defect class:** the code invokes an external command (`subprocess.run([tool,
...])`) and handles SOME failure modes — non-zero exit, empty stdout, invalid
JSON — but NOT others: valid JSON that violates the expected schema (missing a
key the code indexes), or a hang. The unhandled case raises an **uncaught
exception** (KeyError / IndexError / TypeError) that propagates to a traceback
and non-zero exit instead of the contract-mandated "log a warning and continue."

**Trap:** the test suite calls the SUT against the REAL tool, which always
returns well-formed output. The malformed-JSON branch is never exercised, so
the gap sails past. Monkeypatching `subprocess.run` would work but couples the
probe to the SUT's internals and obscures what's really being tested.

**Probe shape — inject a fake `tool` earlier on PATH, don't touch the SUT:**

```python
import json, os, subprocess, sys, tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    proj = td / "proj"; proj.mkdir(); (proj / ".beads").mkdir()  # look real to SUT
    bindir = td / "bin"; bindir.mkdir()
    fake = bindir / "bd"
    # Emit parseable JSON that OMITS the key the SUT will index.
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "if 'list' in sys.argv:\n"
        "    print(json.dumps([{'id': 'bead-1'}]))  # no 'status' key\n"
        "else:\n"
        "    print('ok')\n"
    )
    fake.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"   # prepend so our fake wins
    r = subprocess.run([sys.executable, str(SUT), "--workspace-root", str(td),
                        "--kanban-db", str(kanban)], capture_output=True, text=True, env=env)
    if r.returncode != 0 and "KeyError" in r.stderr:
        print("CONFIRMED: missing 'status' key crashes with uncaught KeyError")
    elif "warning" in r.stderr.lower():
        print("handled gracefully (warning logged, exit 0)")
```

**Why this beats monkeypatching:** the SUT runs unmodified in a real subprocess.
You're testing exactly what a corrupted tool DB would trigger in production —
same code path, same `subprocess.run` call, same `PATH` resolution. No
`unittest.mock.patch`, no import-time surgery, no coupling to private function
names. The probe is a one-file recipe that ports to any "SUT shells out to X"
scenario (git, docker, kubectl, bd, hermes CLI itself).

**Common shapes this catches:**
- `except json.JSONDecodeError` wrapping `json.loads` but NOT the subsequent
  `obj["required_key"]` — the parse succeeds, the index crashes.
- `result.returncode != 0` checked for the read call but the write call's
  failure silently swallowed (no `changes -= 1`, no warning).
- Exit-code checks that forget the command can exit 0 with empty stdout
  (`json.loads(result.stdout or "[]")` papers over this; a bare
  `json.loads(result.stdout)` does not).

**Generalization — other fake-binary variants worth one probe each:**
- Emit stdout that is valid JSON but the WRONG type (`{}` when a list is
  expected → `TypeError: string indices must be integers` on iteration).
- Exit 0 with empty stdout (the `or "[]"` / `or "{}"` default question).
- Emit stdout with trailing garbage after valid JSON (`[...]\nGARBAGE`).
- Hang forever (prefix the script with `import time; time.sleep(3600)` and
  run with a timeout — tests whether the SUT sets `timeout=` on the call).

---

## 6. Normalization-variant probing (the optionxform / key-case trap)

**Defect class:** a function preserves some property (a comment, a value, an
association) keyed by a name that a downstream API *normalizes* (lowercases,
strips, transliterates). The implementation stores the association under the
**original** form but looks it up under the **normalized** form (or vice
versa), so the lookup misses and the property is silently dropped. Tests that
only use inputs already in the normalized form (all-lowercase keys, ASCII-only
strings, no whitespace) pass because the two forms coincide there.

**Trap:** the dev's tests use only the normalized representative — e.g. every
test key is lowercase (`key1`, `key2`) — so the case-mismatch code path is
never exercised. The suite is green, the AC appears satisfied, and the bug
ships. This is the class of gap a fresh-eyes probe exists to catch.

**Probe shape — deliberately use the NON-normalized form:**

```python
# configparser default: optionxform = str.lower  -> keys lowercased on read.
# If your code keys a side-table by the raw key from a line-scan but reads
# values from parser.items() (lowercased), the side-table lookup misses.

# Probe with an UPPERCASE / MixedCase key preceding a comment:
f.write("[s]\n; hi-prec comment\nKeyX = v\n")      # KeyX, not keyx
out = merge([f])
assert "; hi-prec comment" in out, "comment dropped — case-mismatch in lookup"
assert "KeyX" in out, "key case not preserved"      # not 'keyx'

# Contrast control (must still pass): lowercase key
f2.write("[s]\n; comment\nkeylower = v\n")
assert "; comment" in merge([f2])                    # this one works
```

If the contrast passes but the uppercase variant fails, you have isolated a
normalization bug — same code path, same property, only the lexical form
differs. This is far stronger evidence than "comment not preserved" in the
abstract.

**Self-verify the expectation first (§1 applies):** confirm from the contract
that the property *should* be preserved across normalization. Some contracts
genuinely specify case-folding (e.g. INI keys are conventionally case-
insensitive on read). In that case the key-case change is correct, but the
**associated property** (comment) still must not be dropped — adjust the probe
to assert the property survives even if the key spelling doesn't.

**The canonical instance — `configparser.optionxform`:**
Python's `configparser` lowercases all option names by default
(`optionxform = str.lower`). Any code that builds a parallel structure
(comment map, order list, metadata) keyed by the *raw* key from a manual line
scan, then looks it up using keys from `parser.items()` / `parser[section]`,
will silently miss for any key containing uppercase letters. Two fixes, both
correct:
- `parser.optionxform = str` — preserve case end-to-end (preferred when the
  contract wants byte-faithful round-trips, e.g. AC9 "equivalent to that file").
- Normalize both sides to lowercase — fixes the property drop but keys emit
  lowercased; only acceptable if "equivalent" is read loosely.

**Generalization — other normalization axes to probe one variant each:**
- **Whitespace in keys**: `key with space = v` vs `key = v` (leading/trailing
  strip behavior differs across parsers).
- **Unicode lookalikes**: ASCII `a` vs Cyrillic `а` — NFC/NFD normalization.
- **Delimiter variants**: `key:value` vs `key = value` (some parsers accept
  both but only index one form).
- **Path separators**: `C:\100%done` (the interpolation gotcha, but also a
  backslash-escaping normalization axis on non-Windows parsers).
- **Repeated keys within one file**: does the last value win, and does the
  *first* key's comment survive or the last's?

**Rule of thumb:** if the library you're building on documents ANY
normalization step (case-folding, whitespace trimming, delimiter coercion),
write at least one probe per axis that uses the NON-normalized input. A test
suite using only normalized inputs is not evidence the normalization boundary
is handled — it's evidence the boundary was never crossed.

---

## 7. Precondition-violating input (the unhashable-value trap)

**Defect class:** a probe calls a function with an input that violates a
**language-level precondition** inherent to the operation — most often
hashability for a function that builds a `dict`/`set` from the input. The
function correctly raises `TypeError`, but the reviewer (having written the
probe to test a *different* property like no-mutation) misreads the crash as a
function bug and either files a spurious finding or blocks on a "crash" that
is actually the probe being malformed.

**Trap:** distinct from §1 (wrong *expectation*) — here the probe's
**input** is illegal for the function under test. The classic shape: a
no-mutation probe that reuses one rich fixture across all four functions,
including one whose values must be hashable.

**Concrete example (real session):**
```
# No-mutation probe iterating all functions with ONE shared dict:
d = {"k": {"nested": {"deep": 1}}, "v": [9, 8]}   # values are dict + list
snap = copy.deepcopy(d)
dict_diff(d, d)        # OK — values only compared, never hashed
deep_merge(d, d)       # OK
invert_dict(d)         # 💥 TypeError: unhashable type: 'dict'
flatten_dict(d)        # OK
# Reviewer sees TypeError mid-suite, suspects an invert_dict crash bug.
# It isn't: invert_dict must use values as dict keys, so unhashable values
# are a documented-precondition violation, not a defect.
```

**Discipline — separate legal inputs per function:**
1. Before writing a probe that feeds arbitrary data to a function, ask: **what
   does this function require of its input that the others don't?** Functions
   that invert/swap/build-a-set-from values require **hashable** values.
   Functions that compare values require **equatable** values (almost always
   satisfied). Functions that iterate require **iterable** inputs.
2. Maintain a **per-function legal fixture**, not one shared monster dict.
   For a no-mutation sweep, build the input each function is actually allowed
   to receive:
   ```python
   fixtures = {
       "dict_diff": ({"a": {"x": 1}, "lst": [1, 2]}, {"a": {"y": 2}}),  # any values
       "deep_merge": ({"a": {"x": [1]}}, {"a": {"y": 2}}),              # any values
       "invert_dict": {"a": 1, "b": 2, "c": 3},                         # HASHABLE values only
       "flatten_dict": {"k": {"n": 1}, "lst": [9, 8]},                  # any values
   }
   ```
3. If you DO want to probe the unhashable-input path itself, do it
   **deliberately and in isolation** — assert that `TypeError` IS raised
   (that's the contract-correct behavior), don't let it abort a larger probe.

**Confirm-before-filing gate (§1 applies):** when a probe crashes with
`TypeError: unhashable type`, the first question is not "is the function
broken?" but "was the input even legal for this function?" Re-derive the
function's precondition from its contract signature before treating the crash
as evidence. `invert`/`swap`/`reverse-lookup`/`build-lookup` verbs almost
always imply hashability of the swapped operand; that's a property of the
operation, not a bug.

**Common shapes this catches (probe-construction bugs, not code bugs):**
- `invert_dict({"k": {...}})` / `dict_swap({"k": [1, 2]})` — values used as
  keys must be hashable; nested dicts/lists aren't.
- `set(values)` where `values` came from JSON that may contain lists/dicts.
- Using a function's *output* as another function's *input* in a pipeline
  probe, when the output type violates the next function's precondition.
- A "round-trip" probe (`invert(invert(d)) == d`) that silently fails because
  `invert(d)` produced keys that `invert` can't accept as values — except
  here it crashes rather than silently misbehaves, so it's caught at runtime.

---

## 8. Probe-input contamination via a shared builder / padding char

**Defect class:** a probe uses a *helper* to construct inputs (pad to a target
length, fill in defaults, build a fixture from parameters), and the helper's
pad/fill value silently introduces a property the **specific test case is
trying to exclude**. The input does not crash (unlike §7) and the expectation
is correctly *derived* (unlike §1) — but the input does not satisfy the test's
own semantic premise, so the code's correct handling of the actual input looks
like a bug. This is the most insidious probe-construction error because the
output is internally consistent: the code is right, the expectation is right,
only the *input* is wrong, and nothing flags it.

**Trap:** a single shared builder used across many test variants. The builder
picks ONE pad char (say `'c'`, a lowercase letter) and reuses it for every
case — including the "must contain NO lowercase" case. The resulting string
secretly contains lowercase, the function correctly returns the
lowercase-present result, and the probe reports FAIL against an expectation
that would be right *if the input were what the test assumed*.

**Concrete example (real session — password-strength checker):**
```python
def with_len(target, upper=True, lower=True, digit=True, special=True):
    chars = ("A" if upper else "") + ("b" if lower else "") + \
            ("5" if digit else "") + ("!" if special else "")
    chars += "c" * (target - len(chars))   # <-- 'c' is LOWERCASE
    return chars

# "no-lowercase" probe — caller wants a string with upper+digit+special, NO lower:
p = with_len(12, lower=False, special=True)
# p == "A5!ccccccccc"  -->  CONTAINS LOWERCASE ('c')
check("no-lower (upper+digit+special) -> weak", strength(p), "weak")
# strength(p) returns "strong" (correctly — p has lowercase!)
# probe reports FAIL. Code is right; the builder contaminated the input.
```

The same session also hit the §1 variant in the same probe family: a string
written by hand as `"Abcdefgh1é!"` was *assumed* to be 12 chars but was 11 —
a length miscount masquerading as a boundary failure. Both were probe bugs;
both would have produced spurious Critical findings if filed without
self-verification.

**Discipline — three guards, apply all three:**

1. **The pad char must not belong to any class the test excludes.** Choose the
   pad from a class the test *includes* (so padding only reinforces, never
   introduces). If the test excludes lowercase, pad with an uppercase letter
   or a digit that is already required — never `'c'`. When no included class
   is safe (the test excludes everything), make padding explicit per-case.
   ```python
   def with_len(target, upper=True, lower=True, digit=True, special=True):
       chars = ("A" if upper else "") + ("b" if lower else "") + \
               ("5" if digit else "") + ("!" if special else "")
       # pad from an ALREADY-PRESENT class so we never add an excluded one
       pad = "A" if upper else ("5" if digit else ("b" if lower else "!"))
       chars += pad * (target - len(chars))
       assert len(chars) == target
       return chars
   ```

2. **Assert the input's defining property before asserting on the output.**
   For a "no-lowercase" test, assert `not has_lowercase(p)` (or
   `"a" not in p and "c" not in p`) BEFORE calling `strength(p)`. If the
   precondition assertion fails, you've caught contamination at the source
   instead of misattributing the downstream output to a code bug.
   ```python
   p = with_len(12, lower=False, special=True)
   assert not has_lowercase(p), f"input contaminated: {p!r}"   # guard
   check("no-lower -> weak", strength(p), "weak")
   ```

3. **Print `repr(input)` alongside every result.** Length miscounts and
   smuggled classes are obvious in a repr but invisible in a label. A
   sanity-print line (`len(p)`, `has_upper/lower/digit/special(p)`) next to
   each probe turns the contamination self-evident — in the real session, a
   `len(...)` sanity block immediately exposed that the "12-char" inputs were
   10–11 chars.

**Detection signal during review:** if a probe FAILs but (a) the code's
output is a value the contract *permits* for *some* input shape, and (b) the
test's label describes a property the input might not actually have — stop and
print the input's real properties. The failure is in the input, not the code.

**Common shapes this catches (probe-construction bugs, not code bugs):**
- A length-padding helper whose pad char belongs to a class a variant excludes
  (lowercase pad in a no-lowercase test; digit pad in a no-digit test).
- A fixture factory that fills "unspecified" fields with a default that
  satisfies a constraint the test meant to violate (default `count=1` in a
  "zero-count" test; default `enabled=True` in a "disabled" test).
- A boundary probe that hand-counts a string's length and is off by one —
  always assert `len(p) == expected` in the builder rather than trusting the
  literal.
- Reusing one rich fixture across many function/property tests where each test
  needs a *different* subset of properties present/absent (the §7 sibling,
  but silent instead of crashing).

---

## 9. Purity-probe self-contamination (the locals/globals diff trap)

**Defect class:** a probe that verifies "no side effects / no global state
mutation" (a common AC: "the function is pure") by snapshotting `locals()` or
`globals()` before and after the call, then diffing. The diff is **non-empty**
not because the function mutated anything, but because the probe's OWN
bookkeeping variables (`pre`, `post`, `sentinel`, `before_globals`) were
created between the two snapshots and so appear in the diff. The reviewer sees
`FAIL  no new globals  got {'before_globals', 'sentinel'}` and either files a
spurious Critical or burns a turn chasing a phantom side effect.

**Trap:** this is structurally identical to measuring a voltage with a meter
that injects current — the measurement apparatus contaminates the measurement.
It does NOT crash (unlike §7) and the expectation ("diff should be empty") is
correctly *derived* (unlike §1) — only the *measurement technique* is wrong,
so nothing in §1/§7/§8 flags it. It is the most common purity-probe error and
it produces false-FAILs that look exactly like real side-effect findings.

**Concrete example (real session — reverse_words purity check):**
```python
# v1 — BROKEN: globals() at module scope captures the probe's own vars
before_globals = set(globals().keys())   # <-- creates 'before_globals'
sentinel = reverse_words("alpha beta")   # <-- creates 'sentinel'
after_globals = set(globals().keys())    # <-- creates 'after_globals'
check("no new globals", after_globals - before_globals, set())
# FAILS: diff == {'before_globals', 'sentinel', 'after_globals'} — MY vars!

# v2 — ALSO BROKEN: locals() inside a function captures 'pre' itself
def purity_probe():
    pre = set(locals())                  # <-- 'pre' is now a local
    out = reverse_words("alpha beta")    # <-- 'out' is now a local
    post = set(locals())                 # <-- 'post' is now a local
    return post - pre - {"out"}          # diff still contains 'pre', 'post'!
# FAILS: diff == {'pre', 'post'} — still my bookkeeping.
```

Two iterations wasted on probe bugs before the correct shape was found.

**Discipline — three correct shapes, pick one:**

1. **Test the TARGET module's namespace, not your own.** Snapshot
   `vars(target_module)` (or `dir(target_module)`) before and after the call.
   The target module's `__dict__` only changes if the function genuinely
   mutates module-level state — your probe's locals never appear in it.
   ```python
   import reverse_words as rw_mod
   pre = set(vars(rw_mod))
   _ = rw_mod.reverse_words("alpha beta gamma")
   post = set(vars(rw_mod))
   check("no new module attrs", post - pre, set())   # clean
   ```

2. **Hold snapshots in a separate namespace object** (a class instance or
   `types.SimpleNamespace`) whose `__dict__` you control. Put `pre`/`post` on
   the object; diff the TARGET's namespace, not the holder's.
   ```python
   class Frame: pass
   f = Frame()
   f.pre = set(vars(rw_mod))
   _ = rw_mod.reverse_words("alpha beta")
   f.post = set(vars(rw_mod))
   check("no module mutation", f.post - f.pre, set())
   del f   # proves the holder itself is transient
   ```

3. **For caller-frame purity, never diff `locals()`.** `locals()` reflects
   every assignment in the current frame, including the ones your probe makes
   to hold the snapshot. If you must check "the call doesn't leak into the
   caller's frame," run the call inside a function whose ONLY locals are the
   call result, and assert on the result — there is no clean way to diff
   `locals()` around a call you also instrument.

**Related trap — idempotence-vs-normalization confusion (a §1 variant).**
When verifying a function that BOTH normalizes whitespace AND transforms
(e.g. `reverse_words` = `split()` + `reversed` + `join`), do NOT assert
"idempotent" (`f(f(x)) == f(x)`) as the purity/normalization invariant.
`reverse_words(reverse_words("a b")) == reverse_words("b a") == "a b"`, which
is NOT equal to `reverse_words("a b") == "b a"` — the function is its own
inverse on word order, so it is correctly NON-idempotent. The right invariant
is "output is always in canonical/normalized form": `f(x) == " ".join(f(x).split())`
holds for every input. Confusing these produces a false-FAIL that looks like a
real defect. Re-derive the invariant from the contract semantics before
asserting it (§1 applies): "idempotent" is right for pure normalizers
(`strip`, `lower`, `split`-then-`join` with no transform); it is WRONG for
normalizers that also transform.

**Detection signal during review:** a purity probe FAILs with a diff
containing identifiers that match your probe's own variable names (`pre`,
`post`, `sentinel`, `before_*`, `after_*`, `result`, `out`). If every element
of the "leaked" set is a name you introduced to hold a snapshot, the function
is clean and the probe is broken — re-target the measurement onto the SUT's
namespace, not your own.

**Common shapes this catches (probe-construction bugs, not code bugs):**
- `globals()` diff at module scope in an ad-hoc probe script — captures every
  `import` and assignment the probe itself makes.
- `locals()` diff inside a function — captures the snapshot-holding vars
  themselves (`pre`, `post`).
- `dir(builtins)` diff — usually clean, but a probe that imports a helper
  mid-test can appear to "add a builtin" if the diff logic is sloppy.
- Asserting idempotence on a normalize-AND-transform function (reverse, sort,
  shuffle-then-dedupe) — the transform breaks idempotence by design.
