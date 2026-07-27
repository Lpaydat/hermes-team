---
name: prototype-verification
description: "Independently verify a built prototype against its locked grill decisions. Two layers: the static verify-script (structure/content/README/build-rules) AND runtime verification (actually run the tool, exercise every mode, assert exit codes, test flag combos and stateful features). Use when you are the verifier session in a loop_engine phase, or a standalone verification task."
disable-model-invocation: false
---

# Prototype Verification

You are the **independent verifier** for a prototype build. Your job is not to
trust the builder's self-report, nor to trust the static verify-script alone.
Your job is to prove — with real command output — that the prototype does what
its locked grill decisions promise, and to surface silent bugs the builder could
not see in their own code.

Load this skill when you are:
- The verifier session in a `venture-prototype` loop_engine phase.
- A standalone verification task (kanban card or direct request) asked to
  "verify the prototype matches its design decisions."
- Reviewing a prototype before founder handoff and wanting real evidence, not
  a glance at the README.

## The two-layer check — both are mandatory

A prototype can pass every static check (36/47, say) and still have **runtime
bugs** the script cannot see: a CLI flag that silently no-ops, a mode that
crashes only with certain flag combinations, a drift detector that never fires.
Do not equate "script exit 0" with "prototype works."

### Layer 1 — Static (the verify-script)

Run `python3 /tmp/verify-<slug>.py`. This catches:
- Missing files, missing README sections, unbalanced HTML braces.
- Unfulfilled locked decisions (decision value not found in prototype content).
- Build-rule violations (external deps, no simulated-data label, wrong theme).

The verify-script is written by the builder from the template in
`venture-prototype/references/verify-script-template.md`. It is necessary but
not sufficient.

### Layer 2 — Runtime (YOU do this)

Actually run the prototype's commands and confirm the behavior the design
decisions promise. This is where silent bugs live. See
[references/runtime-verification.md](references/runtime-verification.md) for the
full checklist and reproducible recipes. Summary:

1. **Happy path** — run the documented one-liner. Capture real output. Confirm
   it produces what the decisions promise.
2. **Every output mode** — `--json`, `--verbose`, `--report`, each run. For
   `--json`: pipe through `json.load()` and assert the schema programmatically
   (a `findings` array exists, severities are valid). Do not eyeball JSON.
3. **Exit-code contract** — if the design promises "exit 1 on HIGH findings,"
   assert `$?` is literally 1. Do not assume.
4. **Flag combinations** — flags documented as independent sometimes share
   hidden state. Test `--save-X` alone, `--check-Y` alone, and together.
5. **Stateful features** (manifests, caches, drift, provenance) — test in a
   sandbox copy; see the drift recipe below.

## Testing drift / hash-based provenance without trashing fixtures

Drift detection compares current hashes against a stored manifest. You must
(a) save a baseline, (b) confirm no-drift on an unchanged repo, (c) mutate a
file and confirm drift *fires*. **Never mutate the project's own sample
fixture** — the next run depends on it being pristine.

```bash
cp -r ~/projects/<slug>/prototype/sample-repo /tmp/pf_sandbox_repo
python3 scan.py /tmp/pf_sandbox_repo --save-manifest /tmp/pf_baseline.json   # baseline

# Clean-run: expect ZERO drift findings
python3 scan.py /tmp/pf_sandbox_repo --drift /tmp/pf_baseline.json --json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
     drift=[f for f in d['findings'] if f.get('category')=='drift-provenance']; \
     print('drift (should be 0):', len(drift))"

# Mutate one file, re-run: expect a CHANGED/DRIFT finding
printf '\n# drift test mutation\n' >> /tmp/pf_sandbox_repo/README.md
python3 scan.py /tmp/pf_sandbox_repo --drift /tmp/pf_baseline.json --json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
     drift=[f for f in d['findings'] if f.get('category')=='drift-provenance']; \
     print('drift after mutation (should be >0):', len(drift))"
```

Clean-run showing drift → baseline wrong or hasher non-deterministic.
Post-mutation showing nothing → drift detection is broken. Both are FAIL.

## Debugging "flag silently does nothing"

When a documented flag (`--save-manifest`, `--export`) produces no file and no
error, trace the data flow:

1. Find the flag handler in `main()` and the condition guarding the side effect.
2. Find where its dependent data is populated. Often a dict/list is only filled
   inside a *sibling* flag's code path — e.g. `current_hashes` only computed under
   `--drift`, so `--save-manifest` alone sees an empty dict and its
   `if result.get("current_hashes"):` guard is falsy → silent no-op.
3. Confirm by running the flag *with* the sibling (point the sibling at a
   nonexistent path if needed). If it suddenly works, the coupling is confirmed.

This pattern — "feature A's output is silently gated on feature B running first"
— recurs in single-file tools where two features share a helper whose invocation
is conditional. Report it as a defect with exact line numbers; do not paper over it.

## What to report

State **PASS**, **FAIL**, or **PARTIAL PASS** with specific evidence, not
impressions:

- Finding counts by severity ("26 HIGH, 1 MEDIUM, 27 total").
- Which promised capabilities were confirmed, by rule ID / output line.
- Which were missed or broken, with the command that exposed it and the
  offending code location.
- A binary "PASS" that hides a silent-flag bug is dishonest. Use PARTIAL PASS
  and list both the passing evidence and the defects.

## Pitfalls

- **Trusting the static script as the whole verification.** It only reads files.
  Runtime behavior is a separate axis the script cannot see. Always do Layer 2.
  Real example (2026-07-25): the App Store Impersonation Monitor prototype passed
  47/47 static checks (AST parse, regex grep, file existence) but crashed on
  execution with `NameError: name 'imagehash' is not defined`. The import block
  set `HAS_ICON_LIBS = False` when imagehash wasn't installed, but
  `compute_icon_similarity()` called `imagehash.hex_to_hash()` without checking
  `HAS_ICON_LIBS`. Static analysis cannot catch unguarded optional-import usage
  — only running the script exposes it.
- **The verify script itself not including a runtime execution step.** The verify
  script template in venture-prototype/references/ was updated on 2026-07-25 to
  include Category 5 (runtime execution) and Category 4 (environment/import checks).
  However, the builder may use an older cached copy instead of calling skill_view
  for the latest template. Always verify the runtime category is present before
  trusting the verify script. If missing, it's a static-only false confidence
  generator: the original template passed 47/47 for a prototype that crashed on
  launch. See
  [references/verify-script-runtime-category.md](references/verify-script-runtime-category.md)
  for a standalone Category 5 code block to append when the template was not used.
- **Self-reported demo metrics from a prototype that never ran.** When a builder
  reports "precision 35%, recall 100%" in kanban_complete metadata, but the
  prototype crashes on execution, those metrics are fabricated — they're the
  expected values from the design, not measured output. Always run the prototype
  yourself and verify that the reported metrics appear in real stdout/stderr.
- **Eyeballing JSON instead of parsing it.** `--json` output must be run through
  `json.load()` with assertions on the schema. "It looks like JSON" is not
  verification.
- **Assuming exit codes.** A tool that's supposed to exit 1 on HIGH findings but
  exits 0 (or 2) has a broken CI contract. Assert `$?` explicitly every time.
- **Mutating the project fixture to test drift.** The fixture must stay pristine
  for future runs. Always copy to `/tmp` first.
- **Reporting PASS on a mixed result.** If anything is broken, say PARTIAL PASS
  and enumerate defects. The founder/PO needs the defect list to decide.
- **Stopping at the first failure.** Keep verifying the rest of the surface so
  the report gives complete repair scope, not just the first bug found.

## NEVER

- **NEVER modify prototype files during verification.** You are a read-only
  verifier. If you need a mutation to test drift, do it in a `/tmp` sandbox copy.
- **NEVER report "PASS" without exercising runtime.** Static-only verification is
  incomplete and gives false confidence.
- **NEVER fabricate output.** If a command fails or you can't run it, say so.
  Report the blocker honestly rather than inventing a result.
