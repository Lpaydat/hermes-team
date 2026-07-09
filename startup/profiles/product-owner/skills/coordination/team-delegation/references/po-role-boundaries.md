# Product-Owner Role Boundaries & Beads-as-Masterplan Architecture

The PO's job in the dev workflow is narrow and specific. Violating these boundaries
invalidates the workflow (the agent did the planner's job instead of letting tech-lead
work autonomously — Jul 2026 correction).

## What PO Owns (WHAT domain)

| Task | Skill | When |
|------|-------|------|
| Grill the user about the product | `grilling` | In-session, before PRD |
| Write the PRD | `to-spec` | After grilling, in-session |
| Decompose into slices | `to-tickets` | After PRD, in-session, WITH user approval |
| Create beads + dependencies | `bd` CLI | After user approves slices |
| Prioritize which bead to work on next | `bd ready` + PRD priorities | In the cron loop |
| Create ONE kanban card for tech-lead | `kanban_create` | For the highest-priority ready bead |
| Observe and steer | `kanban log/show/tail` | Throughout |

## What PO Does NOT Do

- ❌ **Write contracts/specs in task bodies** — that's doing the planner's job (the Jul 2026 cheat)
- ❌ **Create step-by-step plans for tech-lead** — tech-lead handles the HOW autonomously
- ❌ **Manually unblock tasks** — the reviewer creates fix cards itself; PO should not interfere
- ❌ **Interfere with the loop** — PO observes, takes notes, only intervenes on fatal breakage
- ❌ **Run `to-tickets` and hand slices to tech-lead as a wrapper** — PO runs `to-tickets` to create
  beads (the masterplan), then the automation loop surfaces ready beads to PO one at a time

## The Clean Handoff Point

```
WHAT domain (PO)                     HOW domain (tech-lead)
━━━━━━━━━━━━━━━━                     ━━━━━━━━━━━━━━━━━━━━━
User says "I want X"                 Receives ONE bead as kanban card
PO grills user (grilling)            → Technical design (architecture, modules)
PO writes PRD (`to-spec`)               → Runs loops-engineering skill
PO runs `to-tickets` → beads created    → Creates dev/reviewer cards per bead
─────── HANDOFF: ONE bead ──────→    → Developer invokes harness
                                     → Reviewer adversarial review
                                     → Fix loop if needed
PO observes via kanban               → Tech-lead escalates if iteration ≥ 3
```

## Beads as Masterplan, Kanban as Execution

```
Beads (masterplan)                   Kanban (execution)
━━━━━━━━━━━━━━━━━━                   ━━━━━━━━━━━━━━━━━━
Durable across sprints               Ephemeral — archive after done
Epics → beads → sub-beads             One card per bead that's ready
Dependencies enforce build order      Cards are one execution cycle
Created ONCE from `to-tickets`           Created per-cycle by PO's cron

bd ready → surfaces what's ready      Each card = dev→harness→reviewer
```

## The Full Automation Loop

```
━━━ IN-SESSION (PO + user) ━━━━━━━━━━━━━━━━━━━━━━━━━
PO grills user → PRD written (`to-spec`)
PO runs `to-tickets` → presents slices → user approves
PO creates ALL beads + dependencies in bd
Session ends → beads persist as the masterplan

━━━ AUTOMATION LOOP (CRON, no user) ━━━━━━━━━━━━━━━━
Script: bd ready → if empty, exit silently (zero tokens)
Script: check running loops against quota → if at cap, exit
PO: read ready beads → pick highest priority
PO: create ONE kanban card for tech-lead with bead content
Tech-lead: receives card → runs loops-engineering
  → creates dev/reviewer cards
  → developer invokes harness (pi/zz)
  → reviewer adversarial review
  → fix loop if needed
Loop completes → kanban card archived
Next cron tick → repeat

━━━ OBSERVATION (PO + user, async) ━━━━━━━━━━━━━━━━━
PO monitors kanban board via discovery cron
PO steers if needed (re-prioritize, block, escalate)
User reviews via Discord/dashboard
```

## How Two Profiles Communicate

There is NO direct messaging between Hermes profiles. Communication channels:

| Channel | What it carries | When to use |
|---------|----------------|-------------|
| **Kanban card body** | The task spec (bead content, contract, evals) | Handoff: PO → tech-lead |
| **Kanban comments** | Questions, answers, findings, review iterations | Async discussion during execution |
| **Beads issues** | The masterplan (epics, beads, dependencies) | What to build and in what order |
| **Files on disk** | PRD.md, contract.md, design.md | Large structured artifacts |
| **bd memory** | PO's reasoning about priority/context per bead | Persists across sessions |

## The Existing Beads Watchdog

A shell script (`beads-watchdog.sh` in tech-lead's scripts/) already exists. It:
1. Runs `bd ready` on active projects (zero tokens — pure shell)
2. Checks if tech-lead is already running (control 1)
3. Creates kanban cards with idempotency keys (control 2)
4. Relies on `max_in_progress=1` (control 3)

**Current limitation**: it's purely mechanical — no prioritization. If 3 beads are ready,
it creates 3 cards and tech-lead grabs whichever the dispatcher picks first.

**Evolution path**: replace the mechanical card creation with a PO-driven cron that
reads ready beads, compares to PRD priorities, and creates ONE card for the highest-
priority bead. The script part (bd ready + exit if empty) stays free; the LLM part
only fires when there's a decision to make.

## Who Runs to-spec vs to-tickets? (FAANG model)

In real FAANG development:
- **Product Manager** writes the PRD — what to build, user stories, success metrics
- **Tech Lead** takes the PRD and writes the technical design + creates engineering tasks

In our architecture, PO combines both PM and PO roles (single front door for the user).
`to-spec` and `to-tickets` are both WHAT decisions (product slicing), so PO owns them.
Tech-lead owns the HOW (technical approach, harness invocation, dev/reviewer cards).

The PO role is NOT just a wrapper that passes beads to tech-lead. PO **decides what to
do next** based on business priority — that's the real value-add over a mechanical script.

## Skill Library Management (shared skills — LIVE Jul 2026)

Mattpocock and ponytail skills are centralized in git repos and symlinked to all profiles.
This is the implemented architecture (not a proposal — deployed and verified):

```
~/.hermes-teams/shared-skills/                    ← team-level (above all profiles)
├── mattpocock/         ← git clone of github.com/mattpocock/skills
│   └── skills/{engineering,productivity,misc,personal,in-progress,deprecated}/
├── mattpocock/     ← Hermes-compatible symlink structure
│   ├── engineering -> ../mattpocock/skills/engineering
│   ├── productivity -> ../mattpocock/skills/productivity
│   └── ...
├── ponytail/           ← git clone of github.com/DietrichGebert/ponytail
│   └── skills/{ponytail,ponytail-audit,...}/
├── ponytail-hub/       ← Hermes-compatible symlink structure
│   └── ponytail -> ../ponytail/skills
└── README.md

profiles/<each>/skills/
├── mattpocock -> ../../../../shared-skills/mattpocock  ← ONE symlink per profile
├── ponytail -> ../../../../shared-skills/ponytail-hub      ← ONE symlink per profile
```

**Update all profiles at once:**
```bash
cd ~/.hermes-teams/shared-skills/mattpocock && git pull
cd ~/.hermes-teams/shared-skills/ponytail && git pull
```

**Read-only protection** (`chmod -R a-w` on shared dirs): Hermes curator cannot modify these.
To customize per-profile (allow evolution): copy the skill to `profiles/<name>/skills/custom/<skill-name>/`.

**Lessons from the migration:**
- Hermes discovers skills by walking the `skills/` directory recursively, including through symlinks
- `.bak.*` directories in `skills/` ARE scanned as skill sources — remove backups, don't leave them
- Upstream mattpocock v1.0.0+ restructured into categories (engineering/, productivity/, etc.)
- `decision-mapping` was merged into `domain-modeling` upstream
- `diagnose` → `diagnosing-bugs`, `write-a-skill` → `writing-great-skills` (renamed)
- New skills from upstream: `code-review`, `research`, `codebase-design`
