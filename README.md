# Hermes Team Config

Backup of the full Hermes Agent team configuration. This is the working setup — profiles, skills, plugins, scripts, cron jobs, and kanban boards.

## What's Here

### Profiles (11)

| Profile | Role | Gateway |
|---------|------|---------|
| `product-owner` | Front door — plans work, dispatches beads, steers priorities | running |
| `tech-lead` | Technical planning — contracts, delegation via `kanban_delegate` | running |
| `developer` | Code generation via pi harness (GLM-4.5-air for testing, GLM-5.2 for production) | running |
| `verifier` | Adversarial code review — two-phase protocol, AC gates, mutation testing | running |
| `ops` | System health — healthcheck, cron backup, session archiver | running |
| `scout` | AI research scanning | running |
| `venture-builder` | Demand signal scanning, pipeline cycles | running |
| `advisor` | Startup advisory (stopped) | stopped |
| `base` | Base profile (stopped) | stopped |
| `researcher` | Deep research (stopped) | stopped |
| `default` | Default profile (stopped) | stopped |

### Dev Workflow

The core dev loop: PO plans → cron dispatches → tech-lead delegates → developer builds → verifier reviews → merge to main.

```
User/Agent → PO (dev-planning skill)
  → discuss → PRD → beads + deps → close PRD bead
  → walk away

Workflow Engine cron (1min)
  → bead-sync: sync card status → bead status
  → auto-dispatch: bd ready → create PO dispatch card
  → board-scanner: blocked tasks → escalate to proper profile

PO receives dispatch card (dev-dispatch skill)
  → creates tech-lead cards for ALL ready beads

Tech-lead receives card
  → kanban_delegate → dev → verifier → merge → done
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `workflow-engine.py` | `product-owner/scripts/` | Combined cron: bead-sync + dispatch + scanner (1min) |
| `kanban_delegate` plugin | `tech-lead/plugins/dev_workflow/` | Tool that creates dev+verifier cards and blocks tech-lead atomically |
| `session-archiver.py` | `ops/scripts/` | Archives kanban worker sessions >3 days old |
| `hygiene-guard.sh` | `product-owner/scripts/` | Scans active projects for stale/orphan beads (4h) |
| `healthcheck.sh` | `ops/scripts/` | System health: tools, gateways, disk, auth (1h) |
| `cron-store-backup.sh` | `ops/scripts/` | Backs up all profiles' cron/jobs.json (6h) |
| `discovery-guard.sh` | `tech-lead/scripts/` | Project discovery scan, gated by active-projects.json (4h) |

### Cron Jobs

| Profile | Name | Schedule |
|---------|------|----------|
| product-owner | Dev Workflow Engine | 1m |
| product-owner | Task Hygiene Watchdog | 4h |
| product-owner | Weekly Sprint Report | weekly |
| ops | Ops Healthcheck Watchdog | 1h |
| ops | Cron Store Backup | 6h |
| ops | Session Archiver | 6h |
| tech-lead | Project Discovery | 4h |
| scout | Daily AI Research Scout | 8x/day |
| venture-builder | Daily Demand Signal Scan | 3h |
| venture-builder | RequestHunt Weekly Deep Scan | 3x/week |
| venture-builder | Pipeline + Build Cycle | 4x/day |

### Skills (PO-created)

| Skill | Purpose |
|-------|---------|
| `dev-planning` | Discuss → PRD → beads + deps |
| `dev-dispatch` | Receive PO card from cron → create tech-lead cards |
| `dev-workflow-orchestration` | [ARCHIVED] Historical reference, 22+ battle tests |
| `project-discovery` | Scan active projects for work signals |
| `task-hygiene-validator` | Validate beads for structural quality |

### Kanban Boards

| Board | Purpose |
|-------|---------|
| `startup` | Main dev workflow board |
| `hermes-hq` | Team coordination |
| `board-scanner-test` | Board scanner test board |

## What's NOT Here

| Excluded | Why |
|----------|-----|
| `state.db` / `sessions/` / `logs/` | Ephemeral runtime state |
| `.env` | Secrets |
| `hermes-agent/` source | Reinstallable via `hermes` CLI |
| `mattpocock/` / `ponytail/` shared skills | Reinstallable via `hermes skills install` |
| `node_modules/` / `__pycache__/` | Build artifacts |
| Cron output logs / lock files | Runtime state |

## Restore

```bash
# Clone into .hermes-teams
git clone -b config https://github.com/Lpaydat/hermes-team.git ~/.hermes-teams

# Reinstall hermes-agent
cd ~/.hermes-teams/startup/hermes-agent && pip install -e .

# Reinstall shared skills
hermes skills install mattpocock
hermes skills install ponytail

# Restart gateways
hermes gateway start --profile product-owner
hermes gateway start --profile tech-lead
hermes gateway start --profile developer
hermes gateway start --profile verifier
hermes gateway start --profile ops
```

## Test Results (Jul 2026)

| Test | Result |
|------|--------|
| Core loop (TL→DEV→VER→merge) | ✅ 22+ battle tests |
| Parallel execution (3 concurrent) | ✅ Test 22 + 5-case validation |
| Merge conflict resolution | ✅ C6 3/3 |
| Tech-lead re-block on FAIL | ✅ C9 3/3 (via C6) |
| `kanban_delegate` reliability | ✅ 5/5 |
| Board scanner v2 | ✅ 7/7 test suite + production |
| Bead-sync timing | ✅ Correct lifecycle |
| Crash recovery | ✅ Self-healed |

## Model Config

All profiles use `zai/glm-5.2`. No fallback models (deepseek removed). Developer uses `glm-4.5-air` for testing (forces bugs for verify→fix cycle). Switch to `glm-5.2` for production.
