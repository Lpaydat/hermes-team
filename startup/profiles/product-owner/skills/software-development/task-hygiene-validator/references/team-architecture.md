# Team Architecture — Multi-Domain Agent Org Design

Approved architecture for managing multiple projects across multiple
domains (software, ecommerce, content, etc.) with a Hermes agent fleet.

## Org structure

```
SHARED SERVICES (company-wide, 1 each)
├── product-owner    → discovery, filing, steering (ALL projects)
├── scout            → daily industry/AI scan → kanban
└── researcher       → deep research → ~/vault/wiki/

SPECIALISTS (1 per domain, run in parallel)
├── tech-lead        → coding projects (max_in_progress=1)
├── commerce-lead    → ecommerce (created manually by user)
├── content-lead     → youtube/content (created manually by user)
└── ...future        → user creates with care when new domain starts

ROUTING
└── Single board (hermes-hq) — tasks routed by assignee
```

## Key design decisions

### 1. Shared services serve ALL domains

Product-owner doesn't need to be a domain specialist. The role is:
help the user define what each project is FOR (goal.md), file issues
properly, route them to the right specialist, and watch for scope
creep. This works whether the project is Rust code or YouTube scripts.

### 2. Specialists run in parallel

Each specialist profile has its own `max_in_progress_per_profile: 1`.
This means tech-lead can work on a coding task while commerce-lead
works on a pricing update simultaneously. They don't block each other
because they're different profiles on the same board.

**Do NOT raise max_in_progress on a single profile to get parallelism.**
A coding agent and a commerce agent need different skills, memory, and
context. Use separate profiles instead.

### 3. Single board for all dispatch

The gateway dispatcher watches ONE board. Multiple boards don't mean
parallel dispatch — they mean stranded work on boards the dispatcher
doesn't poll.

Routing is by **assignee** (profile name), not by board slug:
```
[#001] [tau-xxx] Fix overlay rendering     → tech-lead
[#002] [store-xxx] Update product prices   → commerce-lead
[#003] [yt-xxx] Edit video script          → content-lead
```

### 4. Three-layer separation

| Layer | Purpose | Scope |
|-------|---------|-------|
| **Beads** (`.beads/`) | Issue tracking — what needs doing | One DB per project |
| **Kanban** (`hermes-hq`) | Dispatch — who does it and when | Single board, all projects |
| **`.driver/`** | Steering — why we're doing it | Per-project, read by whoever picks up the task |

### 5. New specialist profiles are created manually

The user creates new profiles deliberately — they require domain-specific
skills, tools, and careful configuration. Do NOT auto-create profiles.

When a new domain starts:
1. User clones `base` profile
2. User configures skills, toolsets, memory
3. User tests the profile in isolation
4. Tasks route to it via `assignee` on hermes-hq

## Division of labor — who does what

### Product-owner (this profile)

**Come to product-owner when:**
- New feature idea → validates against goal, files in beads properly
- New bug → files with reproduction steps
- "What should we work on next?" → analyzes gap, proposes priorities
- New project idea → defines vision, scope, success criteria, sets up `.driver/`
- "Is this task still relevant?" → checks goal-traceability

**Product-owner shapes WHAT to build and WHY. Does not write code.**

### Specialist profiles (tech-lead, future commerce/content leads)

**Go to a specialist when:**
- "Implement this issue" → writes code/content, runs tests, ships
- "Fix this bug" → debugs and ships the fix
- "Refactor X" → does the change

**Specialists build HOW. One task at a time per profile.**

## Concurrency model

- **Within a profile**: strictly serial (`max_in_progress_per_profile:
  1`). Multiple tasks queue; dispatcher picks one at a time in priority
  order.
- **Across profiles**: fully parallel. Tech-lead and commerce-lead run
  simultaneously without interference.
- **Queue depth is safe**: 5 queued tasks for tech-lead doesn't break
  anything — they process one at a time.

## Mixed-domain task routing

```
You → product-owner: "I need to update product prices in the store"
    → product-owner checks store/.driver/goal.md (creates if missing)
    → files beads issue in store's .beads/ DB
    → creates kanban task on hermes-hq: [store-xxx] Update prices,
      assignee=commerce-lead
    → dispatcher spawns commerce-lead (parallel to tech-lead on pir)
    → commerce-lead reads store/.driver/goal.md for context, executes
```

## Board cleanup

Stale per-project boards (created speculatively, never used) should be
deleted. They create confusion and store dead tasks. Keep only
`hermes-hq` as the single dispatch surface.

Deletion steps:
1. Archive/clear all tasks on the stale board
2. Delete the board's DB: `rm -rf ~/.hermes/kanban/boards/<slug>`
3. Verify `hermes kanban boards` shows only `hermes-hq`
