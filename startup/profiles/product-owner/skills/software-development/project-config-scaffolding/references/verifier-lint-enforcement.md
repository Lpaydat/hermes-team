# Verifier Lint/Format Enforcement — the cross-node contract gap

Companion to lesson #42 in `workflow-engine-gauntlet-lessons` (which couldn't
be patched — skill is pinned). This file captures the same finding from the
perspective of the scaffolding skill: **scaffolding tooling without enforcing
it is dead config.**

## The gap (found 2026-08-07)

The setup node scaffolds `ruff.toml`, `pyproject.toml` with `[tool.ruff]`, and
a `Makefile` with `lint`/`format`/`check` targets. But the verifier nodes in
`tech-lead-execute.json` (`verify`, `re-verify`, `merge-verify`) and the
`close` node run **only `pytest`** — never `make lint`, never
`make format-check`. Unformatted, lint-failing code ships through the pipeline
with a PASS verdict.

## Why this is a cross-node contract gap (not a verifier-quality gap)

Distinct from gauntlet lessons about verifier *test quality* (shallow tests,
happy-path lock-in, missing features). Those are about the verifier writing
tests that don't catch bugs. This is about the verifier *omitting an entire
category of checks* — it never runs the linter/formatter at all, even though
the setup node just scaffolded them.

## The Makefile is the language-abstraction layer

Verifier node bodies call `make lint` / `make format-check` / `make check`, not
`ruff check` directly. This keeps the template language-agnostic: the same
verifier body works for Python (ruff) and Node (eslint/prettier), because the
Makefile maps the generic target name to the language-specific tool.

## What the scaffolded Makefile must include

```makefile
.PHONY: test lint format format-check check

test:
	pytest -v

lint:
	ruff check src tests

format:
	ruff format src tests

format-check:
	ruff format --check src tests

check: lint format-check test
```

`format-check` is the critical missing target: the verifier is forbidden from
editing dev code, so it needs the `--check` variant of any tool that mutates
files. `check` folds lint + format-check + test into one "is this shippable"
gate.

## What the verifier nodes must do

- `verify` and `re-verify`: insert a "Lint + Format Gate" phase running
  `make lint && make format-check`. Any failure → `verdict = FAIL`.
- `merge-verify`: change Check 3 from `pytest -q` to `make check`.
- Add `lint_pass` (boolean) + `format_clean` (boolean) to each verifier output
  schema — schema fields are ENFORCED, body text is IGNORED.
- Zero edge changes needed: `verify→fix` already fires on any FAIL, so lint
  failures route through the existing fix loop.

## Generalization — the cross-node enforcement principle

When any node scaffolds or configures tooling (lint, format, type-check,
security scan), EVERY downstream node that claims to "verify" or "check" the
code must actually invoke that tooling. Audit the pipeline end-to-end: does the
node that creates the tool also appear in the nodes that check the code?

## Full proposal

`startup/scripts/workflow_engine/VERIFIER-LINT-ENFORCEMENT-PROPOSAL.md` — exact
diffs for the Makefile template and all 4 affected nodes in
`tech-lead-execute.json` (~50 lines, 2 files, 0 new nodes, 0 new edges).
