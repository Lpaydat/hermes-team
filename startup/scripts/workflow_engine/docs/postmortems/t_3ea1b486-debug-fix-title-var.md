# Post-mortem: debug-fix subworkflow card titles rendered with blank variables

**Bug ID:** t_3ea1b486
**Date:** 2026-08-06
**Branch:** fix-v1-merge-gap

## Summary

Cards spawned by the `debug-fix` subworkflow were born with blank variable
slots — titles like `[bug] Fix failing tests:` (trailing `${bug_title}` empty)
and, on older cards, blank `Repo` / `Failing tests` / `Context` body fields.
The root cause is a template variable-prefix mismatch in
`templates/debug-fix.json` that an earlier fix (commit 85b6465) only
half-corrected.

## Root cause

`debug-fix.json` defines two task nodes (`debug`, `verify-fix`). Each has a
`title_template` and a `body_template`. When the `merge-test` parent workflow
dispatches the `debug-fix` subworkflow node, it passes data via
`input_mapping` (e.g. `bug_title`, `repo`, `failing_tests`). The child
workflow's `_build_ctx` (`runtime.py:1118-1132`) stores every input_mapping
value under the `trigger.{key}` namespace — so `bug_title` becomes
`trigger.bug_title` in the resolution context.

Commit 85b6465 ("fix: debug-fix body uses trigger.* prefix for subworkflow
input vars") correctly changed the **body_template**s from bare `${repo}` to
`${trigger.repo}`. It did **not** change the two **title_template**s, which
kept referencing bare `${bug_title}`. `resolve_template(title_template, ctx)`
(`runtime.py:2240-2241`) looks up `bug_title` (no such key — only
`trigger.bug_title` exists) and resolves it to an empty string.

## Fix

`templates/debug-fix.json`:
- `debug` node: `title_template` `${bug_title}` → `${trigger.bug_title}`
- `verify-fix` node: `title_template` `${bug_title}` → `${trigger.bug_title}`

A scan of all templates confirms these were the only two bare-key references
in any `title_template` / `body_template`; after the fix, zero non-prefixed
`${var}` references remain across all template fields.

## Validation

- **Regression test** added: `test_subworkflow.py::test_subworkflow_child_title_resolves_mapping`.
  Constructs a parent→child subworkflow with an `input_mapping` of `bug_title`
  and a child `title_template` of `${trigger.bug_title}`; asserts the spawned
  child card title contains the mapped value. Verified it FAILS against the
  broken bare `${bug_title}` form (title renders `[bug] Fix: `) and PASSES
  against the fixed `${trigger.bug_title}` form.
- **Full suite:** 449 passed, 1 skipped (was 448+1; +1 is the new test). No
  regressions.
- **Live-equivalent repro:** loaded the real `debug-fix.json` (post-fix) into
  a FakeWorld and dispatched it via the exact `merge-test` input_mapping; the
  child debug card rendered `TITLE: [bug] Fix failing tests: [merge-test]
  EXT-DBG3: full debug-fix test` and `BODY: **Repo:** /tmp/ext-dbg-repo`.

## Symptom (live evidence)

- Card `t_35ae2df7` (created 1786023473, AFTER commit 85b6465 @ 1786023258):
  body correct, title still `[bug] Fix failing tests:` (blank) — proves the
  title bug survived the body-only fix.
- Card `t_3ea1b486` (created 1786023172, BEFORE 85b6465): both title and body
  blank.
- The trigger_context plumbing was correct all along — both debug-fix
  instances carried populated `bug_title` / `repo` / `failing_tests`; only the
  template variable name was wrong.

## Mechanism

`_build_ctx` namespaces input_mapping values as `trigger.{key}` (deliberate —
it merges `inst.trigger_context` under the `trigger.` prefix). Any template
field resolved through `resolve_template(..., ctx)` must therefore use the
`trigger.` prefix for mapped vars. The body_templates were corrected; the
title_templates were not, because they sat on the line above the changed
body line in the same commit's diff and were overlooked.

## How it slipped through

No existing test exercised a subworkflow child **card title** rendered from
an input_mapping variable. `test_subworkflow_input_mapping` asserts the
child instance's `trigger_context` dict (the plumbing), not the rendered
title string that lands on the board card. The body was implicitly covered
by dataflow tests that read `tasks.body`; titles were never asserted. The
regression test added here closes that gap.

## Action items

- The template-authoring surface has no guard against bare-key variable
  references. A lint check (`${var}` not starting with a known namespace) run
  over `templates/*.json` would have caught this at author time. Consider
  adding one to the template-load path or a pre-commit hook.
