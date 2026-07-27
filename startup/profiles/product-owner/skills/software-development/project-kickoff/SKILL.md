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
