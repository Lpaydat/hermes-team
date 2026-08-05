---
name: project-kickoff
description: "The PO's playbook for new projects — routes to the two-part kickoff pipeline. Use when the user brings a new project idea, wants to migrate an existing system, or says 'let's build X'. Routes to project-kickoff-grill (Part 1) then project-kickoff-spec (Part 2)."
---

# Project Kickoff

You own the flow from "the user has an idea" to "work is routed to specialists." The pipeline is split into two parts for context isolation — grilling can produce 100+ questions across multiple sessions, and spec synthesis needs fresh context.

## The pipeline

```
Part 1: project-kickoff-grill          → outputs grill decisions
Part 2: project-kickoff-spec           → reads grill decisions, outputs spec + ADRs + tickets
```

## When to load this

Load this the moment the user says anything about building, migrating, or changing architecture. Not after discussion. Immediately.

**Critical failure mode (real session, 2026-07-26):** The user said "I want to migrate and add new features" and "let's discuss first." The PO discussed architecture for 8 turns, felt confident, then loaded `to-spec` directly — WITHOUT loading this skill and WITHOUT grilling. The retrofit grill surfaced 19 critical decisions the spec was missing. Load this skill BEFORE responding.

## Routing

1. If no grill decisions exist → load `project-kickoff-grill` (Part 1)
2. If grill decisions exist → load `project-kickoff-spec` (Part 2)
3. If unsure → check for `~/projects/<slug>/.driver/grill/decisions.md`

## What each part does

- **`project-kickoff-grill`** — discuss architecture (3 questions), then adversarially grill every decision through 9 stress categories. Persists grill decisions to `~/projects/<slug>/.driver/grill/decisions.md`. Can span multiple sessions.

- **`project-kickoff-spec`** — gate checks grill decisions exist, then: synthesize spec via `to-spec`, create architect design card, decompose into tracer-bullet tickets via `to-tickets`, set up project infrastructure.

## The to-spec tension

The shared `to-spec` skill says "no interview, just synthesis." This is correct for SYNTHESIS of an already-grilled conversation — it's wrong as an entry point for un-grilled ideas. For new projects, always go through Part 1 first. Never jump to `to-spec` directly.

## Parallel system framing (NOT replacement)

When the user says "build X that does what Y does," the natural temptation is to frame X as "replacing Y." This is almost always WRONG for this user. The correct framing: X is a parallel system that extracts Y's capabilities into a harness-agnostic/standalone platform. Both systems coexist indefinitely.

**Real failure (2026-08-05):** During the ngin grill, multiple ADRs described ngin as "replacing Hermes kanban." The user corrected: "if current one is facebook, we're building twitter. why you try to delete the car when creating the plane." Required rewriting 5 ADRs and the spec's Problem Statement.

**The rule:** When proposing a new system that provides the same capabilities as an existing one, use "extracts" or "provides an alternative to" — never "replaces" or "retires." Both systems coexist. Migration is a user choice, not a project goal. Add a hard rule to CONTEXT.md: "Do NOT touch [existing system] code."

## Verify code behavior BEFORE proposing architecture

During grill sessions, the PO may need to describe how an existing system works to inform design decisions. NEVER describe system behavior from memory — read the actual code first. If subagents have already analyzed the system, read their output before proposing anything.

**Real failure (2026-08-05):** The PO proposed a dispatch model where "each profile gateway polls for its own cards" during the ngin grill. The user asked to confirm. Reading the code revealed: there is ONE dispatcher (singleton lock), it spawns processes for ALL profiles. The subagent analysis had already documented this correctly. The PO looked lazy and unprepared.

**The rule:** When asked "how does X work?", read the code. When proposing architecture that depends on how an existing system works, cite the file and line you read. Do not reconstruct from memory.

## Recurring architectural mistakes — enforce via CONTEXT.md

When the PO makes the same architectural mistake multiple times in a session (e.g., proposing agents poll for work when the decided model is daemon-spawns), verbal promises to stop are insufficient. Record the rule in three places:

1. **CONTEXT.md Hard Rules** — the domain model read before any design work
2. **ADR** — the architectural decision record with "why this exists" citing the incidents
3. **Persistent memory** — carries across sessions

If the mistake recurs, point at the ADR number. No argument.

## Grill-with-docs: maintain CONTEXT.md and ADRs inline

When running a grill session using the `grill-with-docs` skill, capture decisions as they crystallize — not at the end:

- **Terms resolved** → add to CONTEXT.md Language section immediately
- **Hard-to-reverse decisions with real trade-offs** → write ADR immediately (offer to the user)
- **Hard rules** (never do X) → add to CONTEXT.md Hard Rules section

This produces a living design document that the spec synthesis (Part 2) can reference directly. See `references/ngin-grill-session.md` for a complete example of this pattern applied to a real project.
