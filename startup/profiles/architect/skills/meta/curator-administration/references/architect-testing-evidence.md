# Architect Gate — Testing Evidence

The architect profile and its gate ceremony were built by Claude Code in a
7-ticket pipeline (`hermes-teams-1y1.1` through `1y1.7`) and then live-tested
with 6 edge-case drills on isolated kanban boards.

## The 7 capabilities (tracer beads)

| Bead | What it built |
|------|--------------|
| 1y1.1 | Architect profile (dispatch + intercom) |
| 1y1.2 | ADR convention (create, supersede, chain A→B→C) |
| 1y1.3 | Architecture routing (questions → ADR or escalate) |
| 1y1.4 | Architecture gate (T0–T3 blast-radius triage) |
| 1y1.5 | T2 ceremony (design-it-twice fan-out + human approval) |
| 1y1.6 | Conformance lens (ADR checking) |
| 1y1.7 | Brownfield intake (existing codebase adoption) |

## The 6 edge-case drills (all live, durable-state observed)

| Edge | Board | Result | Defects found |
|------|-------|--------|---------------|
| T2 human REJECTS (safety critical) | test41-t2-reject | ✅ Rejection re-blocked gate — can't silently open | none |
| Routing escalation (anti-hallucination) | test42-route-escalate | ✅ Escalated, fabricated no ADR | none |
| ADR supersession chain A→B→C | (in 1y1.2 board) | ✅ Middle ADR byte-stable, chain resolves | none |
| Brownfield idempotent re-inventory | test43-brownfield-idem | ✅ Second run added nothing | none |
| Conformance no-op / multi-violation | test39-conf-edge | ✅ Substance passes | 1 fixed (token mismatch) |
| Gate T3 / paved-road / multi-yes | test40-gate-edge | ✅ Pass | 1 fixed (metadata seam) |

## Test boards still on disk

```
~/.hermes-teams/startup/kanban/boards/
  test32-architect/          kanban.db
  test34-conformance/        kanban.db
  test35-routing/            kanban.db
  test36-brownfield/         kanban.db
  test37-gate/               kanban.db
  test38-t2/                 kanban.db
  test39-conf-edge/          kanban.db
  test40-gate-edge/          kanban.db
  test41-t2-reject/          kanban.db
  test42-route-escalate/     kanban.db
  test43-brownfield-idem/    kanban.db
```

These are durable evidence — query them with `kanban_list` (set the board slug)
to inspect the run history, card states, and metadata that the drills asserted.

## Two defects found during testing (both fixed in commit 886361b)

### 1. Blocked verdicts can't carry structured metadata

`hermes kanban block` has no `--metadata` param — only `kanban_complete` does.
So T3 and T2-at-escalation (which block the card) can only carry their
disposition in the block reason/summary as prose, not structured metadata.
The gate skill's completion contract was corrected to reflect this honest
seam: done-completions (T0/T1, T2-after-approval) carry structured metadata;
blocked verdicts carry a parseable summary prefix (`T3 handback-wayfinder:`).

### 2. Conformance no-op token mismatch

The conformance lens stamped `"no docs/adr/"` (prose) but the contract
specified the token `"no-docs-adr"`. Fixed to match the contract token.

## Source conversation

The build-and-test session is at:
```
~/.claude/projects/-home-lpaydat--hermes-teams/ba9243c7-9056-4872-93c6-810df32eb4df.jsonl
```

Session ID: `ba9243c7` (6.2 MB). The user asked "did you run the live tests
and observe yet?" at approximately line 2378; the full edge-case matrix
concludes at approximately line 2634.

See `references/claude-code-session-mining.md` for how to parse these files.

> **Note:** This reference is filed under `curator-administration` rather than
> `architecture-gate` because the gate skill is pinned and blocks autonomous
> writes. The content belongs conceptually to the gate — when the pin is
> lifted, move it there.
