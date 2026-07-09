# QA Swarm End-to-End Test Postmortem (2026-07-09)

First real test of the QA swarm protocol against cross-browser-ai MVP. Two approaches tested (Option A: CLI, Option B: plugin), three test runs total.

## Test 1 — Option A (CLI), unmodified skills

**Result: all 4 workers crashed immediately, twice each.**

Root causes:
1. **Skill name bracket bug** — the skill used `[:qa-functional]` bracket notation. The CLI parser (`parse_worker_arg`) splits on `:` and captured the literal `]` in the skill name → `qa-functional]` → agent crash on startup (skill not found)
2. **Hardcoded platform skills** — `kanban_swarm.py` creates verifier with `skills=["requesting-code-review"]` and synthesizer with `skills=["humanizer"]`. Neither exists on the QA profile → crash

Fixes applied:
- Changed skill syntax from `[:qa-functional]` to `:qa-functional` (colon-separated, no brackets)
- Installed stub versions of `requesting-code-review` and `humanizer` on the QA profile that redirect to QA verifier/synthesizer roles
- Did NOT edit platform source (`kanban_swarm.py`) — reverted immediately. Platform source is overwritten on `hermes update`.

## Test 2 — Option A (CLI), fixes applied

**Result: all 4 workers completed successfully. ~20 min per worker.**

Worker findings:
- Functional: 10 claims, 4 proven, 5 disproven, 1 untested. P0: results page 404.
- Journeys: 8 journeys, 3 proven, 3 disproven, 2 blocked by demo mode.
- Security: 28 checks, 25 passed, 5 findings. P1: SSRF via /api/test.
- Exploratory: 5 charters, 7 findings. P1: rate limit bypass via X-Forwarded-For.

**Problem: card bodies were generic boilerplate.** Workers had to read a shared blackboard blob to find their assignment, container details, and port. The orchestrator wrote a good blackboard, but nothing guaranteed it.

## Test 3 — Option B (Plugin), `qa_swarm` tool

**Result: all 4 workers completed successfully. ~10-17 min per worker. Zero crashes.**

Worker card bodies were tailored with specific checklists:
```
TEST CHECKLIST (prove each claim with real evidence):
1. LANDING PAGE — GET /
   - HTTP 200?
   - Headline present?
   - URL input field present?
...
CONTAINER SETUP:
podman run -d --name qa-w1-func -p 18081:3000 -e DEMO_MODE=true localhost/qa-test:t_af9675ed
```

Workers started testing immediately — no blackboard parsing needed. Faster, deeper, same quality findings.

## Option A vs Option B comparison

| Metric | Option A (CLI) | Option B (Plugin) |
|---|---|---|
| Worker crashes (test 1) | 8 (bracket bug) | 0 |
| Card body quality | Generic boilerplate | Tailored checklist |
| Worker self-sufficiency | Parse blackboard for assignment | Knew exactly what to test |
| Port allocation | Manual (blackboard) | Auto-allocated, baked in |
| Container command | Not in card body | Full podman run command in body |
| Skill names | Error-prone (CLI syntax) | Structured param, no brackets |
| Total findings | 18 | 19 |
| Test time per worker | ~20 min | ~10-17 min |

**Verdict: Option B (plugin) is better.** Faster, more reliable, tailored content. The plugin is the recommended approach. Fall back to CLI only if the plugin isn't loaded.

## Finding routing gap discovered

The synthesizer filed P1 findings directly to `developer` as plain kanban cards. Developer fixed them and marked `done` — but **no verifier checked the fixes**. This bypasses the dev→verifier→merge pipeline invariant.

**Fix:** QA findings must go to `tech-lead` (not `developer`). The tech-lead triages and uses `kanban_delegate` to create a dev+verifier pair, matching the normal pipeline:
```
QA finding → tech-lead → kanban_delegate → developer + verifier → merge → QA re-test
```

## What worked well

- Swarm topology (root + workers + verifier + synthesizer) created correctly by both approaches
- Blackboard pattern for evidence sharing worked — workers posted structured JSON, synthesizer read it
- Container isolation worked — each worker started its own Podman container on a unique port
- Heartbeats worked — workers sent heartbeats every ~60s during long operations
- Auto-promotion worked — orchestrator blocked on synthesizer, auto-promoted when it completed
- Real findings produced — P0 results-404, P1 SSRF, P1 rate limit bypass, all with curl reproduction evidence
- The P0 found in test 2 was FIXED by the developer before test 3 — the pipeline caught a real bug and it got fixed

## Platform constraints confirmed

- `kanban_swarm.py` hardcodes `requesting-code-review` and `humanizer` skills for verifier/synthesizer
- `max_in_progress_per_profile` needs gateway restart to take effect
- The dispatcher lock is held by the venture-builder gateway (PID 926), not the QA gateway
- `auto_decompose` can be `false` in root config but still active if the holding gateway started before the change
- Platform source edits are overwritten on `hermes update` — work around at profile level only
