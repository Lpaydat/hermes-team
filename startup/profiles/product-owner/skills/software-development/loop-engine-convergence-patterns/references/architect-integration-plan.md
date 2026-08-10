# Architect Gate — Implementation (commit `14a9cda`, branch `architect-gate-wiring`)

The architect now runs BEFORE decomposition for all feature specs. Three changes to dev-dispatch.json wired the architect into the default pipeline path.

## What Changed

### Routing (edges)

**Before:**
```
entry → route-architect     [type == 'architecture']     ← DEAD ROUTE, nobody set this type
entry → route-decompose     [catch-all default]          ← features bypassed architect
```

**After:**
```
entry → route-bug           [type == 'bug']
entry → route-scout         [type == 'research']
entry → route-ops           [type == 'ops']
entry → route-tickets       [type == 'tickets']           ← pre-made tickets still skip the gate
entry → route-architect     [NOT bug/research/ops/tickets] ← DEFAULT now hits the gate
route-architect → route-decompose  [unconditional]         ← after stamp, decompose always fires
```

### route-architect Node

Rewritten from a vague "weigh alternatives, record an ADR" body to:

- **Profile:** `architect` (unchanged)
- **Skill:** `architecture-gate` (NEW — force-loads the T0-T3 triage rubric, paved-road stack, spec-authorship split)
- **Body:** reads spec from `${trigger.card_body}`, runs five-question blast-radius triage, decides tech stack, stamps `Implementation Decisions` + `Testing Decisions` sections into spec file on disk
- **Title template:** `[architect] ${trigger.title}`
- **Output schema:** `{verdict, tier, artifacts, approval, spec_file, tech_stack, testing_decisions}`
- **T2/T3 escalation:** block with `escalated-t2:` or `T3 handback-wayfinder:`

### route-decompose Node

Untouched. It already reads the spec, which now has architecture sections stamped in by the architect.

### route-tickets Path

Preserved. Pre-made tickets (`type=tickets`) still route directly from entry, skipping the architect gate.

## How It Works

```
PO writes spec card (product sections: problem, solution, user stories)
  │
  ▼
route-architect fires
  architect reads spec from card_body (works because CardInfo.body was fixed)
  runs T0-T3 blast-radius triage:
    T0: wave through (no artifact, stamp only)
    T1: one ADR + paved-road stack stamp
    T2: full design doc + human approval (blocks card)
    T3: hand back for wayfinder decomposition (blocks card)
  stamps Implementation Decisions + Testing Decisions into spec file
  completes with {verdict: "stamped", tier, artifacts, approval, spec_file, tech_stack}
  │
  ▼
route-decompose fires (unconditional edge)
  PO reads SAME spec (now has architecture sections)
  decomposes into tickets that inherit tech stack + structure decisions
  │
  ▼
[ticket-NN] cards created → tech-lead-execute fires per ticket
```

The spec file on disk is the handoff mechanism — architect edits it surgically, decompose reads the stamped version.

## The architecture-gate Skill (Already Built)

Located at `profiles/architect/skills/architecture/architecture-gate/SKILL.md`. Key capabilities:

- **T0-T3 triage rubric**: 5 mechanical questions (interface change? data model? new dep? cross-team? security?). All no → T0 (wave through). Any yes → T1 floor. Wide blast radius → T2/T3.
- **Paved road stack**: Python, pytest, JSON/sqlite. No justification needed. Deviations must be justified in an ADR.
- **Spec-authorship split**: PO owns Problem/Solution/User Stories. Architect owns Implementation Decisions + Testing Decisions. Surgical edits only — never rewrite the whole file.
- **Completion contract**: `{tier: "T0|T1|T2", artifacts: ["ADR-001"], approval: "waved-through|adr-recorded|human-approved"}`

## Pipeline Ordering

```
idea → features → constraints → tech stack → architecture → scaffold → plan → dev
```

Constraints (platform, scale, team, budget) shape the tech stack. The architect decides tech stack + structure. Scaffold/setup consumes the architecture output. You cannot scaffold without knowing the stack, and you can't know the stack without architecture review.

Architect integration is a PREREQUISITE for the preparation/setup step.

## Livetest Results (PASSED)

Livetested on board `arch-test` with a "Bookmark Manager CLI" spec (6 user stories, local file storage).

**Architect output:**
- Triaged as **T1** (feature): 2 yes (interface change — new CLI contract; data-model change — new persisted entity), 3 no
- Produced **ADR-001** (file-based JSON store on the paved road; sqlite deferred)
- Stamped `SPEC.md` at `/tmp/arch-test-repo/SPEC.md` with Implementation Decisions (Python 3, argparse, JSON storage, data model, CLI surface, title fetch strategy) and Testing Decisions (pytest, offline, stubbed network)
- Appended stamp line: `Architecture: reviewed by architect — tier T1, 2026-08-07, gate card t_f4ac8d23`
- Product sections left byte-for-byte identical (spec-authorship split respected)

**Decomposition output:**
- loop_engine converged (1 iteration)
- 5 tickets created: ticket-01 (add+scaffold), ticket-02 (list), ticket-03 (search), ticket-04 (delete), ticket-05 (tag)
- Tickets INHERITED architect's decisions: `bookmarks.json` storage, argparse subcommands (`bm add <url>`), monotonic integer IDs, atomic write (temp + os.replace), isolated title fetcher with stub seam

**Full chain proven:** `[spec] → [architect] (T1, ADR-001, SPEC.md stamped) → [decompose] (5 tickets) → [ticket-01..05] → tech-lead-execute fires`

### Pitfall: `adrs` vs `artifacts` metadata key

The architect noted during livetest: `kanban_complete` path-validates any `artifacts` key and rejects ADR-ID values like `"ADR-001"` that the gate contract specifies. The architect worked around this by using `adrs` as the metadata key instead. If you see the architect's metadata with `adrs` instead of `artifacts`, this is why — it's a kanban tool validation constraint, not an architect skill bug.

## Verification (20/20 checks passed)

Ad-hoc verification confirmed:
- Template loads with 7 nodes
- route-architect has skill=architecture-gate, title_template, blast-radius + paved-road in body
- Output schema has tier, tech_stack, spec_file fields
- Edge routing: entry→route-architect (default), route-architect→route-decompose (unconditional), route-tickets preserved, direct decompose removed
- route-decompose unchanged (profile=product-owner, loop_engine body intact)
- 113 engine tests pass (0 regressions)
