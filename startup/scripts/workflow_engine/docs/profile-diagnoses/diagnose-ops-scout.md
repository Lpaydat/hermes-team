# Diagnosis: ops, scout, researcher Profiles + Legacy Cron Scanner/Human-Escalation

**Generated:** 2026-07-31
**Sources:** SOUL.md, config.yaml, skills, cron jobs.json, cron scripts, `workflow-engine.py`

---

## Table of Contents

1. [Profile Summary: What Each Does](#1-profile-summary-what-each-does)
2. [Triggers](#2-triggers)
3. [Scanner Monitoring (workflow-engine.py)](#3-scanner-monitoring-workflow-enginepy)
4. [Human Escalation](#4-human-escalation)
5. [Ops Cron Management](#5-ops-cron-management)
6. [Scout Work Discovery](#6-scout-work-discovery)
7. [JSON Node Definitions for Automatable Tasks](#7-json-node-definitions-for-automatable-tasks)

---

## 1. Profile Summary: What Each Does

### ops — Platform Engineer & Environment Manager

**Role:** Owns the developer environment — tools, configs, indexes, infrastructure. Builds and maintains the stage so other agents can perform. Does NOT write application code.

| Dimension | Detail |
|-----------|--------|
| **Identity** | `ops` — specialized Hermes agent |
| **Model** | `glm-5.2` (zai provider), `reasoning_effort: xhigh`, `rate_limit_delay: 30` |
| **Toolsets** | Full: terminal, file, skills, memory, session_search, web, kanban, todo, cronjob, delegation, code_execution, clarify |
| **Approvals** | `smart` mode with command_allowlist for safe ops commands (systemctl status, df, which, hermes profile list, git status, tool version checks) |
| **Concurrency** | `max_in_progress: 3` per profile / total |
| **Plugins** | kanban_chains, skill_enforcer |

**Core responsibilities:**
- **First-time setup**: Install tools globally (bd, pi, zz, codegraph, graphify), configure MCP servers, set up profile configs, create kanban boards
- **New project onboarding**: Create `.beads/`, `.driver/` (goal.md, progress.md, decisions.md, gaps.md), index codebase, add to `active-projects.json`
- **Health monitoring**: Gateways running? Tools installed? Configs valid? Indexes fresh? Cron jobs healthy?
- **Fix drift**: Restart dead gateways, reinstall missing tools, fix broken configs
- **Tool evaluation**: Research and trial new tools, recommend additions

**Key skills:**
- `healthcheck` — Watchdog pattern, silent when healthy, reports only what's broken
- `dev-env-setup` — Idempotent setup, per-project onboarding, profile config pitfalls documented
- `team-observability` — Reads team telemetry (kanban DB, gateway state, cron schedule), diagnoses throughput/failure/latency/load/structure

---

### scout — AI Scout (Breadth-First Research)

**Role:** Fast, breadth-first research scout specializing in Agentic AI and Generative AI. Scans the AI frontier daily, triages what matters, files deep-research tasks for the researcher, delivers a morning digest to Telegram. **Fast and shallow** — titles, abstracts, summaries. Does NOT write Obsidian notes.

| Dimension | Detail |
|-----------|--------|
| **Identity** | `scout` — AI Scout (specialized via `/transform`) |
| **Model (cron)** | `deepseek-v4-flash` (deepseek provider) — **currently broken: no API key** |
| **Model (config default)** | `glm-5.2` (zai provider) |
| **Toolsets** | Minimal: hermes-cli, kanban |
| **Approvals** | Default (no command_allowlist) |
| **Concurrency** | `max_in_progress: 3` per profile / total |

**Core workflow (6 phases):**
1. **Fetch** — Poll tiered sources (T1–T4) daily
2. **Dedup** — Check every item against SQLite via `scout-db.py dedup-check`
3. **Triage** — Sort into: deep-research → file kanban task; notable → catalog + digest; signal → catalog + digest; drop
4. **File** — Create kanban tasks for deep-research candidates, assigned to `researcher`
5. **Deliver** — Send structured digest to Telegram
6. **Discover** — Add new sources, prune stale ones

**Source tiers:**
- **T1:** arXiv, Hugging Face Daily Papers, Simon Willison, Lilian Weng, import AI, Matt Pocock
- **T2:** The Verge AI, Ars Technica, The Batch, MIT Tech Review, Hacker News, GitHub trending
- **T3:** YouTube (AI Explained, Yannic Kilcher, Two Minute Papers, etc.), X/Twitter (Karpathy, Jim Fan, swyx, etc.)
- **T4:** Reddit (r/LocalLLaMA, r/MachineLearning, etc.), Medium/dev.to (gated)

**Key skills:** `research-scout` (v3.0.0, 6-phase workflow), `web-research`, `web-source-research`, `computer-use`

**⚠️ Issues found:**
- Last cron run **FAILED**: `RuntimeError: No usable credentials found for provider 'deepseek'. Set DEEPSEEK_API_KEY.`
- Telegram delivery **broken**: `platform 'telegram' not configured/enabled`
- Config disables `research-scout`, `blogwatcher`, `messaging-delivery`, `xurl` in interactive mode (cron forces them via job-level `skills` list)
- `scout-db.py register` has a parameter bug (source_tier reads from wrong argv position)

---

### researcher — Deep Researcher (Depth-First Knowledge Engineer)

**Role:** Thorough, depth-first knowledge engineer. Picks up deep-research kanban tasks filed by the scout, reads sources fully, synthesizes curated Obsidian wiki notes that compound over time. **Slow and thorough.** The **only** thing that writes to `~/vault/wiki/`.

| Dimension | Detail |
|-----------|--------|
| **Identity** | `researcher` — Deep Researcher (specialized via `/transform`) |
| **Model** | `glm-5.2` (zai provider), `reasoning_effort: xhigh` |
| **Toolsets** | Minimal: hermes-cli, kanban |
| **Approvals** | Default (no command_allowlist) |
| **Concurrency** | `max_in_progress: 3` per profile / total |

**Core workflow:**
1. **Orient** — Read the kanban task, check what the vault already knows
2. **Read** — Read every listed source fully (arxiv PDFs, articles, video transcripts)
3. **Synthesize** — Write curated wiki note(s): 200–500+ words, YAML frontmatter, `[[wiki-links]]`
4. **Cross-reference** — Backlink from existing notes, update index, track topics in SQLite
5. **Register** — Record the note in SQLite so the scout's dedup knows it's been processed
6. **Complete** — Mark the kanban task done with a useful summary

**Research fan-out:** Uses `kanban_chains` (NOT background subagents) for broad research — decomposes into sub-questions, fans out researcher cards, parks in dependency-wait, synthesizes on promotion.

**Key skills:** Academic verification suite (`academic-citation-verification`, `academic-literature-verification`, `source-code-verification`, `library-state-verification`, `performance-verification`, `docs-verification`, `source-code-audit`), `cloud-cost-research`, `github-apps` / `github-app-integration`

**⚠️ Notable:** Config disables `deep-research`, `llm-wiki`, `obsidian`, `obsidian-vault`, `youtube-content` — the SOUL.md describes writing Obsidian notes, but the enabling skills are disabled. No cron jobs configured (purely task-driven via kanban dispatch from scout).

---

## 2. Triggers

### ops Triggers

| Trigger | Mechanism | Response |
|---------|-----------|----------|
| Cron tick (every 5 min) | `healthcheck.sh` no_agent script | Runs 4 checks (tools, gateways, disk, Z.AI auth); silent if healthy, prints findings if broken |
| Cron tick (every 6h) | `cron-store-backup.sh` no_agent script | Backs up all profiles' `jobs.json`; alerts if any is missing but backup exists |
| Cron tick (every 6h) | `session-archiver.py` no_agent script | Archives kanban worker sessions >3 days old across 7 profiles |
| On-demand / kanban task | Human or PO files task → `ops` | Execute dev-env-setup, fix drift, onboard project |
| Gateway failure | Detected by healthcheck | Reported in findings (does NOT auto-fix — watchdog only) |

### scout Triggers

| Trigger | Mechanism | Response |
|---------|-----------|----------|
| Cron tick (8×/day, every 3h) | `scout-guard.sh` → agent prompt → `research-scout` skill | Guard checks `.last-scout` marker: `ALREADY_SCOUTED` → skip (zero tokens via `wakeAgent:false`); `NEEDS_SCOUTING` → run full 6-phase workflow |
| Machine was off | Guard detects gap in `.last-scout` | Agent runs full scout (catches up) |

### researcher Triggers

| Trigger | Mechanism | Response |
|---------|-----------|----------|
| Kanban task from scout | `kanban_create(assignee="researcher")` → dispatcher | Deep research: read sources, write wiki note, cross-reference, complete |
| Direct user request | User asks for deep research | Same workflow |
| Broad research fan-out | Researcher calls `kanban_chains` | Decomposes into sub-researcher cards, synthesizes on completion |

### Legacy workflow-engine.py Triggers (product-owner cron, every 1 min)

| Phase | Trigger | Response |
|-------|---------|----------|
| bead-sync | Every tick, per project | Sync kanban card status → bd bead status |
| dispatch | bd `ready` beads exist | Create PO dispatch card (or route bug→debugger, wayfinder→scoped profile) |
| human-escal | Bead tagged `human` | Create operator HQ escalation card |
| scanner | Task status = `blocked` | Escalate up the chain or mark HUMAN_REQUIRED |

---

## 3. Scanner Monitoring (workflow-engine.py)

The scanner runs as **Phase 3** of the legacy `workflow-engine.py`, which runs every minute as a no_agent cron on the product-owner profile (`5838e048ae7f`, 31,299 completed runs).

### What the scanner monitors

The scanner scans **every project board** (from `active-projects.json`) for tasks with `status = 'blocked'`.

### Scanner logic (per blocked task)

```
For each blocked task on each board:
  1. Skip if assignee is "default" or "" (no profile owns it)
  2. Skip if task has a HUMAN_REQUIRED comment (already escalated to human)
  3. Check if escalation was resolved:
     - Look for a done task with title "[ESCALATION] ...{task_id}..."
       whose run summary starts with "RESOLVED:"
     - If found → unblock the original task
  4. Check if escalation already exists (active, not done/archived):
     - If yes → skip (don't duplicate)
  5. Create escalation card:
     - Target = ESCALATION_CHAIN[assignee]
     - If no higher profile → comment HUMAN_REQUIRED on the task
     - Else → create "[ESCALATION] Resolve block on {task_id}" card
```

### Escalation chain

```python
ESCALATION_CHAIN = {
    "developer":     "tech-lead",
    "verifier":      "tech-lead",
    "debugger":      "tech-lead",
    "qa":            "tech-lead",
    "tech-lead":     "product-owner",
    "product-owner": None,  # → HUMAN_REQUIRED
}
```

### Scanner monitoring scope

| Check | What it watches | Action |
|-------|-----------------|--------|
| Blocked tasks | `tasks WHERE status = 'blocked'` | Escalate to next profile in chain |
| Resolved escalations | Done tasks with `RESOLVED:` summary matching `[ESCALATION] %{task_id}%` | Unblock original task |
| HUMAN_REQUIRED marker | Comments containing `HUMAN_REQUIRED` | Skip (already human-flagged) |
| Block reason | `task_events` payload for `blocked`/`gave_up` kind | Included in escalation card body |

---

## 4. Human Escalation

### Two distinct escalation mechanisms

#### A. Scanner-based escalation (Phase 3 of workflow-engine.py)

When a blocked task has **no higher profile** in the escalation chain (i.e., `product-owner` is blocked, or assignee is unknown):

```python
# No higher profile → mark HUMAN_REQUIRED
run_kanban(board, ["comment", task_id, "--author", "board-scanner",
                   f"HUMAN_REQUIRED: No higher profile for {assignee}"])
```

This leaves a comment on the task. The scanner will skip it on future ticks (the HUMAN_REQUIRED comment is a sentinel).

#### B. Human-flagged bead escalation (Phase 2b of workflow-engine.py)

When a bead is tagged with the `human` label (set by whoever escalates — e.g., the wayfinding citation rule):

```python
# Creates an operator HQ card on the hermes-hq board
title = "[ESCALATION] human answer needed: {bead_title}"
run_kanban("hermes-hq", [
    "create", title,
    "--assignee", "default",
    "--priority", "10",
    "--body", body,  # includes bead ID, description, how to respond
    "--idempotency-key", f"bead-human-{bead_id}",
])
```

**Key properties:**
- Board: `hermes-hq` (operator board, not project board)
- Assignee: `default` (reaches the human operator)
- Idempotent: one card per bead (`bead-human-{bead_id}`)
- Skips closed beads
- Response mechanism: `bd human respond {bead_id}` (comments + closes the bead)

### What triggers human escalation

| Trigger | Source | Mechanism |
|---------|--------|-----------|
| Task blocked, assignee = `product-owner` | Scanner (Phase 3) | `HUMAN_REQUIRED` comment on task |
| Task blocked, unknown assignee | Scanner (Phase 3) | `HUMAN_REQUIRED` comment on task |
| Bead tagged `human` | Any agent or human via `bd tag <id> human` | HQ escalation card (Phase 2b) |
| Scout cron failure | Cron system | `last_status: "error"` in jobs.json (no auto-escalation — requires manual review) |

---

## 5. Ops Cron Management

### Ops cron jobs (3 total)

All ops cron jobs are **no_agent scripts** (zero tokens — no LLM call). They follow the **watchdog pattern**: silent when healthy, output only when there's a problem.

| Job | ID | Schedule | Script | Pattern |
|-----|----|----------|--------|---------|
| **Ops Healthcheck Watchdog** | `55530bb40ee9` | every 5 min | `healthcheck.sh` | Silent watchdog; prints findings only when broken |
| **Cron Store Backup** | `f7ef62ac35a2` | every 6h (360m) | `cron-store-backup.sh` | Backs up all profiles' jobs.json; alerts on missing |
| **Session Archiver** | `03678064b87f` | every 6h (360m) | `session-archiver.py` | Archives kanban worker sessions >3 days old |

### healthcheck.sh — 4 checks

```bash
# 1. Required tools on PATH: bd, pi, zz, codegraph, graphify
# 2. Team gateways: any hermes-gateway-*.service in failed state?
# 3. Disk: /tmp or home at/over 95%?
# 4. Z.AI auth: hermes auth status zai resolves?
```

**Output rules:** All pass → exit 0 (no output). Any failure → consolidated markdown report with `CHECK: detail` + most-likely fix per check.

**Guardrails:** Never auto-fix. Reports only, points to fixing skill/command. Time-boxes each check at 10s.

### cron-store-backup.sh

- Iterates all `~/.hermes/profiles/*/cron/jobs.json`
- Validates JSON before backing up (won't overwrite good backup with corrupt file)
- Keeps 7 rotations per profile
- Alerts if a profile has cron output history but no jobs.json (and a backup exists)

### session-archiver.py

- Archives kanban worker sessions (first message: "work kanban task t_xxx") older than 3 days
- Covers 7 profiles: tech-lead, developer, verifier, product-owner, scout, venture-builder, ops
- Uses official `SessionDB.set_session_archived()` API
- Silent when nothing to archive

### Ops does NOT manage other profiles' crons

Ops cron is self-contained. It does **not**:
- Monitor or repair scout's or researcher's cron jobs
- Restart failed cron jobs on other profiles
- Escalate cron failures to a human

Cron failures on other profiles are visible only via `jobs.json` `last_status` / `last_error` fields, which require manual inspection or the `team-observability` skill.

---

## 6. Scout Work Discovery

### How the scout discovers work

The scout is a **scheduled scanner**, not reactive. It runs 8×/day (every 3 hours at `:30`) and polls a fixed set of tiered sources.

### Discovery pipeline

```
scout-guard.sh (check .last-scout marker)
    ↓ NEEDS_SCOUTING
research-scout skill (6 phases)
    ↓
Phase 1: FETCH — Poll T1-T4 sources (arXiv API, HF Daily Papers, blog RSS, HN, GitHub trending, Reddit, YouTube)
    ↓
Phase 2: DEDUP — scout-db.py dedup-check against SQLite
    ↓ NEW items only
Phase 3: TRIAGE — Sort into 4 buckets:
    • deep-research (≥2 of: landscape-changing, T1, high signal, core to agentic/gen AI) → kanban task for researcher
    • notable (significant release/technique) → SQLite + digest
    • signal (minor but tracking) → SQLite + digest one-liner
    • drop (noise) → silent
    ↓
Phase 4: CATALOG — Register notable + signal in SQLite
    ↓
Phase 5: DELIVER — Telegram digest (includes 🔬 Queued for deep research section)
    ↓
Phase 6: DISCOVER — Add new sources to sources.md, prune stale ones, register emerging terms
    ↓
FINALIZE — Write .last-scout marker
```

### Topic-level deep-research filing

The scout has **editorial judgment**: if it spots high-value themes (≥3 sources converging on same concept, trending topics with no wiki note yet, field shifts that will matter for weeks), it files a **topic-level** deep-research task — not just per-item tasks.

### Work handoff mechanism

```
scout → kanban_create(title="Deep research: ...", assignee="researcher", body="...")
         ↓ dispatcher picks up
researcher → reads task, does deep research, writes wiki note, completes task
```

### Current state

- **Scout cron is BROKEN**: `RuntimeError: No usable credentials found for provider 'deepseek'`
- No scout runs have succeeded recently (last_status: `error`)
- No deep-research tasks are being filed for the researcher
- The researcher has no cron jobs — it is entirely dependent on scout (or direct user request) for work

---

## 7. JSON Node Definitions for Automatable Tasks

These are the automatable tasks extracted from the three profiles and the legacy workflow engine, structured as workflow node definitions.

### Node: ops-healthcheck

```json
{
  "id": "ops-healthcheck",
  "name": "Ops Environment Healthcheck",
  "type": "script",
  "profile": "ops",
  "trigger": {
    "kind": "interval",
    "minutes": 5
  },
  "script": "healthcheck.sh",
  "no_agent": true,
  "checks": [
    {"id": "tools-on-path", "command": "command -v {tool}", "items": ["bd", "pi", "zz", "codegraph", "graphify"], "severity": "broken"},
    {"id": "gateways-running", "command": "systemctl --user list-units 'hermes-gateway-*.service' --state=failed", "severity": "broken"},
    {"id": "disk-space", "command": "df -P /tmp ~", "threshold": "95%", "severity": "degraded"},
    {"id": "zai-auth", "command": "hermes auth status zai", "severity": "broken"}
  ],
  "output_rule": "silent_when_healthy",
  "on_failure": "report_findings_only"
}
```

### Node: ops-cron-backup

```json
{
  "id": "ops-cron-backup",
  "name": "Cron Store Backup",
  "type": "script",
  "profile": "ops",
  "trigger": {
    "kind": "interval",
    "minutes": 360
  },
  "script": "cron-store-backup.sh",
  "no_agent": true,
  "action": "backup_all_profiles_jobs_json",
  "retention": 7,
  "validate_before_backup": true,
  "on_corrupt": "skip_and_warn",
  "on_missing_with_backup": "alert_restore_available"
}
```

### Node: ops-session-archive

```json
{
  "id": "ops-session-archive",
  "name": "Session Archiver",
  "type": "script",
  "profile": "ops",
  "trigger": {
    "kind": "interval",
    "minutes": 360
  },
  "script": "session-archiver.py",
  "no_agent": true,
  "target_profiles": ["tech-lead", "developer", "verifier", "product-owner", "scout", "venture-builder", "ops"],
  "criteria": {
    "source": "cli",
    "first_message_pattern": "work kanban task %",
    "older_than_days": 3,
    "not_already_archived": true
  },
  "output_rule": "silent_when_nothing_to_archive"
}
```

### Node: scout-daily-scan

```json
{
  "id": "scout-daily-scan",
  "name": "Daily AI Research Scout",
  "type": "agent",
  "profile": "scout",
  "trigger": {
    "kind": "cron",
    "expr": "30 1,4,7,10,13,16,19,22 * * *"
  },
  "guard": {
    "script": "scout-guard.sh",
    "marker": "~/vault/meta/.last-scout",
    "skip_if": "ALREADY_SCOUTED",
    "wake_agent_on_skip": false
  },
  "skill": "research-scout",
  "model": "deepseek-v4-flash",
  "provider": "deepseek",
  "phases": [
    {"id": "fetch", "sources": ["T1", "T2", "T3", "T4"]},
    {"id": "dedup", "script": "scout-db.py dedup-check"},
    {"id": "triage", "buckets": ["deep-research", "notable", "signal", "drop"]},
    {"id": "file-tasks", "assignee": "researcher", "type": "kanban_create"},
    {"id": "catalog", "script": "scout-db.py register"},
    {"id": "deliver", "channel": "telegram"},
    {"id": "discover", "actions": ["source-add", "source-prune", "topic-touch"]}
  ],
  "finalize": {"write_marker": "~/vault/meta/.last-scout"},
  "deliver": "telegram"
}
```

### Node: scanner-blocked-escalation

```json
{
  "id": "scanner-blocked-escalation",
  "name": "Board Scanner — Blocked Task Escalation",
  "type": "script",
  "profile": "product-owner",
  "trigger": {
    "kind": "cron",
    "expr": "* * * * *"
  },
  "script": "workflow-engine.py",
  "phase": "scanner",
  "scope": "all_active_project_boards",
  "monitor": {
    "condition": "tasks.status = 'blocked'",
    "skip_if": ["assignee IN ('default', '')", "has_comment('HUMAN_REQUIRED')"]
  },
  "escalation_chain": {
    "developer": "tech-lead",
    "verifier": "tech-lead",
    "debugger": "tech-lead",
    "qa": "tech-lead",
    "tech-lead": "product-owner",
    "product-owner": null
  },
  "on_resolved": {
    "detect": "done task with title '[ESCALATION] %{task_id}%' AND run.summary LIKE 'RESOLVED:%'",
    "action": "unblock original task"
  },
  "on_no_higher_profile": {
    "action": "comment HUMAN_REQUIRED on task",
    "author": "board-scanner"
  },
  "create_escalation": {
    "title": "[ESCALATION] Resolve block on {task_id}: {title[:40]}",
    "priority": 10,
    "body_includes": ["assignee", "block_reason", "resolve_steps"]
  }
}
```

### Node: human-escalation-ping

```json
{
  "id": "human-escalation-ping",
  "name": "Human-Flagged Bead Escalation",
  "type": "script",
  "profile": "product-owner",
  "trigger": {
    "kind": "cron",
    "expr": "* * * * *"
  },
  "script": "workflow-engine.py",
  "phase": "human-escal",
  "scope": "all_active_project_boards",
  "monitor": {
    "condition": "beads with label 'human' AND status != 'closed'",
    "idempotency_key": "bead-human-{bead_id}"
  },
  "create_card": {
    "board": "hermes-hq",
    "assignee": "default",
    "priority": 10,
    "title": "[ESCALATION] human answer needed: {bead_title}",
    "body_includes": ["bead_id", "description", "respond_command"]
  },
  "respond_mechanism": "bd human respond {bead_id}"
}
```

### Node: bead-status-sync

```json
{
  "id": "bead-status-sync",
  "name": "Bead Status Sync",
  "type": "script",
  "profile": "product-owner",
  "trigger": {
    "kind": "cron",
    "expr": "* * * * *"
  },
  "script": "workflow-engine.py",
  "phase": "bead-sync",
  "scope": "all_active_project_boards",
  "status_map": {
    "ready": "in_progress",
    "running": "in_progress",
    "blocked": "blocked",
    "done": "closed",
    "archived": "open"
  },
  "direction": "kanban_card_status → bd_bead_status",
  "skip": ["closed beads", "gt:slot labeled beads", "already_matching"]
}
```

### Node: dispatch-ready-beads

```json
{
  "id": "dispatch-ready-beads",
  "name": "Dispatch Ready Beads",
  "type": "script",
  "profile": "product-owner",
  "trigger": {
    "kind": "cron",
    "expr": "* * * * *"
  },
  "script": "workflow-engine.py",
  "phase": "dispatch",
  "scope": "all_active_project_boards",
  "routing": {
    "bug": {"assignee": "debugger", "skip_po": true},
    "wayfinder:research": {"assignee": "scout"},
    "wayfinder:task": {"assignee": "ops"},
    "wayfinder:architecture": {"assignee": "architect"},
    "default": {"assignee": "product-owner", "card_prefix": "[dispatch]"}
  },
  "skip_labels": ["gt:slot", "wayfinder:grilling", "wayfinder:prototype", "wayfinder:map", "venture:brief"],
  "skip_types": ["epic"],
  "dedup": "idempotency_key = bead-{bead_id}",
  "po_card_gate": "only one active [dispatch]% card per board"
}
```

---

## Cross-Cutting Findings

### Broken / Degraded Systems

| System | Status | Impact |
|--------|--------|--------|
| **Scout cron** | ❌ BROKEN — DeepSeek API key missing | No AI frontier scanning; no deep-research tasks filed for researcher |
| **Scout Telegram delivery** | ❌ BROKEN — platform not configured | Even if scout ran, digests wouldn't deliver |
| **Researcher pipeline** | ⚠️ STALLED — no scout tasks arriving | Researcher is idle unless directly tasked by user |
| **Researcher skills** | ⚠️ DISABLED — `deep-research`, `llm-wiki`, `obsidian`, `obsidian-vault` all disabled in config | SOUL.md describes Obsidian wiki writing, but enabling skills are off |
| **New workflow engine cron** | ❌ BROKEN — script path not found (`startup/scripts/workflow_engine/main.py`) | New engine failing every tick; old engine (`workflow-engine.py`) still running |
| **QA trigger** | ⏸️ DISABLED — commented out in workflow-engine.py | Replaced by "new workflow engine" which is itself broken |

### Automatable vs. Requires-Human

| Task | Automatable? | Notes |
|------|-------------|-------|
| Ops healthcheck | ✅ Already automated (no_agent script) | Silent watchdog |
| Cron backup | ✅ Already automated (no_agent script) | |
| Session archiving | ✅ Already automated (no_agent script) | |
| Scout daily scan | ✅ Automated but BROKEN | Needs DeepSeek API key + Telegram config |
| Bead status sync | ✅ Already automated | |
| Ready bead dispatch | ✅ Already automated | |
| Blocked task escalation | ✅ Already automated | |
| Human-flagged bead ping | ✅ Already automated | |
| Deep research (wiki note writing) | ❌ Requires agent (LLM) | Task-driven via kanban, not cron |
| Environment drift repair | ❌ Requires agent judgment | Healthcheck detects, dev-env-setup skill fixes |
| Tool evaluation | ❌ Requires agent judgment | Research + trial + recommendation |
