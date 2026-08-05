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

**The user's exact framing for extraction projects:** "ngin is our program that extract hermes kanban, dispatcher, our workflow engine that wrote for hermes kanban. to make it harness agnostic workflow orchestration that work with any harness that support heartbeat. we extract one of hermes capability to make it workable with other harness. just that." The project's reason for existing is the extraction thesis — state it in the opening paragraph of CONTEXT.md.

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

## Spec review: built complete, no backward compat

Specs for extraction/parallel projects are built complete from the first build.
No backward compatibility, no migration code, no legacy support, no "port from
old format." The user's exact words: "we don't need any backward compatibility,
we don't need migration code. this should be complete from the first build."

When reviewing a spec before publishing, scan for:
- "replaces" / "retires" / "obsoletes" → rewrite as "provides the X layer"
- "migration" / "cutover" / "port from" → remove entirely
- "existing tables (keep)" / "already exists" → state as definitive schema
- "backward compat" / "legacy" → remove
- "migration path" in research doc references → describe content, not migration

**Automated review catches what manual review misses.** Write a Python script
that scans for backward-compat/migration/legacy/replacement language. Manual
review said "no issues" twice; automated scan found 12 hits the third time. The
script doesn't get tired or pattern-match on expected outcomes. Use:
`grep -rn "replace\|legacy\|migration\|cutover\|backward" spec.md` as a final
gate before publishing. Then verify story numbering is sequential, phase
boundaries are clean (no Phase 2 concepts in Phase 1), and the harness contract
is complete.

## Dispatching specs to the pipeline

When the user says "let's use the workflow to implement this" or "feed the spec
to the pipeline," the answer is YES — create a spec card and let it run. Don't
invent concerns about which task tracker to use during development, don't
propose manual ticket breakdowns, don't overthink it.

The proven procedure:

```bash
# Create a fresh board for the project
hermes kanban boards create <slug>

# Create the spec card — assign to product-owner for decomposition
hermes kanban --board <slug> create "[spec] <title>" \
  --assignee product-owner \
  --body "$(cat <spec-file>.md)" \
  --priority 10 \
  --json
```

**Who gets the spec card?** The PRODUCT-OWNER, not tech-lead. The PO
decomposes the spec into tracer-bullet tickets, then dispatches each ticket
to tech-lead. Skipping the PO and assigning directly to tech-lead was a
real mistake (2026-08-05): "I don't understand why you delegate spec to
tech-lead instead of PO to make it create tickets and follow the workflow.
why skip to techlead directly?"

For small, single-purpose specs (build a Markdown converter), tech-lead-execute
can handle decomposition internally. For large platform specs (40+ stories),
the PO must decompose first.

**Board detection is automatic.** The Hermes dispatcher enumerates ALL boards
on disk every tick (`_kb.list_boards(include_archived=False)`). New boards are
picked up without restart. The `_default_spawn` function injects
`HERMES_KANBAN_BOARD` into the worker env. Workers cannot accidentally land on
the wrong board. No manual board injection needed.

**Engine tick CLI syntax:** `python3 workflow_engine/main.py --verbose tick`
(NOT `tick --board X`). The engine scans all boards by default.

**Don't overcomplicate dispatch.** When the user wants to use the pipeline,
create the card and step back. Don't add guidance, don't manually decompose,
don't create tickets by hand. The spec IS the guidance — let the pipeline
interpret it.

## Grill-with-docs: maintain CONTEXT.md and ADRs inline

When running a grill session using the `grill-with-docs` skill, capture decisions as they crystallize — not at the end:

- **Terms resolved** → add to CONTEXT.md Language section immediately
- **Hard-to-reverse decisions with real trade-offs** → write ADR immediately (offer to the user)
- **Hard rules** (never do X) → add to CONTEXT.md Hard Rules section

This produces a living design document that the spec synthesis (Part 2) can reference directly. See `references/ngin-grill-session.md` for a complete example of this pattern applied to a real project.

## Check repo is archived before writing ADRs

Before writing an ADR that says "work in repo X," check if repo X has a `SUPERSEDED.md` or is archived. If it is, you need a user decision: un-archive it, or work in the new location.

**Real failure (2026-08-05):** The PO wrote ADR-0006 ("work in ngin repo") without checking `~/workspace/ngin/SUPERSEDED.md`. The tech-lead agent discovered the repo was archived read-only and blocked the spec card with `needs_input`. The archive said code moved to `~/workspace/personal/pir/crates/tau-dispatch`. The PO had to un-archive the repo, delete SUPERSEDED.md, push, and unblock the card — wasting a full dispatch cycle.

**The check:** Before any ADR references a repo path:
```bash
ls <repo>/SUPERSEDED.md 2>/dev/null && echo "REPO IS ARCHIVED — get user decision"
git -C <repo> log --oneline -1  # verify it's not read-only
```

## Workflow pipeline dispatch: use a dedicated board

When feeding a spec to the workflow pipeline, create a dedicated board for the project — don't reuse `hermes-hq`. This keeps the project's cards isolated and makes monitoring cleaner.

```bash
hermes kanban boards create <slug>
hermes kanban --board <slug> create "[spec] <title>" \
  --assignee product-owner --body "$(cat spec.md)" --priority 10 --json
```

**Stale state cleanup:** If a previous dispatch was killed mid-run, clean ALL state before re-dispatching:
```python
# Delete workflow instances, trigger keys, trigger watermarks for the board
wdb.execute("DELETE FROM workflow_instances WHERE board='<slug>'")
wdb.execute("DELETE FROM trigger_keys WHERE key LIKE '%<old-card-ids>%'")
wdb.execute("DELETE FROM trigger_watermark WHERE board='<slug>'")
# Archive all cards on the board
db.execute("UPDATE tasks SET status='archived' WHERE status != 'archived'")
```

If you don't clean trigger keys, the engine will think the spec card was already processed and won't start a new workflow instance.
