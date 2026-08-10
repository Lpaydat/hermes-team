# Verifier Lint/Format Enforcement — Minimal Changes to `tech-lead-execute.json`

## Problem

The setup node (per `CONFIG-FILE-DESIGN.md`) scaffolds `pyproject.toml` with
`[tool.ruff]`, a `Makefile` with `test`/`lint`/`format`/`check` targets, and
`.gitignore`. **But none of the verifier nodes in `tech-lead-execute.json` ever
run ruff.** Every verifier (`verify`, `re-verify`, `merge-verify`) and the
`close` node run **only `pytest`**. A developer can land unformatted,
lint-failing code and the workflow will PASS it.

The configured tooling is currently dead config — created but never enforced.

## Current verifier surface (3 nodes + 1 tech-lead node)

| Node | Profile | What it runs today |
|---|---|---|
| `verify` | verifier | `pytest` (behavior tests) |
| `re-verify` | verifier | `pytest` (re-run after fix) |
| `merge-verify` | verifier | `pytest -q` (Check 3) |
| `close` | tech-lead | `pytest -q` (Step 2) |

## Design constraints discovered

1. **Verifier must NOT edit dev code** (Phase 4: "Do NOT Edit Dev Code"). The
   scaffolded Makefile's `format` target **writes** changes (`ruff format src
   tests`). The verifier needs a **check-only** variant. → **The scaffolded
   Makefile is missing a `format-check` target.** This is a gap in the setup
   node's output, not in tech-lead-execute.

2. **The Makefile is the right abstraction layer.** The verifier template is
   language-agnostic; the setup node writes language-correct targets. Calling
   `make lint` works for Python (ruff) today and Node (eslint) tomorrow without
   touching the verifier body. Hardcoding `ruff check` in 4 places breaks the
   moment a project deviates to Node.

3. **mypy is not in the paved-road Makefile today.** `CONFIG-FILE-DESIGN.md`
   lists mypy only as a "future optional" (`[tool.mypy]`). The minimal proposal
   covers ruff concretely; mypy/eslint ride the same `make lint` mechanism once
   the setup node adds them to the Makefile.

4. **No edge-condition changes needed.** `verify→fix` already fires on any
   `verdict == 'FAIL'`. A lint FAIL flows through the existing fix loop with
   zero edge edits — the win of folding lint into the same verdict.

## Proposed changes (two parts)

### Part A — Setup node: add `format-check` target to scaffolded Makefile

The scaffolded `configs/_shared/Makefile` must gain a check-only format target,
because the verifier is forbidden from editing dev code and `ruff format`
without `--check` mutates files.

```diff
 .PHONY: test lint format format-check check

 test:
 \tpytest -v

 lint:
 \truff check src tests

 format:
 \truff format src tests

+format-check:
+\truff format --check src tests
+
-check: lint test
+check: lint format-check test
```

**Why `check` gains `format-check`:** `make check` is the canonical "is this
code shippable" target. Format violations are shippability failures. The
verifier and close node should run `make check`, so `check` must include the
format gate.

> Note: `src tests` paths assume the paved-road layout. If the project has no
> `src/` dir, `ruff check .` is the safe fallback. The setup node should emit
> the path list matching the scaffolded structure.

### Part B — `tech-lead-execute.json`: add Lint+Format Gate to 3 verifier nodes

The change is **identical in shape** across `verify`, `re-verify`, and
`merge-verify`: run `make lint` + `make format-check` (fallback to direct ruff
commands if no Makefile), treat any failure as `verdict = FAIL`.

#### B1. `verify` node — insert new Phase between Phase 2 and Phase 3

Insert after "Write ADDITIONAL tests for every gap..." and before "### Phase 3:
Execute — Run ALL Tests":

```diff
 Write ADDITIONAL tests for every gap you find. Append them to the same test file.

+### Phase 2b: Lint + Format Gate (ENFORCE SCAFFOLDED TOOLING)
+
+The setup node scaffolded a Makefile with `lint` and `format-check` targets
+(ruff on the Python paved road; eslint on Node). Enforce them — behavior tests
+alone are not enough; unformatted or lint-failing code must not pass.
+
+Run, in order:
+
+```
+make lint         # ruff check src tests  — zero violations required
+make format-check # ruff format --check   — zero reformatting needed
+```
+
+Fallback if no Makefile exists (legacy project): run the tools directly:
+```
+ruff check src tests || true     # Python
+ruff format --check src tests || true
+# Node: npx eslint . && npx prettier --check .
+```
+
+Rules:
+- You MUST NOT run `make format` or `ruff format` without `--check` — those
+  EDIT dev code, which Phase 4 forbids. Check-only.
+- Any lint violation or format diff → this is a finding. Append it to findings.
+- If lint/format fails AND behavior tests pass: verdict = FAIL (lint failure
+  is a real failure, not a warning).
+
 ### Phase 3: Execute — Run ALL Tests
```

Add two fields to the `verify` node output schema:

```diff
             "behavior_test_file": {
               "type": "string"
             },
             "production_mode_tested": {
               "type": "boolean"
+            },
+            "lint_pass": {
+              "type": "boolean"
+            },
+            "format_clean": {
+              "type": "boolean"
             }
```

Update the completion metadata block to include `lint_pass` and `format_clean`:

```diff
-{verdict: "PASS"|"FAIL"|"ESCALATE", findings_count: N, behavior_tests_total: N, behavior_tests_passed: N, behavior_test_file: "path", production_mode_tested: true}
+{verdict: "PASS"|"FAIL"|"ESCALATE", findings_count: N, behavior_tests_total: N, behavior_tests_passed: N, behavior_test_file: "path", production_mode_tested: true, lint_pass: true|false, format_clean: true|false}
```

#### B2. `re-verify` node — insert new Phase between Phase 2 and Phase 3

Same lint+format gate. Fixes can introduce lint violations; re-enforce.

```diff
 5. **Deployment readiness**: Test the fix under production configuration — test fixtures can mask deployment-only regressions.

+### Phase 2b: Lint + Format Gate (RE-ENFORCE)
+
+Re-run the same lint + format check from the first verify (`make lint` &&
+`make format-check`). The developer's fix must not introduce lint violations
+or reformatting needs. Same rules: check-only, never edit dev code, any
+failure → verdict = FAIL.
+
 ### Phase 3: Run ALL Tests
```

Add `lint_pass` + `format_clean` to the `re-verify` output schema and metadata
(identical diff to B1).

#### B3. `merge-verify` node — add Check 3b after Check 3

```diff
 ### Check 3: Tests pass on merged master

 ```
 git checkout master
-pytest -q
+make check    # lint + format-check + test (fails on any)
 ```

-ALL tests must pass. ANY failure — FAIL.
+If no Makefile: `ruff check src tests && ruff format --check src tests && pytest -q`.
+ANY lint, format, or test failure — FAIL.

+### Check 3b: Lint + format clean on merged master
+
+(Folded into Check 3 via `make check` above. If you ran pytest directly in
+Check 3, run `make lint && make format-check` here separately. The merged
+result must be lint-clean and format-clean, not just test-green.)
+
 ### Check 4: No stray worktrees with unmerged work
```

Add `lint_pass` + `format_clean` to the `merge-verify` output schema:

```diff
             "tests_pass": {
               "type": "boolean"
             },
+            "lint_pass": {
+              "type": "boolean"
+            },
+            "format_clean": {
+              "type": "boolean"
+            },
             "all_tests": {
```

### Part C (optional, recommended) — `close` node: `make check` instead of `pytest -q`

The tech-lead's `close` node Step 2 runs `pytest -q`. For consistency it should
run `make check` so the merge gate enforces lint too. This is the tech-lead
node, not the verifier, but it's the same one-line change and prevents a green
close followed by a red merge-verify.

```diff
 ```sh
 git checkout master
-pytest -q
+make check
 ```
```

## What does NOT need to change

- **Edges.** `verify→fix` and `re-verify→fix` already fire on `FAIL`. Lint
  failures produce `FAIL`, so they route through the existing fix loop. No new
  edges, no new nodes.
- **`fix` node body.** It already says "Fix YOUR code so ALL tests pass." The
  developer sees `lint_pass: false` in the verifier metadata and fixes lint
  alongside test failures. No body edit required (though optionally add "and
  lint passes" to the instruction for clarity).
- **`plan` node.** No verifier concern.
- **Verdict enum.** `PASS`/`FAIL`/`ESCALATE` already covers lint outcomes.

## Why this is minimal

| Change | Files | Lines touched |
|---|---|---|
| Part A: Makefile `format-check` target | `configs/_shared/Makefile` (setup node output) | +4 |
| Part B1: verify lint gate + 2 schema fields | `tech-lead-execute.json` | ~+20 body, +6 schema |
| Part B2: re-verify lint gate + 2 schema fields | `tech-lead-execute.json` | ~+8 body, +6 schema |
| Part B3: merge-verify `make check` + 2 schema fields | `tech-lead-execute.json` | ~+6 body, +6 schema |
| Part C (optional): close `make check` | `tech-lead-execute.json` | ~1 line |

**Total: ~50 lines across 2 files, zero new nodes, zero new edges.**

The design leverages the existing Makefile abstraction so the same verifier
body works for Python (ruff), Node (eslint/prettier), and future stacks without
per-language branching in the template.
