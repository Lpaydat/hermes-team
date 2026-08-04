# Behavior-Test Injection Gap — Forensic Analysis

## Lesson #33 support: why the Pomodoro verifier missed the tab-injection bug

### The bug

`format_log_line()` in `pomodoro.py:80-85` interpolates `entry['task']` raw
into a tab-separated line. A task name containing a tab character produces
6 fields instead of 4, corrupting the TSV.

```python
task = 'implement\tinject\tauth'
→ '2024-01-15\t09:00-09:25\tWORK\timplement\tinject\tauth (cycle 1)'
# 6 fields, not 4
```

### What the verifier wrote (51 tests across 7 classes)

| Class | Tests | Inputs tested |
|-------|-------|---------------|
| TestPhaseSequence (6) | finite/zero/default/custom/alternation | work/break/cycles ints |
| TestFormatTime (12) | 0,1,9,10,59,60,61,125,600,1499,1500,3600 | numeric seconds only |
| TestRenderLine (2) | WORK 1500/1, BREAK 300/2 | phase+time+cycle |
| TestSessionLogging (4) | dir/file create, JSONL, fields, append | task="implement auth" |
| TestDateFiltering (3) | filter, today default, --date | dates only |
| **TestLogFormat (1)** | `test_format_log_line_tab_separated` | **task="implement auth" — NO special chars** |
| TestAdversarialProbes (9) | negative time, zero work, missing/empty file | **NO tab anywhere** |

### The three failures

1. **Happy-path lock-in:** The format test asserted `len(fields) == 4` using
   "implement auth" (no tabs). Could only confirm the spec example
   round-trips — never stressed the delimiter boundary.

2. **Docstring vs. input mismatch:** verify-b wrote
   `"""task name with special chars (tabs, quotes)"""` but supplied only
   quotes (`'quote "test"'`). Named the threat without exercising it.

3. **No format-injection stress test:** Adversarial probes tested time math,
   missing files, empty strings — never tested delimiter injection.

### Both verifiers claimed 100% coverage

- Primary: `verdict=PASS, findings_count=0, gaps=[], score=1.0`
- verify-b: `verdict=PASS, findings_count=0, gaps=[], score=1.0`

The `gaps: []` array is the systemic failure signal — asserting
completeness that was never earned.

### The one-line test that would have caught it

```python
s = {"task": "a\tb", "start": "2024-01-15T09:00:00", "end": "2024-01-15T09:25:00", "cycle": 1}
assert len(format_log_line(s).split("\t")) == 4  # FAILS: gets 5
```

### The infrastructure fix

A deterministic fuzz script that injects every ASCII control character
into every string field, then asserts format integrity. This catches
the entire class with zero imagination required:

```python
# scripts/format-injection-fuzz.py
import string

CONTROL_CHARS = [c for c in string.printable if not c.isalnum() and c not in ' .-_/:']

def fuzz_format_injection(format_fn, field_name, base_entry):
    """Inject control chars into field_name, assert format integrity."""
    failures = []
    for char in CONTROL_CHARS:
        entry = dict(base_entry)
        entry[field_name] = f"test{char}injected"
        line = format_fn(entry)
        fields = line.split('\t')
        if len(fields) != len(format_fn(base_entry).split('\t')):
            failures.append(f"char {repr(char)} → {len(fields)} fields (expected {len(format_fn(base_entry).split('\t'))})")
    return failures
```

Run as part of the verify node. No LLM imagination needed.

### Root cause

The verifier can only break what it imagines. No amount of body_template
instruction fixes this — it's a fundamental limitation of LLM-generated
tests. The fix is deterministic: a script that probes every delimiter-
injection case, every time.

### Generalization

Any spec with a delimiter-joined format (CSV, TSV, pipe-separated, log
lines, JSON-in-string) is vulnerable. The verify node should ALWAYS
include a delimiter-injection probe. Prefer a script over body text.

### Source

- Board: livetest-unbias-1 (Pomodoro Timer CLI)
- Spec: "Log format: tab-separated: 2024-01-15 09:00-09:25 WORK implement auth (cycle 1)"
- Code: `workspaces/t_c7370277/pomodoro.py:80-85`
- Verify cards: `t_fa987e67` (51 tests), `t_57119cb8` (39 tests)
- Forensic subagent: `deleg_787bf7a2/task-0.log`
