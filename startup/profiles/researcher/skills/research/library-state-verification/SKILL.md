---
name: library-state-verification
description: "Verify the current state of a library or package — actively maintained? last release date? what version? what algorithm/behavior does it implement? does it support X backend? what's the install name? — using package registry JSON (npm/PyPI) and the GitHub repo API as primary sources, falling back to source/docs only when the registry can't answer. Use when the ask is 'is this library still maintained in 20XX', 'check the current state of these N libraries', a dependency audit, or library selection for a new project. Sibling to source-code-verification (behavior from code) and docs-verification (guarantees from docs); load THIS one when the question is about maintenance STATUS and METADATA, not implementation internals or doc guarantees."
---

# Library state verification

Verify the current, dated state of a library or package against primary sources — package registries and the GitHub API — not blog roundups, not your training-data memory of "how library X works." Every claim must trace to a registry record (version + timestamp) or an API field (pushed_at, archived flag). Libraries move; "I recall" is not evidence.

## When to load

- "Is library X still actively maintained in 20XX?"
- "Check the current state of these N libraries" (version, last release, algorithm, dependencies).
- "What's the package name for X? Does it support Redis/Valkey/Postgres?"
- A dependency audit: "which of these are abandoned?"
- Library selection for a new project: "for a FastAPI rate-limiting stack, what are the options and are they healthy?"
- Any ask that bundles **maintenance status** with **behavior/feature** questions.

If the question is purely *how the code implements Y* (clone + read source), load `source-code-verification`. If it's purely *what the docs guarantee*, load `docs-verification`. **This skill is for status + metadata** — version, release cadence, maintenance posture, install name, declared dependencies — with source/docs as confirmatory follow-up only where the registry is silent.

## The method (in order)

### 1. Hit the registry JSON API first — it answers 80% of the question

Don't `npm view` or browse the website; the JSON endpoint gives you machine-clean, complete data in one fetch.

- **npm:** `https://registry.npmjs.org/<package>` → JSON with:
  - `dist-tags.latest` — the current latest version.
  - `time[<version>]` — ISO timestamp of that version's publish (and `time.created`, `time.modified`).
  - `versions[<latest>].repository.url`, `.homepage`, `.dependencies`, `.keywords`, `.engines`.
  - `time` is a full release-history map — sort it descending to see cadence at a glance.
- **PyPI:** `https://pypi.org/pypi/<package>/json` → JSON with:
  - `info.version`, `info.summary`, `info.home_page`, `info.project_urls` (repo + docs), `info.requires_dist` (declared deps + extras like `limits[redis]; extra == "redis"`).
  - `releases[<version>][0].upload_time` — ISO timestamp of the file upload (more reliable than `info` for "when did this actually ship").
  - `releases` is keyed by version → list-of-files; sort by `upload_time` for cadence.

See `references/registry-recipes.md` for the exact field paths, the parse snippets, and the gotchas (e.g. PyPI `requires_dist` encodes optional extras that reveal Redis/Valkey/DB support without cloning).

### 2. Download-to-file, THEN parse — never pipe curl into an interpreter

The shell safety guard blocks `curl … | python3` (and `| bash`, `| sh`) as untrusted-code execution. This is the single most common tooling block on this class of task. The guard-friendly pattern:

```
curl -sL -o /tmp/<name>.json "https://registry.npmjs.org/<package>"
curl -sL -o /tmp/<name>.json "https://pypi.org/pypi/<package>/json"
```

then `python3` reading from the file (heredoc or a local script), or `read_file` + `jq`. Download-then-process is guard-friendly AND leaves the artifact on disk for re-reading. Batch the 4–8 downloads in one `terminal` call (they're independent), then parse in a follow-up call.

### 3. GitHub repo API for the maintenance signals the registry can't give

`https://api.github.com/repos/<org>/<repo>` → JSON with the fields that actually answer "is it alive?":

- `pushed_at` — last commit push (more current than the latest *release*; a repo can be healthy with infrequent releases).
- `archived` — **false** required; `true` = read-only, dead.
- `open_issues_count` — a rough health signal; combine with cadence (a low-release lib with 96 open issues is riskier than one with 6).
- `stargazers_count` — adoption signal, not maintenance signal (don't over-weight).
- `license.spdx_id`, `description`, `default_branch`.
- `message` field = API error (rate-limited / not found / moved) — check for it before reading fields.

**Casing/redirect gotcha:** the `repository.url` in the registry may not be the exact GitHub path (wrong case, renamed org, moved). slowapi's PyPI metadata implies `laurents/slowapi` but the live repo is `laurentS/slowapi`. If `/repos/<path>` 404s, search via `https://api.github.com/search/repositories?q=<name>` or check the repo's own redirect. Don't assert "not found" from a single casing.

### 4. Read source/docs ONLY where the registry is silent — and prefer raw URLs over the browser

The registry answers version/release/deps/package-name. It does NOT answer "what algorithm does it implement?" or "does the Redis path use atomic INCR?" For those:

- Fetch the README and key source files directly via `raw.githubusercontent.com` (fast, full-text, no bot wall, no snapshot truncation):
  - `https://raw.githubusercontent.com/<org>/<repo>/<branch>/README.md`
  - `https://raw.githubusercontent.com/<org>/<repo>/<branch>/<path>/<file>.ts`
- Use the GitHub trees API to find the real file paths when you don't know them: `https://api.github.com/repos/<org>/<repo>/git/trees/<branch>?recursive=1` then filter for `doc`/`.md`/`.rst`/`source` paths. README locations vary (root vs `docs/` vs `doc/source/`); rst vs md; branch `main` vs `master` — resolve via `default_branch` from step 3, don't guess.
- Reserve `browser_navigate` for wiki pages or JS-rendered content that has no raw equivalent (e.g. GitHub wiki pages like `BurstyRateLimiter`). The browser is slower and snapshots truncate; raw files don't.

### 5. Follow the "delegates to a shared backend" chain — the wrapper is not the implementation

Many libraries are thin wrappers over a shared lower-level library. **The wrapper's marketing describes behavior the backend actually implements.** Examples from rate-limiting: both `slowapi` and `flask-limiter` delegate their strategies to `alisaifee/limits` (visible in `requires_dist` as `limits>=2.3` / `limits>=3.13`). So "what algorithms does slowapi offer?" must be answered from `limits/doc/source/strategies.rst`, not slowapi's README. The same pattern recurs elsewhere (Express middleware over a store plugin; ORM features over a driver).

Detection signal: `requires_dist` / `dependencies` names a library that is itself a rate-limiter/storage/auth/serialization primitive. When you see it, trace the claim to the backend's source/docs and cite *that* path.

### 6. Distinguish release cadence from maintenance health

A single timestamp is not a verdict. Read the cadence and the signal together:

- **Healthy:** multiple releases within the last few months, low open-issue count, `archived:false`, recent `pushed_at`.
- **Resume-and-pause:** long gap between releases then a recent one (e.g. slowapi: 2024-02 → 2026-06), often with a high open-issue backlog. "Active" but higher risk for a product hot path.
- **Dead/abandoned:** no releases in 2+ years AND no recent `pushed_at`, OR `archived:true`.
- **Dormant-but-stable:** no recent releases, low issues, the library is "done" (e.g. a small utility). Not necessarily a reject — note the distinction.

Report the cadence (list the last 5–8 releases with dates), not just the latest timestamp, so the reader can judge.

## Pitfalls

- **Piping curl into python/bash.** The guard blocks it. Download-to-file-then-parse, always. (Same lesson is in `docs-verification`; it bites here too because registry-fetch scripts are tempting to one-line.)
- **Trusting `npm view` / the website summary over the JSON.** The website rounds and lags; `time[version]` in the JSON is the authoritative publish timestamp.
- **Asserting "not found" from one GitHub path casing.** Registry `repository.url` casing ≠ live repo casing. Verify via search API or a redirect before declaring a repo missing.
- **Answering "what algorithm" from the wrapper README.** If the lib delegates (see step 5), the README describes the backend's features. Trace to the backend's source or you'll cite the wrong path.
- **Treating stars as maintenance.** Stars measure adoption, not health. A 10k-star lib can be archived; a 600-star lib can be actively shipped. Report `pushed_at` + cadence + issue count, not ⭐ alone.
- **Forgetting to pin the date.** "Latest release 2026-06-08" is meaningless without "verified 2026-07-12." State the verification date; these facts expire.
- **Workspace cleanup after task completion.** If the task is already `done`, its scratch workspace may be garbage-collected. A file written there can vanish. For durable output, post to the kanban blackboard (comment) as the primary record, and write the report file as a secondary artifact (recreate the dir if needed).

## Verification (self-check before reporting)

- [ ] Did I state the verification date? (These facts expire.)
- [ ] Does every version/release claim cite the registry JSON (not the website)?
- [ ] Does every "actively maintained" claim cite `pushed_at` + cadence + `archived` (not stars alone)?
- [ ] Did I check `requires_dist`/`dependencies` for a shared-backend library before claiming the wrapper "implements" a feature?
- [ ] Did I download-to-file rather than piping curl into an interpreter?
- [ ] For "not found" repo claims, did I rule out a casing/redirect issue?
- [ ] Did I read the last 5–8 releases (cadence), not just the latest timestamp?

## Output shape

A findings file (Markdown) with: a summary table (library × last-release × active? × algorithm × Redis/backend × package-name), then per-library detail with registry citations and maintenance posture, then a cross-cutting observations section (shared defaults, shared weaknesses, which libs offer which algorithms), then a full "Sources (URLs)" list. If part of a kanban council, post a condensed table + key differentiators to the shared blackboard as a comment so downstream workers inherit the verdicts.

## Related skills

- `source-code-verification` — sibling. Load when the question is *how the code implements Y* (clone, grep, cite file:line). The two compose: use THIS skill to establish maintenance status + which lib, then source-code-verification to prove a specific behavior in its repo.
- `docs-verification` — sibling. Load when the question is *what the official docs guarantee*. Shares the download-to-file guard workaround and the verbatim-quote discipline.
- `research` (mattpocock) — the general research umbrella; this skill specializes its "primary sources" step for the registry-and-API case.

## Reference

- `references/registry-recipes.md` — concrete field paths and parse snippets for npm and PyPI JSON, the GitHub `/repos/` maintenance-signal field map, the casing/redirect gotcha worked example (slowapi), and the shared-backend-delegation pattern (slowapi/flask-limiter → limits). Read this on your first library-state task.
