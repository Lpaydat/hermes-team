# Stateless Graph Engine Pipeline (current)

> Verified 2026-08-08 by reading the actual code: `model.py`, `runtime.py`,
> `store.py`, all 16 templates, and the loop_engine plugin.

## Engine location

- **Engine code:** `startup/scripts/workflow_engine/` (model.py + runtime.py + store.py + main.py)
- **Templates:** `startup/scripts/workflow_engine/templates/*.json`
- **State DB:** `startup/kanban/workflow-state.db` (SQLite, WAL mode)
- **Config dirs:** `startup/scripts/workflow_engine/configs/{python,rust,node,go,_shared}/`
- **Profile-launched copy:** `startup/profiles/<profile>/scripts/workflow_engine/` (symlinked)
- **Cron:** 1-minute interval, runs `main.py tick`

## Tick pipeline (per instance)

```
GC          → cleanup old instances/keys/watermarks (7-day retention)
SYNC        → read card status from board → update node states (stateless derivation)
RESET       → back-edge resets (increment iteration if < maxIterations)
              dead-branch skip propagation
ACTIVATE+DISPATCH → evaluate activation (AND/OR edges, fan-in barrier)
              dispatch ready TASK nodes as cards
              run COMMAND nodes synchronously (in-tick)
              poll WAIT nodes
TRIGGERS    → scan completed cards matching trigger conditions
              create new instances (dedup via trigger_keys)
```

## Template inventory (16 production templates)

### Pipeline templates (the active workflow chain)

| Template | Trigger | What it does |
|----------|---------|-------------|
| `dev-dispatch` | PO card done, title [spec]/[ticket-] | Routing junction: routes by trigger.type to specialist |
| `tech-lead-execute` | tech-lead card done, title [spec]/[ticket-] | Per-ticket execution: plan(loop_engine)→verify→fix↔re-verify→close→merge-verify |
| `refactor-cycle` | [milestone-NN] card done | Repo refactor scan after milestone completion |
| `debug-fix` | (subworkflow) | test_failure → debugger → verifier |

### dev-dispatch routing paths

```
entry (command junction)
  ├─ trigger.type == 'bug'       → route-bug (debugger)
  ├─ trigger.type == 'research'  → route-scout (scout)
  ├─ trigger.type == 'ops'       → route-ops (ops)
  ├─ trigger.type == 'tickets'   → route-tickets (PO parses pre-made tickets)
  └─ default                     → route-architect → route-setup → route-decompose → route-milestone
```

**Default chain (architect→setup→decompose→milestone):**
- route-architect: stamps Implementation + Testing Decisions into spec file, assigns tier (T0-T3), decides tech stack from tech-preferences.json
- route-setup: tech-lead scaffolds language-specific config files (ruff/clippy/biome/golangci + Makefile) from `configs/<lang>/`
- route-decompose: PO calls loop_engine with to-tickets skill → decomposes spec into atomic ticket plan
- route-milestone: PO groups tickets into milestones (2-5 per group, max 5), creates [milestone-NN] cards with parents=ticket_ids. When all parents complete, kanban dep-gate auto-promotes.

### tech-lead-execute flow

```
plan (tech-lead, loop_engine with dev+verifier phases, max 5 iters)
  → verify (verifier, adversarial behavior tests + lint gate)
  → fix (developer) ← FAIL
  → re-verify (verifier) ← fix loops, max 10 iterations
  → close (tech-lead, merge ticket branch to master)
  → merge-verify (verifier, mechanical git+test confirmation) — only if task_count > 1
```

### Other templates (builder, QA, utility)

| Template | Purpose |
|----------|---------|
| `builder-grill-build` | Builder idea intake → grill → build |
| `builder-idea-intake` | Signal scan → idea intake |
| `builder-promote` | Prototype → production promotion |
| `builder-queue-builds` | Queue builds from signal scan |
| `builder-signal-scan` | Scan for project signals |
| `builder-single` | Single build (no grill) |
| `qa-gate` | QA verification gate |
| `mini-pipeline` | Minimal 2-node pipeline (testing) |
| `echo-test` | Echo test (engine validation) |
| `dev-pipeline` | Dev pipeline (legacy, minimal) |
| `dev-review-loop` | Dev review loop (FAIL→fix→re-review, unrolled once) |

### Disabled templates (`.disabled` / `.failed` suffix)

A/B test variants for QA and tech-lead workflows. Kept for reference. Do not activate without understanding why they were disabled (A/B test results documented in workflow-engine-development references).

## loop_engine plugin

**Location:** `startup/plugins/loop_engine/` (tools.py + schemas.py + __init__.py)

**Installed on profiles:** product-owner, tech-lead, architect, debugger, builder

**What it does:** Tool-driven convergence engine. The calling agent invokes `loop_engine` with:
- `goal`: what to accomplish
- `phases`: array of execution+verifier pairs (one per task)
- `max_iterations`: per-phase retry cap

loop_engine then:
1. Creates execution cards (developer builds)
2. Creates verifier cards (verifier checks)
3. Advances → next phase on PASS
4. Replans → re-executes on FAIL
5. Escalates → stops on repeated failure
6. Dependency-parks the calling card until ALL phases converge

**Key invariant:** loop_engine handles ALL card creation internally. The calling agent does NOT call kanban_create or kanban_chains.

## Trigger condition keys (supported by _matches_trigger)

- `assignee`: exact match on card assignee
- `status`: exact match on card status
- `metadata.<field>`: match on metadata key
- `title_prefix`: card title starts with this
- `title_prefix_any`: card title starts with ANY of the listed prefixes (array)
- `title_not_prefix` / `title_not_prefix2`: card title does NOT start with this

## Board isolation

The engine only scans boards in `active-projects.json` (allowlist). Boards not in the allowlist are ignored. Projects are discovered dynamically by scanning for `.beads/` directories.

**active-projects.json format:** The engine reads ONLY the `board` field (`runtime.py:3279`: `proj.get("board")`). The `repo`/`path`/`name` fields are advisory. Both `{"board": "X", "repo": "/path"}` and `{"board": "X", "path": "/path", "name": "X"}` work; only `board` is required.

## Node types

| Type | Behavior | Card created? |
|------|----------|---------------|
| `task` (default) | Dispatch to agent profile | Yes |
| `command` | Run shell synchronously in-tick | No |
| `wait` | Poll condition each tick, proceed when true | No |
| `subworkflow` | Create child workflow instance | Child cards |
| `foreach` | Fan-out: iterate list, dispatch one card per item | N cards |

## Key invariants (from model.py)

- Workflow IDs must NOT contain underscores (self-trigger guard relies on this)
- Back-edges require iteration caps (`max_iterations` field or condition referencing iteration)
- Explicit edges take precedence over `depends_on` when present
- Templates validate at load time: reachability, exit-node existence, back-edge termination
