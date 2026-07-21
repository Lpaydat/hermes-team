# E2E Test Findings — 2026-07-21

## Session 1: GitHub Sentence Grill (8 questions, 14 decisions)

**Idea**: A web page that shows your GitHub contributions as a single sentence.

**Result**: Complete design spec produced in ~45 minutes. 14 decisions locked (D1-D14). SUMMARY.md and CONTEXT.md written by PO. Full DONE.flag cycle achieved.

**What worked**:
- Session tracking (after fixing via SESSION.key)
- `<Q>` tag extraction (after PO was explicitly prompted)
- PO found a real contradiction: D3 said "no OAuth" but D4's math assumed authenticated API (5000 req/hour)
- PO verified claims against live data (scraped torvalds' profile to validate language extraction claim)
- Progress steps UX (skeleton screen + fake progress) accepted as a design decision

**Bugs found and fixed**:
1. SESSION.key capture — PO wrote made-up SESSION_ID. Fixed by capturing the real session key from `hermes sessions list`.
2. PO writes inline ~40% instead of to QUESTION.md — Fixed by switching to `<Q>` tag extraction. PO never needs to write to a file.
3. PO re-asks resolved decisions — Mitigated by pushing back with "Already answered — see D{N}."

**Speed**: PO (glm-5.2 via zai) averaged 60-200s per resume turn. Total ~45 min for 8 questions.

## Session 2: CLI Startup Name Generator (aborted at Q2)

**Idea**: A CLI tool that generates a random startup name and tagline.

**Result**: Aborted after Q2 — PO took >12 min on the first resume without finishing.

**Issue**: zai provider congestion or rate limiting. Same PO config as session 1 but nearly 10x slower.

**Lesson**: Provider performance varies across sessions. If a resume takes >10 min, kill and retry. Not a skill bug.

## `<Q>` Tag Extraction Tests

The perl extraction regex:
```perl
perl -0777 -ne 'if (/<Q>\s*(.*?)\s*<\/Q>/s) { print $1 }'
```

Results (7/7 pass):
- Simple question in tags ✓
- Multi-line question ✓
- Question with surrounding text before/after tags ✓
- Whitespace-gapped tags ✓
- No tags present — returns empty ✓
- Multiple Q tags — returns first only ✓
- Empty content between tags — returns empty ✓

## Key File Locations

- Skill: `~/.hermes-teams/shared-skills/self-grill/`
- answer.sh: `~/.hermes-teams/shared-skills/self-grill/scripts/answer.sh`
- Operational playbook: `~/.hermes-teams/startup/profiles/builder/skills/coordination/grill-rpc-ops/`
- PO grill skill: `~/.hermes-teams/startup/profiles/product-owner/skills/mattpocock/grill-with-docs/`
