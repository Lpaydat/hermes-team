---
name: ad-hoc-verification
description: "Produce fresh, independent verification evidence for changed code when the runtime flags a workspace as unverified or no canonical test/lint/build command is detected. Write a focused one-shot script under /tmp with a hermes-verify- prefix, exercise the changed behavior directly (not through the suite), clean it up, and report explicitly as ad-hoc verification rather than suite-green. Use when the runtime injects a 'workspace does not have fresh passing verification evidence' prompt, when you edited code but the suite was not re-run against the change, or when you need a second independent verification path alongside an existing test run."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [verification, testing, ad-hoc, ast, importlib, runtime-prompt]
    related_skills: [tdd, loops-engineering, requesting-code-review]
---

# Ad-Hoc Verification

## Overview

When the runtime injects "workspace does not have fresh passing verification evidence yet," it is asking for a **new** signal that the *changed* code actually behaves — not a restatement that the suite once passed. Re-running the full suite may be part of the answer, but the stronger move is a focused script that exercises the changed paths directly, independently of the suite. This skill is the recipe for that script: where it goes, how it loads the code without import side-effects, how it asserts static constraints (stdlib-only, no-CLI) robustly, and how it cleans up after itself.

The key distinction: **suite-green** means "all N tests pass." **Ad-hoc verification** means "I wrote a fresh probe targeting the changed behavior, ran it, and here is what it showed." They are complementary; the runtime prompt wants the latter.

## When to Use

- The runtime injects a "workspace not verified" / "no fresh passing verification evidence" system message after you edited code.
- No canonical test/lint/build command was detected for the repo (no `pytest`, `make test`, `npm test` discovered).
- You want a second, independent verification path alongside an existing suite run — especially to re-check code paths a regex/AST edit touched.
- You changed code and the suite was run *before* the edit, not after.

Don't use for:
- Routine suite runs when a canonical command exists and was just executed — that *is* fresh evidence.
- Creative/visual work the user has not signed off on yet (tests come after approval there).

Exception to the default workflow — when the changed artifact is **intentionally failing** (adversarial reproduction tests, red-phase TDD), do NOT expect exit 0 / all [PASS]. The suite is supposed to fail by design. Use the meta-verification pattern in the "Verifying intentionally-failing artifacts" section instead: assert the fail/pass split matches expectation.

## The script

Place it at `/tmp/hermes-verify-<topic>.py`. The `/tmp` location and `hermes-verify-` prefix are conventional — the runtime's own prompt names this shape, and matching it makes the artifact recognizable and trivially cleanable.

A copy-modify template lives at [scripts/hermes-verify-template.py](scripts/hermes-verify-template.py). The non-negotiable structure:

1. **Load the module via `importlib`, not `import`.** This avoids polluting `sys.modules` / side-effects and works regardless of packaging. Read the file path, build a spec, exec into a fresh module object.
2. **Assert the public surface first** — the names that are supposed to exist, then behavior. If the surface is wrong, behavior tests are meaningless.
3. **Exercise the changed paths directly.** If you edited a regex, the script must feed inputs that distinguish the old regex from the new one — not just any input that passes.
4. **Use `tempfile.TemporaryDirectory()` for any filesystem touch.** Never write to the repo or the user's home. The skill's contract is "leave nothing behind outside `/tmp`."
5. **Print `[PASS]`/`[FAIL]` per check, exit non-zero on any failure.** Make the verdict grep-able.
6. **Clean up: `rm -f /tmp/hermes-verify-<topic>.py` after the run.** Confirm removal.

## Static-constraint checks — use AST, never substring search

When verifying constraints like "stdlib only," "no argparse," "no sys.exit," "no `__main__` guard," **walk the AST, do not substring-search the source.** This is the single most common ad-hoc-verification bug.

```python
import ast
tree = ast.parse(inspect.getsource(module))
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for a in node.names:
            assert a.name != "argparse"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "exit" and isinstance(node.func.value, ast.Name):
            assert node.func.value.id != "sys"
```

**Why substring fails:** docstrings and comments legitimately mention the forbidden thing. A module whose docstring says "no argparse, no sys.exit — those belong to Slice 2" will *fail* a `"argparse" not in src` check even though the code is correct. The AST sees only actual imports and calls; prose is invisible to it. This bit a real verification pass — the test was tightened to AST and has stayed green since.

## How it differs from the test suite

| | Test suite | Ad-hoc verification script |
|---|---|---|
| Lives in | repo (`test_*.py`) | `/tmp`, deleted after |
| Scope | whole module / contract | changed paths only |
| Loaded by | `import` (packaging-aware) | `importlib` (path-direct) |
| Static checks | usually behavioral | AST-walk for constraints |
| Purpose | long-term regression net | one-shot fresh-evidence signal |

Run both when you can. The suite proves breadth; the ad-hoc script proves the *specific change* works and the constraints still hold.

## Workflow

1. Identify the changed paths and the constraints the change must satisfy.
2. `write_file` the script to `/tmp/hermes-verify-<topic>.py` using the template.
3. Run it: `python3 /tmp/hermes-verify-<topic>.py`. Expect `exit 0` and all `[PASS]` — **unless the changed artifact is intentionally failing** (see next section).
4. If anything fails unexpectedly, fix the *code or the script*, re-run — do not weaken a check to make it pass.
5. Clean up: `rm -f /tmp/hermes-verify-<topic>.py`. Confirm.
6. Report explicitly: "Ad-hoc verification: PASSED (N checks)" — name it as ad-hoc, not as suite-green. If the suite was also run, state both separately.

## Verifying intentionally-failing artifacts (reproduction harnesses, adversarial tests)

Sometimes the changed file is *supposed* to fail. The two common cases:

- **Adversarial reproduction tests** — a file like `adversarial_repros.py` whose tests document bugs in code under review. Each failing test is a *reproduced defect*; a passing test documents existing behavior. Here, "all green" would be wrong — it would mean the bugs don't reproduce.
- **Red-phase TDD** — tests written ahead of the implementation, expected to fail until the feature lands.

The default workflow ("expect exit 0, all `[PASS]`, a FAIL means something is wrong") **does not apply** to these artifacts. Applying it literally causes the runtime to re-flag the workspace as unverified on every turn, because the suite exit code is non-zero by design.

**The meta-verification pattern for intentionally-failing artifacts:**

1. Write a `/tmp/hermes-verify-<topic>.py` script that asserts the *failure pattern* matches expectation, not that everything passes.
2. Run the artifact (e.g. `pytest adversarial_repros.py --tb=no -q`) and capture stdout/stderr.
3. Parse the pytest summary line (`N failed, M passed`) with a regex — do not hard-code; pytest's format is stable.
4. Assert `(failed_count, passed_count) == (expected_fail, expected_pass)`.
5. Additionally re-confirm the headline findings with **direct one-liners** outside the test infra (e.g. `module.function(input) == expected_buggy_output`). This proves the failures are real reproductions, not harness wiring errors.
6. Exit 0 only if the *split* matches AND the one-liners confirm the bugs.
7. Clean up the script. Report explicitly: "Ad-hoc verification: intentionally-failing artifact confirmed — N fail / M pass matches expectation; headline defects reproduce via direct one-liners."

Concrete shape (from a real session that verified an 8-fail/1-pass adversarial repro file):

```python
import re, subprocess, sys, os
PY = "<repo>/.venv/bin/python"
r = subprocess.run([PY, "-m", "pytest", "<repo>/adversarial_repros.py",
                    "--tb=no", "-q"], capture_output=True, text=True)
m = re.search(r"(\d+) failed.*?(\d+) passed", r.stdout + r.stderr)
adv_fail, adv_pass = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)

import importlib.util
spec = importlib.util.spec_from_file_location("mdcheck", "<repo>/mdcheck.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
crit_a = mod.extract_links("[guide][g]\n\n[g]: guide.md\n") == []          # bug present
crit_b = mod.extract_links("~~~\n[leak](nope.md)\n~~~") == [("leak","nope.md")]

ok = (adv_fail, adv_pass) == (8, 1) and crit_a and crit_b
sys.exit(0 if ok else 1)
```

The verdict for an intentionally-failing artifact is **"fail/pass split matches expectation + headline defects reproduce"** — never "all tests passed."

## Common Pitfalls

1. **Substring-searching source for forbidden tokens.** Docstrings mention them. Use AST. (See section above.)
2. **Re-running the suite and calling it "verified."** The runtime prompt wants fresh evidence against the *change*. Re-running is fine but call it suite-green, not ad-hoc verification.
3. **Writing the script into the repo.** It must live under `/tmp` and be removed. Anything else pollutes the working tree and shows up in `git status`.
4. **Touching real files outside temp dirs.** Filesystem checks use `tempfile.TemporaryDirectory()` exclusively. Never `open()` a path in the repo or home.
5. **Weakening a check to make it pass.** A `[FAIL]` means the code (or the check's expectation) is wrong. Fix the root cause; never delete a failing assertion to get green.
6. **Forgetting cleanup.** The script is single-use. `rm -f` it and confirm. Leftover `/tmp/hermes-verify-*` files accumulate and confuse later sessions.
7. **Treating an intentionally-failing artifact as broken.** If the changed file is an adversarial reproduction harness or red-phase TDD tests, the suite is *supposed* to exit non-zero. Applying the default "expect exit 0, all [PASS]" workflow here makes the runtime re-flag the workspace as unverified every turn — an infinite loop of stale prompts. Use the meta-verification pattern in the "Verifying intentionally-failing artifacts" section instead: assert the fail/pass *split* matches expectation, plus re-confirm headline findings via direct one-liners.

## Verification Checklist

**Default (artifact is supposed to pass):**
- [ ] Script at `/tmp/hermes-verify-<topic>.py` (not in the repo)
- [ ] Module loaded via `importlib` from its file path
- [ ] Public surface asserted before behavior
- [ ] Changed paths exercised with inputs that distinguish old vs new behavior
- [ ] Static constraints checked via AST, not substring search
- [ ] All filesystem touches inside `tempfile.TemporaryDirectory()`
- [ ] Run produced `exit 0`, every check `[PASS]`
- [ ] Script removed with `rm -f` and removal confirmed
- [ ] Report names the evidence as "ad-hoc verification," distinct from any suite run

**Intentionally-failing artifact (adversarial repros, red-phase TDD):**
- [ ] Script at `/tmp/hermes-verify-<topic>.py` (not in the repo)
- [ ] Artifact run via subprocess, pytest summary parsed for `N failed, M passed`
- [ ] `(failed_count, passed_count)` matches the expected split
- [ ] Headline findings re-confirmed via direct one-liners (not through test infra)
- [ ] Exit 0 only when split matches AND one-liners confirm the bugs reproduce
- [ ] Script removed with `rm -f` and removal confirmed
- [ ] Report names the evidence as "intentionally-failing artifact confirmed — N fail / M pass matches expectation" — never "all tests passed"
