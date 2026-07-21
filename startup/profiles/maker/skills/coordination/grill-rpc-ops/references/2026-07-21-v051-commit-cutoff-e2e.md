# v0.5.1 E2E — Commit Cutoff Grill (2026-07-21)

## Setup
- Idea: "A CLI tool that blocks git commits after a configurable cutoff time"
- Skill loaded: grill-rpc (our own, not grill-with-docs)
- Model: glm-5.2 via zai

## Results
- 9 questions across 8 branches
- 20 decisions locked (D1-D20)
- 2 contradictions caught by PO:
  1. JSON config vs zero-dependencies bash (D9 vs D8) → resolved: plain text file
  2. Hard block vs --no-verify (D4 vs D13) → resolved: advisory, not enforcement
- Grill completed naturally — PO declared spec ready for tickets

## What v0.5 improvements confirmed

### grill-rpc skill
PO loaded it, understood branch structure immediately. Protocol instructions in system context (via skill) are stronger than -z prompt. PO asked structured questions with recommended answers.

### Auto decision-locking
Builder wrote `Lock D{n}: title = content` in answers. answer.sh extracted via `grep -iE 'Lock D[0-9]+:'` and inserted under `## Decisions` in branch files. Worked after the v0.5.1 fix (removed `^` anchor, changed insertion method).

### No-tag-tolerant extraction
PO used `<Q>` tags ~40% of the time. Fallback (last paragraph with `?`) caught the rest. No more stderr-dump failures from missing tags.

### Auto _state.md updates
Decision counts updated after every turn. Minor overcount (LOCKs in Q&A log section also counted) but functional.

## Bugs found and fixed

1. **LOCK grep anchor** — `^Lock` didn't match indented lines in heredoc input. Fix: removed `^` anchor.
2. **LOCK insertion location** — LOCKs appended to EOF instead of under `## Decisions`. Fix: temp-file rewrite that inserts after `## Decisions` header.
3. **_state.md count pattern** — counted `^D[0-9]` but LOCKs stored as `Lock D{n}:`. Fix: `grep -ic '^Lock D[0-9]\|^D[0-9]'`.
4. **Fallback question fragments** — when PO output has multiple `?`, fallback sometimes grabs fragments. Not fully resolved — the orchestrator can read the full output when this happens.

## Branch coverage
- Product (7): CLI command, JSON→plaintext config, single-sentence output, sleep cost metric, deliberate action, work-life motivation, no override
- User (0): covered by product branch answers
- Mechanism (3): bash script, plain text config, git hook installation
- Data (0): trivially simple (reads one file)
- Edges (3): plain text config, no-config=do-nothing, --no-verify accepted
- Output (2): plain text block message, stderr+exit 1
- Deployment (2): manual copy to .git/hooks, single bash script
- Constraints (3): advisory only, any bash+git system, zero dependencies

## Key insight
The branch model works. PO stayed on topic, didn't re-ask resolved questions, and caught real design contradictions. The grill produced a buildable spec in ~30 minutes of wall time.
