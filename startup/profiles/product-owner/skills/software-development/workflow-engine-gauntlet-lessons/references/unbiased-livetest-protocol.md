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

## Round 6 results (5 unbiased tests)

All 5 specs built and verified autonomously with zero hints:

| # | Spec | Verify Path | Fix Iters | Close | Instance |
|---|------|-------------|-----------|-------|----------|
| 1 | Markdown to HTML CLI | PASS | 0 | merged | active (dead-branch) |
| 2 | URL Shortener REST API | FAIL→fix→PASS | 2 | merged | completed |
| 3 | CSV Deduplicator Tool | PASS | 0 | merged | active (dead-branch) |
| 4 | Tic-Tac-Toe Game (minimax) | FAIL→fix→PASS | 1 | merged | completed |
| 5 | String Validator Library | FAIL→fix→ESCALATE | 1+4 | merged | completed |

**5/5 work complete. 3/5 instances auto-completed. 2/5 stuck on dead-branch-cycle (work IS done, close card ran).**

Verify caught real bugs: CRLF injection (URL Shortener), production-mode missing db.create_all (Tic-Tac-Toe), test coverage gaps (String Validator). No false PASS results — production_mode_tested=True enforced via schema.
