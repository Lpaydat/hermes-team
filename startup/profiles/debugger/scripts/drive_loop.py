#!/usr/bin/env python3
"""Re-invocation helper for the debug-loop on livetest-pipeline-g70.

Re-invoke with: python drive_loop.py
Reads phase state from the root blackboard via loop_id (drift-immune).
Passes the SAME 3-phase plan every time (required — engine re-validates
on every call); loop_id keys it to the existing root so phases advance.
"""
import importlib, os, sys

DRIVER = "t_ac4bf2c8"
ROOT = "t_8a7db96d"
os.environ["HERMES_KANBAN_TASK"] = DRIVER
os.environ["HERMES_KANBAN_BOARD"] = "livetest-pipeline"

PLUGINS = "/home/lpaydat/.hermes-teams/startup/plugins"
sys.path.insert(0, PLUGINS)
le = importlib.import_module("loop_engine.tools")

WT = "/home/lpaydat/projects/livetest-pipeline/.worktrees/debug-g70"
BRANCH = "debug/livetest-pipeline-g70-ragged-short-row"

GOAL = (
    "Bug livetest-pipeline-g70: Ragged-row handling asymmetry. "
    "csv2json convert() (csv2json/cli.py) uses csv.DictReader(restval='') so "
    "SHORT rows (too few fields) are silently padded with '' -> null (exit 0) "
    "while LONG rows (too many fields) correctly raise csv.Error (exit 1). "
    "Repro: printf 'a,b,c\\n1,2,3\\n4,5\\n6,7,8\\n' -> row2 {a:4,b:5,c:null} exit 0 (BUG). "
    "Expected: symmetric error 'ragged row at line N: expected 3 fields, got 2'. "
    "env: python3.11, pyproject pytest, venv at .venv. stakes=low(floor). "
    "originator=qa(re-test t_3002b399). bug-id=livetest-pipeline-g70. "
    "branch=debug/livetest-pipeline-g70-ragged-short-row "
    "worktree=/home/lpaydat/projects/livetest-pipeline/.worktrees/debug-g70"
)

def sub(s):
    return s.replace("__WT__", WT).replace("__BRANCH__", BRANCH)

# Phase bodies (must match the original invocation; loop_id keys advancement)
P0_EXEC_BODY = sub("""Bug livetest-pipeline-g70 — reproduce the short-row ragged-row asymmetry as a TIGHT, MINIMAL, RED signal.

WORKSPACE: cd __WT__  (git branch __BRANCH__ already checked out there).
Python venv: __WT__/.venv/bin/python OR the repo root .venv. The package is installed editable (pip install -e .) — verify `python -m csv2json --help` works first.

THE BUG (from convert() in csv2json/cli.py):
- Line 67: rows = csv.DictReader(reader, restval="")
- restval="" fills missing cells in SHORT rows with "", which then infers to null.
- Line 74: `if None in row` only catches LONG rows (extra fields under key None).
- So a short row (fewer fields than the header) silently succeeds (exit 0).

REPRO (black-box, from the QA report):
  printf 'a,b,c\\n1,2,3\\n4,5\\n6,7,8\\n' > __WT__/ragged.csv
  python -m csv2json __WT__/ragged.csv   # currently exits 0, row2 = {"a":4,"b":5,"c":null}
  echo $?   # 0 — BUG. Expected: exit 1 with 'ragged row at line 3: expected 3 fields, got 2'.

YOUR TASK:
1. Run the black-box repro above; capture the exact current (wrong) output + exit code.
2. MINIMISE: find the smallest CSV that still triggers the short-row silent-pass. (Hint: a header 'a,b' + one data row '1' is the minimal case.)
3. Write a FAILING pytest regression test at __WT__/tests/test_csv2json.py that asserts short rows raise (use the existing test_c14_ragged_row_clean_error as the template — it already tests LONG rows; add a sibling test for SHORT rows). Name it `test_c14_ragged_row_short_fields_clean_error`. It should assert returncode==1, 'ragged row' in stderr, and 'expected N fields, got M' in stderr.
4. Run `__WT__/.venv/bin/python -m pytest tests/test_csv2json.py::test_c14_ragged_row_short_fields_clean_error -q` and confirm it FAILS (RED) right now — that is the point. Paste the RED output.
5. Record on the blackboard (via kanban_comment on this task): the exact repro command, the minimal CSV, the RED test name + its failing assertion, and the current wrong behaviour.
Do NOT fix the code. Only build the RED signal. Commit the new failing test on the branch (git add + git commit -m 'test: add RED repro for short-row ragged-row (livetest-pipeline-g70)').""")

P0_VER_BODY = sub("""You are the INDEPENDENT verifier for phase 0 (reproduce + minimise).

DoD — a reliable, minimal repro exists that goes RED on this bug and will go GREEN when fixed. ALL of the following must hold (mechanical, ground-truth checks — cite each):
1. A new pytest test exists in __WT__/tests/test_csv2json.py named `test_c14_ragged_row_short_fields_clean_error` (or equivalent) that exercises a SHORT row (fewer fields than the header).
2. That test currently FAILS (RED) — re-run it yourself: `cd __WT__ && .venv/bin/python -m pytest tests/test_csv2json.py -k ragged_row_short -q` and capture exit code + the failing assertion. It MUST be non-zero (failing) now.
3. The existing LONG-row test (test_c14_ragged_row_clean_error) still PASSES (the bug is asymmetric — only the short-row direction is broken). Re-run and confirm.
4. The repro is minimal (no irrelevant columns/rows). State the minimal CSV used.

Re-open each citation: read the test file_line, re-run the test capturing the RED output. Quote what you found.

If no repro is possible from the provided env, set recommendation=escalate with gaps naming exactly what is needed.

Return dod_verdict: dod_met=true/advance if all four hold; dod_met=false/replan with concrete gaps otherwise. Cite evidence (test file_line + the RED test_output) for every material claim.""")

P1_EXEC_BODY = sub("""Bug livetest-pipeline-g70 — ship the minimal, root-cause fix.

WORKSPACE: cd __WT__  (git branch __BRANCH__).
Python venv: __WT__/.venv/bin/python  (package installed editable).

ROOT CAUSE (confirmed in phase 0):
convert() in csv2json/cli.py:67 uses csv.DictReader(reader, restval=""). The restval="" sentinel is indistinguishable from a genuinely-empty cell, so SHORT rows (too few fields) silently get "" -> null with no error. The long-row check (`if None in row`, line 74) has no symmetric short-row check.

THE FIX (minimal, at the correct seam):
Use a UNIQUE sentinel object for restval (e.g. `_MISSING = object()`, then `csv.DictReader(reader, restval=_MISSING)`). After the existing long-row check, add a short-row check: if any value in the row IS the sentinel, the row has too few fields — count how many are missing and raise the SYMMETRIC csv.Error:
  raise csv.Error(f"ragged row at line {rows.line_num}: expected {expected} fields, got {got}")
where got = expected - (number of sentinel values). This matches the existing long-row message format exactly (ADR-004).

IMPORTANT: Do NOT change the behaviour for genuinely-empty cells (empty string -> null is correct and tested by test_c5/test_c19/test_all_types_smoke). The sentinel must ONLY catch actually-missing fields, never a real empty cell. After detecting, you must also exclude the sentinel from the output object (filter it out before building the dict, or the object() will fail json.dumps).

REGRESSION TEST: the failing test from phase 0 (test_c14_ragged_row_short_fields_clean_error) should now go GREEN. Verify it does. Also confirm the docstring on convert() is updated to reflect symmetric handling.

Run the FULL suite: `cd __WT__ && .venv/bin/python -m pytest tests/ -q`. ALL 54 tests must pass (53 existing + 1 new). Paste the green output.

Commit on the branch: git add + git commit -m 'fix: reject short rows as ragged (symmetric to long rows, livetest-pipeline-g70)'.

In your completion metadata, state: (a) the exact lines changed, (b) whether a correct test seam existed (yes/no), (c) at least one alternative you considered and rejected (e.g. 'switch to csv.reader + manual zip' — rejected because DictReader already handles quoted fields/dup-header detection).""")

P1_VER_BODY = sub("""You are the INDEPENDENT verifier for phase 1 (fix + falsify + code review).

WORKSPACE: cd __WT__  (branch __BRANCH__).

Evaluate the parent execution's fix. dod_met=true/advance ONLY if ALL FIVE hold:

1. REPRO GREEN: the short-row repro now errors correctly. Re-run the phase-0 repro (printf 'a,b,c\\n1,2,3\\n4,5\\n6,7,8\\n' | python -m csv2json <file>) and confirm exit 1 with 'ragged row at line 3: expected 3 fields, got 2'. Cite the test_output.

2. REGRESSION TEST AT A CORRECT SEAM: test_c14_ragged_row_short_fields_clean_error exists and PASSES. It tests the ROOT behaviour (short row -> error), not a symptom. Re-run it. Cite file_line + test_output.

3. FULL SUITE GREEN: `cd __WT__ && .venv/bin/python -m pytest tests/ -q` — all pass, no new regression (the empty-cell -> null tests test_c5/test_c19/test_all_types_smoke MUST still pass — the sentinel must not break genuine empty cells). Cite test_output.

4. FALSIFY — break it another way. Exercise adjacent paths the fix did NOT target:
   (a) A row with exactly the right number of empty fields: 'a,b\\n,\\n' -> should still produce {"a":null,"b":null} exit 0 (empty cells are NOT short rows).
   (b) A quoted field containing a comma that spans the 'expected' width: 'a,b\\n"x,y",z\\n' -> should still work (quoted comma is one field).
   (c) A header-only file: 'a,b\\n' -> [] exit 0.
   (d) The minimal short row: 'a,b\\n1\\n' -> exit 1 'expected 2 fields, got 1'.
   Re-run each and cite the result. Any of these breaking = the fix is a symptom-fix.

5. CODE-QUALITY REVIEW (read csv2json/cli.py convert()):
   - Style/cleanliness: the sentinel approach is idiomatic; no leftover debugging.
   - Fix-logic correctness: addresses the CAUSE (restval indistinguishable from empty), smallest sound change; the error message matches the long-row format (ADR-004).
   - The sentinel is excluded from the output dict (object() would crash json.dumps).
   - The docstring on convert() is updated.
   - Alternatives: at least one named alternative was rejected for a stated reason (read from developer metadata).
   - No new debt (no TODOs, workarounds, escape hatches).
   Cite file_line for any gap.

Return dod_verdict: dod_met=true/advance only if all five hold; dod_met=false/replan with concrete cited gaps if any fail. recommendation=escalate with gaps naming 'no-correct-seam' or 'root-cause-spans-boundary' if the design-flaw signal is present (it should NOT be here — this is a clean localized fix).""")

P2_EXEC_BODY = sub("""You (the debugger, in a fresh worker context) write the RCA.

WORKSPACE: cd __WT__  (branch __BRANCH__).
Read the blackboard / prior comments on this loop's root card for: the repro (phase 0), the fix + falsification verdict (phase 1). You need all four inputs.

Write the post-mortem at __WT__/docs/postmortems/livetest-pipeline-g70-ragged-short-row.md (create the docs/postmortems/ dir if needed — mirror docs/adr/).

Follow the 9arm structure. MANDATORY (all four must be present):
- Summary (one paragraph)
- Root cause (the restval="" sentinel indistinguishable from genuine empty cells; cite csv2json/cli.py:67 and the missing short-row check vs line 74)
- Fix (the unique-sentinel approach + symmetric csv.Error; cite the commit SHA + function/file:line)
- Validation (the regression test that went RED->GREEN; the full suite green; the falsification probes that held — be HONEST about coverage: state exactly which adjacent paths were probed)
CONDITIONAL (usually present): Symptom, Mechanism, How it slipped through (the original implementation only handled the long-row DictReader-None-key case; short rows were implicitly accepted by restval=""), Action items.

Blameless. Code-identifiers FIRST-CLASS (function names, file paths, commit SHAs). Mechanism-over-narrative. Answer Matt Pocock P6: 'what would have prevented this bug?' (e.g. a property-based test over row-width variance; or treating restval as a code smell).
Commit on the branch: git add docs/ + git commit -m 'docs: post-mortem for livetest-pipeline-g70 (ragged-row short-row)'.""")

P2_VER_BODY = sub("""You are the INDEPENDENT verifier for phase 2 (converge / RCA).

Read __WT__/docs/postmortems/livetest-pipeline-g70-ragged-short-row.md.

Structural/citation check (ground-truth, no judgment score):
1. All FOUR mandatory sections present: Summary, Root cause, Fix, Validation.
2. Code-identifiers cited and RE-OPENABLE: re-open csv2json/cli.py at the cited line(s); re-open the commit SHA (git show --stat <sha>). Quote what you found.
3. The Validation section is HONEST about coverage (does not overclaim).
4. The root cause cited matches the actual fix (the restval sentinel).

Return dod_verdict: dod_met=true/advance if all hold (cite the postmortem file_line + the re-opened code-identifiers); dod_met=false/replan naming the missing input otherwise. A post-mortem of a hypothesis is worse than none — refuse to advance until all four inputs are present and faithful.""")

phases = [
    {
        "title": "Reproduce + minimise the short-row ragged-row bug (tight RED)",
        "execution": {"assignee": "researcher", "title": "Build the tight RED repro for short-row ragged-row bug", "body": P0_EXEC_BODY},
        "verifier": {"assignee": "verifier", "title": "Verify tight RED achieved for short-row ragged-row bug", "metric_type": "ground_truth", "body": P0_VER_BODY},
        "max_iterations": 3,
    },
    {
        "title": "Fix the short-row ragged-row asymmetry + falsify",
        "execution": {"assignee": "developer", "skill": "developer-loop", "title": "Ship minimal fix for short-row ragged-row asymmetry + regression test", "body": P1_EXEC_BODY},
        "verifier": {"assignee": "verifier", "title": "Falsify + code-review the short-row ragged-row fix", "metric_type": "ground_truth", "body": P1_VER_BODY},
        "max_iterations": 5,
    },
    {
        "title": "Write the RCA / post-mortem for livetest-pipeline-g70",
        "execution": {"assignee": "debugger", "title": "Author the post-mortem (RCA) at docs/postmortems/", "body": P2_EXEC_BODY},
        "verifier": {"assignee": "verifier", "title": "Verify the RCA has all four mandatory inputs + code-identifiers", "metric_type": "ground_truth", "body": P2_VER_BODY},
        "max_iterations": 2,
    },
]

args = {
    "strict_fact_basis": True,
    "goal": GOAL,
    "runner": "debugger",
    "loop_id": ROOT,
    "phases": phases,
}

result = le.loop_engine(args, task_id=DRIVER, _profile="debugger")
print(result)
