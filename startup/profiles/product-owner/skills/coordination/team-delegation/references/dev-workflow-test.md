# Dev Workflow End-to-End Test — Case Study

**Date:** 2026-07-04 · **Board:** `startup` · **Model:** GLM 5.2 (Z.AI) · **Profiles:** product-owner, tech-lead, reviewer

## What was tested

A full spec → build → review dependency chain on the `startup` kanban board. The project: a
small but real time-tracker CLI (`tt`) in Python — single-file, stdlib only, with tests and
README. Chosen because it exercises real engineering (file I/O, data persistence, edge cases,
test writing, adversarial review) without external API dependencies.

## Pipeline structure

Three tasks, each a child of the one before (via `kanban_create parents=[...]`):

| # | Task title | Assignee | Purpose |
|---|-----------|----------|---------|
| 1 | `[tt] SPEC: Define acceptance criteria & architecture` | product-owner | Write spec (user stories, CLI interface, data model, 16 ACs, 11 edge cases) |
| 2 | `[tt] BUILD: Implement time-tracker CLI` | tech-lead | Implement from spec: tt.py + tests + README |
| 3 | `[tt] REVIEW: Code review of implementation` | reviewer | Adversarial review against spec + build task |

Auto-promotion worked flawlessly: each child sat in `todo` until its parent hit `done`,
then promoted to `ready`, then the dispatcher claimed and spawned a worker within ~30s.

## Timings

| Stage | Duration | Notes |
|-------|----------|-------|
| Spec (product-owner) | ~2 min | Written as a kanban comment + structured metadata |
| Build (tech-lead) | 7m 34s | 328-line tt.py + 48 pytest tests + README. Hit 3 test failures (capsys accumulation), diagnosed and fixed. Wrote own validation script (22/22 ACs). |
| Review (reviewer) | 7m 06s | Independent verification: re-ran pytest, wrote own AC suite, AST import audit, 12 adversarial probes. Found 5 minor/nit issues. Verdict: PASS. |
| **Total wall clock** | **~16 min** | |

## Key observations

### Dependency chain reliability
Zero manual intervention needed for promotion. The exact sequence:
`created (todo)` → parent `done` → `promoted` (ready) → `claimed` (running) → heartbeats every ~60s → `completed` (done).

### Reviewer independence (the strongest signal)
The reviewer did NOT trust the developer's claims. It:
1. Re-ran the full pytest suite independently (48/48 confirmed)
2. Wrote 4 separate verification scripts: `check_imports.py` (AST stdlib audit),
   `run_ac_tests.py` (subprocess-based AC suite), `adversarial_probes.py` (12 edge attacks),
   `verify_findings.py` (reproduced each filed finding)
3. Found 5 issues the developer missed:
   - Valid-JSON-with-wrong-types crashes (4 cases: sessions=string, active=string, missing key, next_id=string)
   - `summary --task ""` skips filtering (falsy check instead of `is not None`)
   - Dead `timezone` import
   - Empty task name accepted silently
   - Non-atomic load→modify→save (no file locking)
4. Correctly assessed severity against the spec — noted the spec defines "corrupt JSON" narrowly
   (parse errors only), so the wrong-type crashes are beyond-spec robustness gaps, not spec violations.

This is the right behavior for a quality gate. The `adversarial-review` skill the reviewer
loaded drives this: "execute first, static-only claims are disqualified."

### Pre-flight gotchas discovered
Before the pipeline could run, two profiles needed fixes:
1. **Reviewer gateway not installed** — `hermes gateway install --profile reviewer` + `start`.
   Without this, the dispatcher cannot spawn a worker for the profile.
2. **`pi` (v0.80.3) on volatile path** — only reachable via fnm session shim
   (`/run/user/1000/fnm_multishells/<session>/bin/pi`). Created stable wrapper at `~/.local/bin/pi`.
3. **`zz` fish-only** — defined as a fish function wrapping `zlaude`. Created bash wrapper at
   `~/.local/bin/zz` so headless workers (which run bash) can find it.

### Harness setup verified
- All profiles: `approvals.mode: smart`, terminal/file/code_execution enabled
- `command_allowlist` includes script execution
- Terminal backend: local (not docker/ssh)
- GLM 5.2 via Z.AI configured on all profiles

## Monitoring commands used

```bash
hermes kanban --board startup list                    # board overview (✓/●/▶/◻ icons)
hermes kanban --board startup log t_c57ac51a          # full execution trace (every tool call, diff, terminal output)
hermes kanban --board startup log t_c57ac51a --tail 3000  # last N bytes of log
hermes kanban --board startup tail t_0b526ee8         # live-follow a running task
hermes kanban --board startup show t_0b526ee8         # body + comments + events + run metadata
hermes kanban --board startup runs t_c57ac51a --json  # structured run data (durations, test counts, metadata dict)
hermes kanban --board startup watch                   # board-wide real-time event stream
hermes kanban --board startup stats                   # per-status + per-assignee counts
```

## Workspace artifacts

Build task workspace: `~/.hermes-teams/startup/kanban/boards/startup/workspaces/t_c57ac51a/`
- `tt.py` (328 lines, 9.4 KB)
- `tests/test_tt.py` (441 lines, 48 tests across 8 classes)
- `README.md` (3.1 KB)

Review task workspace: `~/.hermes-teams/startup/kanban/boards/startup/workspaces/t_0b526ee8/`
- `check_imports.py` — AST-based stdlib verification
- `run_ac_tests.py` — independent subprocess-based acceptance test suite
- `adversarial_probes.py` — 12 edge-case probes
- `verify_findings.py` — reproductions for each filed finding
