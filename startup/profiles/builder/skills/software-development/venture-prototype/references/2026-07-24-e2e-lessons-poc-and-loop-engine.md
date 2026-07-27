# E2E Lessons: POC Gate and loop_engine (2026-07-24)

## POC gate was skipped

The PentestForge riskiest assumption ("can validation layer achieve <1% FPR?") is a technical capability question. The venture-prototype skill says: technical risk → build POC first. The builder skipped it, noting "needs real LLM agents."

Fair judgment call — some technical risks can't be POC'd without real infrastructure. But the gate was not explicitly evaluated and documented. The builder should write a `poc-result.md` explaining WHY the POC was skipped, not silently skip.

## loop_engine was NOT used

We enabled it and wrote patterns in the skill. The builder ignored it — did a one-shot build. The skill said "use for complex builds" which let the builder self-assess as "simple enough."

**Fix:** skill now says MANDATORY, no exceptions. The E2E test proved the builder will skip it every time when given the choice. The "don't trust the LLM" principle means the verifier gate must run on every build, even single-file HTML.

## Phase 0 verify script pattern

The verification script (`/tmp/verify-<slug>.py`) parses `Lock D` lines from `context/*.md` and checks:
1. Prototype files exist
2. README has all 9 required sections
3. Each locked decision is referenced in README

This is the DoD in executable form. The verifier runs it. If exit != 0, the phase replans. Same as Claude Code's approach: don't let the model evaluate its own work.

## loop_engine usage across profiles

Only debugger (58 calls) and architect (14 calls) have actually used loop_engine. tech-lead, developer, qa, verifier — 0 tool calls despite having it enabled. Profiles won't use it unless explicitly instructed. A skill saying "you should" isn't enough — the kanban card body or SOUL.md needs "you must."
