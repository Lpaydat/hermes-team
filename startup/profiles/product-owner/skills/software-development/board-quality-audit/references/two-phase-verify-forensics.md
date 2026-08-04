## 19. Two-phase "Attack Your Own Tests" verify body — forensic detection

The **two-phase adversarial verify body** (Phase 1: spec→behavior-test matrix;
Phase 2: "attack your own tests" — read every test, find gaps, write ADDITIONAL
tests) is a newer verify-card prompt designed to force the verifier into
self-critique. The critical audit question is: **did Phase 2 actually execute,
or did the verifier write one test file and declare victory?**

This is distinct from the older per-phase DoD verify body (which runs mutation
testing + fresh-eyes probes). A board can have BOTH: the per-phase verifiers
use the old body, and a single integration `[verify-b]` card uses the new
two-phase body. They are different prompts producing different evidence shapes.

### a. The five evidence signals that Phase 2 genuinely ran

Do NOT trust the verdict ("PASS, 79/79") alone. Check for these concrete
artifacts — the more present, the higher the confidence Phase 2 executed:

1. **Two physically distinct test files on disk.** Phase 1 produces
   `test_behavior.py`; Phase 2 produces a SEPARATE file, typically named
   `test_attack.py` or `test_adversarial.py`. If only one file exists, Phase 2
   either didn't run or appended to Phase 1 (weaker signal — check the file
   for a labeled "Phase 2" section). Find them via the run metadata's
   `behavior_test_file` and `attack_test_file` fields:
   ```sql
   SELECT metadata FROM task_runs WHERE task_id = '<verify-b-card-id>';
   -- look for: "behavior_test_file": ".../test_behavior.py",
   --           "attack_test_file": ".../test_attack.py"
   ```
   These files live in `/tmp/hermes-verify-<slug>/` (survives board cleanup —
   see §17b) or may need recovery from `logs/t_<verify-id>.log`.

2. **The attack file has a HIGHER count than the behavior file, and tests
   DIFFERENT things.** If `test_attack.py` has 47 tests and `test_behavior.py`
   has 32, and the attack tests cover control chars / Unicode / huge input /
   unclosed markers while the behavior tests cover spec-element rendering, that
   is genuine Phase 2 gap-filling. If both files test the same things with the
   same inputs, Phase 2 was a copy.

3. **`attack_categories_covered` in the run metadata.** The two-phase body
   asks the verifier to report categories. A metadata blob listing 10-12
   named categories ("boundary_values", "control_chars (0x01-0x1F, 0x7F)",
   "unicode", "huge_input", "nested_inline_formatting", etc.) is strong
   evidence. Cross-check: do the category names map to real tests in the file?

4. **A self-caught probe-inversion.** This is the strongest single signal. The
   two-phase body explicitly asks the verifier to question its own tests. If
   the metadata records `probe_inversions_caught_and_fixed: 1` with a detail
   string ("javascript: URL — my assertion was wrong; corrected"), the
   verifier genuinely re-read its work and found its OWN error. A rubber-stamp
   verifier never reports a probe-inversion (it would mean admitting its first
   test was wrong).

5. **Coverage of the specific gaps the two-phase body names.** The prompt body
   lists common LLM-missed gaps: delimiter injection, control characters
   (0x00-0x1F, 0x7F), empty/None inputs, Unicode, production-mode testing,
   boundary values. Grep the attack test file for the actual bytes:
   ```sh
   grep -n "0x01\|0x1f\|0x7f\|\\\\x00\|\\\\t\|null\|None\|inject\|delim" test_attack.py
   ```
   A test NAMED `test_special_chars` that only uses quotes (not tabs, not null)
   is the docstring-vs-input mismatch pattern (§18a) — Phase 2 claimed coverage
   it didn't exercise.

### b. The production-mode claim — verify it structurally

The two-phase body explicitly asks: "What happens in production mode? Test
with TESTING=False." For a CLI tool (no web framework), the honest
interpretation is: **tests run the real entry script via `subprocess`, not
imports with test harness flags.** Check the behavior test file:

```python
# GOOD (production-mode honest): invokes the real CLI binary
res = subprocess.run([sys.executable, "md2html.py", src], capture_output=True, text=True)

# WEAK (test-harness-dependent): imports the module and calls main() directly
md2html.main(["input.md"])  # no real process, no real argparse, conftest may mask
```

A metadata claim `production_mode_tested: true` with detail "CLI tests run real
md2html.py via subprocess; no conftest.py, no TESTING flag" is credible. A bare
`production_mode_tested: true` with no detail is a yellow flag — check whether
ANY test uses subprocess.

### c. Scoring two-phase verify vs mutation-test verify

A board with BOTH verify body types should score them separately:

| Verify body type | Where | Strength signal | Integrity guarantee |
|---|---|---|---|
| Per-phase DoD + mutation testing | 5 `[verify]` cards | "3/3 mutations caught" | mutation loop (break code → tests fail → restore → green) |
| Two-phase attack (integration) | 1 `[verify-b]` card | separate `test_attack.py` + self-caught probe-inversion | Phase 2 gap-filling + self-critique |

**A 9-10 on verify accuracy requires EITHER a mutation loop (old body) OR a
genuine Phase 2 attack file (new body).** Both is strongest. Neither — just a
large behavior suite with no mutations and no attack file — caps at 7-8.

**The blemish to note on two-phase verify:** attack tests often assert "no
crash" / "valid HTML" for the hardest inputs (control chars, huge input)
rather than asserting exact rendered output. This is *appropriate* when the
spec doesn't define behavior for those inputs, but it means some "PASS" results
are crash-resistance checks, not correctness checks. Note this honestly in the
report — it's a test-quality observation, not a defect.

### d. Worked example — livetest-unbias-6 (Markdown→HTML Converter)

Integration verify card `t_66d8f1d3` used the two-phase body. All five signals
present:

| Signal | Evidence |
|---|---|
| Two distinct files | `test_behavior.py` (32 tests) + `test_attack.py` (47 tests), both in `/tmp/hermes-verify-md2html-integration/` |
| Attack tests cover new ground | control chars (0x01-0x1F loop + 0x7F), Unicode (emoji/CJK/Cyrillic/RTL), huge input (100K lines, 1M-char line), None/int raises, nested formatting, unclosed markers, empty edge cases, XSS/URL-escaping |
| attack_categories_covered | 12 named categories in run metadata |
| Self-caught probe-inversion | `probe_inversions_caught_and_fixed: 1` — "javascript: URL with embedded parens — my assertion was wrong per the [text](url) regex, not a code bug" |
| Production-mode honest | 3 CLI tests via real subprocess, no conftest, no TESTING flag; metadata detail confirms |

The per-phase verifiers (5 cards) used the OLD body with mutation testing
(3/3 mutations caught on each). The integration card used the NEW two-phase
body. Together: 9-10 verify accuracy. Phase 2 genuinely executed — it produced
a distinct 47-test attack file and demonstrated honest self-critique (the
self-caught probe-inversion).

**The inline-code gap from round 1 was caught and tested.** The two-phase body
explicitly names "delimiter injection" and the attack file includes
`test_code_inside_bold_not_reformatted`, `test_multiple_code_spans_one_line`,
`test_unclosed_inline_code`. The code-span-lost-inside-link-text bug (found by
the per-phase verifier on Phase 5, fixed in a `[fix]` card, re-verified) was
also regression-tested in both suites. The verify=PASS verdict is accurate.
