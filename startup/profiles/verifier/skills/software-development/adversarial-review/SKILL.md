---
name: adversarial-review
description: "Verify developer card output against contract + bead criteria. Use on EVERY verification card. Executes tests, scans for stubs/dead code/uncovered functions, dispatches fresh-eyes subagent, runs /review + ponytail-review, scrutinizes intent, probes error paths, mutation-checks tests, synthesizes findings, gates on AC checklist, then verdicts."
version: 5.2.0
metadata:
  hermes:
    tags: [verify, validation, merge, kanban, adversarial, evidence]
    category: software-development
---

# adversarial-review — the code is broken; prove it, then prove your proof

Your verification card is a child of a developer card. The parent's completion metadata auto-injects: `branch_name`, `worktree_path`, `harness_session_id`, `changed_files`. You are **trace-blind** — you judge the OUTPUT, never the reasoning that produced it.

**Done when**: verdict reached (PASS → merge, FAIL → fix card, ESCALATE → tech-lead).

## The independence principle

A verifier that only checks "were my previous findings fixed?" develops **confirmation bias** — it stops hunting for new issues. Backward-only verification degrades over iterations (Huang et al., "LLMs Cannot Self-Correct Reasoning Yet"). Every iteration runs BOTH a delta check AND a fresh-eyes pass from scratch.

## 1. Execute first

Run against the developer's branch (via `git -C <worktree_path>`): `evals_cmd` → test suite → build → lint/typecheck. Record actual outputs.

Static diff-judging without execution is **disqualified** — LLM judges without execution run 52-78% accuracy.

**Done when**: all four outputs recorded (pass or fail).

## 2. Completeness gate — stubs, dead code, uncovered functions

Before the two-phase protocol, mechanically scan the diff for incomplete code.
These are **auto-Critical findings** — no reasoning needed, just detection.

### 2a. Stub / placeholder scan

Scan every file in the diff for:

```
grep -nE '(TODO|FIXME|HACK|XXX|STUB|NotImplementedError|\.\.\.)' <changed .py files>
```

And AST-scan for stub function bodies:

```python
# Functions whose body is only: pass, return None, docstring+pass, or docstring+return None
```

**Any match → Critical finding**: "Stub at file:line — function X has no implementation body."

**Exception**: `__init__` with only `super().__init__()` is not a stub. Verify by reading.

**Done when**: every stub pattern checked, findings filed or cleared.

### 2b. Deferred-work scan (ponytail-debt)

Run `ponytail-debt` on the changed files. Any `ponytail:` comments → **Important finding**:
"Deferred work: file:line — developer marked this for later."

**Done when**: ponytail-debt returns clean or all markers filed as findings.

### 2c. Uncovered-function scan

List every function/method/class added or modified in the diff. Cross-reference
each against the bead acceptance criteria:

```bash
git diff <merge-base> --name-only -- '*.py' | xargs -I{} python3 -c "
import ast, sys
tree = ast.parse(open('{}').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        print('{}:{}: {}'.format('{}', node.lineno, node.name))
"
```

For each function found in the diff:
- Is it exercised by at least one AC?
- Is it called by a test that maps to an AC?
- If **no AC covers it** → **Note finding**: "Uncovered function: X — not referenced by any acceptance criterion. May be dead code or missing AC coverage."

**Done when**: every function in the diff is mapped to an AC or flagged as uncovered.

## 3. Two-phase protocol

### Phase A: Delta check (skip on iteration 1)

Re-verify that all N-1 findings were fixed. Read prior findings from the `REVIEW-ITERATION: <N-1>` comment on the developer card. For each: re-run the repro. Record one of:

- **FIXED** — finding no longer reproduces; the code/test was genuinely corrected.
- **STILL-FAILING** — reproduces unchanged.
- **REGRESSED** — reproduces, plus new symptoms in the same area.
- **RESOLVED-BY-SKIP** ⚠️ — the developer silenced the finding by `@pytest.mark.skip`-ping the test, `xfail`-ing it, deleting it, or commenting out assertions, rather than fixing the underlying behavior. **This is NOT a fix.** See [probe-patterns.md](references/probe-patterns.md) §"Skip-as-fix detection" — it converts to a Critical carrying the original defect.

**Done when**: every prior finding has a status (RESOLVED-BY-SKIP counts as a finding, not a close).

### Phase A+: Constraint-drift sweep (every iteration ≥ 2)

Read the FULL comment thread on the developer card AND the parent chain (fix card → review card → … → root), newest-first. Developers ship justifications ("architecturally impossible", "frozen module", "cannot persist across processes") that were **true at iteration N-1 but invalidated by a later planner/tech-lead comment**. A developer working from a stale `parents` handoff snapshot won't have seen the superseding steer.

For each justification the developer cites in their fix (skip reason, design-decision docstring, "can't do X because Y" in metadata):
1. Find the origin of constraint Y in the thread.
2. Check for a later comment that lifts/changes Y (search for "OBSOLETE", "superseded", "SPEC GAP FIX", "resolution", "lifted", "authorized to modify").
3. If a later comment supersedes Y → the justification is void; the underlying finding reopens. File as a Critical with evidence = the superseding comment + a fresh probe.

**Done when**: every developer justification is either confirmed-current or flagged as citing a stale constraint.

### Phase B: Fresh-eyes subagent (every iteration, parallel with C)

Dispatch `delegate_task` with **deliberately restricted context**:

- `context`: contract.md + bead ACs + git diff + worktree path
- `goal`: "Execute the test suite. For each acceptance criterion, write your own probe and verify independently. Report PASS/FAIL per criterion with actual output. Find bugs the tests miss."
- `toolsets`: ["terminal", "file"]
- **Never pass**: prior findings, developer's completion report, trace ledger

The subagent's clean context is your independence guarantee.

**Done when**: subagent returns per-AC PASS/FAIL + discovered bugs.

### Phase C: Static analysis (parallel with B)

Run `/review` and `ponytail-review` on the diff:

| Axis | Question | Tool |
|------|----------|------|
| Standards | "Is the code well-written?" | `/review --since <merge-base> --spec contract.md` |
| Spec | "Did the code meet the contract?" | `/review` spec axis |
| Complexity | "Is the code over-engineered?" | `ponytail-review` (delete, stdlib, yagni, shrink tags) |

Cross-check against bead ACs (`bd show <bead-id>`). If contract says X but bead says Y → **spec gap**, not a code bug.

**Done when**: all three axes produce findings (or "clean").

## 4. Synthesize

Combine Phase A + B + C results:

1. **Deduplicate** — both phases may find the same issue; count once
2. **Detect regressions** — Phase A says "fixed" but Phase B found a new issue in the same area → REGRESSED (Critical)
3. **Prioritize** — Critical > Important > Minor > Note

**Done when**: unified findings list with no duplicates, every finding has severity.

## 5. Probe synthesis gaps + intent review

Examine what neither phase tested. Write probes for edge cases, codebase interactions, trust-boundary inputs, concurrency. This is where your judgment adds value beyond systematic phases.

### 5a. Scrutinize the intent (should this exist?)

Before writing more probes, step back and ask: **is this change the right solution?** Load `scrutinize` skill. Run a one-pass review:

1. **State the goal in one sentence** — if you can't, the spec is underspecified
2. **Simpler alternative?** — could stdlib do this? Does a smaller change solve 90% with 10% risk?
3. **Trace the actual code path** — entry point → call sites → branches → state → exit. Not just the diff lines — follow through unchanged code at the seams.
4. If a simpler approach exists → **Important finding**: "Over-engineered: X could be replaced with Y (stdlib 2-liner)."

This is the only step that questions the **architecture**, not just the implementation.

**Done when**: scrutinize pass complete, findings filed or cleared.

### 5b. Error-path probing (production killers)

Systematically probe failure modes that tests typically skip. For each public function in the diff:

| Input class | Probe |
|-------------|-------|
| None / empty | `func(None)`, `func("")`, `func([])` — should raise or return safely, not crash |
| Boundary | `func(-1)`, `func(0)`, `func(MAX_INT)` |
| Type mismatch | `func("string")` when int expected, `func(b"bytes")` when str expected |
| Huge input | `func("A" * 10_000_000)` — should handle without OOM |
| Concurrent access | If thread-safety promised: hammer from N threads |
| File system errors | If file ops: full disk (mock), missing dir, permission denied, locked file |
| Partial failure | If multi-step: kill mid-operation, retry |
| **Valid JSON, schema-violating** | If the code parses subprocess/external JSON: emit `json.loads`-valid output that OMITS a key the code indexes (`[{"id":"x"}]` when code does `b["status"]`). `json.loads` succeeds so an `except JSONDecodeError` does NOT catch — the subsequent `dict[...]` raises **uncaught `KeyError`**. The #1 gap when devs wrap only the parse, not the field access. Probe via a fake binary on PATH — see [probe-patterns.md](references/probe-patterns.md) §5 — no monkeypatching of the SUT. |

Any uncaught crash → **Important finding**: "Unhandled error path: func(None) raises uncaught TypeError instead of ValueError." (A crash on schema-violating-but-parseable JSON is the same severity — an `except JSONDecodeError` that leaves `dict["key"]` exposed is a half-written guard.)

**Done when**: at least one error-path probe per public function, all results recorded.

### 5c. Mutation check (anti-test-tampering)

Pick the 3 most critical assertions from the developer's test suite. For each:
1. Mutate the implementation slightly (e.g., change `>` to `>=`, swap return values, comment out a guard)
2. Run the developer's tests
3. **Target the behavior's enforcement line, not a downstream refinement.** Trace the behavior to the EARLIEST line where it is enforced and mutate THAT. Mutating a line that runs AFTER the behavior already took effect often has no observable impact → false "NOT-CAUGHT (test gap!)". Worked example: "skip missing values" is enforced at `present = [r for r in rows if not _is_missing(r)]`; mutating the later `numbers = [n for n in (_try_number(v) for v in present) if n is not None]` line (which consumes already-filtered `present`) cannot re-introduce missing values, so tests still pass and you would falsely file a Critical test-gap.
4. **Self-verify a NOT-CAUGHT result before filing.** After mutating, call the function on a fixture that exercises the behavior and compare mutated vs original output. If output is unchanged, your mutation missed the enforcement line — re-target, do not file. A NOT-CAUGHT filed without this check is the #1 false-Critical in mutation testing.
5. If tests **still pass** with a correctly-targeted mutation → the test is **not actually testing that behavior** → **Critical finding**: "Test X does not guard behavior Y — mutation at file:line passed undetected."
6. **Restore + re-verify (non-negotiable).** Every mutation EDITS the implementation. After all mutations, restore via `git -C <worktree> checkout -- <file>` (or `git stash` if several files) — NOT manual re-patching, which drifts. Then **re-run the suite on the restored tree** and confirm green. Any test run from BEFORE the mutation cycle is now stale: you altered the exact files your verdict rests on, so an earlier "24 passed" no longer describes the current state. A green verdict based on pre-mutation runs while the worktree was mutated partway through has no factual basis — the verification-status gate will (correctly) flag it as unverified. Produce fresh evidence against the post-restore state before verdicting.

This is expensive — limit to 3 mutations per review.

**Done when**: 3 mutation checks completed, results recorded, implementation restored via git, suite re-run green on the restored tree.

**Done when**: gap probes executed, results added to findings list.

## 6. Verify-findings gate

Re-run the repro for **every finding** before filing. A finding must carry:
- failing test/eval output (pasted, actual), OR
- a repro command another agent can run, OR
- a line-anchored contract violation (file:line + quoted contract item)

Doesn't reproduce → demote to note or drop. A Critical you wouldn't re-verify isn't Critical.

**Self-verify the probe itself.** A "failing" probe is evidence of a contract violation ONLY if the probe's *expectations* are correct AND the probe's *inputs* satisfy the test's own premise. Before filing, (a) re-derive the expected output by hand from the contract semantics, independent of the probe's assertion; AND (b) assert the input actually has the property the test label claims (a "no-lowercase" test must not pad with `'c'`; a "12-char boundary" input must actually be 12 chars). If the probe's expectation is wrong (typo in expected-set, conflating substring with regex, off-by-one, mutable-default aliasing) OR the input is contaminated (pad char smuggles in an excluded class, hand-counted length is off), the implementation behaved correctly and the "failure" is a bug in your probe — fix the probe and re-run, do NOT file the finding. This is the single most common fresh-eyes error: an adversarial probe that "fails" because it asserts the wrong thing or feeds the wrong thing. When in doubt, isolate: print `repr(actual)`, `repr(expected)`, AND `repr(input)` and compare all three to the contract by hand. See [probe-patterns.md](references/probe-patterns.md) §1 (wrong expectation), §7 (precondition-violating input), §8 (input contamination via a shared builder/pad char).

**Done when**: every finding has verified evidence attached, and every probe's expectation has been re-derived from the contract.

## 7. AC checklist gate

For each bead acceptance criterion (`bd show <bead-id>`): write your own probe (not the developer's test), execute it, record PASS/FAIL. Any AC that fails → **Critical finding**.

The developer's proof is a **claim**; your execution is the **fact**.

**Done when**: every AC has independent PASS/FAIL with actual output.

## 8. Verdict → [verdict-routing.md](references/verdict-routing.md)

**PASS**: zero Critical/Important + all ACs verified → merge via [merge-protocol.md](references/merge-protocol.md).

**FAIL**: create fix card for developer with findings → [verdict-routing.md](references/verdict-routing.md) for card creation template.

**ESCALATE**: iteration ≥ 3 or spec gap → [verdict-routing.md](references/verdict-routing.md) for escalation procedure.

## Never

- Write or fix code (including conflict resolution)
- Merge without post-rebase execution
- File a finding without verified evidence
- Read the developer's trace as a first resort
- Re-contract, amend beads, or edit contracts
- Accept "done" claims — execution is the fact
- Skip Phase B on iterations 2+ — confirmation bias is the #1 failure mode

## Pitfalls

- **Confirmation bias**: checking ONLY prior findings on iterations 2+. Phase B exists to break this.
- **Rubber-stamping**: PASS without executed evidence attached.
- **Finding inflation**: burying real Criticals under unverified Minors.
- **Context leak**: accidentally passing prior findings to Phase B subagent destroys its independence.
- **Stale iteration count**: forgetting `REVIEW-ITERATION: <N>` breaks the escalation circuit breaker.
- **Skip-as-fix evasion**: developer resolves a finding by `pytest.mark.skip` / `xfail` / deletion / commented-out assertion with a plausible-sounding reason ("architecturally impossible") instead of fixing the code. A green suite with a newly-appeared skip is not a fix. A skip reason that cites a constraint is a load-bearing claim — verify the constraint is still current (see next). See [probe-patterns.md](references/probe-patterns.md) §"Skip-as-fix detection."
- **Constraint-drift blind spot**: developer's skip/design justification references a constraint ("frozen module", "cannot persist", "impossible") that a *later* planner/tech-lead comment on the same thread has already lifted or superseded. Always sweep the full thread newest-first before accepting any "can't do X" rationale. See §Phase A+.
- **Probe-inversion**: a probe "fails" because its own asserted expectation is wrong (typo, substring-vs-regex confusion, off-by-one), not because the code is wrong. Self-verify the probe's expectation against the contract before filing. See §5 and [probe-patterns.md](references/probe-patterns.md) §"Self-verify before filing."
- **Precondition-violating input**: a probe crashes mid-suite because the *input* was illegal for the function under test (e.g. `invert_dict({"k": {...}})` → `TypeError: unhashable type`), not because the function is broken. The classic shape is a no-mutation probe reusing one rich fixture across all functions, including one whose values must be hashable. Use a per-function legal fixture, and if you deliberately probe the illegal-input path, assert that the `TypeError` IS raised. See [probe-patterns.md](references/probe-patterns.md) §7.
- **Normalization-variant blind spot**: dev tests use only the normalized input form (all-lowercase keys, ASCII strings, single delimiter), so a bug on the non-normalized form (uppercase key → `configparser.optionxform` lowercases it → comment-map lookup misses → comment silently dropped) passes the suite. Write at least one probe per normalization axis using the non-normalized variant. See [probe-patterns.md](references/probe-patterns.md) §6.
- **Probe-input contamination**: a shared input-builder (pad-to-length helper, fixture factory) uses one pad/fill char across all test variants, and that char belongs to a class a variant is trying to EXCLUDE — so the "no-lowercase" test secretly contains lowercase, the function correctly returns the lowercase-present result, and the probe reports FAIL. Distinct from §1 (wrong expectation) and §7 (crash on illegal input): here nothing crashes and the expectation is correctly derived, but the *input* violates the test's own premise. Guard: pad from an already-present class, assert the input's defining property before asserting on output, and print `repr(input)` + `len(input)` next to every result. See [probe-patterns.md](references/probe-patterns.md) §8.
- **Mutation-mistargeting** (§5c): a mutation "isn't caught" because you mutated a line DOWNSTREAM of where the behavior is enforced — the skip/filter happened upstream, your mutation operates on already-filtered data, and cannot change the observable output. Produces a false Critical test-gap finding that looks exactly like a real one. Guard: trace the behavior to its earliest enforcement line and mutate that; then assert the mutation actually changes the function's output on a behavior-exercising fixture BEFORE filing NOT-CAUGHT. If mutated output == original output on such a fixture, you missed the line — re-target, never file.
- **Pre-mutation evidence staleness** (§5c step 6): reporting "all tests green" from a run BEFORE you entered the mutation cycle, after you have since edited the implementation under test, is a stale-evidence verdict. The verification-status gate flags any turn that edited code without fresh post-edit evidence. Guard: treat the mutation cycle as invalidating all prior suite runs; restore via git and re-run the suite on the restored tree before citing any green in your verdict.
- **Probe-script pollution**: the verifier's own ad-hoc probes (independent AC fixtures, edge-case repros, mutation harnesses) belong under `/tmp/hermes-verify-*.py`, NOT in the worktree under review. The worktree is the developer's deliverable space — a stray `verify_probes.py` you forget to delete (or that survives an interrupted run) can ride into the merge commit and ship to master. Write probes to `/tmp`, import the SUT via `sys.path.insert(0, <worktree>)`, run them from there; they vanish when the session ends. A probe you must remember to `rm` from the worktree is fragile (root-path delete guards, interrupted runs); a probe never written to the worktree cannot leak. The dev's `test_*.py` files stay in the worktree — your throwaway probes do not.
- **Purity-probe self-contamination** (§9): a purity check that diffs `locals()`/`globals()` around the call will false-FAIL because the probe's OWN snapshot variables (`pre`, `post`, `sentinel`, `before_globals`) appear in the diff — the measurement apparatus contaminates the measurement. Two real-session iterations wasted on this before the correct shape was found. Never diff the probe's own frame; snapshot the TARGET MODULE's namespace (`vars(target_module)` / `dir(target_module)`) instead, or hold snapshots on a separate namespace object (`types.SimpleNamespace`, a throwaway class). Related §1-variant: do NOT assert `f(f(x))==f(x)` ("idempotent") as the purity invariant for a function that normalizes AND transforms (e.g. `reverse_words`) — it is correctly non-idempotent (its own inverse on word order). Assert "output is canonical" (`f(x) == " ".join(f(x).split())`) instead. See [probe-patterns.md](references/probe-patterns.md) §9.
