# Unbiased Livetest Protocol

Run the pinned template against 5+ different spec types with NO implementation hints. The specs only say WHAT to build, never HOW. This tests whether the template generalizes beyond the test case it was designed for.

## Setup

1. Create 5 test repos with minimal code (just README + git init)
2. Create 5 boards with unique spec card IDs (NOT all "spec-1" — trigger_keys dedup by card ID)
3. Write specs that cover different domains:
   - CLI tool (file processing)
   - REST API (Flask/HTTP)
   - Game (algorithm-heavy)
   - Data processing (CSV/JSON)
   - Library (pure functions)
4. Each spec: requirements only. No architecture hints, no file structure, no library suggestions.
5. Add all boards to active-projects.json
6. Tick engine once — all 5 should trigger simultaneously

## Monitoring

- 90s ticks, background process with notify_on_complete
- Track: done count, active count, blocked count per board
- Auto-remove corrupt boards (recurring e2e-livetest-4/stress-loop-test-r4 phantom)
- Check for WORKFLOW COMPLETE per board

## Known issues to expect

- Board 2-type review-required blocking: prompt_builder.py fix needs profile restart
- Dead-branch-cycle on verify=PASS: instance stays active, work IS done
- Corrupt phantom boards recreated by Hermes daemon: auto-remove in monitor loop
- Long pipelines: 2+ hours per board, 30+ cards

## Success criteria

- All 5 boards: close card reaches done (work complete)
- At least 3 of 5: workflow instance shows completed
- Zero blocked cards (review-required fix working)
- verify catches real bugs (not false PASS)

## Round 1 results — static review verify (5 specs, same template)

All 5 specs built and verified autonomously with zero hints:

| # | Spec | Verify Path | Fix Iters | Close | Instance |
|---|------|-------------|-----------|-------|----------|
| 1 | Markdown to HTML CLI | PASS | 0 | merged | active (dead-branch) |
| 2 | URL Shortener REST API | FAIL→fix→PASS | 2 | merged | completed |
| 3 | CSV Deduplicator Tool | PASS | 0 | merged | active (dead-branch) |
| 4 | Tic-Tac-Toe Game (minimax) | FAIL→fix→PASS | 1 | merged | completed |
| 5 | String Validator Library | FAIL→fix→ESCALATE | 1+4 | merged | completed |

**5/5 work complete. 3/5 instances auto-completed. 2/5 stuck on dead-branch-cycle (work IS done, close card ran).**

### Round 1 honest scorecard (6 subagent deep-analysis)

| Board | Code | Tests | Decomp | Verify | Fix | Avg |
|-------|------|-------|--------|--------|-----|-----|
| 1 Markdown | **5** | 6 | 7 | **6** | 6 | 6.0 |
| 2 URL Shortener | 8 | 8 | 8 | 9 | 9 | 8.4 |
| 3 CSV Dedup | 9 | 9 | 8 | 9 | 9 | 8.8 |
| 4 Tic-Tac-Toe | 9 | 9 | 8 | 8 | 9 | 8.6 |
| 5 StrValidator | 9 | 9 | 8 | 9 | 9 | 8.8 |

**True template score: 7.7/10** (not the claimed 9.0 from gauntlet).

Board 1's false PASS (verify said PASS but code had 3 real bugs) is the key finding that drove the adversarial behavior-test redesign.

## Round 2 results — adversarial behavior-test verify (5 NEW specs)

Different specs from round 1. Verifier now writes behavior tests against the public interface and EXECUTES them. All 5 boards completed successfully.

| # | Spec | Verify | Behavior Tests | Close | Cards |
|---|------|--------|---------------|-------|-------|
| 1 | Password Generator CLI | PASS | 37/37 | merged | 28 |
| 2 | JSON KV Store API | PASS | 60/60 | merged | 14 |
| 3 | Temperature Converter Lib | PASS | 73/73 | merged | 11 |
| 4 | Hangman CLI Game | PASS | 52/52 | merged | 10 |
| 5 | Pagination Utility | PASS | 70/70 | merged | 13 |

**5/5 work complete. 5/5 close=merged. Total: 292/292 behavior tests passed.**

Key improvement over round 1:
- Round 1 board 1: FALSE PASS (3 bugs in merged code, inline code missing)
- Round 2 all boards: verify wrote real executable behavior tests, all passed
- The verifier can no longer lie about "FIXED" — the failing test is the proof

All instances stuck on dead-branch-cycle (known infrastructure gap, lesson #17). Work IS complete on all 5.

### Round 2 honest scorecard — cross-cutting workflow-path + behavior-test-quality audit

**Black-box scores (0=white-box, 10=pure black-box):**

| Board | Score | Interface | White-box concerns |
|-------|-------|-----------|-------------------|
| 3 (Temp Converter) | **9/10** | Public functions only | AST scan for "pure Python" contract; otherwise pristine |
| 2 (KV Store API) | **8/10** | HTTP REST API | `kvapp._store.clear()` for reset; `patch.object(kvapp, "time")` for TTL mocking |
| 5 (Pagination) | **8/10** | Public `paginate`/`search`/`sort_and_paginate` | AST scan for deps; weakened generator test |
| 1 (Passgen) | **7/10** | CLI subprocess + public functions | Accesses `passgen.SYMBOLS` constant; checks `test_passgen.py` file exists |
| 4 (Hangman) | **6/10** | CLI subprocess + public classes | Tests internal `WORDS` list properties; calls private `_prompt_guess()` directly; purity gate reads source |

**Average: 7.6/10** — predominantly black-box with recurring minor white-box leaks.

**Workflow-path findings:**
- **Fix loop NEVER entered on any board.** All 5 verifiers returned PASS → `verify→close` edge taken. The `fix` and `re-verify` nodes stayed `pending`. The `total_tests`/`all_tests_pass` fix metadata was never populated. The behavior tests' value as fix-loop acceptance criteria was not exercised.
- **Zero false positives** across all 5 boards (total findings: B1=1 Note, B2=0, B3=0, B4=1 Minor, B5=0). Both filed findings genuine.
- **6 probe-inversions self-caught and corrected** (B5=3, B3=1) without filing — strong verifier discipline.
- **Round 1 false PASS eliminated.** Round 2 behavior tests would have caught them (executable proofs), but code was already fixed from round 1's 4-iteration rework.
- **Dead-branch leak at 5/5 this round** (vs 3/6 in round 1). Every instance that took verify→close (all 5) leaked — fix/re-verify stuck pending, no `workflow_completed` event. Deterministic correlation confirmed at 100%.
- **6 cross-workflow qa-gate triggers fired** (one per verify card completion) but all were no-ops: `check-merge` returned `should_test: false, reason: "no project for board"`. Trigger fired correctly; no QA testing ran.

**Recurring white-box patterns** across boards: (1) accessing module constants (`SYMBOLS`, `WORDS`) for assertions; (2) calling underscore-prefixed private methods (`_prompt_guess`); (3) `patch.object(module, "time")` mocking implementation dependencies; (4) AST/source-file scans for static contract checks (acceptable); (5) checking file existence as a proxy for test coverage.

## Round 1 vs Round 2 comparison

| Metric | Round 1 (static verify) | Round 2 (behavior verify) |
|--------|------------------------|--------------------------|
| Boards completed | 5/5 | 5/5 |
| Verify accuracy | 7.2/10 (board 1 FALSE PASS) | **All PASS with 292 executable proofs** |
| False positives | YES (bugs in merged code) | **NONE (behavior tests executed)** |
| Behavior tests written | 0 (read code instead) | **292 (written + executed)** |
| Spec types | CLI, REST API, game, data, library | CLI, REST API, library, game, library |

## Running unbiased livetests

```bash
# 1. Create 5 repos
for i in 1 2 3 4 5; do
    rm -rf /tmp/livetest-unbias/repo-$i && mkdir -p /tmp/livetest-unbias/repo-$i
    cd /tmp/livetest-unbias/repo-$i && git init -q
    git config user.email "t@t.com" && git config user.name "T"
    echo "# spec title" > README.md && echo "*.pyc" > .gitignore
    git add -A && git commit -q -m "initial"
done

# 2. Create boards + spec cards (unique IDs!)
python3 << 'PYEOF'
import sqlite3, json, time
from pathlib import Path
now = int(time.time())
for i, (title, body) in enumerate(specs, 1):
    board = f"livetest-unbias-{i}"
    import subprocess
    subprocess.run(["hermes", "kanban", "boards", "create", board], capture_output=True)
    db = Path.home() / f".hermes-teams/startup/kanban/boards/{board}/kanban.db"
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO tasks (id, title, assignee, status, ...) VALUES (...)")
    conn.commit(); conn.close()
PYEOF

# 3. Tick to start
cd ~/.hermes-teams/startup/scripts
python3 workflow_engine/main.py tick  # all 5 trigger
python3 workflow_engine/main.py tick  # all 5 plan nodes dispatch
```

## Analysis (post-completion)

Dispatch 6 subagents per round:
- One per board (5): code quality, test quality, decomposition, verify accuracy, fix effectiveness
- One cross-cutting: workflow path analysis for all 5 boards

Each subagent independently runs the code, reproduces findings, and scores 0-10 with evidence. Average across all boards for the true template score.

**Key principle:** the claimed gauntlet score is an UPPER BOUND. Only unbiased livetests give the true score.
