# Tag Compliance Failure — E2E Test Findings (2026-07-21, v0.3 graph-backed)

## The test

Ran two E2E grill sessions with PO (glm-5.2 via zai) using `<Q>`, `<LOCK>`, and `<DONE>` tags for structured output extraction.

## What happened

### Session 1: grill-test3 (CLI startup name generator)
- **Launch**: PO used `<Q>` tags on Q1. Extraction worked.
- **Turn 2**: PO did NOT use `<Q>` tags — wrote question as inline markdown. answer.sh fell back to stderr.
- **Turn 3**: PO did NOT use `<Q>` or `<LOCK>` tags despite explicit reminders in the answer text. Zero decisions locked to graph.
- **Early surrender**: In a prior attempt (grill-test3, first try), PO wrote `<DONE>` after Q1 — one question, zero decisions.
- **Anti-surrender prompt**: Adding "NEVER write <DONE> until 8 categories covered" prevented early surrender but did NOT improve tag compliance.

### Session 2: grill-test3b (too-late-to-code CLI)
- **Launch**: 11 min to first response (provider congestion).
- **Turn 2**: PO output contained `<DONE>` → answer.sh marked grill done → zero decisions locked.
- After reopening root and retrying with stronger anti-surrender prompt: PO used `<Q>` on launch but ignored all tags on resume turns.

## Root cause

glm-5.2 does not reliably follow structured output format instructions. The `-z` launch prompt instructions compete with the `grilling` skill's natural conversational style ("Ask questions one at a time, provide your recommended answer"). The skill says nothing about tags, so PO defaults to markdown prose.

## Key finding: the grilling skill

All three Matt Pocock grill skills are the same thing:
- `grill-me` → "Run a /grilling session"
- `grill-with-docs` → "Run a /grilling session, using /domain-modeling"
- `grilling` → the ACTUAL prompt (4 sentences): interview relentlessly, one question at a time, walk the design tree, provide recommended answers.

There is no structured output, no tag format, no file protocol in the actual grill behavior. The skill is designed for interactive conversation, not structured RPC.

## Design decision: orchestrator handles structure

Since PO can't reliably output structured data:
1. PO grills in natural prose (as it naturally does)
2. The orchestrator (builder) reads PO's raw output and identifies questions/decisions
3. The orchestrator locks decisions by editing branch files
4. answer.sh handles `<Q>` extraction as a best-effort optimization (with stderr fallback)
5. No reliance on `<LOCK>` or `<DONE>` tags from PO

This makes the system work with any model grade.
