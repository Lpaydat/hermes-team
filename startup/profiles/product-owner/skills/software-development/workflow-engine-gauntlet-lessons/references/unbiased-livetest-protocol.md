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

Different specs from round 1. Verifier now writes behavior tests against the public interface and EXECUTES them.

| # | Spec | Verify Path | Work Status | Cards |
|---|------|-------------|-------------|-------|
| 1 | Password Generator CLI | WIP (review-required block) | 12 done, running |
| 2 | JSON KV Store API | DONE | 14 done |
| 3 | Temperature Converter Lib | DONE | 11 done |
| 4 | Hangman CLI Game | DONE | 10 done |
| 5 | Pagination Utility | DONE | 13 done |

**4/5 work complete.** Board 1 stuck on review-required blocking again (prompt_builder fix needs profile restart).

The adversarial behavior-test template changes the verify approach:
- Verifier writes behavior tests mapping every spec requirement → executable test
- Tests go through the public interface (CLI stdin/stdout, HTTP, public functions)
- Tests are black-box: survive refactors, don't test implementation details
- Fix must pass ALL tests including verifier's behavior tests
- Re-verify writes NEW attack vectors on top of re-running old tests

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
