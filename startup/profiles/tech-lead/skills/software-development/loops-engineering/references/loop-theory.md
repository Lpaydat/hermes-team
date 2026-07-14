# Loop Theory — Reference

Condensed theory behind the loops-engineering skill. Read when designing a new loop pattern, debugging loop quality, or onboarding to the role.

## The Three Nested Loops (Andrew Ng)

Loop engineering is not one loop — it's three nested at different time horizons. Each feeds the one inside it:

```
 ┌───────────────────────────────────────────────────────────┐
 │  EXTERNAL FEEDBACK LOOP (hours → weeks)                    │
 │  Alpha testers, friends, A/B testing, production data      │
 │  → Informs the product vision                             │
 │  │                                                        │
 │  │  ┌─────────────────────────────────────────────────┐   │
 │  │  │  DEVELOPER FEEDBACK LOOP (tens of min → hours)   │   │
 │  │  │  Human examines product, steers coding agent     │   │
 │  │  │  → Updates/clarifies the spec                    │   │
 │  │  │  → Builds evals when problems recur              │   │
 │  │  │  │                                             │   │
 │  │  │  │  ┌───────────────────────────────────────┐   │   │
 │  │  │  │  │  AGENTIC CODING LOOP (minutes)         │   │   │
 │  │  │  │  │  Agent writes code, tests, iterates    │   │   │
 │  │  │  │  │  until bug-free and meets spec         │   │   │
 │  │  │  │  │  → This is where the 5 phases live     │   │   │
 │  │  │  │  └───────────────────────────────────────┘   │   │
 │  │  │  └─────────────────────────────────────────────┘   │
 │  │  └─────────────────────────────────────────────────────┘
 └───────────────────────────────────────────────────────────┘
```

### Agentic Coding Loop (minutes)
Given a spec + evals, the agent writes code, tests, and iterates until bug-free. This is where the five phases operate. When the system repeatedly hits certain problems, build evals — structured assertions that make the failure gradable.

### Developer Feedback Loop (tens of min → hours)
The human examines the product and steers the agent. As agents get better at self-testing, less human time goes to QA and more goes to product-level decisions: what features to offer, where the spec should actually say. The spec is NOT static — it evolves as you see what the agent builds. Tech-lead operates this loop on the user's behalf: accept (spec met) → next issue; reject with feedback → re-delegate; escalate (spec wrong) → re-contract.

### External Feedback Loop (hours → weeks)
Alpha testers, friends, production A/B testing. Slow but irreplaceable — where you learn if you're building the right thing. After each epic, flag: "This needs external feedback before proceeding."

## Context Engineering (Anthropic)

Context is a finite resource with diminishing returns (context rot). The goal: the smallest possible set of high-signal tokens that maximize the desired outcome.

| Technique | Application |
|-----------|-------------|
| Just-in-time retrieval | Lightweight identifiers (file paths, issue refs) loaded at runtime via tools. CodeGraph for structured code understanding. Don't pre-stuff. |
| Compaction | Fresh agent with compressed state from the 3-file crash set (contract.md, progress.md, log.md). |
| Structured note-taking | Beads issues + kanban comments = persistent memory outside the context window. |
| Sub-agent separation | Maker explores extensively, returns condensed summary. Checker gets clean context. Lead synthesizes. |
| Minimal viable toolset | Each task gets only the tools it needs. |

## Autonomous Operation

The tech-lead runs autonomously once the plan is approved.

**Trigger mechanisms:**
1. **Direct chat** (`hermes -p tech-lead`): interactive contracting, planning
2. **Kanban task + dispatcher**: task assigned to `tech-lead`, gateway dispatcher spawns every 60s
3. **Kanban swarm**: parallel workers → verifier → synthesizer
4. **Cron job**: scheduled discovery (beads-watchdog every 5 min)

> **Cron syntax pitfall**: `schedule: "5m"` creates a ONE-SHOT job (fires once in 5 min, then stops). For recurring intervals, use standard cron expressions: `schedule: "*/5 * * * *"` with `repeat: 999999`.

> **kanban CLI flag pitfall**: `hermes kanban list` does NOT support `--board <slug>`. It always uses the current board (set via `hermes kanban boards switch`). Only `hermes kanban create` supports `--board`. When scripting, use `--json` output and parse with python3 — don't use `grep -c` on human-readable output (it returns multi-line counts that break integer comparisons).

**Heartbeat rule**: call `kanban_heartbeat(note="...")` at least once per hour during long operations. Without a heartbeat within 1 hour (after 4h+ runtime), the dispatcher reclaims the task.

**Sub-agent monitoring**: every delegated agent MUST be capped: wall-clock `timeout` wrapper + `--max-turns`, with `total_cost_usd` asserted from the JSON envelope post-hoc (`--max-budget-usd` does not exist — see harness-commands.md). Use `terminal(background=true, notify_on_complete=true)` for auto-completion signals. Poll with `process(action='poll')` for stuck agents.

**Gateway IS the dispatcher**: the gateway's built-in watcher runs `dispatch_once()` every 60 seconds. No separate daemon needed.

**Beads watchdog**: `~/.hermes/profiles/tech-lead/scripts/beads-watchdog.sh` + `scripts/process-beads.py` — zero-cost cron script scanning all beads projects every 5 min, reports ready work to Telegram. Active projects controlled by `~/.hermes-teams/startup/active-projects.json`. **Never add projects to the active list without asking the user** — they own that decision, and stale "ready" issues usually indicate inactivity, not urgency.

**Three-control duplicate prevention** (proven pattern for autonomous task creation):
1. **Concurrency cap**: `kanban.max_in_progress_per_profile` in the profile config (`startup/profiles/<profile>/config.yaml`) — caps same-profile concurrency at N (currently 6). At low N this bounds parallel spawns; the script also checks `hermes kanban list --status running` before creating anything.
2. **Board scan before create**: the script queries all existing tech-lead tasks, extracts beads IDs from titles (e.g. `[<project>-<hash>] ...`), and skips any issue that already has a task — regardless of task status (ready, running, blocked, done).
3. **Idempotency keys**: every `hermes kanban create` uses `--idempotency-key "beads-{issue_id}"` so even if both controls fail, the board itself rejects the duplicate.

Tested: three consecutive cron ticks produce exactly one task per ready issue, zero duplicates.

## Memory Architecture

- **Kanban board** = orchestration memory (task state, comments, handoffs across sessions)
- **Beads** = project task memory (epics, beads, sub-beads, dependencies, acceptance checklists)
- **3-file crash state** (`contract.md`, `progress.md`, `log.md`) = per-engagement recovery state
- **~/vault/journal/<project>/** = dev journey logs (build-in-public raw material)
- **~/vault/wiki/** = researcher's curated knowledge (READ ONLY — do not write here)

## Self-Improvement Loop

1. **Read scout findings**: query `~/vault/meta/scout.db` via `python3 ~/.hermes/profiles/research/scripts/scout-db.py <command>`
2. **Read researcher wiki**: `search_files` on `~/vault/wiki/`
3. **Commission research**: `kanban_create(title="Scout: <topic>", assignee="scout")` or `kanban_create(title="Deep research: <topic>", assignee="researcher")`
4. **Update this skill**: when new techniques are discovered, patch via `skill_manage(action='patch')`

Topics to track: loop engineering, harness engineering, prompt engineering, context engineering, agentic coding patterns, new harness releases, MCP ecosystem.

## Multi-Profile Team

| Profile | Role | Time horizon | How to interact |
|---------|------|-------------|-----------------|
| **product-owner** | Discovery & steering — scans projects, finds gaps, files issues, proposes priorities | Hours (discovery cron every 1-2h) | `kanban_create(assignee="product-owner")` or runs on its own cron |
| **tech-lead** | Execution — designs and runs coding loops (5 phases) | Minutes to hours (per task) | `kanban_create(assignee="tech-lead")` or watchdog auto-creates |
| **scout** | Fast daily AI scout — scans sources, triages, files research tasks | Daily | `kanban_create(assignee="scout")` |
| **researcher** | Deep research — reads sources fully, writes wiki notes | On-demand | `kanban_create(assignee="researcher")` |
| **base** | Unspecialized clone template | — | Do not assign tasks |

### The 24/7 loop

```
product-owner (every 1-2h)
  → discovers work, files beads issues, updates .driver/ state
  → contracts user for decisions via Telegram

beads-watchdog (every 5min, zero tokens)
  → scans bd ready, creates kanban tasks on project boards

gateway dispatcher (every 60s)
  → picks up ready tasks, spawns tech-lead (max 1 at a time)

tech-lead (per-task)
  → Discover → Plan → Execute → Validate → Iterate → Reflect
  → reads .driver/ for context, updates progress on completion
```

The loop runs continuously until: goal.md's success criteria are met, OR user pauses the project, OR a decision gap can't be resolved and the user doesn't respond.

## Harness Pruning (Karpathy VIII)

The harness exists to compensate for the model. As the model improves, half of what you wrote becomes overhead. Re-read your harness (skills, scripts, loops) against each new model release and delete anything the model now does for free. A harness that grows monotonically is a harness you have stopped reading.

## The Bottleneck Always Moves (Karpathy IX)

When coding stops being the bottleneck → planning becomes it. When planning is solved → verification. When verification is automated → taste. You don't finish; you find the next thing to fix. The whole point of the loop is to make the next bottleneck visible.
