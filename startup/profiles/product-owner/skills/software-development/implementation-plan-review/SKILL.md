---
name: implementation-plan-review
description: "Review a multi-ticket implementation plan or decomposition against the actual codebase BEFORE execution — verify scope realism, confirm blocking edges by reading the exact functions/queries/structs each ticket touches, assess cross-ticket blast radius (migration collisions, shared-file conflicts), and find prefactoring opportunities. Use when asked to 'review the tickets', 'sanity-check the plan', 'is this decomposition realistic?', 'what's the blast radius?', or 'does the architecture need restructuring for these features?'. Complements dev-planning (produces plans) and scrutinize (single-artifact review) by focusing on multi-unit decomposition review against real code."
---

# Implementation Plan Review

Review a decomposition (set of tickets/units with dependency edges) against the
actual codebase. The goal: catch scope errors, wrong blocking edges, hidden
blast radius, and prefactoring opportunities BEFORE implementation starts —
when fixes are cheap.

## When to load

- A plan/decomposition exists (IMPLEMENTATION-PLAN.md, ticket list, spec with
  build units) and someone asks "is this realistic?"
- Before fanning out tickets to developers — the last sanity gate.
- After a decomposition but before execution, when cross-ticket interactions
  haven't been checked against real code.

## Operating stance

- **Code-grounded, not doc-grounded.** The plan doc describes intent. Your job
  is to verify that intent against what the code actually does. Read the SPECIFIC
  function, query, struct, or migration each ticket modifies — not module-level
  overviews. Blast radius lives in the details.
- **Per-ticket + cross-cutting.** Review each unit individually AND scan for
  interactions between units (shared files, migration collisions, trait changes
  that ripple).
- **Architecture-fit first.** Before line-by-line, answer: does the existing
  extension mechanism (trait, plugin, phase pipeline, migration system) handle
  these features, or does it need restructuring? This is the highest-value
  finding.

## Workflow

### 1. Verify the baseline

Build the project. Run the tests. Record the count (e.g. "574/575 green"). If
the baseline is broken, blast-radius assessment is unreliable — flag it and
note which failures are environmental vs code defects. A green baseline is your
reference point for "what does this change break?"

### 2. Map the decomposition

Read the plan/decomposition doc. For each unit, extract:
- **What it claims to do** (one sentence).
- **Its stated dependencies** (blocking edges).
- **The files/modules it says it will touch.**

Build a mental (or written) dependency graph. Note which tracks are claimed as
"parallel / independent."

### 3. Drill into exact code per ticket

For EACH ticket, read the specific code it modifies — not the module doc. This
is where hidden scope and wrong edges surface:

- **SQL queries:** Does the query select the columns the ticket needs?
  (Example: a "max_runtime" ticket needs `started_at` in the running-runs query,
  but the query doesn't select it → hidden schema-read gap.)
- **Struct definitions:** Does the struct have the fields the ticket assumes?
  (Example: ticket says "check started_at" but `RunningRun` has no such field.)
- **Trait signatures:** Does the change fit the existing interface, or does it
  require a trait change that ripples to all implementors?
- **Migration files:** What's the current schema version? What does the ticket
  assume? Are migration numbers assigned at plan-time (collision risk across
  parallel tracks) or merge-time?
- **Function bodies:** Does the existing logic do what the ticket claims it will
  extend? Is there dead code in the module the ticket plans to reuse?

### 4. Assess cross-ticket interactions

Scan for interactions invisible at the single-ticket level:

- **Migration numbering collisions:** If two independent tracks each claim
  migration numbers, they collide when built in parallel. Fix: assign numbers at
  merge time, or serialize tracks.
- **Shared-file conflicts:** Multiple tickets modifying the same function
  (e.g. `build_spawn_env`) create merge conflicts. Prefactor by extracting a
  shared helper first.
- **Prefactoring that unblocks multiple tickets:** A trait unification or helper
  extraction done once can serve several tickets. Surface it as a standalone
  pre-step.
- **Dead code to clean before reuse:** Modules with unused functions (build
  warnings) that a ticket plans to extend — clean first to avoid confusion.
- **Architectural restructuring vs extension:** Does the core extension point
  (tick pipeline, plugin system, trait) support the new features as additive
  insertions, or does it need restructuring? Most well-designed systems support
  additive extension — confirm by checking the trait signature and wiring point.

### 5. Report

Structure the output for a decision-maker who needs to fan out tickets:

**Executive summary** (3-5 sentences): how many tickets are ready as-specified,
how many need adjustment, and whether the core architecture needs restructuring.

**Tick/architecture assessment** (if applicable): does the extension mechanism
handle the new features? What's the minimal change needed? Propose the new
ordering if phases/nodes are added.

**Per-ticket findings:** For each unit — scope realistic? blocking edges
correct? blast radius (small/medium/large/zero)? prefactoring recommendation?

**Cross-cutting findings:** migration collisions, shared-file conflicts,
prefactoring opportunities, dead code.

**Summary table:** ticket | scope OK? | blocking edges | blast radius | prefactor?

Close with a verdict: how many ready, how many need work, and the single
biggest risk.

## Key principles

- **Cite file:line for every claim.** "The query doesn't select started_at
  (crash_detect.rs:198)" is a finding. "Might need schema changes" is hand-wave.
- **Distinguish "ticket says X" from "code confirms/refutes X."** The plan's
  claims and your verification are different — keep them separate.
- **Blast radius is about ripple, not line count.** A 3-line trait signature
  change has large blast radius (all implementors). A 200-line new file has zero.
- **Prefactoring is the highest-leverage output.** Finding a helper extraction
  or trait unification that unblocks 3 tickets is worth more than 10 line-level
  nits.
- **Verify the stated dependencies.** A ticket that claims "depends on nothing"
  but actually modifies a function another ticket also touches has a hidden
  dependency. Read the code both tickets touch.

## Reference

- [references/ngin-16-ticket-review.md](references/ngin-16-ticket-review.md) —
  worked example: reviewing 16 implementation units for a Rust daemon against
  the actual codebase. Demonstrates drilling into exact queries/structs,
  finding migration collisions, assessing tick-pipeline restructuring, and
  surfacing prefactoring opportunities.
